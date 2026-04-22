"""GoHighLevelStatisticsSource — compute per-webinar metrics from synced GHL tables.

Joins ghl_contact / ghl_opportunity / webinargeek_subscribers / webinar_list_assignments
against the Planning `webinars` table to produce the same
raw-metric shape as WorkbookMockStatisticsSource (then the existing
compute_derived_metrics() in services.statistics derives the ratios).

Invited numbers come from the app (Planning assignments), not GHL. Group A
(sales) comes from ghl_opportunity keyed on Webinar Source Number v2.
Yes/Maybe/Self Reg counts come from parsing GHL contact text fields.
Attendance / watch time comes from webinargeek_subscribers joined by email.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    GHLContact, GHLOpportunity, Webinar, WebinarGeekSubscriber, WebinarListAssignment,
)
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


# Deal Won / Disqualified stage IDs (from reference project)
DEAL_WON_STAGE_ID = "544b178f-d1f2-4186-a8c2-00c3b0eeefe8"
DISQUALIFIED_STAGE_ID = "62448525-88ab-4e82-b414-b6880e69e2de"

# Lead quality buckets
LEAD_QUALITY_GREAT = "Great"
LEAD_QUALITY_OK = "Ok"
LEAD_QUALITY_BARELY = "Barely Passable"
LEAD_QUALITY_BAD_DQ = "Bad / DQ"

# Qualified = any lead_quality except DQ (per user: qualified = shows with a non-DQ quality)
QUALIFIED_SET = {LEAD_QUALITY_GREAT, LEAD_QUALITY_OK, LEAD_QUALITY_BARELY}


# ---------------------------------------------------------------------------
# Parsing helpers for free-text contact fields
# ---------------------------------------------------------------------------

def _invite_response_regex(webinar_number: int, response: str) -> str:
    """Regex to find e{N}-{Yes|Maybe} token in calendar_invite_response_history.

    Uses word boundaries and case-insensitive match. Prefix letter is literal "e".
    """
    # Example: "e119-Yes, e113-Maybe" — so we look for "e119-Yes" as a whole token
    return rf"(?i)\be{webinar_number}-{response}\b"


def _webinar_series_regex(webinar_number: int) -> str:
    """Regex to find e{N} token in calendar_webinar_series_history.

    Example value: "e136, e127, e121, e118, e114"
    """
    return rf"(?i)\be{webinar_number}\b"


# ---------------------------------------------------------------------------
# Aggregation query helpers
# ---------------------------------------------------------------------------

async def _webinar_summary_from_app(
    db: AsyncSession, webinar_id: str
) -> dict[str, float | None]:
    """Fetch invited/listSize/listRemain/accountsNeeded from app-side assignments."""
    result = await db.execute(
        select(
            func.coalesce(func.sum(WebinarListAssignment.volume), 0).label("list_size"),
            func.coalesce(func.sum(WebinarListAssignment.remaining), 0).label("list_remain"),
            func.coalesce(func.sum(WebinarListAssignment.gcal_invited), 0).label("gcal_invited"),
            func.coalesce(func.sum(WebinarListAssignment.accounts_used), 0).label("accts_used"),
        ).where(WebinarListAssignment.webinar_id == webinar_id)
    )
    row = result.one()
    list_size = int(row.list_size) if row.list_size is not None else 0
    return {
        "listSize": list_size,
        "listRemain": int(row.list_remain) if row.list_remain is not None else 0,
        "gcalInvited": int(row.gcal_invited) if row.gcal_invited is not None else 0,
        "accountsNeeded": int(row.accts_used) if row.accts_used is not None else 0,
        "invited": list_size,  # app-side: invited = sum of planned volumes
    }


async def _count_contact_field_match(
    db: AsyncSession, column, pattern: str
) -> int:
    """Count rows where the given TEXT column matches the regex."""
    result = await db.execute(
        select(func.count(GHLContact.ghl_contact_id)).where(column.op("~*")(pattern))
    )
    return int(result.scalar() or 0)


async def _count_attended_for_broadcast_filtered(
    db: AsyncSession,
    broadcast_id: str | None,
    invite_response_pattern: str | None,
    registration_between: tuple | None,
    min_minutes: int | None = None,
    require_sms_tag: bool = False,
) -> int:
    """Count contacts attended a webinar (via webinargeek_subscribers join on email)
    with optional filters: invite response pattern (yes/maybe), self-reg date window,
    minimum minutes_viewing, SMS click tag.
    """
    if not broadcast_id:
        return 0

    q = (
        select(func.count(func.distinct(GHLContact.ghl_contact_id)))
        .select_from(GHLContact)
        .join(
            WebinarGeekSubscriber,
            func.lower(WebinarGeekSubscriber.email) == func.lower(GHLContact.email),
        )
        .where(WebinarGeekSubscriber.broadcast_id == broadcast_id)
    )

    # Attended = watched_live=True OR minutes_viewing > 0
    attended_filter = or_(
        WebinarGeekSubscriber.watched_live.is_(True),
        WebinarGeekSubscriber.minutes_viewing > 0,
    )
    q = q.where(attended_filter)

    if min_minutes is not None:
        q = q.where(WebinarGeekSubscriber.minutes_viewing >= min_minutes)

    if invite_response_pattern:
        q = q.where(
            GHLContact.calendar_invite_response_history.op("~*")(invite_response_pattern)
        )

    if registration_between:
        start_date, end_date = registration_between
        q = q.where(
            GHLContact.webinar_registration_in_form_date >= start_date,
            GHLContact.webinar_registration_in_form_date < end_date,
        )

    if require_sms_tag:
        q = q.where(GHLContact.has_sms_click_tag.is_(True))

    result = await db.execute(q)
    return int(result.scalar() or 0)


async def _count_broadcast_attendees(
    db: AsyncSession, broadcast_id: str, min_minutes: int | None = None,
    require_sms_tag: bool = False,
) -> int:
    """Total attended count (no contact-field filter) for a broadcast."""
    if require_sms_tag:
        # Need GHL contact join for tag — use the filtered helper
        return await _count_attended_for_broadcast_filtered(
            db, broadcast_id, None, None, min_minutes, require_sms_tag=True
        )

    q = select(func.count()).where(
        WebinarGeekSubscriber.broadcast_id == broadcast_id,
        or_(
            WebinarGeekSubscriber.watched_live.is_(True),
            WebinarGeekSubscriber.minutes_viewing > 0,
        ),
    )
    if min_minutes is not None:
        q = q.where(WebinarGeekSubscriber.minutes_viewing >= min_minutes)
    result = await db.execute(q)
    return int(result.scalar() or 0)


# ---------------------------------------------------------------------------
# Main source class
# ---------------------------------------------------------------------------

class GoHighLevelStatisticsSource:
    """Compute per-webinar metrics from synced GHL tables + webinargeek + planning."""

    async def get_raw_webinars(self) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            # Load all webinars ordered by number ascending (we'll sort desc in UI)
            result = await db.execute(
                select(Webinar).order_by(Webinar.number.asc())
            )
            webinars = list(result.scalars().all())

        raw_webinars: list[dict[str, Any]] = []
        webinar_numbers = [w.number for w in webinars]

        for idx, w in enumerate(webinars):
            # Find the previous webinar date for self-reg window
            prev_date = None
            if idx > 0:
                prev_date = webinars[idx - 1].date
            current_date = w.date

            async with AsyncSessionLocal() as db:
                metrics = await self._compute_webinar_metrics(
                    db, w, prev_date, current_date
                )

            raw_webinars.append({
                "number": w.number,
                "date": w.date.isoformat() if w.date else None,
                "title": w.main_title,
                "workbookRow": 0,  # not applicable for GHL source
                "rows": [{
                    "workbookRow": 0,
                    "kind": "list",
                    "status": w.status,
                    "note": None,
                    "listUrl": None,
                    "description": f"Webinar {w.number}",
                    "listName": None,
                    "sendInfo": None,
                    "descLabel": None,
                    "titleText": w.main_title,
                    "createdDate": None,
                    "industry": None,
                    "employeeRange": None,
                    "country": None,
                    "metrics": metrics,
                }],
            })

        # Return descending by number (most recent first) to match UI expectation
        raw_webinars.reverse()
        return raw_webinars

    async def _compute_webinar_metrics(
        self,
        db: AsyncSession,
        w: Webinar,
        prev_date,
        current_date,
    ) -> dict[str, float | None]:
        N = w.number
        broadcast_id = w.broadcast_id
        metrics: dict[str, float | None] = {}

        # --- Base (from app) ---
        base = await _webinar_summary_from_app(db, w.id)
        metrics.update(base)

        # --- gcalInvitedGhl: contacts whose series history contains e{N} ---
        metrics["gcalInvitedGhl"] = await _count_contact_field_match(
            db, GHLContact.calendar_webinar_series_history, _webinar_series_regex(N)
        )

        # --- Yes / Maybe marked (contact count) ---
        yes_re = _invite_response_regex(N, "Yes")
        maybe_re = _invite_response_regex(N, "Maybe")
        metrics["yesMarked"] = await _count_contact_field_match(
            db, GHLContact.calendar_invite_response_history, yes_re
        )
        metrics["maybeMarked"] = await _count_contact_field_match(
            db, GHLContact.calendar_invite_response_history, maybe_re
        )

        # --- Yes attended / 10m+ / SMS click ---
        if broadcast_id:
            metrics["yesAttended"] = await _count_attended_for_broadcast_filtered(
                db, broadcast_id, yes_re, None
            )
            metrics["yes10MinPlus"] = await _count_attended_for_broadcast_filtered(
                db, broadcast_id, yes_re, None, min_minutes=10
            )
            metrics["yesAttendBySmsClick"] = await _count_attended_for_broadcast_filtered(
                db, broadcast_id, yes_re, None, require_sms_tag=True
            )

            metrics["maybeAttended"] = await _count_attended_for_broadcast_filtered(
                db, broadcast_id, maybe_re, None
            )
            metrics["maybe10MinPlus"] = await _count_attended_for_broadcast_filtered(
                db, broadcast_id, maybe_re, None, min_minutes=10
            )
            metrics["maybeAttendBySmsClick"] = await _count_attended_for_broadcast_filtered(
                db, broadcast_id, maybe_re, None, require_sms_tag=True
            )
        else:
            for k in (
                "yesAttended", "yes10MinPlus", "yesAttendBySmsClick",
                "maybeAttended", "maybe10MinPlus", "maybeAttendBySmsClick",
            ):
                metrics[k] = None

        # --- Yes / Maybe bookings: yes/maybe contact + booked_call_webinar_series == N ---
        if metrics["yesMarked"]:
            r = await db.execute(
                select(func.count(GHLContact.ghl_contact_id)).where(
                    GHLContact.calendar_invite_response_history.op("~*")(yes_re),
                    GHLContact.booked_call_webinar_series == N,
                )
            )
            metrics["yesBookings"] = int(r.scalar() or 0)
        else:
            metrics["yesBookings"] = 0
        if metrics["maybeMarked"]:
            r = await db.execute(
                select(func.count(GHLContact.ghl_contact_id)).where(
                    GHLContact.calendar_invite_response_history.op("~*")(maybe_re),
                    GHLContact.booked_call_webinar_series == N,
                )
            )
            metrics["maybeBookings"] = int(r.scalar() or 0)
        else:
            metrics["maybeBookings"] = 0

        # --- Self-reg marked/attended/10m+/bookings (webinar_registration_in_form_date in window) ---
        if prev_date and current_date:
            window = (prev_date, current_date)
            r = await db.execute(
                select(func.count(GHLContact.ghl_contact_id)).where(
                    GHLContact.webinar_registration_in_form_date >= prev_date,
                    GHLContact.webinar_registration_in_form_date < current_date,
                )
            )
            metrics["selfRegMarked"] = int(r.scalar() or 0)

            if broadcast_id:
                metrics["selfRegAttended"] = await _count_attended_for_broadcast_filtered(
                    db, broadcast_id, None, window
                )
                metrics["selfReg10MinPlus"] = await _count_attended_for_broadcast_filtered(
                    db, broadcast_id, None, window, min_minutes=10
                )
            else:
                metrics["selfRegAttended"] = None
                metrics["selfReg10MinPlus"] = None

            r = await db.execute(
                select(func.count(GHLContact.ghl_contact_id)).where(
                    GHLContact.webinar_registration_in_form_date >= prev_date,
                    GHLContact.webinar_registration_in_form_date < current_date,
                    GHLContact.booked_call_webinar_series == N,
                )
            )
            metrics["selfRegBookings"] = int(r.scalar() or 0)
        else:
            for k in ("selfRegMarked", "selfRegAttended", "selfReg10MinPlus", "selfRegBookings"):
                metrics[k] = None

        # --- Total regs/attended/10m+/30m+ ---
        if broadcast_id:
            r = await db.execute(
                select(func.count()).where(WebinarGeekSubscriber.broadcast_id == broadcast_id)
            )
            metrics["totalRegs"] = int(r.scalar() or 0)
            metrics["totalAttended"] = await _count_broadcast_attendees(db, broadcast_id)
            metrics["total10MinPlus"] = await _count_broadcast_attendees(db, broadcast_id, min_minutes=10)
            metrics["total30MinPlus"] = await _count_broadcast_attendees(db, broadcast_id, min_minutes=30)
            metrics["attendBySmsReminder"] = await _count_broadcast_attendees(
                db, broadcast_id, require_sms_tag=True
            )
        else:
            for k in ("totalRegs", "totalAttended", "total10MinPlus", "total30MinPlus", "attendBySmsReminder"):
                metrics[k] = None

        # --- Unsubscribes in webinar window ---
        if prev_date and current_date:
            r = await db.execute(
                select(func.count(GHLContact.ghl_contact_id)).where(
                    GHLContact.cold_calendar_unsubscribe_date >= prev_date,
                    GHLContact.cold_calendar_unsubscribe_date < current_date,
                )
            )
            metrics["unsubscribes"] = int(r.scalar() or 0)
        else:
            metrics["unsubscribes"] = None

        # --- Sales (opportunities keyed on webinar_source_number) ---
        r = await db.execute(
            select(GHLOpportunity).where(GHLOpportunity.webinar_source_number == N)
        )
        opps = list(r.scalars().all())
        n_opps = len(opps)

        def cnt(pred) -> int:
            return sum(1 for o in opps if pred(o))

        metrics["totalBookings"] = n_opps if n_opps > 0 else 0
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        metrics["totalCallsDatePassed"] = cnt(
            lambda o: o.call1_appointment_date is not None and o.call1_appointment_date <= now_utc
        )
        metrics["confirmed"] = cnt(lambda o: (o.call1_appointment_status or "").lower() == "confirmed")
        metrics["shows"] = cnt(lambda o: (o.call1_appointment_status or "").lower() == "showed")
        metrics["noShows"] = cnt(lambda o: (o.call1_appointment_status or "").lower() in ("noshow", "no show", "no-show"))
        metrics["canceled"] = cnt(lambda o: (o.call1_appointment_status or "").lower() == "cancelled")
        metrics["won"] = cnt(lambda o: o.pipeline_stage_id == DEAL_WON_STAGE_ID)
        metrics["disqualified"] = cnt(lambda o: o.pipeline_stage_id == DISQUALIFIED_STAGE_ID)

        # Lead quality buckets
        metrics["leadQualityGreat"] = cnt(lambda o: o.lead_quality == LEAD_QUALITY_GREAT)
        metrics["leadQualityOk"] = cnt(lambda o: o.lead_quality == LEAD_QUALITY_OK)
        metrics["leadQualityBarelyPassable"] = cnt(lambda o: o.lead_quality == LEAD_QUALITY_BARELY)
        metrics["leadQualityBadDq"] = cnt(lambda o: o.lead_quality == LEAD_QUALITY_BAD_DQ)

        # Qualified = shows with a non-DQ quality (user: "qualified / shows")
        metrics["qualified"] = cnt(
            lambda o: (o.call1_appointment_status or "").lower() == "showed"
            and o.lead_quality in QUALIFIED_SET
        )

        # avgProjectedDealSize = avg of numeric dropdown values
        proj_vals = [o.projected_deal_size_value for o in opps if o.projected_deal_size_value]
        metrics["avgProjectedDealSize"] = (sum(proj_vals) / len(proj_vals)) if proj_vals else None

        # avgClosedDealValue = sum of monetary_value for Deal Won
        won_vals = [
            float(o.monetary_value) for o in opps
            if o.pipeline_stage_id == DEAL_WON_STAGE_ID and o.monetary_value is not None
        ]
        metrics["avgClosedDealValue"] = sum(won_vals) if won_vals else None

        # --- Skipped ---
        metrics["ghlPageViews"] = None
        metrics["lpRegs"] = None

        return metrics


async def get_last_sync_summary() -> dict | None:
    """Return latest completed GHL sync metadata for UI badge on Statistics page."""
    from db.models import GHLSyncRun
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(GHLSyncRun)
            .where(GHLSyncRun.status.in_(["completed", "running"]))
            .order_by(GHLSyncRun.started_at.desc())
            .limit(1)
        )
        run = r.scalar_one_or_none()
        if run is None:
            return None
        return {
            "run_id": run.id,
            "sync_type": run.sync_type,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "contacts_synced": run.contacts_synced,
            "opportunities_synced": run.opportunities_synced,
        }
