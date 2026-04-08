"""
Twilio WhatsApp client.

- Validates X-Twilio-Signature on every inbound webhook (security requirement)
- Chunks long messages (WhatsApp 1600 char limit)
- Sends media (video clips for confirmation, thumbnails for profile URLs)
- All sends are fire-and-forget with error logging — never raise to caller
"""

import logging
from typing import Optional

from twilio.request_validator import RequestValidator
from twilio.rest import Client

from config import settings

logger = logging.getLogger(__name__)

MAX_MSG_LENGTH = 1600
TWILIO_MEDIA_MAX_MB = 16


def _get_client() -> Client:
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


# ---------------------------------------------------------------------------
# Signature validation (call this in the webhook route)
# ---------------------------------------------------------------------------
def validate_signature(url: str, params: dict, signature: str) -> bool:
    """
    Validate that an inbound webhook is genuinely from Twilio.
    Must be called before processing any inbound message.
    Returns False if signature is invalid — caller should return 403.
    """
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    return validator.validate(url, params, signature)


# ---------------------------------------------------------------------------
# Send helpers
# ---------------------------------------------------------------------------
def _chunk_message(text: str) -> list[str]:
    """Split text into chunks that fit within WhatsApp's 1600-char limit."""
    if len(text) <= MAX_MSG_LENGTH:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:MAX_MSG_LENGTH])
        text = text[MAX_MSG_LENGTH:]
    return chunks


def send_message(to: str, body: str) -> None:
    """
    Send a WhatsApp text message to a phone number.
    to: must include 'whatsapp:' prefix, e.g. 'whatsapp:+14165551234'
    Chunks automatically if body exceeds 1600 chars.
    """
    client = _get_client()
    for chunk in _chunk_message(body):
        try:
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=to,
                body=chunk,
            )
        except Exception as e:
            logger.error("twilio_client: failed to send message to %s — %s", to, e)


def send_media(to: str, body: str, media_url: str) -> None:
    """
    Send a WhatsApp message with a media attachment (video or image).
    media_url must be publicly accessible (use R2 pre-signed URL).
    Falls back to text-only if media send fails.
    """
    client = _get_client()
    try:
        client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=to,
            body=body,
            media_url=[media_url],
        )
    except Exception as e:
        logger.error("twilio_client: media send failed to %s — %s. Falling back to text.", to, e)
        send_message(to, body)


def notify_lloyd(body: str) -> None:
    """Convenience: send a message to Lloyd's WhatsApp number."""
    send_message(settings.LLOYD_WHATSAPP_NUMBER, body)


def notify_lloyd_media(body: str, media_url: str) -> None:
    """Convenience: send Lloyd a message with media."""
    send_media(settings.LLOYD_WHATSAPP_NUMBER, body, media_url)


# ---------------------------------------------------------------------------
# Inbound message parsing
# ---------------------------------------------------------------------------
def parse_inbound(form_data: dict) -> dict:
    """
    Parse a Twilio inbound webhook form payload into a clean dict.
    Returns: {from_, body, num_media, media_urls}
    """
    num_media = int(form_data.get("NumMedia", 0))
    media_urls = [
        form_data.get(f"MediaUrl{i}", "")
        for i in range(num_media)
    ]
    return {
        "from_": form_data.get("From", ""),
        "body": (form_data.get("Body", "") or "").strip(),
        "num_media": num_media,
        "media_urls": media_urls,
    }
