"""
Statistics service — loads workbook fixture, computes derived metrics, aggregates parents.

v1 uses a static JSON fixture (WorkbookMockStatisticsSource).
Later GoHighLevel integration swaps only the source behind the same interface.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Source adapter protocol
# ---------------------------------------------------------------------------

class StatisticsSource(Protocol):
    async def get_raw_webinars(self) -> list[dict[str, Any]]: ...


class WorkbookMockStatisticsSource:
    """Loads from api/data/statistics_workbook_snapshot.json (cached in memory)."""

    _cache: list[dict[str, Any]] | None = None

    async def get_raw_webinars(self) -> list[dict[str, Any]]:
        if self._cache is None:
            fixture_path = (
                Path(__file__).resolve().parent.parent
                / "api"
                / "data"
                / "statistics_workbook_snapshot.json"
            )
            with open(fixture_path) as f:
                data = json.load(f)
            self._cache = data["webinars"]
        return self._cache


# ---------------------------------------------------------------------------
# Derived metric computation
# ---------------------------------------------------------------------------

def _safe_div(a: float | None, b: float | None) -> float | None:
    """a / b, returning None on null inputs or zero denominator."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _safe_per1k(a: float | None, b: float | None) -> float | None:
    """a / (b / 1000), returning None on null inputs or zero denominator."""
    if a is None or b is None or b == 0:
        return None
    return a / (b / 1000)


def compute_derived_metrics(m: dict[str, float | None]) -> dict[str, float | None]:
    """Compute all derived fields from raw metrics. Zero-division → None."""
    inv = m.get("invited")

    derived: dict[str, float | None] = {
        # Pass through all raw fields
        **m,
        # Delivery
        "unsubPercent": _safe_div(m.get("unsubscribes"), inv),
        "ctrPercent": _safe_div(m.get("ghlPageViews"), inv),
        "lpRegPercent": _safe_div(m.get("lpRegs"), m.get("ghlPageViews")),
        # Yes
        "yesPer1kInv": _safe_per1k(m.get("yesMarked"), inv),
        "yesPercent": _safe_div(m.get("yesMarked"), inv),
        "yesAttendPercent": _safe_div(m.get("yesAttended"), m.get("yesMarked")),
        "yesStay10MinPercent": _safe_div(m.get("yes10MinPlus"), m.get("yesAttended")),
        "yesAttendBySmsClickPercent": _safe_div(
            m.get("yesAttendBySmsClick"), m.get("yesAttended")
        ),
        "yesBookingsPer1kInv": _safe_per1k(m.get("yesBookings"), inv),
        # Maybe
        "maybePer1kInv": _safe_per1k(m.get("maybeMarked"), inv),
        "maybeAttendPercent": _safe_div(m.get("maybeAttended"), m.get("maybeMarked")),
        "maybeStay10MinPercent": _safe_div(
            m.get("maybe10MinPlus"), m.get("maybeAttended")
        ),
        "maybeAttendBySmsClickPercent": _safe_div(
            m.get("maybeAttendBySmsClick"), m.get("maybeAttended")
        ),
        "maybeBookingsPer1kInv": _safe_per1k(m.get("maybeBookings"), inv),
        # Self Reg
        "selfRegPer1kInv": _safe_per1k(m.get("selfRegMarked"), inv),
        "selfRegAttendPercent": _safe_div(
            m.get("selfRegAttended"), m.get("selfRegMarked")
        ),
        "selfRegStay10MinPercent": _safe_div(
            m.get("selfReg10MinPlus"), m.get("selfRegAttended")
        ),
        "selfRegBookingsPer1kInv": _safe_per1k(m.get("selfRegBookings"), inv),
        # Attendance
        "invitedToRegPercent": _safe_div(m.get("totalRegs"), inv),
        "regToAttendPercent": _safe_div(
            m.get("totalAttended"), m.get("totalRegs")
        ),
        "invitedToAttendPercent": _safe_div(m.get("totalAttended"), inv),
        "totalAttendedPer1kInv": _safe_per1k(m.get("totalAttended"), inv),
        "attendBySmsReminderPercent": _safe_div(
            m.get("attendBySmsReminder"), m.get("totalAttended")
        ),
        "total10MinPlusPer1kInv": _safe_per1k(m.get("total10MinPlus"), inv),
        "attend10MinPercent": _safe_div(
            m.get("total10MinPlus"), m.get("totalAttended")
        ),
        "total30MinPlusPer1kInv": _safe_per1k(m.get("total30MinPlus"), inv),
        "attend30MinPercent": _safe_div(
            m.get("total30MinPlus"), m.get("totalAttended")
        ),
        # Sales
        "bookingsPerAttended": _safe_div(
            m.get("totalBookings"), m.get("totalAttended")
        ),
        "bookingsPerPast10Min": _safe_div(
            m.get("totalBookings"), m.get("total10MinPlus")
        ),
        "totalBookingsPer1kInv": _safe_per1k(m.get("totalBookings"), inv),
        "showPercent": _safe_div(m.get("shows"), m.get("totalBookings")),
        "closeRatePercent": _safe_div(m.get("won"), m.get("shows")),
        "qualPercent": _safe_div(m.get("qualified"), m.get("shows")),
    }
    return derived


# ---------------------------------------------------------------------------
# Parent aggregation
# ---------------------------------------------------------------------------

