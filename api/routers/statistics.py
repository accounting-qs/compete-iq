"""
Statistics router — read-only dashboard data from workbook fixture.
All routes require bearer auth.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import require_auth
from services import statistics as stats_svc

router = APIRouter(dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StatisticsMetrics(BaseModel):
    # Raw source fields
    listSize: float | None = None
    listRemain: float | None = None
    gcalInvited: float | None = None
    gcalInvitedGhl: float | None = None
    accountsNeeded: float | None = None
    invited: float | None = None
    unsubscribes: float | None = None
    ghlPageViews: float | None = None
    lpRegs: float | None = None
    yesMarked: float | None = None
    yesAttended: float | None = None
    yes10MinPlus: float | None = None
    yesAttendBySmsClick: float | None = None
    yesBookings: float | None = None
    maybeMarked: float | None = None
    maybeAttended: float | None = None
    maybe10MinPlus: float | None = None
    maybeAttendBySmsClick: float | None = None
    maybeBookings: float | None = None
    selfRegMarked: float | None = None
    selfRegAttended: float | None = None
    selfReg10MinPlus: float | None = None
    selfRegBookings: float | None = None
    totalRegs: float | None = None
    totalAttended: float | None = None
    attendBySmsReminder: float | None = None
    total10MinPlus: float | None = None
    total30MinPlus: float | None = None
    totalBookings: float | None = None
    totalCallsDatePassed: float | None = None
    confirmed: float | None = None
    shows: float | None = None
    noShows: float | None = None
    canceled: float | None = None
    won: float | None = None
    disqualified: float | None = None
    qualified: float | None = None
    leadQualityGreat: float | None = None
    leadQualityOk: float | None = None
    leadQualityBarelyPassable: float | None = None
    leadQualityBadDq: float | None = None
    avgProjectedDealSize: float | None = None
    avgClosedDealValue: float | None = None

    # Derived fields
    unsubPercent: float | None = None
    ctrPercent: float | None = None
    lpRegPercent: float | None = None
    yesPer1kInv: float | None = None
    yesPercent: float | None = None
    yesAttendPercent: float | None = None
    yesStay10MinPercent: float | None = None
    yesAttendBySmsClickPercent: float | None = None
    yesBookingsPer1kInv: float | None = None
    maybePer1kInv: float | None = None
    maybeAttendPercent: float | None = None
    maybeStay10MinPercent: float | None = None
    maybeAttendBySmsClickPercent: float | None = None
    maybeBookingsPer1kInv: float | None = None
    selfRegPer1kInv: float | None = None
    selfRegAttendPercent: float | None = None
    selfRegStay10MinPercent: float | None = None
    selfRegBookingsPer1kInv: float | None = None
    invitedToRegPercent: float | None = None
    regToAttendPercent: float | None = None
    invitedToAttendPercent: float | None = None
    totalAttendedPer1kInv: float | None = None
    attendBySmsReminderPercent: float | None = None
    total10MinPlusPer1kInv: float | None = None
    attend10MinPercent: float | None = None
    total30MinPlusPer1kInv: float | None = None
    attend30MinPercent: float | None = None
    bookingsPerAttended: float | None = None
    bookingsPerPast10Min: float | None = None
    totalBookingsPer1kInv: float | None = None
    showPercent: float | None = None
    closeRatePercent: float | None = None
    qualPercent: float | None = None


class ApiStatisticsRow(BaseModel):
    id: str
    webinarNumber: int
    workbookRow: int
    kind: str  # "list" | "nonjoiners" | "no_list_data"
    status: str | None = None
    note: str | None = None
    listUrl: str | None = None
    description: str | None = None
    sendInfo: str | None = None
    descLabel: str | None = None
    titleText: str | None = None
    segmentName: str | None = None
    createdDate: str | None = None
    industry: str | None = None
    employeeRange: str | None = None
    country: str | None = None
    metrics: StatisticsMetrics


class ApiStatisticsWebinar(BaseModel):
    id: str
    number: int
    date: str | None = None
    title: str | None = None
    workbookRow: int
    source: str  # "workbook_mock"
    summary: StatisticsMetrics
    rows: list[ApiStatisticsRow]


class StatisticsMetaResponse(BaseModel):
    source: str  # "ghl" | "workbook"
    last_sync: dict | None = None


class StatisticsResponse(BaseModel):
    webinars: list[ApiStatisticsWebinar]
    meta: StatisticsMetaResponse


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/webinars", response_model=StatisticsResponse)
async def list_statistics_webinars(source: str = "auto"):
    """Return all statistics webinars with derived metrics.

    source: "auto" (default), "ghl", or "workbook".
    """
    webinars = await stats_svc.get_statistics_webinars(source=source)

    # Resolve which source was actually used for the UI badge
    if source == "workbook":
        used = "workbook"
    elif source == "ghl":
        used = "ghl"
    else:
        used = "ghl" if await stats_svc._has_ghl_data() else "workbook"

    last_sync = None
    if used == "ghl":
        from services.ghl_statistics_source import get_last_sync_summary
        last_sync = await get_last_sync_summary()

    return {
        "webinars": webinars,
        "meta": {"source": used, "last_sync": last_sync},
    }
