"""GoHighLevel API v2 client — auth, pagination, rate limiting.

Scoped to a single location. Used for syncing contacts and opportunities
into the local DB for the Statistics dashboard.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator

import httpx

from config import settings

logger = logging.getLogger(__name__)


# Opportunity custom field IDs
OPP_FIELD_WEBINAR_SOURCE_NUMBER = "gp70TwLRM9Tnsfr7FR9Y"
OPP_FIELD_LEAD_QUALITY = "M8RuTSXsLhZMvdMWAlLr"
OPP_FIELD_PROJECTED_DEAL_SIZE = "Oo9ktilF7QwTNBzksT3k"

# Call appointment fields (from reference project — used for shows / no-shows)
OPP_FIELD_CALL1_APPT_STATUS = "V82ErbW24izA5aQUzRUv"
OPP_FIELD_CALL1_APPT_DATE = "bFDWu3koncdxn26h6nAm"

# Contact custom field IDs
CONTACT_FIELD_CALENDAR_INVITE_RESPONSE_HISTORY = "ghPIByTtKxRmHveNu4b1"
CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_HISTORY = "6YyME5pcbkr2zpxMHDPK"
CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_NON_JOINERS = "6TYlHOaOXS2DWHH5kR8D"
CONTACT_FIELD_BOOKED_CALL_WEBINAR_SERIES = "rsgthoV5ScH49VPFZlyq"
CONTACT_FIELD_IS_BOOKED_CALL = "wWkP8RfjazF5HdAzR9hA"
CONTACT_FIELD_WEBINAR_REGISTRATION_IN_FORM_DATE = "PUuRqljS3gWyBEmwBxwL"
CONTACT_FIELD_COLD_CALENDAR_UNSUBSCRIBE_DATE = "OLQt9nEWyG7tpYIdNs4F"

# Tag we need to preserve as a boolean on the contact
SMS_CLICK_TAG = "webinar reminder sms clicked"


class GHLClient:
    """Async GHL API v2 client."""

    def __init__(self) -> None:
        if not settings.GHL_API_KEY:
            raise RuntimeError("GHL_API_KEY not configured")
        if not settings.GHL_LOCATION_ID:
            raise RuntimeError("GHL_LOCATION_ID not configured")

        self._headers = {
            "Authorization": f"Bearer {settings.GHL_API_KEY}",
            "Version": "2021-07-28",
            "Accept": "application/json",
        }
        self._base_url = settings.GHL_API_BASE_URL
        self._location_id = settings.GHL_LOCATION_ID
        self._pipeline_id = settings.GHL_PIPELINE_ID
        self._page_delay_s = settings.GHL_PAGE_DELAY_MS / 1000.0
        self._page_size = settings.GHL_PAGE_SIZE

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        url = f"{self._base_url}{path}"
        response = await client.get(url, headers=self._headers, params=params)
        response.raise_for_status()
        return response.json()

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict) -> dict:
        url = f"{self._base_url}{path}"
        response = await client.post(url, headers=self._headers, json=body)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Opportunities
    # ------------------------------------------------------------------

    async def stream_opportunities(
        self, updated_after: datetime | None = None
    ) -> AsyncGenerator[dict, None]:
        """Yield raw GHL opportunity dicts one at a time, handling pagination.

        updated_after: if set, only fetch opportunities updated after this ts.
        """
        if not self._pipeline_id:
            raise RuntimeError("GHL_PIPELINE_ID not configured")

        params: dict = {
            "location_id": self._location_id,
            "pipeline_id": self._pipeline_id,
            "limit": self._page_size,
        }
        if updated_after:
            params["startAfter"] = int(updated_after.timestamp() * 1000)

        cursor_id: str | None = None
        cursor_after: int | None = None
        page = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                page += 1
                page_params = dict(params)
                if cursor_id and cursor_after is not None:
                    page_params["startAfterId"] = cursor_id
                    page_params["startAfter"] = cursor_after

                data = await self._get(client, "/opportunities/search", page_params)
                opps = data.get("opportunities", [])
                if not opps:
                    break

                for opp in opps:
                    yield opp

                meta = data.get("meta", {})
                total = meta.get("total", 0)
                fetched = (page - 1) * self._page_size + len(opps)
                logger.info("GHL: fetched %d / %d opportunities", fetched, total)

                cursor_id = meta.get("startAfterId")
                cursor_after = meta.get("startAfter")

                if not cursor_id or fetched >= total:
                    break

                await asyncio.sleep(self._page_delay_s)

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    async def stream_contacts(
        self, updated_after: datetime | None = None
    ) -> AsyncGenerator[dict, None]:
        """Yield raw GHL contact dicts. Uses POST /contacts/search with cursor paging.

        updated_after: if set, narrows results to contacts touched after this ts.
        """
        body: dict = {
            "locationId": self._location_id,
            "pageLimit": self._page_size,
        }
        if updated_after:
            body["filters"] = [
                {
                    "field": "dateUpdated",
                    "operator": "gt",
                    "value": int(updated_after.timestamp() * 1000),
                }
            ]

        search_after: list | None = None
        page = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                page += 1
                req = dict(body)
                if search_after is not None:
                    req["searchAfter"] = search_after

                data = await self._post(client, "/contacts/search", req)
                contacts = data.get("contacts", [])
                if not contacts:
                    break

                for c in contacts:
                    yield c

                total = data.get("total", 0)
                logger.info(
                    "GHL: fetched %d contacts (page %d, total %d)",
                    len(contacts), page, total,
                )

                # Cursor lives on the last contact as `searchAfter`
                last = contacts[-1]
                search_after = last.get("searchAfter")
                if not search_after:
                    break

                await asyncio.sleep(self._page_delay_s)


def parse_custom_fields(raw: list[dict] | None) -> dict[str, object]:
    """Convert GHL `customFields` array to {fieldId: value} dict.

    GHL returns entries shaped like {"id": "...", "value": X} or
    {"id": "...", "fieldValue": X} depending on endpoint.
    """
    out: dict[str, object] = {}
    if not raw:
        return out
    for item in raw:
        fid = item.get("id")
        if not fid:
            continue
        val = item.get("fieldValue") if "fieldValue" in item else item.get("value")
        out[fid] = val
    return out


def parse_webinar_source_number(value: object) -> int | None:
    """Parse the Webinar Source Number v2 text value into an int.

    GHL stores it as TEXT even though the values are numeric. Handles strings
    like "136", "136.0", " 136 ". Returns None for unparseable values.
    """
    if value is None:
        return None
    try:
        s = str(value).strip()
        if not s:
            return None
        return int(float(s))
    except (ValueError, TypeError):
        return None


# Projected Deal Size dropdown → numeric value (single number, not a range)
PROJECTED_DEAL_SIZE_VALUES: dict[str, int] = {
    "7,700": 7700,
    "15,000": 15000,
    "20,000": 20000,
    "25,000": 25000,
    # Also handle comma-less variants defensively
    "7700": 7700,
    "15000": 15000,
    "20000": 20000,
    "25000": 25000,
}


def parse_projected_deal_size(option: object) -> int | None:
    """Convert the Projected Deal Size dropdown option string to its numeric value."""
    if option is None:
        return None
    key = str(option).strip()
    return PROJECTED_DEAL_SIZE_VALUES.get(key)
