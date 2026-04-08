"""
Apify client — Meta Ad Library scraper.

Actor: curious_coder~facebook-ads-library-scraper
Input: {"urls": [{"url": "<ad-library-search-url>"}], "maxItems": N}
Pricing: $0.00075 per ad

Two modes:
  - lookup_single_ad(url)          Fast ~60s, for WhatsApp confirmation
  - scrape_competitor_profile(...)  Full profile 2-5 min, for Ad Browser + monitoring

Zero-trust: all payloads validated with Pydantic before touching the DB.
Graceful degradation: raises ApifyError on failure — caller marks job failed.
"""

import asyncio
import logging
import re
import urllib.parse
from typing import Optional

import httpx
from pydantic import BaseModel, ValidationError

from config import settings

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
POLL_INTERVAL = 5   # seconds between run status checks
POLL_TIMEOUT = 300  # max seconds to wait for a run


class ApifyError(Exception):
    pass


# ---------------------------------------------------------------------------
# Nested snapshot models (zero-trust API boundary)
# ---------------------------------------------------------------------------
class ApifySnapshotBody(BaseModel):
    text: Optional[str] = None

    class Config:
        extra = "allow"


class ApifySnapshotImage(BaseModel):
    original_image_url: Optional[str] = None
    resized_image_url: Optional[str] = None
    watermarked_resized_image_url: Optional[str] = None

    class Config:
        extra = "allow"


class ApifySnapshotVideo(BaseModel):
    video_hd_url: Optional[str] = None
    video_sd_url: Optional[str] = None

    class Config:
        extra = "allow"


class ApifyAdSnapshot(BaseModel):
    body: Optional[ApifySnapshotBody] = None
    images: list[ApifySnapshotImage] = []
    videos: list[ApifySnapshotVideo] = []
    display_format: Optional[str] = None   # "IMAGE" or "VIDEO"
    page_name: Optional[str] = None
    page_profile_picture_url: Optional[str] = None
    cta_text: Optional[str] = None
    cta_type: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    link_url: Optional[str] = None

    class Config:
        extra = "allow"


