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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Contact, GHLContact, GHLOpportunity, GHLWebinarStats, OutreachSender, Webinar,
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

def _row_kind_from_assignment(a: WebinarListAssignment) -> str:
    if a.is_nonjoiners:
        return "nonjoiners"
    if a.is_no_list_data:
        return "no_list_data"
    return "list"


def _row_for_assignment(a: WebinarListAssignment, webinar_status: str) -> dict[str, Any]:
    """Build a child row dict from a Planning WebinarListAssignment.

    Base metrics (listSize / listRemain / gcalInvited / accountsNeeded / invited)
    are attributed to this list. GHL / WebinarGeek metrics are left null on the
    list row since they don't decompose per list — they're computed per-webinar
    and shown in the summary.
    """
    sender_name = a.sender.name if a.sender else None
    sender_color = a.sender.color if a.sender else None
    metrics: dict[str, float | None] = {
        "listSize": a.volume or 0,
        "listRemain": a.remaining or 0,
        "gcalInvited": a.gcal_invited or 0,
        "accountsNeeded": a.accounts_used or 0,
        "invited": a.volume or 0,
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
        async with AsyncSessionLocal() as db:
            # Load webinars with their assignments (+bucket, +sender) in one go
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
            webinars = list(result.unique().scalars().all())

        raw_webinars: list[dict[str, Any]] = []

        from datetime import timedelta
        for idx, w in enumerate(webinars):
            # For self-reg and unsub windows, default to 30 days before the
            # webinar date when there's no prior webinar in the DB (otherwise
            # those metrics are always null for the first/only webinar).
            prev_date = webinars[idx - 1].date if idx > 0 else None
            current_date = w.date
            if prev_date is None and current_date is not None:
                prev_date = current_date - timedelta(days=30)

            # Per-list child rows (sorted by display_order, then id)
            assignments = sorted(
                w.assignments,
                key=lambda a: (a.display_order or 0, a.created_at or 0),
            )
            rows = [_row_for_assignment(a, w.status) for a in assignments]

            async with AsyncSessionLocal() as db:
                # Compute webinar-wide summary
                summary = await self._compute_webinar_summary(
                    db, w, assignments, prev_date, current_date,
                )
                # Compute per-list GHL metrics and merge into each row
                per_list = await self._compute_per_list_metrics(
                    db, w, assignments, prev_date, current_date,
                )
                for r, a in zip(rows, assignments):
                    extra = per_list.get(a.id, {})
                    r["metrics"].update(extra)

                # Synthesize Nonjoiners + No List Data rows (if any data exists)
                synthetic = await self._synthetic_special_rows(
                    db, w, assignments, prev_date, current_date,
                )
                rows.extend(synthetic)

            raw_webinars.append({
                "number": w.number,
                "date": w.date.isoformat() if w.date else None,
                "title": w.main_title,
                "workbookRow": 0,
                "rows": rows,
                "summary": summary,
                "status": w.status,
            })

        raw_webinars.reverse()  # descending by number for the UI
        return raw_webinars

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
            "listSize": None,
            "listRemain": None,
            "gcalInvited": None,
            "accountsNeeded": None,
            "invited": nj_count,  # treat nonjoiners as part of the invited pool
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
        nld_counts_sql = """
            WITH
            relevant AS (
                SELECT g.ghl_contact_id, LOWER(g.email) AS lem,
                       g.calendar_invite_response_history AS irh,
                       g.booked_call_webinar_series AS bcws
                FROM ghl_contact g
                WHERE g.calendar_invite_response_history ~* :yes_re
                   OR g.calendar_invite_response_history ~* :maybe_re
                   OR g.calendar_webinar_series_non_joiners ~* :nj_re
                   OR g.booked_call_webinar_series = :N
                   OR g.webinar_registration_number = :N
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
                COUNT(DISTINCT ghl_contact_id) FILTER (WHERE bcws = :N)        AS booked_unplanned
            FROM unplanned
        """
        r = await db.execute(sa_text(nld_counts_sql).bindparams(
            wid=wid, yes_re=yes_re, maybe_re=maybe_re, nj_re=series_nj_re, N=N,
        ))
        row = r.one_or_none()
        total_u, yes_u, maybe_u, booked_u = (int(row[0] or 0), int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)) if row else (0, 0, 0, 0)

        nld_metrics: dict[str, float | None] = {
            "listSize": None,
            "listRemain": None,
            "gcalInvited": None,
            "accountsNeeded": None,
            "invited": total_u,
            "yesMarked": yes_u,
            "maybeMarked": maybe_u,
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
        """
        from sqlalchemy import text as sa_text

        N = w.number
        broadcast_id = w.broadcast_id
        yes_re = _invite_response_regex(N, "Yes")
        maybe_re = _invite_response_regex(N, "Maybe")
        series_re = _webinar_series_regex(N)
        wid = w.id

        out: dict[str, dict[str, float | None]] = {a.id: {} for a in assignments}

        async def _group_count(sql: str, **params) -> dict[str, int]:
            r = await db.execute(sa_text(sql).bindparams(webinar_id=wid, **params))
            # Cast assignment_id to str — Planning assignments use str-uuid ids,
            # raw SQL returns UUID objects which won't match dict lookups.
            return {str(row[0]): int(row[1]) for row in r.fetchall() if row[0] is not None}

        # ── GHL-only counts (no broadcast needed) ────────────────────────
        # yesMarked / maybeMarked — filter on calendar_invite_response_history
        for key, regex in [("yesMarked", yes_re), ("maybeMarked", maybe_re)]:
            counts = await _group_count("""
                SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                  AND g.calendar_invite_response_history ~* :regex
                GROUP BY c.assignment_id
            """, regex=regex)
            for aid, cnt in counts.items():
                if aid in out:
                    out[aid][key] = cnt

        # gcalInvitedGhl per list — calendar_webinar_series_history contains eN
        counts = await _group_count("""
            SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
            FROM contacts c
            JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
            JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
            WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
              AND g.calendar_webinar_series_history ~* :regex
            GROUP BY c.assignment_id
        """, regex=series_re)
        for aid, cnt in counts.items():
            if aid in out:
                out[aid]["gcalInvitedGhl"] = cnt

        # yesBookings / maybeBookings — invite_response matches AND booked_call = N
        for key, regex in [("yesBookings", yes_re), ("maybeBookings", maybe_re)]:
            counts = await _group_count("""
                SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                  AND g.calendar_invite_response_history ~* :regex
                  AND g.booked_call_webinar_series = :N
                GROUP BY c.assignment_id
            """, regex=regex, N=N)
            for aid, cnt in counts.items():
                if aid in out:
                    out[aid][key] = cnt

        # selfRegMarked / selfRegBookings — Webinar_Registration_in_form_date window
        if prev_date and current_date:
            counts = await _group_count("""
                SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                  AND g.webinar_registration_in_form_date >= :start
                  AND g.webinar_registration_in_form_date < :end
                GROUP BY c.assignment_id
            """, start=prev_date, end=current_date)
            for aid, cnt in counts.items():
                if aid in out:
                    out[aid]["selfRegMarked"] = cnt
                    out[aid]["lpRegs"] = cnt  # same formula per user

            counts = await _group_count("""
                SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                  AND g.webinar_registration_in_form_date >= :start
                  AND g.webinar_registration_in_form_date < :end
                  AND g.booked_call_webinar_series = :N
                GROUP BY c.assignment_id
            """, start=prev_date, end=current_date, N=N)
            for aid, cnt in counts.items():
                if aid in out:
                    out[aid]["selfRegBookings"] = cnt

            counts = await _group_count("""
                SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                  AND g.cold_calendar_unsubscribe_date >= :start
                  AND g.cold_calendar_unsubscribe_date < :end
                GROUP BY c.assignment_id
            """, start=prev_date, end=current_date)
            for aid, cnt in counts.items():
                if aid in out:
                    out[aid]["unsubscribes"] = cnt

        # totalBookings per list — UNION of (opps with webinar_source_number = N)
        # + (opps whose contact has booked_call_webinar_series = N). Matches
        # the webinar-level union since the opp-level field is often empty.
        counts = await _group_count("""
            SELECT c.assignment_id, COUNT(DISTINCT o.ghl_opportunity_id)
            FROM contacts c
            JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
            JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
            JOIN ghl_opportunity o ON o.ghl_contact_id = g.ghl_contact_id
            WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
              AND (o.webinar_source_number = :N OR g.booked_call_webinar_series = :N)
            GROUP BY c.assignment_id
        """, N=N)
        for aid, cnt in counts.items():
            if aid in out:
                out[aid]["totalBookings"] = cnt

        # Attendance metrics — need broadcast_id + WebinarGeek subscribers
        if broadcast_id:
            counts = await _group_count("""
                SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN webinargeek_subscribers wgs ON LOWER(wgs.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                  AND wgs.broadcast_id = :bid
                GROUP BY c.assignment_id
            """, bid=broadcast_id)
            for aid, cnt in counts.items():
                if aid in out:
                    out[aid]["totalRegs"] = cnt

            # totalAttended — watched_live OR minutes_viewing > 0
            counts = await _group_count("""
                SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                FROM contacts c
                JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                JOIN webinargeek_subscribers wgs ON LOWER(wgs.email) = LOWER(c.email)
                WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                  AND wgs.broadcast_id = :bid
                  AND (wgs.watched_live = TRUE OR wgs.minutes_viewing > 0)
                GROUP BY c.assignment_id
            """, bid=broadcast_id)
            for aid, cnt in counts.items():
                if aid in out:
                    out[aid]["totalAttended"] = cnt

            for key, min_minutes in [("total10MinPlus", 10), ("total30MinPlus", 30)]:
                counts = await _group_count("""
                    SELECT c.assignment_id, COUNT(DISTINCT LOWER(c.email))
                    FROM contacts c
                    JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
                    JOIN webinargeek_subscribers wgs ON LOWER(wgs.email) = LOWER(c.email)
                    WHERE wla.webinar_id = CAST(:webinar_id AS uuid)
                      AND wgs.broadcast_id = :bid
                      AND (wgs.watched_live = TRUE OR wgs.minutes_viewing > 0)
                      AND wgs.minutes_viewing >= :mm
                    GROUP BY c.assignment_id
                """, bid=broadcast_id, mm=min_minutes)
                for aid, cnt in counts.items():
                    if aid in out:
                        out[aid][key] = cnt

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
            "listSize": sum((a.volume or 0) for a in assignments),
            "listRemain": sum((a.remaining or 0) for a in assignments),
            "gcalInvited": sum((a.gcal_invited or 0) for a in assignments),
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
        N = w.number
        broadcast_id = w.broadcast_id
        metrics: dict[str, float | None] = {}

        # --- Base (from app) ---
        base = await _webinar_summary_from_app(db, w.id)
        metrics.update(base)

        # --- gcalInvitedGhl: read from ghl_webinar_stats cache (populated during sync) ---
        # We don't sync the 200k contacts whose calendar_webinar_series_history
        # contains eN by default — just record the count during the sync.
        r = await db.execute(
            select(GHLWebinarStats.gcal_invited_count)
            .where(GHLWebinarStats.webinar_number == N)
        )
        metrics["gcalInvitedGhl"] = r.scalar()

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
            self_reg_marked = int(r.scalar() or 0)
            metrics["selfRegMarked"] = self_reg_marked
            # Per user: lpRegs uses the same formula as selfRegMarked.
            metrics["lpRegs"] = self_reg_marked

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

        # --- Sales ---
        # Load opps two ways:
        #   (a) opportunities with webinar_source_number = N (primary signal)
        #   (b) opportunities whose contact has booked_call_webinar_series = N
        #       (fallback when the opp-level field isn't populated — common in
        #        this location, so treat the contact field as authoritative)
        r = await db.execute(
            select(GHLOpportunity).where(GHLOpportunity.webinar_source_number == N)
        )
        opps_primary = list(r.scalars().all())

        r = await db.execute(
            select(GHLOpportunity)
            .join(GHLContact, GHLContact.ghl_contact_id == GHLOpportunity.ghl_contact_id)
            .where(GHLContact.booked_call_webinar_series == N)
        )
        opps_fallback = list(r.scalars().all())

        # Union by ghl_opportunity_id
        seen_ids: set[str] = set()
        opps: list[GHLOpportunity] = []
        for o in (*opps_primary, *opps_fallback):
            if o.ghl_opportunity_id in seen_ids:
                continue
            seen_ids.add(o.ghl_opportunity_id)
            opps.append(o)
        n_opps = len(opps)

        def cnt(pred) -> int:
            return sum(1 for o in opps if pred(o))

        metrics["totalBookings"] = n_opps
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
        # lpRegs is populated above when prev_date/current_date exist.
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
