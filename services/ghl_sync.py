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

from db.models import GHLContact, GHLOpportunity, GHLSyncRun, GHLSyncSettings, GHLWebinarStats
from db.session import AsyncSessionLocal
from integrations.ghl_client import (
    CONTACT_FIELD_BOOK_CAMPAIGN_MEDIUM,
    CONTACT_FIELD_BOOK_CAMPAIGN_NAME,
    CONTACT_FIELD_BOOK_CAMPAIGN_SOURCE,
    CONTACT_FIELD_BOOKED_CALL_WEBINAR_SERIES,
    CONTACT_FIELD_CALENDAR_INVITE_RESPONSE_HISTORY,
    CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_HISTORY,
    CONTACT_FIELD_CALENDAR_WEBINAR_SERIES_NON_JOINERS,
    CONTACT_FIELD_COLD_CALENDAR_UNSUBSCRIBE_DATE,
    CONTACT_FIELD_INVITE_RESPONSE_PREFIX,
    CONTACT_FIELD_INVITE_RESPONSE_PREFIX_NON_JOINERS,
    CONTACT_FIELD_IS_BOOKED_CALL,
    CONTACT_FIELD_REGISTRATION_CAMPAIGN_MEDIUM,
    CONTACT_FIELD_REGISTRATION_CAMPAIGN_NAME,
    CONTACT_FIELD_REGISTRATION_CAMPAIGN_SOURCE,
    CONTACT_FIELD_WEBINAR_REGISTRATION_IN_FORM_DATE,
    CONTACT_FIELD_WEBINAR_REGISTRATION_NUMBER,
    CONTACT_FIELD_ZOOM_ATTENDED,
    CONTACT_FIELD_ZOOM_TIME_IN_SESSION_MINUTES,
    CONTACT_FIELD_ZOOM_VIEWING_TIME_IN_MINUTES,
    CONTACT_FIELD_ZOOM_WEBINAR_SERIES_ATTENDED_COUNT,
    CONTACT_FIELD_ZOOM_WEBINAR_SERIES_LATEST,
    CONTACT_FIELD_ZOOM_WEBINAR_SERIES_REG_COUNT,
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
        # Fallback / auxiliary fields (migration 026)
        "calendar_invite_response_prefix": custom.get(CONTACT_FIELD_INVITE_RESPONSE_PREFIX),
        "calendar_invite_response_prefix_non_joiners": custom.get(CONTACT_FIELD_INVITE_RESPONSE_PREFIX_NON_JOINERS),
        "webinar_registration_number": _safe_int(custom.get(CONTACT_FIELD_WEBINAR_REGISTRATION_NUMBER)),
        "zoom_webinar_series_latest": _safe_int(custom.get(CONTACT_FIELD_ZOOM_WEBINAR_SERIES_LATEST)),
        "zoom_webinar_series_registered_total_count": _safe_int(custom.get(CONTACT_FIELD_ZOOM_WEBINAR_SERIES_REG_COUNT)),
        "zoom_webinar_series_attended_total_count": _safe_int(custom.get(CONTACT_FIELD_ZOOM_WEBINAR_SERIES_ATTENDED_COUNT)),
        "zoom_time_in_session_minutes": _safe_int(custom.get(CONTACT_FIELD_ZOOM_TIME_IN_SESSION_MINUTES)),
        "zoom_viewing_time_in_minutes_total": _safe_int(custom.get(CONTACT_FIELD_ZOOM_VIEWING_TIME_IN_MINUTES)),
        "zoom_attended": custom.get(CONTACT_FIELD_ZOOM_ATTENDED),
        "book_campaign_source": custom.get(CONTACT_FIELD_BOOK_CAMPAIGN_SOURCE),
        "book_campaign_medium": custom.get(CONTACT_FIELD_BOOK_CAMPAIGN_MEDIUM),
        "book_campaign_name": custom.get(CONTACT_FIELD_BOOK_CAMPAIGN_NAME),
        "registration_campaign_source": custom.get(CONTACT_FIELD_REGISTRATION_CAMPAIGN_SOURCE),
        "registration_campaign_medium": custom.get(CONTACT_FIELD_REGISTRATION_CAMPAIGN_MEDIUM),
        "registration_campaign_name": custom.get(CONTACT_FIELD_REGISTRATION_CAMPAIGN_NAME),
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


async def _upsert_contacts_batch(db: AsyncSession, rows: list[dict]) -> None:
    """Batch upsert many contacts in a single round-trip.

    Uses INSERT ... VALUES (...), (...) ON CONFLICT (ghl_contact_id) DO UPDATE.
    On Supabase remote DB this is ~10-50x faster than per-row upserts.
    """
    if not rows:
        return
    stmt = pg_insert(GHLContact).values(rows)
    # Column list is the same for every row, derived from the first row's keys.
    update_cols = {k: getattr(stmt.excluded, k) for k in rows[0].keys() if k != "ghl_contact_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ghl_contact_id"], set_=update_cols,
    )
    await db.execute(stmt)


