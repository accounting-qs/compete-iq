"""GoHighLevel sync engine — contacts + opportunities → local DB.

Sync v2 invariants:
- Every code path that creates a sync_run row finalizes it (status set to
  completed | failed | cancelled, completed_at + duration_seconds populated).
  The lifecycle is owned by `_sync_run`, a context manager wrapping the row
  create / register / yield / finalize flow.
- Each sync writes `last_heartbeat_at` on every batch. The scheduler runs a
  periodic sweeper that marks rows with stale heartbeats as failed, so the
  UI can never show a forever-running orphan.
- Cancellation is cooperative: setting `cancel_requested=true` (or calling
  `task.cancel()` via the registry) raises asyncio.CancelledError at the
  next batch boundary, which the lifecycle catches and finalizes as
  'cancelled'.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BlocklistEntry, GHLContact, GHLOpportunity, GHLSyncRun, GHLSyncSettings, GHLWebinarStats
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

# A row whose heartbeat is older than this is considered dead and will be
# reaped by the stale-job sweeper. Tuned to be much larger than the longest
# legitimate gap between heartbeats (one batch ~250 contacts, ~2-10s).
STALE_HEARTBEAT_SECONDS = 600  # 10 minutes

# Lock so only one sync runs at a time in this process
_sync_lock = asyncio.Lock()

# Registry of running sync tasks, keyed by run_id, so the cancel endpoint
# can interrupt them via task.cancel(). Populated by `_sync_run`.
_active_tasks: dict[str, asyncio.Task] = {}


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
    """Batch upsert many contacts in a single round-trip."""
    if not rows:
        return
    stmt = pg_insert(GHLContact).values(rows)
    update_cols = {k: getattr(stmt.excluded, k) for k in rows[0].keys() if k != "ghl_contact_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ghl_contact_id"], set_=update_cols,
    )
    await db.execute(stmt)
    await _upsert_blocklist_from_ghl_batch(db, rows)


async def _upsert_blocklist_from_ghl_batch(db: AsyncSession, rows: list[dict]) -> None:
    """Push GHL DND contacts (cold_calendar_unsubscribe_date set) into blocklist."""
    from api.routers.outreach._helpers import LLOYD_USER_ID

    dnd_rows = [
        {
            "user_id": LLOYD_USER_ID,
            "email": r["email"],
            "source": "ghl_dnd",
            "reason": "GHL cold calendar unsubscribe",
            "source_ref": r.get("ghl_contact_id"),
        }
        for r in rows
        if r.get("email") and r.get("cold_calendar_unsubscribe_date")
    ]
    if not dnd_rows:
        return
    stmt = pg_insert(BlocklistEntry).values(dnd_rows).on_conflict_do_nothing(
        index_elements=["user_id", "email"]
    )
    try:
        await db.execute(stmt)
    except Exception as exc:
        logger.warning("Failed to upsert blocklist from GHL batch: %s", exc)


async def _upsert_opps_batch(db: AsyncSession, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = pg_insert(GHLOpportunity).values(rows)
    update_cols = {k: getattr(stmt.excluded, k) for k in rows[0].keys() if k != "ghl_opportunity_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=["ghl_opportunity_id"], set_=update_cols,
    )
    await db.execute(stmt)


# ---------------------------------------------------------------------------
# Sync v2: lifecycle, heartbeats, cancellation, recovery
# ---------------------------------------------------------------------------

class _SyncState:
    """Mutable per-run state passed to the work block by `_sync_run`.

    The work block bumps `contacts_synced` / `opportunities_synced` /
    `expected_total` / `errors`; the lifecycle code reads them at finalize
    and at every heartbeat.
    """
    __slots__ = ("run_id", "started_at", "contacts_synced", "opportunities_synced", "expected_total", "errors")

    def __init__(self, run_id: str, started_at: datetime) -> None:
        self.run_id = run_id
        self.started_at = started_at
        self.contacts_synced = 0
        self.opportunities_synced = 0
        self.expected_total: int | None = None
        self.errors: list[dict] = []


async def _heartbeat(state: _SyncState) -> None:
    """Persist progress + heartbeat. Raise CancelledError if a cancel was
    requested via the DB flag (defensive — the cancel endpoint also calls
    task.cancel(), but the flag handles cross-process cancellation if we
    ever scale to multiple workers).
    """
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            values: dict = {
                "contacts_synced": state.contacts_synced,
                "opportunities_synced": state.opportunities_synced,
                "last_heartbeat_at": now,
            }
            if state.expected_total is not None:
                values["expected_total"] = state.expected_total
            await db.execute(
                update(GHLSyncRun).where(GHLSyncRun.id == state.run_id).values(**values)
            )
            await db.commit()

            cancel_check = await db.execute(
                select(GHLSyncRun.cancel_requested).where(GHLSyncRun.id == state.run_id)
            )
            if cancel_check.scalar_one_or_none():
                raise asyncio.CancelledError("Cancellation requested via DB flag")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Failed to write heartbeat/progress for %s: %s", state.run_id, exc)


async def _set_expected_total(state: _SyncState, expected: int) -> None:
    state.expected_total = expected
    await _heartbeat(state)


async def _finalize_run(state: _SyncState, status: str) -> None:
    completed = datetime.now(timezone.utc)
    duration = int((completed - state.started_at).total_seconds())
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(GHLSyncRun)
                .where(GHLSyncRun.id == state.run_id)
                .values(
                    status=status,
                    completed_at=completed,
                    duration_seconds=duration,
                    contacts_synced=state.contacts_synced,
                    opportunities_synced=state.opportunities_synced,
                    errors_count=len(state.errors),
                    error_details=state.errors or None,
                )
            )
            await db.commit()
        logger.info(
            "Sync %s finalized: status=%s contacts=%d opps=%d errors=%d %ds",
            state.run_id, status, state.contacts_synced, state.opportunities_synced,
            len(state.errors), duration,
        )
    except Exception:
        logger.exception("Failed to finalize sync run %s", state.run_id)


@asynccontextmanager
async def _sync_run(sync_type: str, trigger: SyncTrigger):
    """Lifecycle wrapper: create row, register task, yield state, guarantee
    finalization on every exit path (success, error, cancellation).
    """
    started = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        run = GHLSyncRun(
            sync_type=sync_type,
            trigger=trigger,
            status="running",
            started_at=started,
            last_heartbeat_at=started,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    state = _SyncState(run_id=run_id, started_at=started)

    task = asyncio.current_task()
    if task is not None:
        _active_tasks[run_id] = task

    try:
        yield state
        await _finalize_run(state, status="completed")
    except asyncio.CancelledError:
        state.errors.append({"type": "cancelled", "error": "Sync cancelled by user or sweeper"})
        await _finalize_run(state, status="cancelled")
        raise
    except Exception as exc:
        logger.exception("Sync %s failed", run_id)
        state.errors.append({"type": "fatal", "error": str(exc)[:500]})
        await _finalize_run(state, status="failed")
    finally:
        _active_tasks.pop(run_id, None)


async def _get_last_successful_sync_start(db: AsyncSession) -> datetime | None:
    result = await db.execute(
        select(GHLSyncRun)
        .where(GHLSyncRun.status == "completed")
        .order_by(GHLSyncRun.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    return run.started_at if run else None


# ---------------------------------------------------------------------------
# Sync entry points
# ---------------------------------------------------------------------------

async def run_sync(sync_type: SyncType, trigger: SyncTrigger = "scheduled") -> str:
    """Run a full or incremental GHL sync. Returns the GHLSyncRun.id."""
    if _sync_lock.locked():
        logger.warning("Sync already running — skipping this trigger (%s/%s)", sync_type, trigger)
        raise RuntimeError("A sync is already running")

    async with _sync_lock:
        async with _sync_run(sync_type, trigger) as state:
            # Resolve incremental window before opening the GHL client
            updated_after: datetime | None = None
            if sync_type == "incremental":
                async with AsyncSessionLocal() as db:
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

            client = await GHLClient.create()  # may raise — caught and finalized by `_sync_run`

            contact_filter = GHLClient.narrow_webinar_filter()
            contact_updated_after = updated_after if sync_type_effective == "incremental" else None
            opp_updated_after = updated_after if sync_type_effective == "incremental" else None

            # --- Contacts ---
            async with AsyncSessionLocal() as db:
                batch: list[dict] = []
                async for c in client.stream_contacts(
                    updated_after=contact_updated_after, filters=contact_filter,
                ):
                    try:
                        batch.append(_build_contact_row(c))
                    except Exception as exc:
                        state.errors.append({"type": "contact", "id": c.get("id"), "error": str(exc)[:500]})
                        logger.exception("Failed to build contact row %s", c.get("id"))
                        continue
                    if len(batch) >= 250:
                        try:
                            await _upsert_contacts_batch(db, batch)
                            state.contacts_synced += len(batch)
                            await db.commit()
                            await _heartbeat(state)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            state.errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                            logger.exception("Failed to upsert contact batch")
                            await db.rollback()
                        batch = []
                if batch:
                    try:
                        await _upsert_contacts_batch(db, batch)
                        state.contacts_synced += len(batch)
                        await db.commit()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        state.errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                        await db.rollback()
                await _heartbeat(state)

            # --- Opportunities ---
            async with AsyncSessionLocal() as db:
                batch = []
                async for o in client.stream_opportunities(opp_updated_after):
                    try:
                        batch.append(_build_opp_row(o))
                    except Exception as exc:
                        state.errors.append({"type": "opportunity", "id": o.get("id"), "error": str(exc)[:500]})
                        continue
                    if len(batch) >= 250:
                        try:
                            await _upsert_opps_batch(db, batch)
                            state.opportunities_synced += len(batch)
                            await db.commit()
                            await _heartbeat(state)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            state.errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                            await db.rollback()
                        batch = []
                if batch:
                    try:
                        await _upsert_opps_batch(db, batch)
                        state.opportunities_synced += len(batch)
                        await db.commit()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        state.errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                        await db.rollback()
                await _heartbeat(state)

            return state.run_id


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
    """Sync one phase (narrow or deep) of a per-webinar pull. Returns run_id."""
    if _sync_lock.locked():
        raise RuntimeError("A sync is already running")

    async with _sync_lock:
        phase_label = "deep" if deep else "narrow"
        sync_type = f"webinar:{webinar_number}:{phase_label}"

        async with _sync_run(sync_type, trigger) as state:
            client = await GHLClient.create()  # may raise — caught and finalized by `_sync_run`

            # Capture expected_total + (narrow only) gcal_invited_count
            if deep:
                contact_filter = GHLClient.gcal_invited_count_filter(webinar_number)
                try:
                    expected = await client.count_contacts_with_filter(contact_filter)
                    await _set_expected_total(state, expected)
                    logger.info("W%d deep phase expects %d contacts", webinar_number, expected)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    state.errors.append({"type": "expected_count", "error": str(exc)[:500]})
            else:
                contact_filter = GHLClient.webinar_number_filter(webinar_number, deep=False)
                try:
                    expected = await client.count_contacts_with_filter(contact_filter)
                    await _set_expected_total(state, expected)
                    logger.info("W%d narrow phase expects %d contacts", webinar_number, expected)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    state.errors.append({"type": "expected_count", "error": str(exc)[:500]})

                try:
                    gcal_count = await client.count_contacts_with_filter(
                        GHLClient.gcal_invited_count_filter(webinar_number)
                    )
                    await _upsert_webinar_stats(webinar_number, gcal_count)
                    logger.info("W%d gcal_invited_count = %d", webinar_number, gcal_count)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    state.errors.append({"type": "gcal_count", "error": str(exc)[:500]})

            # --- Contacts ---
            async with AsyncSessionLocal() as db:
                batch: list[dict] = []
                async for c in client.stream_contacts(filters=contact_filter):
                    try:
                        batch.append(_build_contact_row(c))
                    except Exception as exc:
                        state.errors.append({"type": "contact", "id": c.get("id"), "error": str(exc)[:500]})
                        continue
                    if len(batch) >= 250:
                        try:
                            await _upsert_contacts_batch(db, batch)
                            state.contacts_synced += len(batch)
                            await db.commit()
                            await _heartbeat(state)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            state.errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                            logger.exception("Failed to upsert contact batch")
                            await db.rollback()
                        batch = []
                if batch:
                    try:
                        await _upsert_contacts_batch(db, batch)
                        state.contacts_synced += len(batch)
                        await db.commit()
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        state.errors.append({"type": "contact_batch", "size": len(batch), "error": str(exc)[:500]})
                        await db.rollback()
                await _heartbeat(state)

            # --- Opportunities (narrow phase only — deep skips) ---
            if not deep:
                async with AsyncSessionLocal() as db:
                    batch = []
                    async for o in client.stream_opportunities():
                        row = _build_opp_row(o)
                        batch.append(row)
                        if len(batch) >= 250:
                            try:
                                await _upsert_opps_batch(db, batch)
                                state.opportunities_synced += len(batch)
                                await db.commit()
                                await _heartbeat(state)
                            except asyncio.CancelledError:
                                raise
                            except Exception as exc:
                                state.errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                                await db.rollback()
                            batch = []
                    if batch:
                        try:
                            await _upsert_opps_batch(db, batch)
                            state.opportunities_synced += len(batch)
                            await db.commit()
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            state.errors.append({"type": "opp_batch", "size": len(batch), "error": str(exc)[:500]})
                            await db.rollback()
                    await _heartbeat(state)

            return state.run_id


async def run_webinar_sync_full(webinar_number: int, trigger: SyncTrigger = "manual") -> list[str]:
    """Run both phases sequentially: narrow first (fast), then deep (slow)."""
    narrow_id = await run_webinar_sync(webinar_number, trigger=trigger, deep=False)
    deep_id = await run_webinar_sync(webinar_number, trigger=trigger, deep=True)
    return [narrow_id, deep_id]


# ---------------------------------------------------------------------------
# Cancellation + recovery (called by the router and the scheduler)
# ---------------------------------------------------------------------------

async def request_cancel(run_id: str) -> bool:
    """Request cancellation of a running sync. Returns True if the row was
    found in 'running' state and the cancel was accepted, False otherwise.
    Sets the DB flag and (best-effort) cancels the in-process asyncio task.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(GHLSyncRun).where(GHLSyncRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None or run.status != "running":
            return False
        await db.execute(
            update(GHLSyncRun).where(GHLSyncRun.id == run_id).values(cancel_requested=True)
        )
        await db.commit()

    task = _active_tasks.get(run_id)
    if task is not None and not task.done():
        task.cancel()
    return True


async def recover_orphaned_runs() -> int:
    """Mark every 'running' row whose task is not in this process's registry
    as failed. Called at scheduler startup; on a fresh process, no tasks are
    in the registry, so any 'running' row is by definition an orphan from
    before the deploy.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(GHLSyncRun).where(GHLSyncRun.status == "running")
        )
        runs = result.scalars().all()
        recovered = 0
        for run in runs:
            if run.id in _active_tasks:
                continue
            now = datetime.now(timezone.utc)
            duration = int((now - run.started_at).total_seconds())
            errors = list(run.error_details) if run.error_details else []
            errors.append({"type": "orphaned", "reason": "process_restart_or_crash"})
            await db.execute(
                update(GHLSyncRun)
                .where(GHLSyncRun.id == run.id)
                .values(
                    status="failed",
                    completed_at=now,
                    duration_seconds=duration,
                    errors_count=len(errors),
                    error_details=errors,
                )
            )
            recovered += 1
        if recovered:
            await db.commit()
            logger.warning("Recovered %d orphaned sync run(s)", recovered)
    return recovered


async def sweep_stale_runs() -> int:
    """Periodic sweeper: any 'running' row with a heartbeat older than
    STALE_HEARTBEAT_SECONDS (or no heartbeat at all and started_at older
    than the threshold) is considered dead and marked failed.
    """
    threshold = datetime.now(timezone.utc) - timedelta(seconds=STALE_HEARTBEAT_SECONDS)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(GHLSyncRun).where(GHLSyncRun.status == "running")
        )
        runs = result.scalars().all()
        swept = 0
        for run in runs:
            last = run.last_heartbeat_at or run.started_at
            if last is None or last >= threshold:
                continue
            if run.id in _active_tasks and not _active_tasks[run.id].done():
                # Task is still alive in this process — heartbeat write may have
                # transiently failed; don't reap it.
                continue
            now = datetime.now(timezone.utc)
            duration = int((now - run.started_at).total_seconds())
            errors = list(run.error_details) if run.error_details else []
            errors.append({"type": "stale_heartbeat", "last_heartbeat_at": last.isoformat() if last else None})
            await db.execute(
                update(GHLSyncRun)
                .where(GHLSyncRun.id == run.id)
                .values(
                    status="failed",
                    completed_at=now,
                    duration_seconds=duration,
                    errors_count=len(errors),
                    error_details=errors,
                )
            )
            swept += 1
        if swept:
            await db.commit()
            logger.warning("Swept %d stale sync run(s)", swept)
    return swept


async def get_sync_settings() -> dict:
    """Return current sync settings (always one row, id=1)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(GHLSyncSettings).where(GHLSyncSettings.id == 1))
        s = result.scalar_one_or_none()
        if s is None:
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
