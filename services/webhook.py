"""
WhatsApp webhook service — conversation state machine and background tasks.
Routes call these functions; they handle Twilio validation and HTTP response only.

State machine (per phone number, stored in whatsapp_sessions):
  idle → searching → awaiting_confirmation → done (reset to idle)
  idle → searching → awaiting_handle (if IG auto-resolve fails) → searching → ...
  CANCEL from any state → idle
  20 min inactivity → idle
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Competitor, WhatsAppSession, User
from integrations import apify_client, twilio_client
from integrations.apify_client import ApifyError
from services.competitors import get_or_create_competitor_by_handle, get_user
from services.ads import scrape_and_notify

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 20


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
def is_url(text: str) -> bool:
    return (
        text.startswith("http://")
        or text.startswith("https://")
        or "instagram.com" in text
        or "facebook.com" in text
    )


def is_post_url(text: str) -> bool:
    """Instagram post/reel/tv URLs don't contain the page handle."""
    return bool(re.search(r"instagram\.com/(p|reel|tv)/", text))


async def resolve_ig_handle(url: str) -> str | None:
    """
    Fetch an Instagram post/reel URL and extract the author handle from og:title.
    Returns the handle string, or None if resolution fails.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
            )
        if resp.status_code != 200:
            logger.info("resolve_ig_handle: got status %d for %s", resp.status_code, url)
            return None

        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', resp.text)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', resp.text)
        if m:
            og_title = m.group(1)
            handle_match = re.match(r'^(@?[\w.]+)\s+on Instagram', og_title)
            if handle_match:
                return handle_match.group(1).lstrip("@")
    except Exception as e:
        logger.info("resolve_ig_handle: failed — %s", e)
    return None


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
def is_expired(session: WhatsAppSession) -> bool:
    if not session.last_activity_at:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    return session.last_activity_at < cutoff


async def get_or_create_session(db: AsyncSession, phone_number: str) -> WhatsAppSession:
    result = await db.execute(
        select(WhatsAppSession).where(WhatsAppSession.phone_number == phone_number)
    )
    session = result.scalar_one_or_none()
    if not session:
        session = WhatsAppSession(phone_number=phone_number, state="idle", context={})
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


async def reset_session(db: AsyncSession, session: WhatsAppSession) -> None:
    session.state = "idle"
    session.context = {}
    session.last_activity_at = datetime.now(timezone.utc)
    await db.commit()


async def touch_session(db: AsyncSession, session: WhatsAppSession) -> None:
    session.last_activity_at = datetime.now(timezone.utc)
    await db.commit()


# ---------------------------------------------------------------------------
# Background tasks — own their DB sessions, run after webhook returns
# ---------------------------------------------------------------------------
async def bg_search_core(phone_number: str, search_term: str) -> None:
    """Core Ad Library search. Creates its own DB session."""
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WhatsAppSession).where(WhatsAppSession.phone_number == phone_number)
        )
        session = result.scalar_one_or_none()
        if not session:
            return

        try:
            ad = await apify_client.lookup_single_ad(search_term)
        except ApifyError as e:
            logger.error("bg_search: Apify lookup failed — %s", e)
            await reset_session(db, session)
            twilio_client.send_message(
                phone_number,
                "Something went wrong searching the ad library. Try again in a moment."
            )
            return

        if not ad:
            await reset_session(db, session)
            twilio_client.send_message(
                phone_number,
                "Couldn't find a matching Meta Ads Library profile.\n"
                "Facebook page names sometimes differ from IG handles.\n"
                "Try their Instagram profile URL, or send their page name directly."
            )
            return

        session.context = {
            "url": search_term,
            "candidate": {
                "page_name": ad.page_name,
                "page_id": ad.page_id,
                "ad_archive_id": ad.ad_archive_id,
                "snapshot_url": ad.snapshot_url,
            }
        }
        session.state = "awaiting_confirmation"
        session.last_activity_at = datetime.now(timezone.utc)
        await db.commit()

        display_name = ad.page_name or "Unknown Page"
        preview_text = f"Found: {display_name}\nIs this the right competitor? Reply YES or NO."

        if ad.snapshot_url:
            twilio_client.send_media(phone_number, preview_text, ad.snapshot_url)
        else:
            twilio_client.send_message(phone_number, preview_text)


async def bg_lookup_from_post_url(phone_number: str, post_url: str) -> None:
    """
    Background task for Instagram post/reel URLs.
    Auto-resolves the handle, then searches Ad Library.
    """
    from db.session import AsyncSessionLocal

    handle = await resolve_ig_handle(post_url)

    if handle:
        logger.info("bg_lookup_from_post_url: resolved handle '%s'", handle)
        await bg_search_core(phone_number, handle)
    else:
        logger.info("bg_lookup_from_post_url: could not resolve handle, asking user")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(WhatsAppSession).where(WhatsAppSession.phone_number == phone_number)
            )
            session = result.scalar_one_or_none()
            if not session:
                return
            session.state = "awaiting_handle"
            session.context = {"original_url": post_url}
            session.last_activity_at = datetime.now(timezone.utc)
            await db.commit()

        twilio_client.send_message(
            phone_number,
            "Couldn't auto-detect the page — what's their Instagram handle or page name?"
        )


# ---------------------------------------------------------------------------
# State handlers — called from the webhook route
# ---------------------------------------------------------------------------
async def handle_idle(db, session, message, background_tasks) -> None:
    """Handle messages when session is idle — expect a URL or page name."""
    body = message["body"]
    from_ = message["from_"]

    if not is_url(body):
        twilio_client.send_message(
            from_,
            "Hi! Send me a competitor's Instagram ad URL or profile URL to get started.\n"
            "Example: https://www.instagram.com/reel/ABC123/"
        )
        return

    session.state = "searching"
    session.context = {}
    await touch_session(db, session)

    twilio_client.send_message(from_, "Got it. Searching Meta Ad Library...")

    if is_post_url(body):
        background_tasks.add_task(bg_lookup_from_post_url, from_, body)
    else:
        background_tasks.add_task(bg_search_core, from_, body)


async def handle_searching(db, session, message, background_tasks) -> None:
    """Still waiting for Apify — tell user to hang tight."""
    from_ = message["from_"]
    twilio_client.send_message(from_, "Still searching, hang tight...")
    await touch_session(db, session)


async def handle_awaiting_handle(db, session, message, background_tasks) -> None:
    """Handle the competitor handle/name reply after auto-resolve failed."""
    handle = message["body"].strip()
    from_ = message["from_"]

    session.state = "searching"
    await touch_session(db, session)

    twilio_client.send_message(from_, "Got it. Searching Meta Ad Library...")
    background_tasks.add_task(bg_search_core, from_, handle)


async def handle_awaiting_confirmation(db, session, message, background_tasks) -> None:
    """Handle YES/NO confirmation of a found competitor."""
    body = message["body"].upper().strip()
    from_ = message["from_"]

    if body not in ("YES", "NO", "Y", "N"):
        twilio_client.send_message(from_, "Reply YES to confirm or NO to try again.")
        await touch_session(db, session)
        return

    candidate = session.context.get("candidate", {})

    if body in ("NO", "N"):
        twilio_client.send_message(
            from_,
            "No problem. Try sending their Instagram profile URL or page name."
        )
        await reset_session(db, session)
        return

    # Confirmed — upsert competitor record
    page_name = candidate.get("page_name", "Unknown")
    page_id = candidate.get("page_id")
    handle = (page_name or "unknown").lower().replace(" ", "_")[:50]

    user = await get_user(db)
    if not user:
        twilio_client.send_message(from_, "System error: no user found. Contact support.")
        return

    competitor = await get_or_create_competitor_by_handle(
        db, user.id, handle, display_name=page_name, meta_page_id=page_id
    )

    twilio_client.send_message(from_, "Loading their ad library...")

    background_tasks.add_task(
        scrape_and_notify,
        competitor_id=competitor.id,
        handle=handle,
        from_=from_,
    )

    await reset_session(db, session)


async def process_webhook_message(
    db: AsyncSession,
    message: dict,
    background_tasks,
) -> str:
    """
    Main webhook message handler. Routes to correct state handler.
    Returns a status string for the HTTP response.
    """
    from_ = message["from_"]
    body = message["body"]

    if not from_:
        return "ignored"

    session = await get_or_create_session(db, from_)

    # CANCEL resets from any state
    if body.upper().strip() == "CANCEL":
        await reset_session(db, session)
        twilio_client.send_message(from_, "Cancelled. Send a URL to start again.")
        return "cancelled"

    # Expire stale sessions (not searching — searching has its own long timeout)
    if is_expired(session) and session.state not in ("idle", "searching"):
        await reset_session(db, session)
        twilio_client.send_message(
            from_,
            "Session timed out (20 min). Starting fresh — send a URL to begin."
        )

    # Route to correct state handler
    if session.state == "idle":
        await handle_idle(db, session, message, background_tasks)
    elif session.state == "searching":
        await handle_searching(db, session, message, background_tasks)
    elif session.state == "awaiting_handle":
        await handle_awaiting_handle(db, session, message, background_tasks)
    elif session.state == "awaiting_confirmation":
        await handle_awaiting_confirmation(db, session, message, background_tasks)
    else:
        await reset_session(db, session)
        twilio_client.send_message(from_, "Send a URL to start.")

    return "ok"
