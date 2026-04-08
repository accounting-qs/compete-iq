"""
CompeteIQ Processing Pipeline — State Machine

States:
  raw → cdn_fetched → downloading → downloaded →
  transcribing → transcribed →
  vision_extracting → vision_extracted →
  extracting → extracted
                         ↓
                       failed  (any stage can transition here)

Per-stage DB commits ensure crash recovery resumes from last known good state.
Graceful degradation: transcript="" or on_screen_text="" on failure — pipeline continues.
Concurrency limited by asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS).
All pipeline calls run in FastAPI BackgroundTasks — never block route handlers.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import CompetitorAd, CostLog
from integrations import deepgram_client, r2_client, vision_client
from integrations.r2_client import build_r2_key

logger = logging.getLogger(__name__)

_download_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)


# ---------------------------------------------------------------------------
# State transition helper
# ---------------------------------------------------------------------------
async def _set_status(db: AsyncSession, ad: CompetitorAd, status: str) -> None:
    ad.processing_status = status
    ad.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("pipeline [%s]: → %s", ad.ad_library_id, status)


async def _set_failed(db: AsyncSession, ad: CompetitorAd, reason: str) -> None:
    ad.processing_status = "failed"
    ad.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.error("pipeline [%s]: FAILED — %s", ad.ad_library_id, reason)


# ---------------------------------------------------------------------------
# Cost logging helper
# ---------------------------------------------------------------------------
async def _log_cost(
    db: AsyncSession,
    user_id: str,
    operation_type: str,
    entity_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    metadata: dict = None,
) -> None:
    entry = CostLog(
        user_id=user_id,
        operation_type=operation_type,
        entity_id=entity_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        metadata=metadata or {},
    )
    db.add(entry)
    await db.commit()


# ---------------------------------------------------------------------------
# Individual pipeline stages
# ---------------------------------------------------------------------------
async def _stage_download(db: AsyncSession, ad: CompetitorAd) -> bool:
    """
    Download video from Apify CDN URL → upload to R2.
    Returns True on success, False on failure.
    """
    if not ad.video_cdn_url:
        # Image-only ad — skip download, mark downloaded with no r2_key
        await _set_status(db, ad, "downloaded")
        return True

    competitor_handle = ad.competitor.handle if ad.competitor else "unknown"
    r2_key = build_r2_key(ad.user_id, competitor_handle, ad.ad_library_id)

    # Idempotency: if already in R2, skip re-upload
    if r2_client.object_exists(r2_key):
        logger.info("pipeline [%s]: R2 object already exists, skipping upload", ad.ad_library_id)
        ad.video_r2_key = r2_key
        await _set_status(db, ad, "downloaded")
        return True

    await _set_status(db, ad, "downloading")
    try:
        async with _download_semaphore:
            bytes_uploaded = await r2_client.stream_upload(ad.video_cdn_url, r2_key)

        ad.video_r2_key = r2_key
        await _set_status(db, ad, "downloaded")

        await _log_cost(
            db, ad.user_id, "r2_storage", ad.id,
            metadata={"bytes": bytes_uploaded, "r2_key": r2_key}
        )
        return True

    except ValueError as e:
        # File too large — log and continue without video
        logger.warning("pipeline [%s]: video skipped — %s", ad.ad_library_id, e)
        ad.video_r2_key = None
        await _set_status(db, ad, "downloaded")
        return True  # Continue pipeline — extract from ad_text only

    except Exception as e:
        await _set_failed(db, ad, f"download failed: {e}")
        return False


async def _stage_transcribe(db: AsyncSession, ad: CompetitorAd) -> bool:
    """
    Download from R2 → transcribe with Deepgram.
    Graceful degradation: sets transcript="" on failure, continues.
    """
    await _set_status(db, ad, "transcribing")

    if not ad.video_r2_key:
        # No video (image ad or download skipped) — set empty transcript
        ad.transcript = ""
        await _set_status(db, ad, "transcribed")
        return True

    try:
        video_bytes = await asyncio.get_event_loop().run_in_executor(
            None, r2_client.get_object_bytes, ad.video_r2_key
        )
        transcript, duration_seconds = await deepgram_client.transcribe(video_bytes)
        ad.transcript = transcript

        await _log_cost(
            db, ad.user_id, "deepgram_transcription", ad.id,
            cost_usd=round(duration_seconds * 0.0043 / 60, 6),
            metadata={"duration_seconds": duration_seconds, "chars": len(transcript)}
        )

    except Exception as e:
        logger.error("pipeline [%s]: transcription error — %s. Continuing.", ad.ad_library_id, e)
        ad.transcript = ""

    await _set_status(db, ad, "transcribed")
    return True


async def _stage_vision_extract(db: AsyncSession, ad: CompetitorAd) -> bool:
    """
    Extract on-screen text from video frames using Claude Vision.
    Graceful degradation: sets on_screen_text="" on failure, continues.
    Image-only ads: skip, set on_screen_text="".
    """
    await _set_status(db, ad, "vision_extracting")

    if not ad.video_r2_key or ad.ad_type == "image":
        ad.on_screen_text = ""
        await _set_status(db, ad, "vision_extracted")
        return True

    try:
        video_bytes = await asyncio.get_event_loop().run_in_executor(
            None, r2_client.get_object_bytes, ad.video_r2_key
        )
        on_screen_text = await vision_client.extract_on_screen_text(video_bytes)
        ad.on_screen_text = on_screen_text

        # Rough cost estimate: ~15 frames × $0.004/image
        await _log_cost(
            db, ad.user_id, "claude_vision", ad.id,
            cost_usd=0.06,
            metadata={"enabled": settings.ENABLE_VISION_EXTRACTION}
        )

    except Exception as e:
        logger.error("pipeline [%s]: vision extraction error — %s. Continuing.", ad.ad_library_id, e)
        ad.on_screen_text = ""

    await _set_status(db, ad, "vision_extracted")
    return True


async def _stage_extract_angles(db: AsyncSession, ad: CompetitorAd) -> bool:
    """
    Extract structured angles from transcript + on_screen_text + ad_text using Claude.
    This stage is implemented in claude_client.py (built in next phase).
    Stub here — marks extracted with empty angles so pipeline completes.
    """
    await _set_status(db, ad, "extracting")

    # Full implementation in claude_client.py Phase 1a step 2
    # For now: placeholder so pipeline state machine is complete and testable
    ad.angles = {
        "hook": None,
        "audience": None,
        "problem": None,
        "promise": None,
        "proof": None,
        "cta": None,
        "angle": None,
        "format": ad.ad_type,
    }

    await _set_status(db, ad, "extracted")
    return True


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------
async def process_ad(db: AsyncSession, ad_id: str) -> None:
    """
    Run a competitor ad through the full processing pipeline.
    Designed to be called from FastAPI BackgroundTasks.
    Resumes from the last committed state on crash/restart.

    State machine: raw → cdn_fetched → downloading → downloaded →
                   transcribing → transcribed →
                   vision_extracting → vision_extracted →
                   extracting → extracted
    """
    result = await db.execute(select(CompetitorAd).where(CompetitorAd.id == ad_id))
    ad = result.scalar_one_or_none()

    if not ad:
        logger.error("pipeline: ad %s not found", ad_id)
        return

    status = ad.processing_status

    # Crash recovery: resume from last known good state
    if status == "failed":
        logger.info("pipeline [%s]: retrying from failed state", ad.ad_library_id)
        status = "raw"

    # Skip stages already completed (idempotency)
    if status in ("raw", "cdn_fetched"):
        if not await _stage_download(db, ad):
            return
        status = ad.processing_status

    if status == "downloaded":
        if not await _stage_transcribe(db, ad):
            return
        status = ad.processing_status

    if status == "transcribed":
        if not await _stage_vision_extract(db, ad):
            return
        status = ad.processing_status

    if status == "vision_extracted":
        if not await _stage_extract_angles(db, ad):
            return

    logger.info("pipeline [%s]: complete — status=%s", ad.ad_library_id, ad.processing_status)


async def process_ads_batch(db: AsyncSession, ad_ids: list[str]) -> None:
    """
    Process multiple ads. Each runs independently — one failure does not stop others.
    """
    for ad_id in ad_ids:
        try:
            await process_ad(db, ad_id)
        except Exception as e:
            logger.error("pipeline: unhandled error processing ad %s — %s", ad_id, e)
