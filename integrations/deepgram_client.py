"""
Deepgram Nova-2 transcription client.

- Streams video bytes directly to Deepgram — no temp files
- Graceful degradation: on any error, returns "" so pipeline continues
- Cost logging: duration_seconds tracked for billing
"""

import logging
from typing import Optional

from deepgram import DeepgramClient, PrerecordedOptions, FileSource

from config import settings

logger = logging.getLogger(__name__)

_client: Optional[DeepgramClient] = None


def _get_client() -> DeepgramClient:
    global _client
    if _client is None:
        _client = DeepgramClient(settings.DEEPGRAM_API_KEY)
    return _client


async def transcribe(audio_bytes: bytes, mimetype: str = "video/mp4") -> tuple[str, float]:
    """
    Transcribe audio from raw bytes using Deepgram Nova-2.

    Returns:
        (transcript_text, duration_seconds)
        On failure: ("", 0.0) — pipeline continues without transcript

    Args:
        audio_bytes: raw video/audio bytes
        mimetype: MIME type of the content (default video/mp4)
    """
    if not audio_bytes:
        logger.warning("deepgram_client: received empty bytes, skipping transcription")
        return "", 0.0

    try:
        client = _get_client()

        payload: FileSource = {"buffer": audio_bytes, "mimetype": mimetype}
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
            punctuate=True,
            utterances=False,
        )

        response = await client.listen.asyncprerecorded.v("1").transcribe_file(
            payload, options
        )

        result = response.results
        if not result or not result.channels:
            logger.warning("deepgram_client: empty result returned")
            return "", 0.0

        transcript = result.channels[0].alternatives[0].transcript or ""
        duration = result.metadata.duration if result.metadata else 0.0

        logger.info(
            "deepgram_client: transcribed %.1fs of audio, %d chars",
            duration,
            len(transcript),
        )
        return transcript, float(duration)

    except Exception as e:
        logger.error("deepgram_client: transcription failed — %s", e)
        return "", 0.0
