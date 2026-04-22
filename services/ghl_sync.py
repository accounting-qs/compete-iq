"""GoHighLevel sync engine — contacts + opportunities → local DB.

Strategy:
- Stream paged results from GHL API
- Upsert by GHL ID using INSERT ... ON CONFLICT DO UPDATE (idempotent)
- Record every run in ghl_sync_run table with status/duration/counts
- Errors per-record are logged and counted but do not halt the sync
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GHLContact, GHLOpportunity, GHLSyncRun, GHLSyncSettings
from db.session import AsyncSessionLocal
from integrations.ghl_client import (
    CONTACT_FIELD_BOOKED_CALL_WEBINAR_SERIES,
    CONTACT_FIELD_CALENDAR_INVITE_RESPONSE_HISTORY,
    CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_HISTORY,
    CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_NON_JOINERS,
    CONTACT_FIELD_COLD_CALENDAR_UNSUBSCRIBE_DATE,
    CONTACT_FIELD_IS_BOOKED_CALL,
    CONTACT_FIELD_WEBINAR_REGISTRATION_IN_FORM_DATE,
    GHLClient,
    OPP_FIELD_CALL1_APPT_DATE,
    OPP_FIELD_CALL1_APPT_STATUS,
    OPP_FIELD_LEAD_QUALITY,
    OPP_FIELD_PROJECTED_DEAL_SIZE,
    OPP_FIELD_WEBINAR_SOURCE_NUMBER,
    SMS_CLICK_TAG,
    parse_custom_fields,
    parse_projected_deal_size,
    parse_webinar_source_number,
)

logger = logging.getLogger(__name__)

SyncType = Literal["full", "incremental"]
SyncTrigger = Literal["scheduled", "manual"]


# Lock so only one sync runs at a time in this process
_sync_lock = asyncio.Lock()


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value)
        # GHL returns ISO 8601; also handles trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _parse_date(value: object):
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _safe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None


def _build_contact_row(c: dict) -> dict:
    """Normalize a raw GHL contact payload into our DB row shape."""
    custom = parse_custom_fields(c.get("customFields"))
    tags = c.get("tags") or []

    return {
        "ghl_contact_id": c["id"],
        "email": (c.get("email") or "").strip().lower() or None,
        "date_added": _parse_dt(c.get("dateAdded")),
        "calendar_invite_response_history": custom.get(CONTACT_FIELD_CALENDAR_INVITE_RESPONSE_HISTORY),
        "calendar_webinar_series_history": custom.get(CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_HISTORY),
        "calendar_webinar_series_non_joiners": custom.get(CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_NON_JOINERS),
        "is_booked_call": custom.get(CONTACT_FIELD_IS_BOOKED_CALL),
        "booked_call_webinar_series": _safe_int(custom.get(CONTACT_FIELD_BOOKED_CALL_WEBINAR_SERIES)),
        "webinar_registration_in_form_date": _parse_date(custom.get(CONTACT_FIELD_WEBINAR_REGISTRATION_IN_FORM_DATE)),
        "cold_calendar_unsubscribe_date": _parse_date(custom.get(CONTACT_FIELD_COLD_CALENDAR_UNSUBSCRIBE_DATE)),
        "has_sms_click_tag": SMS_CLICK_TAG in tags,
        "tags": tags,
        "raw_custom_fields": custom if custom else None,
        "created_at_ghl": _parse_dt(c.get("dateAdded")),
        "updated_at_ghl": _parse_dt(c.get("dateUpdated")),
        "synced_at": datetime.now(timezone.utc),
    }


def _build_opp_row(o: dict) -> dict:
    custom = parse_custom_fields(o.get("customFields"))
    opt = custom.get(OPP_FIELD_PROJECTED_DEAL_SIZE)
    return {
        "ghl_opportunity_id": o["id"],
        "ghl_contact_id": o.get("contactId"),
        "pipeline_stage_id": o.get("pipelineStageId"),
        "monetary_value": o.get("monetaryValue"),
        "call1_appointment_status": custom.get(OPP_FIELD_CALL1_APPT_STATUS),
        "call1_appointment_date": _parse_dt(custom.get(OPP_FIELD_CALL1_APPT_DATE)),
        "webinar_source_number": parse_webinar_source_number(custom.get(OPP_FIELD_WEBINAR_SOURCE_NUMBER)),
        "lead_quality": custom.get(OPP_FIELD_LEAD_QUALITY),
        "projected_deal_size_option": str(opt) if opt is not None else None,
        "projected_deal_size_value": parse_projected_deal_size(opt),
        "raw_custom_fields": custom if custom else None,
        "created_at_ghl": _parse_dt(o.get("createdAt")),
        "updated_at_ghl": _parse_dt(o.get("updatedAt")),
        "synced_at": datetime.now(timezone.utc),
    }


async def _upsert_contact(db: AsyncSession, row: dict) -> None:
    stmt = pg_insert(GHLContact).values(**row)
    update_cols = {k: v for k, v in row.items() if k != "ghl_contact_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ghl_contact_id"], set_=update_cols
    )
    await db.execute(stmt)


async def _upsert_opp(db: AsyncSession, row: dict) -> None:
    stmt = pg_insert(GHLOpportunity).values(**row)
    update_cols = {k: v for k, v in row.items() if k != "ghl_opportunity_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ghl_opportunity_id"], set_=update_cols
    )
    await db.execute(stmt)


async def _get_last_successful_sync_start(db: AsyncSession) -> datetime | None:
    result = await db.execute(
        select(GHLSyncRun)
        .where(GHLSyncRun.status == "completed")
        .order_by(GHLSyncRun.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    return run.started_at if run else None


async def run_sync(sync_type: SyncType, trigger: SyncTrigger = "scheduled") -> str:
    """Run a full or incremental GHL sync.

    Returns the GHLSyncRun.id (so a manual trigger can poll it).
    Idempotent on ghl_contact_id / ghl_opportunity_id. Errors per-record
    are counted but do not halt the sync.
    """
    if _sync_lock.locked():
        logger.warning("Sync already running — skipping this trigger (%s/%s)", sync_type, trigger)
        raise RuntimeError("A sync is already running")

    async with _sync_lock:
        # Create sync run row
        async with AsyncSessionLocal() as db:
            run = GHLSyncRun(
                sync_type=sync_type,
                trigger=trigger,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = run.id
            run_started_at = run.started_at

            # For incremental, look up the previous completed run
            updated_after: datetime | None = None
            if sync_type == "incremental":
                last_start = await _get_last_successful_sync_start(db)
                if last_start is None:
                    logger.info("No previous sync found — upgrading incremental → full")
                    sync_type_effective = "full"
                else:
                    # 1-hour buffer for clock skew
                    updated_after = last_start - timedelta(hours=1)
                    sync_type_effective = "incremental"
            else:
                sync_type_effective = "full"

        client = GHLClient()
        contacts_synced = 0
        opps_synced = 0
        errors: list[dict] = []

        try:
            # Sync contacts
            async with AsyncSessionLocal() as db:
                batch = 0
                async for c in client.stream_contacts(updated_after if sync_type_effective == "incremental" else None):
                    try:
                        await _upsert_contact(db, _build_contact_row(c))
                        contacts_synced += 1
                        batch += 1
                        if batch >= 100:
                            await db.commit()
                            batch = 0
                    except Exception as exc:
                        errors.append({"type": "contact", "id": c.get("id"), "error": str(exc)[:500]})
                        logger.exception("Failed to upsert contact %s", c.get("id"))
                await db.commit()

            # Sync opportunities
            async with AsyncSessionLocal() as db:
                batch = 0
                async for o in client.stream_opportunities(updated_after if sync_type_effective == "incremental" else None):
                    try:
                        await _upsert_opp(db, _build_opp_row(o))
                        opps_synced += 1
                        batch += 1
                        if batch >= 100:
                            await db.commit()
                            batch = 0
                    except Exception as exc:
                        errors.append({"type": "opportunity", "id": o.get("id"), "error": str(exc)[:500]})
                        logger.exception("Failed to upsert opportunity %s", o.get("id"))
                await db.commit()

            status = "completed"

        except Exception as exc:
            logger.exception("Sync failed")
            errors.append({"type": "fatal", "error": str(exc)[:500]})
            status = "failed"

        # Finalize the run row
        completed = datetime.now(timezone.utc)
        duration = int((completed - run_started_at).total_seconds())
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(GHLSyncRun)
                .where(GHLSyncRun.id == run_id)
                .values(
                    status=status,
                    completed_at=completed,
                    duration_seconds=duration,
                    contacts_synced=contacts_synced,
                    opportunities_synced=opps_synced,
                    errors_count=len(errors),
                    error_details=errors or None,
                )
            )
            await db.commit()

        logger.info(
            "Sync %s (%s/%s): status=%s, contacts=%d, opps=%d, errors=%d, %ds",
            run_id, sync_type, trigger, status, contacts_synced, opps_synced, len(errors), duration,
        )
        return run_id


async def get_sync_settings() -> dict:
    """Return current sync settings (always one row, id=1)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(GHLSyncSettings).where(GHLSyncSettings.id == 1))
        s = result.scalar_one_or_none()
        if s is None:
            # Seed if missing
            s = GHLSyncSettings(id=1)
            db.add(s)
            await db.commit()
            await db.refresh(s)
        return {
            "incremental_enabled": s.incremental_enabled,
            "incremental_interval_hours": s.incremental_interval_hours,
            "weekly_full_enabled": s.weekly_full_enabled,
            "weekly_full_day_of_week": s.weekly_full_day_of_week,
            "weekly_full_hour_local": s.weekly_full_hour_local,
            "weekly_full_timezone": s.weekly_full_timezone,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
