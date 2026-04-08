"""
Vision client — on-screen text extraction from video frames.

Strategy:
  - Pass 1: 1fps for first VISION_FRAME_SECONDS_DENSE seconds (hook capture)
  - Pass 2: 1 frame per VISION_FRAME_INTERVAL_SPARSE seconds thereafter (CTA/mid-roll)
  - All frames sent in one Claude Vision API call
  - Returns chronological list of unique text segments as JSON
  - Graceful degradation: on any error, returns "" so pipeline continues

ffmpeg provided by imageio-ffmpeg (bundled binary, no system install needed on dev).
Railway nixpacks.toml installs ffmpeg system package for production.
"""

import json
import logging
import os
import subprocess
import tempfile
from typing import Optional

import anthropic

from config import settings

logger = logging.getLogger(__name__)

_anthropic_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_ffmpeg_path() -> str:
    """Return system ffmpeg or imageio-ffmpeg bundled binary."""
    import shutil
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError("ffmpeg not found — install imageio-ffmpeg or system ffmpeg")


def _extract_frames(video_bytes: bytes, duration_hint: Optional[float] = None) -> list[tuple[float, bytes]]:
    """
    Extract frames from video bytes using ffmpeg.
    Returns list of (timestamp_seconds, jpeg_bytes) tuples.
    Frames are resized to 640px width to reduce token cost.
    """
    ffmpeg = _get_ffmpeg_path()
    frames: list[tuple[float, bytes]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.mp4")
        with open(input_path, "wb") as f:
            f.write(video_bytes)

        dense_seconds = settings.VISION_FRAME_SECONDS_DENSE
        sparse_interval = settings.VISION_FRAME_INTERVAL_SPARSE

        # Build vf filter: dense pass + sparse pass using select filter
        # Dense: 1fps for first N seconds
        # Sparse: 1 frame per interval for remainder, using scene change detection
        vf = (
            f"select='if(lt(t,{dense_seconds}),gte(mod(t\\,1),0)*eq(mod(floor(t)\\,1),0),"
            f"gte(mod(t\\,{sparse_interval}),0)*eq(mod(floor(t/{sparse_interval})\\,1),0))',"
            f"scale=640:-2"
        )

        # Simpler approach: two separate extractions
        # Dense: extract 1fps for first N seconds
        dense_pattern = os.path.join(tmpdir, "dense_%04d.jpg")
        subprocess.run(
            [ffmpeg, "-i", input_path, "-t", str(dense_seconds),
             "-vf", "fps=1,scale=640:-2", "-q:v", "5", dense_pattern, "-y"],
            capture_output=True, timeout=30, check=False
        )

        # Sparse: extract 1 frame per interval starting from dense_seconds
        sparse_pattern = os.path.join(tmpdir, "sparse_%04d.jpg")
        subprocess.run(
            [ffmpeg, "-i", input_path, "-ss", str(dense_seconds),
             "-vf", f"fps=1/{sparse_interval},scale=640:-2", "-q:v", "5", sparse_pattern, "-y"],
            capture_output=True, timeout=60, check=False
        )

        # Collect dense frames with timestamps
        for i in range(1, dense_seconds + 2):
            path = os.path.join(tmpdir, f"dense_{i:04d}.jpg")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    frames.append((float(i - 1), f.read()))

        # Collect sparse frames with timestamps
        for i in range(1, 20):  # max 20 sparse frames
            path = os.path.join(tmpdir, f"sparse_{i:04d}.jpg")
            if os.path.exists(path):
                ts = dense_seconds + (i - 1) * sparse_interval
                with open(path, "rb") as f:
                    frames.append((float(ts), f.read()))

    logger.info("vision_client: extracted %d frames", len(frames))
    return frames


async def extract_on_screen_text(video_bytes: bytes) -> str:
    """
    Extract on-screen text overlays from a video.

    Returns JSON string: [{"t": 2.0, "text": "Most coaches fail..."}, ...]
    On failure: returns "" — pipeline continues without on-screen text.
    """
    if not settings.ENABLE_VISION_EXTRACTION:
        return ""

    if not video_bytes:
        return ""

    try:
        frames = _extract_frames(video_bytes)
        if not frames:
            logger.warning("vision_client: no frames extracted")
            return ""

        # Build Claude Vision message with all frames
        import base64
        content = []

        for ts, frame_bytes in frames:
            content.append({
                "type": "text",
                "text": f"[Frame at {ts:.0f}s]"
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(frame_bytes).decode("utf-8"),
                }
            })

        content.append({
            "type": "text",
            "text": (
                "Extract all visible text overlaid on these video frames in chronological order. "
                "Focus on: hook text, headline cards, caption overlays, and CTA text. "
                "Ignore background scene text (signs, books, clothing, TV screens in background). "
                "For each unique text block found, return a JSON array: "
                '[{"t": <seconds>, "text": "<extracted text>"}]. '
                "If a frame has no overlaid text, skip it. "
                "Return only the JSON array, no other text."
            )
        })

        client = _get_client()
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}]
        )

        raw = response.content[0].text.strip()

        # Validate it's parseable JSON before storing
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("Expected JSON array from vision extraction")

        # Deduplicate consecutive identical text entries
        deduped = []
        seen_texts = set()
        for entry in parsed:
            text = entry.get("text", "").strip()
            if text and text not in seen_texts:
                deduped.append(entry)
                seen_texts.add(text)

        result = json.dumps(deduped)
        logger.info("vision_client: extracted %d unique text segments", len(deduped))
        return result

    except Exception as e:
        logger.error("vision_client: extraction failed — %s", e)
        return ""