# ---------------------------------------------------------------------------
# Top-level ad payload — properties provide backward-compat accessors
# so webhook.py and pipeline.py don't need changes.
# ---------------------------------------------------------------------------
class ApifyAdPayload(BaseModel):
    ad_archive_id: str
    page_name: Optional[str] = None
    page_id: Optional[str] = None
    snapshot: Optional[ApifyAdSnapshot] = None
    is_active: Optional[bool] = None
    start_date: Optional[int] = None
    end_date: Optional[int] = None
    publisher_platform: list[str] = []

    class Config:
        extra = "allow"

    @property
    def ad_text(self) -> Optional[str]:
        """Ad body copy."""
        if self.snapshot and self.snapshot.body:
            return self.snapshot.body.text
        return None

    @property
    def ad_creative_bodies(self) -> Optional[list[str]]:
        """Backward-compat shim — callers do '\\n'.join(ad.ad_creative_bodies or [])."""
        text = self.ad_text
        return [text] if text else None

    @property
    def image_url(self) -> Optional[str]:
        """First available image URL."""
        if self.snapshot and self.snapshot.images:
            return self.snapshot.images[0].original_image_url
        return None

    @property
    def snapshot_url(self) -> Optional[str]:
        """Preview URL for WhatsApp confirmation — first image, or profile picture."""
        img = self.image_url
        if img:
            return img
        if self.snapshot and self.snapshot.page_profile_picture_url:
            return self.snapshot.page_profile_picture_url
        return None

    @property
    def video_hd_url(self) -> Optional[str]:
        if self.snapshot and self.snapshot.videos:
            return self.snapshot.videos[0].video_hd_url
        return None

    @property
    def video_sd_url(self) -> Optional[str]:
        if self.snapshot and self.snapshot.videos:
            return self.snapshot.videos[0].video_sd_url
        return None


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
def _to_ad_library_search_url(url_or_term: str) -> str:
    """
    Convert any URL or search term to a Facebook Ad Library keyword search URL.

    Handles:
    - Already an Ad Library URL → pass through
    - Instagram profile URL → extract handle → keyword search
    - Facebook page URL → extract handle → keyword search
    - Plain text (page name / handle) → keyword search
    """
    if "facebook.com/ads/library" in url_or_term:
        return url_or_term

    # Instagram profile: https://www.instagram.com/alexhormozi/
    ig_match = re.match(r"https?://(?:www\.)?instagram\.com/([^/?#]+)/?", url_or_term)
    if ig_match:
        search_term = ig_match.group(1)
    else:
        # Facebook page: https://www.facebook.com/alexhormozi/
        fb_match = re.match(r"https?://(?:www\.)?facebook\.com/([^/?#]+)/?", url_or_term)
        if fb_match:
            search_term = fb_match.group(1)
        else:
            # Plain search term (page name, handle, etc.)
            search_term = url_or_term

    return (
        "https://www.facebook.com/ads/library/"
        "?active_status=all&ad_type=all&country=US"
        f"&q={urllib.parse.quote_plus(search_term)}"
        "&search_type=keyword_unordered"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
async def _start_run(client: httpx.AsyncClient, input_data: dict) -> str:
    """Start an Apify actor run and return the run ID."""
    if not settings.APIFY_ACTOR_ID:
        raise ApifyError("APIFY_ACTOR_ID is not configured")

    resp = await client.post(
        f"{APIFY_BASE}/acts/{settings.APIFY_ACTOR_ID}/runs",
        params={"token": settings.APIFY_API_TOKEN},
        json=input_data,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise ApifyError(f"Failed to start Apify run: {resp.status_code} {resp.text}")

    run_id = resp.json().get("data", {}).get("id")
    if not run_id:
        raise ApifyError("Apify run response missing run ID")
    return run_id


async def _wait_for_run(client: httpx.AsyncClient, run_id: str) -> str:
    """Poll until run SUCCEEDED or FAILED. Returns dataset ID."""
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        resp = await client.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            params={"token": settings.APIFY_API_TOKEN},
            timeout=15,
        )
        if resp.status_code != 200:
            raise ApifyError(f"Failed to poll Apify run {run_id}: {resp.status_code}")

        data = resp.json().get("data", {})
        status = data.get("status")

        if status == "SUCCEEDED":
            return data["defaultDatasetId"]
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise ApifyError(f"Apify run {run_id} ended with status: {status}")

        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    raise ApifyError(f"Apify run {run_id} timed out after {POLL_TIMEOUT}s")


async def _fetch_dataset(client: httpx.AsyncClient, dataset_id: str) -> list[dict]:
    """Fetch all items from a dataset."""
    resp = await client.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        params={"token": settings.APIFY_API_TOKEN, "format": "json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise ApifyError(f"Failed to fetch dataset {dataset_id}: {resp.status_code}")
    return resp.json()


def _validate_ads(raw_items: list[dict]) -> list[ApifyAdPayload]:
    """Validate and filter raw Apify items. Bad payloads are logged and skipped."""
    validated = []
    for item in raw_items:
        try:
            validated.append(ApifyAdPayload(**item))
        except ValidationError as e:
            logger.warning("Skipping malformed Apify ad payload: %s", e)
    return validated


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def lookup_single_ad(url: str) -> Optional[ApifyAdPayload]:
    """
    Fast single-ad lookup from any Meta/IG URL or page name.
    Converts to Ad Library keyword search URL automatically.
    Returns the first matched ad or None if not found.
    Used for WhatsApp confirmation flow.
    """
    search_url = _to_ad_library_search_url(url)
    logger.debug("lookup_single_ad: searching %s", search_url)

    async with httpx.AsyncClient() as client:
        run_id = await _start_run(
            client,
            {"urls": [{"url": search_url}], "maxItems": 3}
        )
        dataset_id = await _wait_for_run(client, run_id)
        raw = await _fetch_dataset(client, dataset_id)

    ads = _validate_ads(raw)
    if not ads:
        logger.info("lookup_single_ad: no ads found for URL %s", url)
        return None
    return ads[0]


async def scrape_competitor_profile(
    handle: str,
    max_ads: int = 50,
    apify_run_id_callback=None,
) -> list[ApifyAdPayload]:
    """
    Full competitor profile scrape.
    handle is used as a keyword search term (underscores → spaces).
    Returns list of validated ad payloads.
    apify_run_id_callback: optional async callable(run_id) — called as soon as
    the run starts so caller can persist the run ID before waiting.
    """
    # Convert slug handle to a human-readable search term
    search_term = handle.replace("_", " ")
    search_url = _to_ad_library_search_url(search_term)
    logger.info("scrape_competitor_profile: %s → %s (max %d)", handle, search_url, max_ads)

    async with httpx.AsyncClient() as client:
        run_id = await _start_run(
            client,
            {"urls": [{"url": search_url}], "maxItems": max_ads}
        )
        if apify_run_id_callback:
            await apify_run_id_callback(run_id)

        dataset_id = await _wait_for_run(client, run_id)
        raw = await _fetch_dataset(client, dataset_id)

    ads = _validate_ads(raw)
    logger.info("scrape_competitor_profile: %d valid ads for handle '%s'", len(ads), handle)
    return ads
