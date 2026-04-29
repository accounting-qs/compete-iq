"""
Statistics router — read-only dashboard data from workbook fixture.
All routes require bearer auth.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
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
    actuallyUsed: float | None = None
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


class StatisticsCopy(BaseModel):
    id: str
    text: str
    variantIndex: int


class ApiStatisticsRow(BaseModel):
    id: str
    webinarNumber: int
    workbookRow: int
    assignmentId: str | None = None
    kind: str  # "list" | "nonjoiners" | "no_list_data"
    status: str | None = None
    note: str | None = None
    listUrl: str | None = None
    description: str | None = None
    listName: str | None = None
    sendInfo: str | None = None
    senderColor: str | None = None
    bucketId: str | None = None
    bucketName: str | None = None
    descLabel: str | None = None
    titleText: str | None = None
    titleCopy: StatisticsCopy | None = None
    descCopy: StatisticsCopy | None = None
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


class ApiStatisticsWebinarSummary(BaseModel):
    """Lightweight webinar identity used by the progressive-load list."""
    id: str
    number: int
    date: str | None = None
    title: str | None = None
    status: str | None = None
    listCount: int = 0
    broadcastId: str | None = None


class StatisticsListResponse(BaseModel):
    webinars: list[ApiStatisticsWebinarSummary]
    meta: StatisticsMetaResponse


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class ContactDrilldownItem(BaseModel):
    ghl_contact_id: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    company_website: str | None = None
    assignment_id: str | None = None
    ghl_url: str
    # When metric unit is "opportunity"
    opportunity_id: str | None = None
    opportunity_url: str | None = None
    opportunity_stage_id: str | None = None
    opportunity_value: float | None = None
    call1_status: str | None = None
    call1_date: str | None = None
    lead_quality: str | None = None


class ContactDrilldownResponse(BaseModel):
    metric: str
    webinar_number: int
    assignment_id: str | None = None
    unit: str  # "contact" | "opportunity"
    total: int
    items: list[ContactDrilldownItem]
    available: bool
    reason: str | None = None


@router.get("/contacts", response_model=ContactDrilldownResponse)
async def list_contacts_for_metric(
    webinar: int,
    metric: str,
    assignment: str | None = None,
    limit: int = 500,
):
    """Return contacts (or opportunities) behind a specific metric on the
    Statistics dashboard. Each item has a GHL deep-link for opening the
    contact / opportunity in a new tab."""
    from config import settings
    from datetime import date, timedelta
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession
    from db.models import Webinar as WebinarModel
    from db.session import AsyncSessionLocal
    from services.statistics_metric_filters import spec_for_metric, build_contacts_query

    async with AsyncSessionLocal() as db:
        # Resolve webinar
        r = await db.execute(select(WebinarModel).where(WebinarModel.number == webinar))
        w = r.scalar_one_or_none()
        if w is None:
            return {
                "metric": metric, "webinar_number": webinar, "assignment_id": assignment,
                "unit": "contact", "total": 0, "items": [],
                "available": False, "reason": f"Webinar {webinar} not found",
            }

        # Compute prev_date (mirrors the source: 30-day fallback when no prior webinar)
        prev_r = await db.execute(
            select(WebinarModel).where(WebinarModel.number < webinar).order_by(WebinarModel.number.desc()).limit(1)
        )
        prev_w = prev_r.scalar_one_or_none()
        prev_date = prev_w.date if prev_w else None
        current_date = w.date
        if prev_date is None and current_date is not None:
            prev_date = current_date - timedelta(days=30)

        spec = spec_for_metric(
            metric, webinar, broadcast_id=w.broadcast_id,
            prev_date=prev_date, current_date=current_date,
        )
        if spec is None:
            return {
                "metric": metric, "webinar_number": webinar, "assignment_id": assignment,
                "unit": "contact", "total": 0, "items": [],
                "available": False, "reason": f"Metric '{metric}' not supported for drill-down",
            }
        if spec.unavailable:
            return {
                "metric": metric, "webinar_number": webinar, "assignment_id": assignment,
                "unit": spec.unit, "total": 0, "items": [],
                "available": False,
                "reason": "Required data missing (broadcast not linked or no prior webinar for date window)",
            }

        sql, params = build_contacts_query(spec, w.id, assignment_id=assignment, limit=limit)
        r = await db.execute(text(sql).bindparams(**params))
        rows = r.mappings().all()

        from integrations.ghl_client import get_ghl_location_id
        loc = (await get_ghl_location_id()) or ""
        items: list[dict] = []
        for row in rows:
            contact_id = row.get("ghl_contact_id")
            opportunity_id = row.get("opportunity_id") if spec.unit == "opportunity" else None
            item = {
                "ghl_contact_id": contact_id,
                "email": row.get("email"),
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "company_website": row.get("company_website"),
                "assignment_id": str(row.get("assignment_id")) if row.get("assignment_id") else None,
                "ghl_url": f"https://app.gohighlevel.com/v2/location/{loc}/contacts/detail/{contact_id}" if contact_id else "",
            }
            if opportunity_id:
                item.update({
                    "opportunity_id": opportunity_id,
                    "opportunity_url": f"https://app.gohighlevel.com/v2/location/{loc}/opportunities/list?opp={opportunity_id}",
                    "opportunity_stage_id": row.get("pipeline_stage_id"),
                    "opportunity_value": float(row["monetary_value"]) if row.get("monetary_value") is not None else None,
                    "call1_status": row.get("call1_appointment_status"),
                    "call1_date": row["call1_appointment_date"].isoformat() if row.get("call1_appointment_date") else None,
                    "lead_quality": row.get("lead_quality"),
                })
            items.append(item)

        return {
            "metric": metric,
            "webinar_number": webinar,
            "assignment_id": assignment,
            "unit": spec.unit,
            "total": len(items),
            "items": items,
            "available": True,
            "reason": None,
        }


async def _resolve_meta(source: str) -> dict:
    used = "workbook" if source == "workbook" else "ghl"
    last_sync = None
    if used == "ghl":
        from services.ghl_statistics_source import get_last_sync_summary
        last_sync = await get_last_sync_summary()
    return {"source": used, "last_sync": last_sync}


@router.get("/webinars", response_model=StatisticsResponse)
async def list_statistics_webinars(source: str = "auto"):
    """Return all statistics webinars with derived metrics.

    Heavy: computes metrics for every webinar. Prefer the split
    `/webinars/list` + `/webinars/{number}` flow for the dashboard.
    """
    webinars = await stats_svc.get_statistics_webinars(source=source)
    meta = await _resolve_meta(source)
    return {"webinars": webinars, "meta": meta}


@router.get("/webinars/list", response_model=StatisticsListResponse)
async def list_statistics_webinar_summaries(source: str = "auto"):
    """Lightweight identity-only list. The dashboard renders parent rows
    immediately from this and then fetches per-webinar metrics in priority
    order via `/webinars/{number}`."""
    webinars = await stats_svc.get_statistics_webinar_list(source=source)
    meta = await _resolve_meta(source)
    return {"webinars": webinars, "meta": meta}


@router.get("/webinars/{number}", response_model=ApiStatisticsWebinar)
async def get_statistics_webinar(number: int, source: str = "auto"):
    """Fully-processed single webinar by number."""
    webinar = await stats_svc.get_statistics_webinar_one(source=source, number=number)
    if webinar is None:
        raise HTTPException(status_code=404, detail=f"Webinar {number} not found")
    return webinar