async def _upsert_opps_batch(db: AsyncSession, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(GHLOpportunity).values(rows)
    update_cols = {k: getattr(stmt.excluded, k) for k in rows[0].keys() if k != "ghl_opportunity_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ghl_opportunity_id"], set_=update_cols,
    )
    await db.execute(stmt)


async def _update_run_progress(
    run_id: str,
    contacts_synced: int,
    opps_synced: int,
    expected_total: int | None = None,
) -> None:
    """Persist live progress on the running sync_run row so the UI can poll it."""
    try:
        async with AsyncSessionLocal() as db:
            values: dict = {
                "contacts_synced": contacts_synced,
                "opportunities_synced": opps_synced,
            }
            if expected_total is not None:
                values["expected_total"] = expected_total
            await db.execute(
                update(GHLSyncRun).where(GHLSyncRun.id == run_id).values(**values)
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist sync progress: %s", exc)


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

        # Scheduled sync uses the narrow filter — excludes the 4.2M-row
        # calendar_webinar_series_history wildcard. Per-webinar sync (run_webinar_sync)
        # handles the wide case on demand.
        contact_filter = GHLClient.narrow_webinar_filter()
        contact_updated_after = updated_after if sync_type_effective == "incremental" else None
        opp_updated_after = updated_after if sync_type_effective == "incremental" else None

        try:
            # Sync contacts — batched upserts per page for speed
            async with AsyncSessionLocal() as db:
                batch: list[dict] = []
                async for c in client.stream_contacts(
                    updated_after=contact_updated_after, filters=contact_filter,
                ):
                    try:
                        batch.append(_build_contact_row(c))
                    except Exception as exc:
                        errors.append({"type": "contact", "id": c.get("id"), "error": str(exc)[:500]})
                        logger.exception("Failed to build contact row %s", c.get("id"))
                        continue
                    if len(batch) >= 250:
                        try:
                            await _upsert_contacts_batch(db, batch)
                            contacts_synced += len(batch)
                            await db.commit()
                            await _update_run_progress(run_id, contacts_synced, opps_synced)
                        except Exception as exc:
                            errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                            logger.exception("Failed to upsert contact batch")
                            await db.rollback()
                        batch = []
                if batch:
                    try:
                        await _upsert_contacts_batch(db, batch)
                        contacts_synced += len(batch)
                        await db.commit()
                    except Exception as exc:
                        errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                        await db.rollback()
                await _update_run_progress(run_id, contacts_synced, opps_synced)

            # Sync opportunities
            async with AsyncSessionLocal() as db:
                batch = []
                async for o in client.stream_opportunities(opp_updated_after):
                    try:
                        batch.append(_build_opp_row(o))
                    except Exception as exc:
                        errors.append({"type": "opportunity", "id": o.get("id"), "error": str(exc)[:500]})
                        continue
                    if len(batch) >= 250:
                        try:
                            await _upsert_opps_batch(db, batch)
                            opps_synced += len(batch)
                            await db.commit()
                            await _update_run_progress(run_id, contacts_synced, opps_synced)
                        except Exception as exc:
                            errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                            await db.rollback()
                        batch = []
                if batch:
                    try:
                        await _upsert_opps_batch(db, batch)
                        opps_synced += len(batch)
                        await db.commit()
                    except Exception as exc:
                        errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                        await db.rollback()
                await _update_run_progress(run_id, contacts_synced, opps_synced)

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


async def _upsert_webinar_stats(webinar_number: int, gcal_invited_count: int) -> None:
    async with AsyncSessionLocal() as db:
        stmt = pg_insert(GHLWebinarStats).values(
            webinar_number=webinar_number,
            gcal_invited_count=gcal_invited_count,
            fetched_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["webinar_number"],
            set_={
                "gcal_invited_count": stmt.excluded.gcal_invited_count,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        await db.execute(stmt)
        await db.commit()


async def run_webinar_sync(
    webinar_number: int,
    trigger: SyncTrigger = "manual",
    deep: bool = False,
) -> str:
    """Sync one phase of a per-webinar pull. Returns run_id.

    Narrow phase (deep=False, default):
      - gcal_invited_count captured in ghl_webinar_stats (drives gcalInvitedGhl)
      - Contacts matching invite_response contains eN / non_joiners contains eN
        / booked_call_webinar_series = N (~1,500 contacts for W136, ~2 min)
      - Opportunities with webinar_source_number = N

    Deep phase (deep=True):
      - Contacts matching calendar_webinar_series_history contains eN (~200k
        for W136, ~3 hours). Run after narrow so stats become usable quickly.
      - Opportunities skipped (already synced in narrow).
    """
    if _sync_lock.locked():
        raise RuntimeError("A sync is already running")

    async with _sync_lock:
        phase_label = "deep" if deep else "narrow"
        sync_type = f"webinar:{webinar_number}:{phase_label}"
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

        client = GHLClient()
        contacts_synced = 0
        opps_synced = 0
        errors: list[dict] = []

        try:
            # Capture expected_total + (narrow only) gcal_invited_count
            if deep:
                contact_filter = GHLClient.gcal_invited_count_filter(webinar_number)
                try:
                    expected = await client.count_contacts_with_filter(contact_filter)
                    await _update_run_progress(run_id, 0, 0, expected_total=expected)
                    logger.info("W%d deep phase expects %d contacts", webinar_number, expected)
                except Exception as exc:
                    errors.append({"type": "expected_count", "error": str(exc)[:500]})
            else:
                contact_filter = GHLClient.webinar_number_filter(webinar_number, deep=False)
                try:
                    expected = await client.count_contacts_with_filter(contact_filter)
                    await _update_run_progress(run_id, 0, 0, expected_total=expected)
                    logger.info("W%d narrow phase expects %d contacts", webinar_number, expected)
                except Exception as exc:
                    errors.append({"type": "expected_count", "error": str(exc)[:500]})

                # Also record the gcal_invited_count while we're making count calls
                try:
                    gcal_count = await client.count_contacts_with_filter(
                        GHLClient.gcal_invited_count_filter(webinar_number)
                    )
                    await _upsert_webinar_stats(webinar_number, gcal_count)
                    logger.info("W%d gcal_invited_count = %d", webinar_number, gcal_count)
                except Exception as exc:
                    errors.append({"type": "gcal_count", "error": str(exc)[:500]})

            # Contacts — batched upserts
            async with AsyncSessionLocal() as db:
                batch: list[dict] = []
                async for c in client.stream_contacts(filters=contact_filter):
                    try:
                        batch.append(_build_contact_row(c))
                    except Exception as exc:
                        errors.append({"type": "contact", "id": c.get("id"), "error": str(exc)[:500]})
                        continue
                    if len(batch) >= 250:
                        try:
                            await _upsert_contacts_batch(db, batch)
                            contacts_synced += len(batch)
                            await db.commit()
                            await _update_run_progress(run_id, contacts_synced, opps_synced)
                        except Exception as exc:
                            errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                            logger.exception("Failed to upsert contact batch")
                            await db.rollback()
                        batch = []
                if batch:
                    try:
                        await _upsert_contacts_batch(db, batch)
                        contacts_synced += len(batch)
                        await db.commit()
                    except Exception as exc:
                        errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                        await db.rollback()
                await _update_run_progress(run_id, contacts_synced, opps_synced)

            # Opportunities (narrow phase only — deep skips)
            # Store ALL opps encountered — bookings are counted at read time by
            # UNION of (opps with webinar_source_number = N) + (contacts with
            # booked_call_webinar_series = N), which catches opps whose custom
            # field isn't set but whose contact has the webinar tag.
            if not deep:
                async with AsyncSessionLocal() as db:
                    batch = []
                    async for o in client.stream_opportunities():
                        row = _build_opp_row(o)
                        batch.append(row)
                        if len(batch) >= 250:
                            try:
                                await _upsert_opps_batch(db, batch)
                                opps_synced += len(batch)
                                await db.commit()
                                await _update_run_progress(run_id, contacts_synced, opps_synced)
                            except Exception as exc:
                                errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                                await db.rollback()
                            batch = []
                    if batch:
                        try:
                            await _upsert_opps_batch(db, batch)
                            opps_synced += len(batch)
                            await db.commit()
                        except Exception as exc:
                            errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                            await db.rollback()
                    await _update_run_progress(run_id, contacts_synced, opps_synced)

            status = "completed"

        except Exception as exc:
            logger.exception("Webinar sync failed")
            errors.append({"type": "fatal", "error": str(exc)[:500]})
            status = "failed"

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
            "Webinar sync %s (W%d/%s): status=%s, contacts=%d, opps=%d, errors=%d, %ds",
            run_id, webinar_number, trigger, status, contacts_synced, opps_synced, len(errors), duration,
        )
        return run_id


async def run_webinar_sync_full(webinar_number: int, trigger: SyncTrigger = "manual") -> list[str]:
    """Run both phases sequentially: narrow first (fast, metrics usable), then
    deep (slow, backfills the 200k-row GCal-invited base).

    Returns both run_ids. Each phase is recorded as a separate row in
    ghl_sync_run so the history shows "webinar:136:narrow" and
    "webinar:136:deep" with their own durations.
    """
    narrow_id = await run_webinar_sync(webinar_number, trigger=trigger, deep=False)
    deep_id = await run_webinar_sync(webinar_number, trigger=trigger, deep=True)
    return [narrow_id, deep_id]


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
