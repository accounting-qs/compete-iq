"""
Ads service — ad queries, enrichment, and scrape orchestration.
Routes call these functions; they never touch the DB directly.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CompetitorAd, ScrapeJob, Competitor
from integrations import r2_client, apify_client
from integrations.apify_client import ApifyError
from processing.pipeline import process_ads_batch
from config import settings

logger = logging.getLogger(__name__)

CDN_MAX_AGE_SECONDS = settings.CDN_URL_MAX_AGE_HOURS * 3600


def enrich_with_video_url(ad: CompetitorAd) -> dict:
    """Add a fresh pre-signed URL to the ad dict. None if no R2 key."""
    data = {
        "id": ad.id,
        "ad_library_id": ad.ad_library_id,
        "ad_type": ad.ad_type,
        "ad_text": ad.ad_text,
        "transcript": ad.transcript,
        "on_screen_text": ad.on_screen_text,
        "angles": ad.angles,
        "processing_status": ad.processing_status,
        "video_url": None,
        "created_at": ad.created_at,
    }
    if ad.video_r2_key:
        try:
            data["video_url"] = r2_client.generate_presigned_url(ad.video_r2_key)
        except Exception as e:
            logger.warning("Failed to generate pre-signed URL for %s: %s", ad.video_r2_key, e)
    return data


async def list_ads_for_competitor(db: AsyncSession, competitor_id: str) -> list[dict]:
    """List all ads for a competitor with fresh pre-signed URLs."""
    result = await db.execute(
        select(CompetitorAd)
        .where(
            CompetitorAd.competitor_id == competitor_id,
            CompetitorAd.deleted_at.is_(None),
        )
        .order_by(CompetitorAd.created_at.desc())
    )
    ads = result.scalars().all()

    now = datetime.now(timezone.utc)
    stale_count = sum(
        1 for ad in ads
        if ad.video_cdn_fetched_at
        and (now - ad.video_cdn_fetched_at).total_seconds() > CDN_MAX_AGE_SECONDS
    )
    if stale_count:
        logger.info("ads: %d stale CDN URLs for competitor %s", stale_count, competitor_id)

    return [enrich_with_video_url(ad) for ad in ads]


async def list_library(
    db: AsyncSession, user_id: str, status_filter: str | None = None
) -> list[dict]:
    """My Library — all scraped ads across all competitors."""
    query = select(CompetitorAd).where(
        CompetitorAd.user_id == user_id,
        CompetitorAd.deleted_at.is_(None),
    )
    if status_filter:
        query = query.where(CompetitorAd.processing_status == status_filter)

    query = query.order_by(CompetitorAd.created_at.desc())
    result = await db.execute(query)
    ads = result.scalars().all()

    return [enrich_with_video_url(ad) for ad in ads]


async def get_ad(db: AsyncSession, ad_id: str) -> dict | None:
    """Get a single ad with fresh pre-signed URL. Returns None if not found."""
    result = await db.execute(
        select(CompetitorAd).where(
            CompetitorAd.id == ad_id,
            CompetitorAd.deleted_at.is_(None),
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        return None
    return enrich_with_video_url(ad)


async def validate_scrape_request(
    db: AsyncSession, user_id: str, ad_ids: list[str]
) -> list[str]:
    """
    Verify all ad IDs exist and belong to user.
    Returns the validated list of IDs.
    Raises ValueError if any IDs are missing.
    """
    result = await db.execute(
        select(CompetitorAd).where(
            CompetitorAd.id.in_(ad_ids),
            CompetitorAd.user_id == user_id,
            CompetitorAd.deleted_at.is_(None),
        )
    )
    ads = result.scalars().all()

    if len(ads) != len(ad_ids):
        raise ValueError("One or more ad IDs not found")

    return [a.id for a in ads]


async def scrape_and_notify(competitor_id: str, handle: str, from_: str) -> None:
    """
    Background task: scrape full competitor profile, store new ads, process them,
    and notify via WhatsApp when done.
    """
    from db.session import AsyncSessionLocal
    from integrations import twilio_client

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Competitor).where(Competitor.id == competitor_id))
            competitor = result.scalar_one_or_none()
            if not competitor:
                return

            job = ScrapeJob(
                user_id=competitor.user_id,
                competitor_id=competitor_id,
                status="running",
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            async def capture_run_id(run_id: str):
                job.apify_run_id = run_id
                await db.commit()

            ads = await apify_client.scrape_competitor_profile(
                handle, max_ads=50, apify_run_id_callback=capture_run_id
            )

            new_ad_ids = []
            for ad_payload in ads:
                existing = await db.execute(
                    select(CompetitorAd).where(
                        CompetitorAd.ad_library_id == ad_payload.ad_archive_id
                    )
                )
                existing_ad = existing.scalar_one_or_none()
                if existing_ad:
                    continue

                video_url = ad_payload.video_hd_url or ad_payload.video_sd_url
                ad_type = "video" if video_url else "image"

                new_ad = CompetitorAd(
                    user_id=competitor.user_id,
                    competitor_id=competitor_id,
                    ad_library_id=ad_payload.ad_archive_id,
                    ad_type=ad_type,
                    ad_text="\n".join(ad_payload.ad_creative_bodies or []),
                    video_cdn_url=video_url,
                    video_cdn_fetched_at=datetime.now(timezone.utc),
                    raw_ad_payload=ad_payload.model_dump(),
                    processing_status="cdn_fetched",
                )
                db.add(new_ad)
                new_ad_ids.append(new_ad.id)

            job.ads_found = len(ads)
            job.new_ads_detected = len(new_ad_ids)
            job.status = "completed"
            await db.commit()

            competitor.last_scraped_at = datetime.now(timezone.utc)
            await db.commit()

            if new_ad_ids:
                await process_ads_batch(db, new_ad_ids)

            frontend_url = "https://competeiq-frontend.onrender.com"
            twilio_client.send_message(
                from_,
                f"Found {len(ads)} ads ({len(new_ad_ids)} new). Done!\n"
                f"\U0001f449 {frontend_url}/competitors/{handle}/ads"
            )

        except ApifyError as e:
            logger.error("scrape_and_notify: Apify error for %s — %s", handle, e)
            if 'job' in dir():
                job.status = "failed"
                job.error_message = str(e)
                await db.commit()
            twilio_client.send_message(
                from_,
                f"Scrape failed for {handle}. Try again in a moment."
            )
        except Exception as e:
            logger.error("scrape_and_notify: unexpected error — %s", e)
            twilio_client.send_message(from_, "Unexpected error during scrape. Check logs.")
