"""Metric filter specs shared between the Statistics dashboard counts and
the per-metric contacts drill-down endpoint.

Each metric maps to a set of SQL WHERE clauses (and optional extra JOINs)
applied against a base query that filters to contacts belonging to a
specific webinar (via contacts.assignment_id -> webinar_list_assignments).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# Known opportunity pipeline stages
DEAL_WON_STAGE_ID = "544b178f-d1f2-4186-a8c2-00c3b0eeefe8"
DISQUALIFIED_STAGE_ID = "62448525-88ab-4e82-b414-b6880e69e2de"
QUALIFIED_LEAD_QUALITIES = ("Great", "Ok", "Barely Passable")


@dataclass
class MetricSpec:
    """Filter spec for one metric.

    The base query for any metric is:
        SELECT ...
        FROM contacts c
        JOIN webinar_list_assignments wla ON c.assignment_id = wla.id
        JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)
        [+ wgs join if needs_wg]
        [+ opp join if needs_opp]
        WHERE wla.webinar_id = :wid
          AND [assignment filter if any]
          AND [all where_clauses joined by AND]

    `params` are bind parameters for the SQL.
    """
    where_clauses: list[str] = field(default_factory=list)
    needs_wg: bool = False
    needs_opp: bool = False
    # What to count / return: "contact" (default) or "opportunity"
    unit: str = "contact"
    params: dict[str, Any] = field(default_factory=dict)
    # If True, this metric is unavailable for the given inputs (e.g. no broadcast_id)
    unavailable: bool = False


def _yes_re(n: int) -> str:
    return rf"\ye{n}-Yes\y"


def _maybe_re(n: int) -> str:
    return rf"\ye{n}-Maybe\y"


def _series_re(n: int) -> str:
    return rf"\ye{n}\y"


ATT_PREDICATE = "(wgs.watched_live = TRUE OR wgs.minutes_viewing > 0)"


def spec_for_metric(
    metric: str,
    webinar_number: int,
    broadcast_id: str | None = None,
    prev_date: date | None = None,
    current_date: date | None = None,
) -> MetricSpec | None:
    """Return the MetricSpec for a given metric key. None if the metric is
    not supported for drill-down (e.g. pure derived ratios like percentages)."""
    N = webinar_number
    yes_re = _yes_re(N)
    maybe_re = _maybe_re(N)
    series_re = _series_re(N)

    # ── Raw counts ─────────────────────────────────────────────────────
    if metric == "gcalInvitedGhl":
        return MetricSpec(
            where_clauses=["g.calendar_webinar_series_history ~* :gcal_re"],
            params={"gcal_re": series_re},
        )
    if metric == "yesMarked":
        return MetricSpec(
            where_clauses=["g.calendar_invite_response_history ~* :yes_re"],
            params={"yes_re": yes_re},
        )
    if metric == "maybeMarked":
        return MetricSpec(
            where_clauses=["g.calendar_invite_response_history ~* :maybe_re"],
            params={"maybe_re": maybe_re},
        )
    if metric in ("yesBookings", "maybeBookings"):
        re_key = "yes_re" if metric == "yesBookings" else "maybe_re"
        return MetricSpec(
            where_clauses=[
                f"g.calendar_invite_response_history ~* :{re_key}",
                "g.booked_call_webinar_series = :N",
            ],
            params={re_key: yes_re if metric == "yesBookings" else maybe_re, "N": N},
        )
    if metric in ("selfRegMarked", "lpRegs"):
        if not (prev_date and current_date):
            return MetricSpec(unavailable=True)
        return MetricSpec(
            where_clauses=[
                "g.webinar_registration_in_form_date >= :sr_start",
                "g.webinar_registration_in_form_date < :sr_end",
            ],
            params={"sr_start": prev_date, "sr_end": current_date},
        )
    if metric == "selfRegBookings":
        if not (prev_date and current_date):
            return MetricSpec(unavailable=True)
        return MetricSpec(
            where_clauses=[
                "g.webinar_registration_in_form_date >= :sr_start",
                "g.webinar_registration_in_form_date < :sr_end",
                "g.booked_call_webinar_series = :N",
            ],
            params={"sr_start": prev_date, "sr_end": current_date, "N": N},
        )
    if metric == "unsubscribes":
        if not (prev_date and current_date):
            return MetricSpec(unavailable=True)
        return MetricSpec(
            where_clauses=[
                "g.cold_calendar_unsubscribe_date >= :unsub_start",
                "g.cold_calendar_unsubscribe_date < :unsub_end",
            ],
            params={"unsub_start": prev_date, "unsub_end": current_date},
        )

    # ── WG attendance metrics ─────────────────────────────────────────
    if metric.startswith(("totalAttended", "total10MinPlus", "total30MinPlus",
                         "totalRegs", "attendBySmsReminder",
                         "yesAttended", "yes10MinPlus", "yesAttendBySmsClick",
                         "maybeAttended", "maybe10MinPlus", "maybeAttendBySmsClick",
                         "selfRegAttended", "selfReg10MinPlus")):
        if not broadcast_id:
            return MetricSpec(unavailable=True)
        wheres = ["wgs.broadcast_id = :bid"]
        params: dict[str, Any] = {"bid": broadcast_id}
        # Total regs has no attendance requirement
        if metric != "totalRegs":
            wheres.append(ATT_PREDICATE)
        # Response-split
        if metric.startswith("yes"):
            wheres.append("g.calendar_invite_response_history ~* :yes_re")
            params["yes_re"] = yes_re
        elif metric.startswith("maybe"):
            wheres.append("g.calendar_invite_response_history ~* :maybe_re")
            params["maybe_re"] = maybe_re
        elif metric.startswith("selfReg"):
            if not (prev_date and current_date):
                return MetricSpec(unavailable=True)
            wheres.append("g.webinar_registration_in_form_date >= :sr_start")
            wheres.append("g.webinar_registration_in_form_date < :sr_end")
            params["sr_start"] = prev_date
            params["sr_end"] = current_date
        # Min-minutes filter
        if "10MinPlus" in metric:
            wheres.append("wgs.minutes_viewing >= 10")
        elif "30MinPlus" in metric:
            wheres.append("wgs.minutes_viewing >= 30")
        # SMS filters
        if metric in ("attendBySmsReminder", "yesAttendBySmsClick", "maybeAttendBySmsClick"):
            wheres.append("g.has_sms_click_tag = TRUE")
        return MetricSpec(where_clauses=wheres, needs_wg=True, params=params)

    # ── Opportunity-based sales / quality metrics ─────────────────────
    # All use UNION condition: opp.webinar_source_number=N OR contact.booked_call=N
    base_opp = "(o.webinar_source_number = :N OR g.booked_call_webinar_series = :N)"

    def opp_spec(extra_where: str, extra_params: dict | None = None) -> MetricSpec:
        return MetricSpec(
            where_clauses=[base_opp, extra_where],
            needs_opp=True,
            unit="opportunity",
            params={"N": N, **(extra_params or {})},
        )

    if metric == "totalBookings":
        return opp_spec("TRUE")
    if metric == "totalCallsDatePassed":
        return opp_spec(
            "o.call1_appointment_date IS NOT NULL AND o.call1_appointment_date <= NOW()"
        )
    if metric == "confirmed":
        return opp_spec("LOWER(COALESCE(o.call1_appointment_status, '')) = 'confirmed'")
    if metric == "shows":
        return opp_spec("LOWER(COALESCE(o.call1_appointment_status, '')) = 'showed'")
    if metric == "noShows":
        return opp_spec("LOWER(COALESCE(o.call1_appointment_status, '')) IN ('noshow','no show','no-show')")
    if metric == "canceled":
        return opp_spec("LOWER(COALESCE(o.call1_appointment_status, '')) = 'cancelled'")
    if metric == "won":
        return opp_spec(f"o.pipeline_stage_id = '{DEAL_WON_STAGE_ID}'")
    if metric == "disqualified":
        return opp_spec(f"o.pipeline_stage_id = '{DISQUALIFIED_STAGE_ID}'")
    if metric == "qualified":
        quals = "','".join(QUALIFIED_LEAD_QUALITIES)
        return opp_spec(
            f"LOWER(COALESCE(o.call1_appointment_status, '')) = 'showed' AND o.lead_quality IN ('{quals}')"
        )
    if metric == "leadQualityGreat":
        return opp_spec("o.lead_quality = 'Great'")
    if metric == "leadQualityOk":
        return opp_spec("o.lead_quality = 'Ok'")
    if metric == "leadQualityBarelyPassable":
        return opp_spec("o.lead_quality = 'Barely Passable'")
    if metric == "leadQualityBadDq":
        return opp_spec("o.lead_quality = 'Bad / DQ'")

    # Unknown / derived metric
    return None


def build_contacts_query(
    spec: MetricSpec,
    webinar_id: str,
    assignment_id: str | None = None,
    limit: int = 500,
) -> tuple[str, dict[str, Any]]:
    """Build the SELECT query that returns contact/opportunity rows matching the spec.

    Returns (sql, params).
    """
    joins = ["JOIN webinar_list_assignments wla ON c.assignment_id = wla.id",
             "JOIN ghl_contact g ON LOWER(g.email) = LOWER(c.email)"]
    if spec.needs_wg:
        joins.append("LEFT JOIN webinargeek_subscribers wgs ON LOWER(wgs.email) = LOWER(c.email)")
    if spec.needs_opp:
        joins.append("JOIN ghl_opportunity o ON o.ghl_contact_id = g.ghl_contact_id")

    wheres = ["wla.webinar_id = CAST(:webinar_id AS uuid)"]
    wheres.extend(f"({w})" for w in spec.where_clauses)

    params = {"webinar_id": webinar_id, "limit": limit, **spec.params}
    if assignment_id:
        wheres.append("c.assignment_id = CAST(:assignment_id AS uuid)")
        params["assignment_id"] = assignment_id

    # Select distinct contact info + optional opp info
    if spec.unit == "opportunity":
        select = """
            DISTINCT
            o.ghl_opportunity_id AS opportunity_id,
            o.pipeline_stage_id,
            o.monetary_value,
            o.call1_appointment_status,
            o.call1_appointment_date,
            o.lead_quality,
            o.webinar_source_number,
            g.ghl_contact_id,
            g.email,
            c.first_name,
            c.last_name,
            c.company_website,
            c.assignment_id
        """
    else:
        select = """
            DISTINCT
            g.ghl_contact_id,
            g.email,
            c.first_name,
            c.last_name,
            c.company_website,
            c.assignment_id
        """

    sql = f"""
        SELECT {select}
        FROM contacts c
        {' '.join(joins)}
        WHERE {' AND '.join(wheres)}
        ORDER BY g.email
        LIMIT :limit
    """
    return sql, params