# Keys that should be summed across children
_SUM_KEYS = [
    "listSize", "listRemain", "gcalInvited", "accountsNeeded",
    "invited", "unsubscribes", "ghlPageViews", "lpRegs",
    "yesMarked", "yesAttended", "yes10MinPlus", "yesAttendBySmsClick", "yesBookings",
    "maybeMarked", "maybeAttended", "maybe10MinPlus", "maybeAttendBySmsClick", "maybeBookings",
    "selfRegMarked", "selfRegAttended", "selfReg10MinPlus", "selfRegBookings",
    "totalRegs", "totalAttended", "attendBySmsReminder",
    "total10MinPlus", "total30MinPlus", "totalBookings",
    "totalCallsDatePassed", "confirmed", "shows", "noShows", "canceled",
    "won", "disqualified", "qualified",
    "leadQualityGreat", "leadQualityOk", "leadQualityBarelyPassable", "leadQualityBadDq",
]


def _sum_or_none(values: list[float | None]) -> float | None:
    """Sum non-None values. Returns None if all inputs are None."""
    nums = [v for v in values if v is not None]
    return sum(nums) if nums else None


def _avg_or_none(values: list[float | None]) -> float | None:
    """Average non-None values. Returns None if all inputs are None."""
    nums = [v for v in values if v is not None]
    return sum(nums) / len(nums) if nums else None


def aggregate_parent_summary(
    child_metrics_list: list[dict[str, float | None]],
) -> dict[str, float | None]:
    """
    Aggregate child raw metrics into a parent summary.

    Rules:
    - Most raw metrics: SUM across all children (including Nonjoiners + NO LIST DATA)
    - avgProjectedDealSize: AVERAGE of non-null child values
    - avgClosedDealValue: SUM of non-null child values
    - accountsNeeded: SUM (source-fed, not recomputed)
    """
    if not child_metrics_list:
        return {}

    agg: dict[str, float | None] = {}

    # Sum keys
    for key in _SUM_KEYS:
        agg[key] = _sum_or_none([m.get(key) for m in child_metrics_list])

    # Special aggregation rules
    agg["avgProjectedDealSize"] = _avg_or_none(
        [m.get("avgProjectedDealSize") for m in child_metrics_list]
    )
    agg["avgClosedDealValue"] = _sum_or_none(
        [m.get("avgClosedDealValue") for m in child_metrics_list]
    )

    return agg


# ---------------------------------------------------------------------------
# Segment name builder
# ---------------------------------------------------------------------------

def _build_segment_name(row: dict[str, Any]) -> str | None:
    """
    segmentName = format(createdDate, 'yyyy mmm dd') + ', ' + industry +
                  ', ' + employeeRange + ' employees, ' + country
    Returns None if any input is missing.
    """
    created = row.get("createdDate")
    industry = row.get("industry")
    emp_range = row.get("employeeRange")
    country = row.get("country")

    if not all([created, industry, emp_range, country]):
        return None

    try:
        dt = datetime.strptime(created, "%Y-%m-%d")
        date_str = dt.strftime("%Y %b %d")
    except (ValueError, TypeError):
        return None

    return f"{date_str}, {industry}, {emp_range} employees, {country}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_workbook_source: StatisticsSource = WorkbookMockStatisticsSource()


def _get_source(use_ghl: bool) -> StatisticsSource:
    if use_ghl:
        # Imported lazily so the workbook source still works if GHL deps missing
        from services.ghl_statistics_source import GoHighLevelStatisticsSource
        return GoHighLevelStatisticsSource()
    return _workbook_source


async def _has_ghl_data() -> bool:
    """Return True if at least one completed GHL sync has landed data in the DB."""
    try:
        from sqlalchemy import func, select
        from db.models import GHLSyncRun
        from db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(func.count(GHLSyncRun.id)).where(GHLSyncRun.status == "completed")
            )
            return int(r.scalar() or 0) > 0
    except Exception:
        return False


async def get_statistics_webinars(source: str = "auto") -> list[dict[str, Any]]:
    """Return fully processed statistics webinars with derived metrics.

    source: "auto" (use GHL if any completed sync, else workbook),
            "ghl", or "workbook".
    """
    if source == "workbook":
        use_ghl = False
    elif source == "ghl":
        use_ghl = True
    else:
        use_ghl = await _has_ghl_data()

    src = _get_source(use_ghl)
    raw_webinars = await src.get_raw_webinars()
    result: list[dict[str, Any]] = []

    for w in raw_webinars:
        processed_rows: list[dict[str, Any]] = []
        raw_metrics_for_agg: list[dict[str, float | None]] = []

        for row in w["rows"]:
            raw_m = row["metrics"]
            raw_metrics_for_agg.append(raw_m)
            derived = compute_derived_metrics(raw_m)
            processed_rows.append(
                {
                    **{k: v for k, v in row.items() if k != "metrics"},
                    "metrics": derived,
                    "segmentName": _build_segment_name(row),
                }
            )

        # Aggregate parent summary from raw child metrics, then derive
        agg_raw = aggregate_parent_summary(raw_metrics_for_agg)
        summary = compute_derived_metrics(agg_raw)

        result.append(
            {
                "id": f"stat-w{w['number']}",
                "number": w["number"],
                "date": w.get("date"),
                "title": w.get("title"),
                "workbookRow": w["workbookRow"],
                "source": "workbook_mock",
                "summary": summary,
                "rows": [
                    {
                        "id": f"stat-w{w['number']}-r{r['workbookRow']}",
                        "webinarNumber": w["number"],
                        **r,
                    }
                    for r in processed_rows
                ],
            }
        )

    return result
