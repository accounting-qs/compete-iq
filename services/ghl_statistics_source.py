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
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Contact, GHLContact, GHLWebinarStats, OutreachSender, Webinar,
    WebinarGeekSubscriber, WebinarListAssignment,
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
    """PostgreSQL regex to find e{N}-{Yes|Maybe} token in
    calendar_invite_response_history. Uses PG's `\\y` word-boundary (Python's
    `\\b` is not supported by PG's regex engine) with case-insensitive flag.

    Example value: "e119-Yes, e113-Maybe"
    """
    return rf"\ye{webinar_number}-{response}\y"


def _webinar_series_regex(webinar_number: int) -> str:
    """PostgreSQL regex to find e{N} token in calendar_webinar_series_history.

    Example value: "e136, e127, e121, e118, e114"
    """
    return rf"\ye{webinar_number}\y"


# ---------------------------------------------------------------------------
# Aggregation query helpers
# ---------------------------------------------------------------------------

async def _webinar_summary_from_app(
    db: AsyncSession, webinar_id: str
) -> dict[str, float | None]:
    """Fetch invited/accountsNeeded from app-side assignments, plus the live
    actuallyUsed count from contacts.outreach_status='used'."""
    result = await db.execute(
        select(
            func.coalesce(func.sum(WebinarListAssignment.volume), 0).label("list_size"),
            func.coalesce(func.sum(WebinarListAssignment.accounts_used), 0).label("accts_used"),
        ).where(WebinarListAssignment.webinar_id == webinar_id)
    )
    row = result.one()
    list_size = int(row.list_size) if row.list_size is not None else 0

    # actuallyUsed: live count of contacts marked sent (outreach_status='used')
    # for any assignment of this webinar. Released contacts go back to
    # 'available' and disappear from this count, so plan/actual diverge by
    # the released amount.
    used_result = await db.execute(
        select(func.count())
        .select_from(Contact)
        .join(WebinarListAssignment, WebinarListAssignment.id == Contact.assignment_id)
        .where(
            WebinarListAssignment.webinar_id == webinar_id,
            Contact.outreach_status == "used",
        )
    )
    actually_used = int(used_result.scalar() or 0)

    return {
        "accountsNeeded": int(row.accts_used) if row.accts_used is not None else 0,
        "invited": list_size,  # app-side: invited = sum of planned volumes
        "actuallyUsed": actually_used,
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
            GHLContact.webinar_registration_in_form_date > start_date,
            GHLContact.webinar_registration_in_form_date <= end_date,
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

def _row_kind_from_assignment(a: WebinarListAssignment) -> str:
    if a.is_nonjoiners:
        return "nonjoiners"
    if a.is_no_list_data:
        return "no_list_data"
    return "list"


def _row_for_assignment(a: WebinarListAssignment, webinar_status: str) -> dict[str, Any]:
    """Build a child row dict from a Planning WebinarListAssignment.

    Base metrics (accountsNeeded / invited) are attributed to this list. GHL /
    WebinarGeek metrics are left null on the list row since they don't
    decompose per list — they're computed per-webinar and shown in the summary.
    """
    sender_name = a.sender.name if a.sender else None
    sender_color = a.sender.color if a.sender else None
    metrics: dict[str, float | None] = {
        "accountsNeeded": a.accounts_used or 0,
        "invited": a.volume or 0,
        # actuallyUsed is filled in by _compute_per_list_metrics — count of
        # contacts marked sent for this assignment (status='used').
        "actuallyUsed": 0,
    }

    # Title + description copy variants chosen for this list
    title_copy = None
    if a.title_copy:
        title_copy = {
            "id": a.title_copy.id,
            "text": a.title_copy.text,
            "variantIndex": a.title_copy.variant_index,
        }
    desc_copy = None
    if a.desc_copy:
        desc_copy = {
            "id": a.desc_copy.id,
            "text": a.desc_copy.text,
            "variantIndex": a.desc_copy.variant_index,
        }

    return {
        "workbookRow": a.display_order or 0,
        "assignmentId": a.id,
        "kind": _row_kind_from_assignment(a),
        "status": webinar_status,
        "note": None,
        "listUrl": a.list_url,
        "description": a.description,
        "listName": a.list_name,
        "sendInfo": sender_name,
        "senderColor": sender_color,
        "bucketId": a.bucket_id,
        "bucketName": a.bucket.name if a.bucket else None,
        "descLabel": None,
        "titleText": a.title_copy.text if a.title_copy else None,
        "titleCopy": title_copy,
        "descCopy": desc_copy,
        "createdDate": a.created_at.date().isoformat() if a.created_at else None,
        "industry": a.bucket.industry if a.bucket else None,
        "employeeRange": a.emp_range_override,
        "country": a.countries_override,
        "metrics": metrics,
    }


class GoHighLevelStatisticsSource:
    """Compute per-webinar metrics from Planning assignments + WebinarGeek
    subscribers + synced GHL contacts/opportunities.

    Returns per-list child rows (one per WebinarListAssignment) with base
    metrics + a pre-computed summary dict combining aggregated list bases
    and webinar-wide GHL/WG metrics.
    """

    async def get_raw_webinars(self) -> list[dict[str, Any]]:
        webinars = await self._load_webinars()
        date_windows = self._date_windows(webinars)
        raw_webinars: list[dict[str, Any]] = []
        for w in webinars:
            prev_date, current_date = date_windows[w.id]
            raw_webinars.append(
                await self._build_raw_webinar(w, prev_date, current_date)
            )
        raw_webinars.reverse()  # descending by number for the UI
        return raw_webinars

    async def get_raw_webinar_list(self) -> list[dict[str, Any]]:
        """Lightweight list — webinar identity + list count, no metrics.

        Powers the progressive-load UI: the page renders the parent rows
        immediately, then fetches per-webinar metrics in priority order.
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Webinar).order_by(Webinar.number.desc()))
            webinars = list(result.scalars().all())

            counts_q = await db.execute(
                select(WebinarListAssignment.webinar_id, func.count())
                .group_by(WebinarListAssignment.webinar_id)
            )
            counts = {str(wid): int(c or 0) for wid, c in counts_q.all()}

        out: list[dict[str, Any]] = []
        for w in webinars:
            out.append({
                "id": f"stat-w{w.number}",
                "number": w.number,
                "date": w.date.isoformat() if w.date else None,
                "title": w.main_title,
                "status": w.status,
                "listCount": counts.get(str(w.id), 0),
                "broadcastId": w.broadcast_id,
            })
        return out

    async def get_raw_webinar(self, number: int) -> dict[str, Any] | None:
        """Fully-processed single webinar (summary + per-list rows + specials)."""
        webinars = await self._load_webinars()
        date_windows = self._date_windows(webinars)
        for w in webinars:
            if w.number == number:
                prev_date, current_date = date_windows[w.id]
                return await self._build_raw_webinar(w, prev_date, current_date)
        return None

    async def _load_webinars(self) -> list[Webinar]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Webinar)
                .options(
                    selectinload(Webinar.assignments)
                    .selectinload(WebinarListAssignment.bucket),
                    selectinload(Webinar.assignments)
                    .selectinload(WebinarListAssignment.sender),
                    selectinload(Webinar.assignments)
                    .selectinload(WebinarListAssignment.title_copy),
                    selectinload(Webinar.assignments)
                    .selectinload(WebinarListAssignment.desc_copy),
                )
                .order_by(Webinar.number.asc())
            )
            return list(result.unique().scalars().all())

    @staticmethod
    def _date_windows(webinars: list[Webinar]) -> dict[str, tuple[Any, Any]]:
        """{webinar_id: (prev_date, current_date)} — window is (prev, current],
        i.e. excludes the previous webinar's day, includes the current's. When
        no prior webinar exists, falls back to a 7-day window that includes
        the current webinar's date (prev = current - 7)."""
        from datetime import timedelta
        out: dict[str, tuple[Any, Any]] = {}
        for idx, w in enumerate(webinars):
            prev_date = webinars[idx - 1].date if idx > 0 else None
            current_date = w.date
            if prev_date is None and current_date is not None:
                prev_date = current_date - timedelta(days=7)
            out[w.id] = (prev_date, current_date)
        return out

    async def _build_raw_webinar(
        self, w: Webinar, prev_date, current_date,
    ) -> dict[str, Any]:
        assignments = sorted(
            w.assignments,
            key=lambda a: (a.display_order or 0, a.created_at or 0),
        )
        rows = [_row_for_assignment(a, w.status) for a in assignments]

        async with AsyncSessionLocal() as db:
            summary = await self._compute_webinar_summary(
                db, w, assignments, prev_date, current_date,
            )
            per_list = await self._compute_per_list_metrics(
                db, w, assignments, prev_date, current_date,
            )
            for r, a in zip(rows, assignments):
                extra = per_list.get(a.id, {})
                r["metrics"].update(extra)

            synthetic = await self._synthetic_special_rows(
                db, w, assignments, prev_date, current_date,
            )
            rows.extend(synthetic)

        return {
            "number": w.number,
            "date": w.date.isoformat() if w.date else None,
            "title": w.main_title,
            "workbookRow": 0,
            "rows": rows,
            "summary": summary,
            "status": w.status,
        }

    async def _synthetic_special_rows(
        self,
        db: AsyncSession,
        w: Webinar,
        assignments: list[WebinarListAssignment],
        prev_date,
        current_date,
    ) -> list[dict[str, Any]]:
        """Build synthetic Nonjoiners + No List Data rows for this webinar.

        - Nonjoiners: GHL contacts whose calendar_webinar_series_non_joiners
          (or the narrower `_prefix_non_joiners`) contains eN, counted at
          webinar level. Always shown (value may be 0).
        - No List Data: contacts with any webinar-N signal (invite_response,
          non-joiners, booked_call=N, registration_number=N, self-reg in
          window) whose email is NOT in any Planning assignment for this
          webinar. "Leftover" counts not attributable to a planned list.
        """
        from sqlalchemy import text as sa_text

        N = w.number
        series_nj_re = _webinar_series_regex(N)
        yes_re = _invite_response_regex(N, "Yes")
        maybe_re = _invite_response_regex(N, "Maybe")
        broadcast_id = w.broadcast_id
        wid = w.id

        # ── Nonjoiners ────────────────────────────────────────────────
        r = await db.execute(sa_text("""
            SELECT COUNT(DISTINCT g.ghl_contact_id)
            FROM ghl_contact g
            WHERE g.calendar_webinar_series_non_joiners ~* :re
               OR g.calendar_invite_response_prefix_non_joiners ~* :re
        """).bindparams(re=series_nj_re))
        nj_count = int(r.scalar() or 0)

        # Nonjoiners row metrics
        nj_metrics: dict[str, float | None] = {
            "accountsNeeded": None,
            "invited": nj_count,  # treat nonjoiners as part of the invited pool
            "actuallyUsed": None,  # not from our planning system → fallback to invited
            "yesMarked": 0,
            "maybeMarked": 0,
            "selfRegMarked": 0,
            "gcalInvitedGhl": nj_count,
        }

        # ── No List Data ──────────────────────────────────────────────
        # Contacts with any webinar-N signal NOT mapped to any Planning list
        # for this webinar. Use EXISTS anti-join.
        # Use LEFT JOIN anti-pattern on LOWER(email) — 156k planned emails
        # is too large for `NOT IN` without hash support; LEFT JOIN ... WHERE
        # planned.email IS NULL compiles to a hash anti-join.
        # LP Regs (= Self Reg Marked) for NO LIST DATA also counts contacts
        # with `webinar_registration_in_form_date` in this webinar's window
        # (prev, current] even when they're NOT on a planned list.
        has_window = bool(prev_date and current_date)
        nld_params: dict[str, Any] = {
            "wid": wid, "yes_re": yes_re, "maybe_re": maybe_re,
            "nj_re": series_nj_re, "N": N,
        }
        if has_window:
            nld_params["sr_start"] = prev_date
            nld_params["sr_end"] = current_date
            relevant_window_pred = (
                "OR (g.webinar_registration_in_form_date > :sr_start "
                "AND g.webinar_registration_in_form_date <= :sr_end)"
            )
            self_reg_filter = (
                "wrd > :sr_start AND wrd <= :sr_end"
            )
        else:
            relevant_window_pred = ""
            self_reg_filter = "FALSE"

        nld_counts_sql = f"""
            WITH
            relevant AS (
                SELECT g.ghl_contact_id, LOWER(g.email) AS lem,
                       g.calendar_invite_response_history AS irh,
                       g.booked_call_webinar_series AS bcws,
                       g.webinar_registration_in_form_date AS wrd
                FROM ghl_contact g
                WHERE g.calendar_invite_response_history ~* :yes_re
                   OR g.calendar_invite_response_history ~* :maybe_re
                   OR g.calendar_webinar_series_non_joiners ~* :nj_re
                   OR g.booked_call_webinar_series = :N
                   OR g.webinar_registration_number = :N
                   {relevant_window_pred}
            ),
            planned AS (
                SELECT DISTINCT LOWER(c.email) AS email
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                WHERE wla.webinar_id = CAST(:wid AS uuid)
                  AND c.email IS NOT NULL
            ),
            unplanned AS (
                SELECT r.*
                FROM relevant r
                LEFT JOIN planned p ON p.email = r.lem
                WHERE p.email IS NULL
            )
            SELECT
                COUNT(DISTINCT ghl_contact_id)                          AS total_unplanned,
                COUNT(DISTINCT ghl_contact_id) FILTER (WHERE irh ~* :yes_re)   AS yes_unplanned,
                COUNT(DISTINCT ghl_contact_id) FILTER (WHERE irh ~* :maybe_re) AS maybe_unplanned,
                COUNT(DISTINCT ghl_contact_id) FILTER (WHERE bcws = :N)        AS booked_unplanned,
                COUNT(DISTINCT ghl_contact_id) FILTER (WHERE {self_reg_filter}) AS lp_regs_unplanned
            FROM unplanned
        """
        r = await db.execute(sa_text(nld_counts_sql).bindparams(**nld_params))
        row = r.one_or_none()
        total_u, yes_u, maybe_u, booked_u, lp_regs_u = (
            (int(row[0] or 0), int(row[1] or 0), int(row[2] or 0), int(row[3] or 0), int(row[4] or 0))
            if row else (0, 0, 0, 0, 0)
        )

        nld_metrics: dict[str, float | None] = {
            "accountsNeeded": None,
            "invited": total_u,
            "actuallyUsed": None,  # not from our planning system → fallback to invited
            "yesMarked": yes_u,
            "maybeMarked": maybe_u,
            "selfRegMarked": lp_regs_u,
            "lpRegs": lp_regs_u,
            "totalBookings": booked_u,
        }

        # Order rows: display_order later than any real list (negative means first; 999999 keeps them at the end)
        rows_out: list[dict[str, Any]] = []
        if nj_count > 0:
            rows_out.append({
                "workbookRow": 999998,
                "kind": "nonjoiners",
                "status": w.status,
                "note": None,
                "listUrl": None,
                "description": "Nonjoiners",
                "listName": None,
                "sendInfo": None,
                "senderColor": None,
                "bucketId": None,
                "bucketName": None,
                "descLabel": None,
                "titleText": None,
                "createdDate": None,
                "industry": None,
                "employeeRange": None,
                "country": None,
                "metrics": nj_metrics,
            })
        if total_u > 0:
            rows_out.append({
                "workbookRow": 999999,
                "kind": "no_list_data",
                "status": w.status,
                "note": None,
                "listUrl": None,
                "description": "NO LIST DATA",
                "listName": None,
                "sendInfo": None,
                "senderColor": None,
                "bucketId": None,
                "bucketName": None,
                "descLabel": None,
                "titleText": None,
                "createdDate": None,
                "industry": None,
                "employeeRange": None,
                "country": None,
                "metrics": nld_metrics,
            })
        return rows_out

    async def _compute_per_list_metrics(
        self,
        db: AsyncSession,
        w: Webinar,
        assignments: list[WebinarListAssignment],
        prev_date,
        current_date,
    ) -> dict[str, dict[str, float | None]]:
        """Return {assignment_id: partial_metrics_dict} with GHL/WG metrics
        filtered to the planning contacts of each list.

        Uses Planning `contacts.assignment_id` to map Planning emails → list.
        Joins to ghl_contact via lowercase email. Only lists whose planned
        contacts actually exist in GHL will show counts > 0.

        Performance: every metric that shares a join shape is computed via
        FILTER (WHERE …) inside one grouped query — three batched queries
        replace ~20 separate scans of the planning + ghl_contact join.
        """
        from sqlalchemy import text as sa_text

        N = w.number
        broadcast_id = w.broadcast_id
        yes_re = _invite_response_regex(N, "Yes")
        maybe_re = _invite_response_regex(N, "Maybe")
        series_re = _webinar_series_regex(N)
        wid = w.id

        out: dict[str, dict[str, float | None]] = {a.id: {} for a in assignments}
        if not assignments:
            return out

        # actuallyUsed per list — live count of contacts marked sent. Drops
        # when contacts are released back to the bucket pool, while volume
        # (planned) stays the same so plan vs. actual stays comparable.
        used_q = await db.execute(
            select(Contact.assignment_id, func.count())
            .where(
                Contact.assignment_id.in_([a.id for a in assignments]),
                Contact.outreach_status == "used",
            )
            .group_by(Contact.assignment_id)
        )
        for aid, cnt in used_q.all():
            if str(aid) in out:
                out[str(aid)]["actuallyUsed"] = int(cnt or 0)
        for aid in out:
            out[aid].setdefault("actuallyUsed", 0)

        has_window = bool(prev_date and current_date)

        # ── Batch A: ghl_contact-only counts (one scan of the planned join) ─
        # Includes yes/maybe marked, gcal invited, yes/maybe bookings,
        # self-reg, self-reg bookings, unsubscribes.
        ghl_params: dict[str, Any] = {
            "wid": wid,
            "yes_re": yes_re,
            "maybe_re": maybe_re,
            "series_re": series_re,
            "N": N,
        }
        window_filter_marker = "FALSE"
        if has_window:
            ghl_params["sr_start"] = prev_date
            ghl_params["sr_end"] = current_date
            window_filter_marker = "g.webinar_registration_in_form_date > :sr_start AND g.webinar_registration_in_form_date <= :sr_end"
            unsub_filter = "g.cold_calendar_unsubscribe_date > :sr_start AND g.cold_calendar_unsubscribe_date <= :sr_end"
        else:
            unsub_filter = "FALSE"
        ghl_sql = f"""
            SELECT
                c.assignment_id,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE g.calendar_invite_response_history ~* :yes_re) AS yes_marked,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE g.calendar_invite_response_history ~* :maybe_re) AS maybe_marked,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE g.calendar_webinar_series_history ~* :series_re) AS gcal_invited_ghl,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE g.calendar_invite_response_history ~* :yes_re AND g.booked_call_webinar_series = :N) AS yes_bookings,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE g.calendar_invite_response_history ~* :maybe_re AND g.booked_call_webinar_series = :N) AS maybe_bookings,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {window_filter_marker}) AS self_reg_marked,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE ({window_filter_marker}) AND g.booked_call_webinar_series = :N) AS self_reg_bookings,
                COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {unsub_filter}) AS unsubscribes
            FROM contacts c
            JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
            JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
            WHERE wla.webinar_id = CAST(:wid AS uuid)
            GROUP BY c.assignment_id
        """
        r = await db.execute(sa_text(ghl_sql).bindparams(**ghl_params))
        for row in r.mappings().all():
            aid = str(row["assignment_id"]) if row["assignment_id"] is not None else None
            if aid is None or aid not in out:
                continue
            m = out[aid]
            m["yesMarked"] = int(row["yes_marked"] or 0)
            m["maybeMarked"] = int(row["maybe_marked"] or 0)
            m["gcalInvitedGhl"] = int(row["gcal_invited_ghl"] or 0)
            m["yesBookings"] = int(row["yes_bookings"] or 0)
            m["maybeBookings"] = int(row["maybe_bookings"] or 0)
            if has_window:
                self_reg = int(row["self_reg_marked"] or 0)
                m["selfRegMarked"] = self_reg
                m["lpRegs"] = self_reg
                m["selfRegBookings"] = int(row["self_reg_bookings"] or 0)
                m["unsubscribes"] = int(row["unsubscribes"] or 0)

        # ── Batch B: WG attendance (one scan of planned + WG join) ───────
        if broadcast_id:
            ATT = "(wgs.watched_live = TRUE OR wgs.minutes_viewing > 0)"
            wg_window_filter = window_filter_marker if has_window else "FALSE"
            wg_params: dict[str, Any] = {
                "wid": wid,
                "bid": broadcast_id,
                "yes_re": yes_re,
                "maybe_re": maybe_re,
            }
            if has_window:
                wg_params["sr_start"] = prev_date
                wg_params["sr_end"] = current_date

            wg_sql = f"""
                SELECT
                    c.assignment_id,
                    COUNT(DISTINCT LOWER(c.email)) AS total_regs,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT}) AS total_attended,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND wgs.minutes_viewing >= 10) AS total_10m,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND wgs.minutes_viewing >= 30) AS total_30m,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND g.has_sms_click_tag = TRUE) AS sms_attended,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :yes_re) AS yes_attended,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :yes_re AND wgs.minutes_viewing >= 10) AS yes_10m,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :yes_re AND g.has_sms_click_tag = TRUE) AS yes_sms,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :maybe_re) AS maybe_attended,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :maybe_re AND wgs.minutes_viewing >= 10) AS maybe_10m,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :maybe_re AND g.has_sms_click_tag = TRUE) AS maybe_sms,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND ({wg_window_filter})) AS self_reg_attended,
                    COUNT(DISTINCT LOWER(c.email)) FILTER (WHERE {ATT} AND ({wg_window_filter}) AND wgs.minutes_viewing >= 10) AS self_reg_10m
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
                JOIN webinargeek_subscribers wgs ON LOWER(wgs.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:wid AS uuid)
                  AND wgs.broadcast_id = :bid
                GROUP BY c.assignment_id
            """
            r = await db.execute(sa_text(wg_sql).bindparams(**wg_params))
            for row in r.mappings().all():
                aid = str(row["assignment_id"]) if row["assignment_id"] is not None else None
                if aid is None or aid not in out:
                    continue
                m = out[aid]
                m["totalRegs"] = int(row["total_regs"] or 0)
                m["totalAttended"] = int(row["total_attended"] or 0)
                m["total10MinPlus"] = int(row["total_10m"] or 0)
                m["total30MinPlus"] = int(row["total_30m"] or 0)
                m["attendBySmsReminder"] = int(row["sms_attended"] or 0)
                m["yesAttended"] = int(row["yes_attended"] or 0)
                m["yes10MinPlus"] = int(row["yes_10m"] or 0)
                m["yesAttendBySmsClick"] = int(row["yes_sms"] or 0)
                m["maybeAttended"] = int(row["maybe_attended"] or 0)
                m["maybe10MinPlus"] = int(row["maybe_10m"] or 0)
                m["maybeAttendBySmsClick"] = int(row["maybe_sms"] or 0)
                if has_window:
                    m["selfRegAttended"] = int(row["self_reg_attended"] or 0)
                    m["selfReg10MinPlus"] = int(row["self_reg_10m"] or 0)

        # ── Batch C: opportunity counts (one scan of planned + opp join) ─
        # Union of (opp.webinar_source_number = N) or (contact.booked_call = N)
        # is enforced in WHERE; per-bucket counts use FILTER.
        qual_in = "('" + "', '".join(QUALIFIED_SET) + "')"
        opp_sql = f"""
            SELECT
                c.assignment_id,
                COUNT(DISTINCT o.ghl_opportunity_id) AS total_bookings,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE o.call1_appointment_date IS NOT NULL AND o.call1_appointment_date <= :now_ts) AS calls_passed,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE LOWER(COALESCE(o.call1_appointment_status, '')) = 'confirmed') AS confirmed,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE LOWER(COALESCE(o.call1_appointment_status, '')) = 'showed') AS shows,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE LOWER(COALESCE(o.call1_appointment_status, '')) IN ('noshow','no show','no-show')) AS no_shows,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE LOWER(COALESCE(o.call1_appointment_status, '')) = 'cancelled') AS canceled,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE o.pipeline_stage_id = :won_stage) AS won,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE o.pipeline_stage_id = :dq_stage) AS disqualified,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE LOWER(COALESCE(o.call1_appointment_status, '')) = 'showed' AND o.lead_quality IN {qual_in}) AS qualified,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE o.lead_quality = :lq_great) AS lq_great,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE o.lead_quality = :lq_ok) AS lq_ok,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE o.lead_quality = :lq_barely) AS lq_barely,
                COUNT(DISTINCT o.ghl_opportunity_id) FILTER (WHERE o.lead_quality = :lq_dq) AS lq_dq
            FROM contacts c
            JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
            JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
            JOIN ghl_opportunity o ON o.ghl_contact_id = g.ghl_contact_id
            WHERE wla.webinar_id = CAST(:wid AS uuid)
              AND (o.webinar_source_number = :N OR g.booked_call_webinar_series = :N)
            GROUP BY c.assignment_id
        """
        r = await db.execute(sa_text(opp_sql).bindparams(
            wid=wid, N=N,
            now_ts=datetime.now(timezone.utc),
            won_stage=DEAL_WON_STAGE_ID,
            dq_stage=DISQUALIFIED_STAGE_ID,
            lq_great=LEAD_QUALITY_GREAT,
            lq_ok=LEAD_QUALITY_OK,
            lq_barely=LEAD_QUALITY_BARELY,
            lq_dq=LEAD_QUALITY_BAD_DQ,
        ))
        for row in r.mappings().all():
            aid = str(row["assignment_id"]) if row["assignment_id"] is not None else None
            if aid is None or aid not in out:
                continue
            m = out[aid]
            m["totalBookings"] = int(row["total_bookings"] or 0)
            m["totalCallsDatePassed"] = int(row["calls_passed"] or 0)
            m["confirmed"] = int(row["confirmed"] or 0)
            m["shows"] = int(row["shows"] or 0)
            m["noShows"] = int(row["no_shows"] or 0)
            m["canceled"] = int(row["canceled"] or 0)
            m["won"] = int(row["won"] or 0)
            m["disqualified"] = int(row["disqualified"] or 0)
            m["qualified"] = int(row["qualified"] or 0)
            m["leadQualityGreat"] = int(row["lq_great"] or 0)
            m["leadQualityOk"] = int(row["lq_ok"] or 0)
            m["leadQualityBarelyPassable"] = int(row["lq_barely"] or 0)
            m["leadQualityBadDq"] = int(row["lq_dq"] or 0)

        # Default any keys we queried to 0 for lists that had no hits — so the
        # UI shows "0" instead of "—" (we genuinely queried and found none).
        default_zero = [
            "yesMarked", "maybeMarked", "gcalInvitedGhl",
            "yesBookings", "maybeBookings",
            "totalBookings", "totalCallsDatePassed", "confirmed", "shows", "noShows",
            "canceled", "won", "disqualified", "qualified",
            "leadQualityGreat", "leadQualityOk", "leadQualityBarelyPassable", "leadQualityBadDq",
        ]
        if has_window:
            default_zero.extend(["selfRegMarked", "selfRegBookings", "lpRegs", "unsubscribes"])
        if broadcast_id:
            default_zero.extend([
                "totalRegs", "totalAttended", "total10MinPlus", "total30MinPlus",
                "attendBySmsReminder",
                "yesAttended", "yes10MinPlus", "yesAttendBySmsClick",
                "maybeAttended", "maybe10MinPlus", "maybeAttendBySmsClick",
            ])
            if has_window:
                default_zero.extend(["selfRegAttended", "selfReg10MinPlus"])
        for aid, m in out.items():
            for k in default_zero:
                m.setdefault(k, 0)

        return out


    async def _compute_webinar_summary(
        self,
        db: AsyncSession,
        w: Webinar,
        assignments: list[WebinarListAssignment],
        prev_date,
        current_date,
    ) -> dict[str, float | None]:
        """Aggregated base metrics (sum over lists) + webinar-wide GHL/WG metrics."""
        summary: dict[str, float | None] = {
            # Base — aggregate from lists
            "accountsNeeded": sum((a.accounts_used or 0) for a in assignments),
            "invited": sum((a.volume or 0) for a in assignments),
        }

        # Fold in webinar-wide GHL/WG metrics (overwrites any base keys they share — none)
        webinar_wide = await self._compute_webinar_metrics(db, w, prev_date, current_date)
        for k, v in webinar_wide.items():
            if k not in summary:  # keep our summed base values
                summary[k] = v
        return summary

    async def _compute_webinar_metrics(
        self,
        db: AsyncSession,
        w: Webinar,
        prev_date,
        current_date,
    ) -> dict[str, float | None]:
        """Webinar-wide GHL/WG metrics. Same FILTER batching pattern as
        _compute_per_list_metrics — groups everything that shares a join shape
        into a single grouped query.
        """
        from sqlalchemy import text as sa_text

        N = w.number
        broadcast_id = w.broadcast_id
        metrics: dict[str, float | None] = {}

        # --- Base (from app) ---
        base = await _webinar_summary_from_app(db, w.id)
        metrics.update(base)

        # --- gcalInvitedGhl: read from ghl_webinar_stats cache (populated during sync) ---
        r = await db.execute(
            select(GHLWebinarStats.gcal_invited_count)
            .where(GHLWebinarStats.webinar_number == N)
        )
        metrics["gcalInvitedGhl"] = r.scalar()

        yes_re = _invite_response_regex(N, "Yes")
        maybe_re = _invite_response_regex(N, "Maybe")
        has_window = bool(prev_date and current_date)

        # ── Batch A: ghl_contact-only counts (one scan) ──────────────────
        ghl_params: dict[str, Any] = {
            "yes_re": yes_re,
            "maybe_re": maybe_re,
            "N": N,
        }
        if has_window:
            ghl_params["sr_start"] = prev_date
            ghl_params["sr_end"] = current_date
            window_filter = "g.webinar_registration_in_form_date > :sr_start AND g.webinar_registration_in_form_date <= :sr_end"
            unsub_filter = "g.cold_calendar_unsubscribe_date > :sr_start AND g.cold_calendar_unsubscribe_date <= :sr_end"
        else:
            window_filter = "FALSE"
            unsub_filter = "FALSE"
        ghl_sql = f"""
            SELECT
                COUNT(g.ghl_contact_id) FILTER (WHERE g.calendar_invite_response_history ~* :yes_re) AS yes_marked,
                COUNT(g.ghl_contact_id) FILTER (WHERE g.calendar_invite_response_history ~* :maybe_re) AS maybe_marked,
                COUNT(g.ghl_contact_id) FILTER (WHERE g.calendar_invite_response_history ~* :yes_re AND g.booked_call_webinar_series = :N) AS yes_bookings,
                COUNT(g.ghl_contact_id) FILTER (WHERE g.calendar_invite_response_history ~* :maybe_re AND g.booked_call_webinar_series = :N) AS maybe_bookings,
                COUNT(g.ghl_contact_id) FILTER (WHERE {window_filter}) AS self_reg_marked,
                COUNT(g.ghl_contact_id) FILTER (WHERE ({window_filter}) AND g.booked_call_webinar_series = :N) AS self_reg_bookings,
                COUNT(g.ghl_contact_id) FILTER (WHERE {unsub_filter}) AS unsubscribes
            FROM ghl_contact g
        """
        r = await db.execute(sa_text(ghl_sql).bindparams(**ghl_params))
        row = r.mappings().one()
        metrics["yesMarked"] = int(row["yes_marked"] or 0)
        metrics["maybeMarked"] = int(row["maybe_marked"] or 0)
        metrics["yesBookings"] = int(row["yes_bookings"] or 0)
        metrics["maybeBookings"] = int(row["maybe_bookings"] or 0)
        if has_window:
            self_reg = int(row["self_reg_marked"] or 0)
            metrics["selfRegMarked"] = self_reg
            metrics["lpRegs"] = self_reg
            metrics["selfRegBookings"] = int(row["self_reg_bookings"] or 0)
            metrics["unsubscribes"] = int(row["unsubscribes"] or 0)
        else:
            for k in ("selfRegMarked", "selfRegBookings", "unsubscribes"):
                metrics[k] = None

        # ── Batch B: WG attendance (one scan) ────────────────────────────
        if broadcast_id:
            ATT = "(wgs.watched_live = TRUE OR wgs.minutes_viewing > 0)"
            wg_window_filter = window_filter if has_window else "FALSE"
            wg_params: dict[str, Any] = {
                "bid": broadcast_id,
                "yes_re": yes_re,
                "maybe_re": maybe_re,
            }
            if has_window:
                wg_params["sr_start"] = prev_date
                wg_params["sr_end"] = current_date

            wg_sql = f"""
                SELECT
                    COUNT(*) AS total_regs,
                    COUNT(*) FILTER (WHERE {ATT}) AS total_attended,
                    COUNT(*) FILTER (WHERE {ATT} AND wgs.minutes_viewing >= 10) AS total_10m,
                    COUNT(*) FILTER (WHERE {ATT} AND wgs.minutes_viewing >= 30) AS total_30m,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND g.has_sms_click_tag = TRUE) AS sms_attended,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :yes_re) AS yes_attended,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :yes_re AND wgs.minutes_viewing >= 10) AS yes_10m,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :yes_re AND g.has_sms_click_tag = TRUE) AS yes_sms,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :maybe_re) AS maybe_attended,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :maybe_re AND wgs.minutes_viewing >= 10) AS maybe_10m,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND g.calendar_invite_response_history ~* :maybe_re AND g.has_sms_click_tag = TRUE) AS maybe_sms,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND ({wg_window_filter})) AS self_reg_attended,
                    COUNT(DISTINCT g.ghl_contact_id) FILTER (WHERE {ATT} AND ({wg_window_filter}) AND wgs.minutes_viewing >= 10) AS self_reg_10m
                FROM webinargeek_subscribers wgs
                LEFT JOIN ghl_contact g ON LOWER(g.email) = LOWER(wgs.email)
                WHERE wgs.broadcast_id = :bid
            """
            r = await db.execute(sa_text(wg_sql).bindparams(**wg_params))
            row = r.mappings().one()
            metrics["totalRegs"] = int(row["total_regs"] or 0)
            metrics["totalAttended"] = int(row["total_attended"] or 0)
            metrics["total10MinPlus"] = int(row["total_10m"] or 0)
            metrics["total30MinPlus"] = int(row["total_30m"] or 0)
            metrics["attendBySmsReminder"] = int(row["sms_attended"] or 0)
            metrics["yesAttended"] = int(row["yes_attended"] or 0)
            metrics["yes10MinPlus"] = int(row["yes_10m"] or 0)
            metrics["yesAttendBySmsClick"] = int(row["yes_sms"] or 0)
            metrics["maybeAttended"] = int(row["maybe_attended"] or 0)
            metrics["maybe10MinPlus"] = int(row["maybe_10m"] or 0)
            metrics["maybeAttendBySmsClick"] = int(row["maybe_sms"] or 0)
            if has_window:
                metrics["selfRegAttended"] = int(row["self_reg_attended"] or 0)
                metrics["selfReg10MinPlus"] = int(row["self_reg_10m"] or 0)
            else:
                metrics["selfRegAttended"] = None
                metrics["selfReg10MinPlus"] = None
        else:
            for k in (
                "totalRegs", "totalAttended", "total10MinPlus", "total30MinPlus", "attendBySmsReminder",
                "yesAttended", "yes10MinPlus", "yesAttendBySmsClick",
                "maybeAttended", "maybe10MinPlus", "maybeAttendBySmsClick",
                "selfRegAttended", "selfReg10MinPlus",
            ):
                metrics[k] = None

        # ── Sales: load the opp set once, compute everything in Python ───
        # The union of (opp.webinar_source_number = N) and
        # (contact.booked_call_webinar_series = N) is small (handful → low
        # hundreds), so a single SELECT then bucketing in Python is faster
        # and simpler than 14 FILTER aggregates against the join.
        r = await db.execute(sa_text("""
            SELECT DISTINCT ON (o.ghl_opportunity_id)
                   o.ghl_opportunity_id,
                   o.call1_appointment_date,
                   o.call1_appointment_status,
                   o.pipeline_stage_id,
                   o.lead_quality,
                   o.projected_deal_size_value,
                   o.monetary_value
            FROM ghl_opportunity o
            LEFT JOIN ghl_contact g ON g.ghl_contact_id = o.ghl_contact_id
            WHERE o.webinar_source_number = :N
               OR g.booked_call_webinar_series = :N
        """).bindparams(N=N))
        opps = r.mappings().all()
        n_opps = len(opps)

        def cnt(pred) -> int:
            return sum(1 for o in opps if pred(o))

        now_utc = datetime.now(timezone.utc)
        metrics["totalBookings"] = n_opps
        metrics["totalCallsDatePassed"] = cnt(
            lambda o: o["call1_appointment_date"] is not None and o["call1_appointment_date"] <= now_utc
        )
        metrics["confirmed"] = cnt(lambda o: (o["call1_appointment_status"] or "").lower() == "confirmed")
        metrics["shows"] = cnt(lambda o: (o["call1_appointment_status"] or "").lower() == "showed")
        metrics["noShows"] = cnt(lambda o: (o["call1_appointment_status"] or "").lower() in ("noshow", "no show", "no-show"))
        metrics["canceled"] = cnt(lambda o: (o["call1_appointment_status"] or "").lower() == "cancelled")
        metrics["won"] = cnt(lambda o: o["pipeline_stage_id"] == DEAL_WON_STAGE_ID)
        metrics["disqualified"] = cnt(lambda o: o["pipeline_stage_id"] == DISQUALIFIED_STAGE_ID)

        metrics["leadQualityGreat"] = cnt(lambda o: o["lead_quality"] == LEAD_QUALITY_GREAT)
        metrics["leadQualityOk"] = cnt(lambda o: o["lead_quality"] == LEAD_QUALITY_OK)
        metrics["leadQualityBarelyPassable"] = cnt(lambda o: o["lead_quality"] == LEAD_QUALITY_BARELY)
        metrics["leadQualityBadDq"] = cnt(lambda o: o["lead_quality"] == LEAD_QUALITY_BAD_DQ)

        metrics["qualified"] = cnt(
            lambda o: (o["call1_appointment_status"] or "").lower() == "showed"
            and o["lead_quality"] in QUALIFIED_SET
        )

        proj_vals = [o["projected_deal_size_value"] for o in opps if o["projected_deal_size_value"]]
        metrics["avgProjectedDealSize"] = (sum(proj_vals) / len(proj_vals)) if proj_vals else None

        won_vals = [
            float(o["monetary_value"]) for o in opps
            if o["pipeline_stage_id"] == DEAL_WON_STAGE_ID and o["monetary_value"] is not None
        ]
        metrics["avgClosedDealValue"] = sum(won_vals) if won_vals else None

        metrics.setdefault("lpRegs", None)

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
