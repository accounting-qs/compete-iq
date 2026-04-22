"""
WebinarGeek API client.

Docs: https://app.webinargeek.com/api_docs
Auth: Bearer API key in Authorization header.
Base URL: https://app.webinargeek.com/api/v2
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://app.webinargeek.com/api/v2"
PAGE_SIZE = 100


class WebinarGeekError(Exception):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


async def _paginated_get(client: httpx.AsyncClient, path: str, api_key: str) -> list[dict[str, Any]]:
    """Fetch all pages of a WebinarGeek list endpoint."""
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        resp = await client.get(
            f"{BASE_URL}{path}",
            headers=_headers(api_key),
            params={"page": page, "per_page": PAGE_SIZE},
            timeout=30,
        )
        if resp.status_code == 401:
            raise WebinarGeekError("Invalid API key")
        if resp.status_code != 200:
            raise WebinarGeekError(f"WebinarGeek {path} returned {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        # WebinarGeek wraps lists under a key (e.g. "webinars", "subscribers") or returns a bare list.
        items: list[dict[str, Any]]
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Find the first list value
            list_keys = [k for k, v in data.items() if isinstance(v, list)]
            items = data[list_keys[0]] if list_keys else []
        else:
            items = []

        if not items:
            break
        results.extend(items)
        if len(items) < PAGE_SIZE:
            break
        page += 1
        if page > 500:  # safety
            logger.warning("WebinarGeek pagination exceeded 500 pages for %s", path)
            break
    return results


async def verify_api_key(api_key: str) -> bool:
    """Quick check that the key works. Hits /webinars with per_page=1."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/webinars",
            headers=_headers(api_key),
            params={"per_page": 1, "page": 1},
            timeout=15,
        )
        if resp.status_code == 401:
            return False
        if resp.status_code >= 400:
            raise WebinarGeekError(f"WebinarGeek verify returned {resp.status_code}: {resp.text[:200]}")
        return True


async def list_webinars(api_key: str) -> list[dict[str, Any]]:
    """Fetch all webinars (which contain broadcasts)."""
    async with httpx.AsyncClient() as client:
        return await _paginated_get(client, "/webinars", api_key)


async def list_broadcasts(api_key: str, webinar_id: str | int) -> list[dict[str, Any]]:
    """Fetch broadcasts for a given webinar."""
    async with httpx.AsyncClient() as client:
        return await _paginated_get(client, f"/webinars/{webinar_id}/broadcasts", api_key)


async def list_subscribers(api_key: str, broadcast_id: str | int) -> list[dict[str, Any]]:
    """Fetch all subscribers for a broadcast."""
    async with httpx.AsyncClient() as client:
        return await _paginated_get(client, f"/broadcasts/{broadcast_id}/subscribers", api_key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_dt(val: Any) -> Optional[datetime]:
    """Best-effort ISO-8601 parse. WebinarGeek returns ISO timestamps."""
    if not val or not isinstance(val, str):
        return None
    try:
        # Handles both "2026-04-21T10:00:00Z" and "2026-04-21T10:00:00+00:00"
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def coerce_bool(val: Any) -> Optional[bool]:
    """Handles 'Yes'/'No'/'Unsubscribed'/True/False/None from WG."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("yes", "true", "1"):
            return True
        if s in ("no", "false", "0", ""):
            return False
        if s == "unsubscribed":
            return None
    return None
