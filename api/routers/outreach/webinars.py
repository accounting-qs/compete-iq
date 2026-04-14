"""Outreach sub-router: Webinars + Assignments CRUD + Account tracking."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func as sa_func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import require_auth
from api.routers.outreach._helpers import (
    LLOYD_USER_ID, webinar_dict, assignment_dict, copy_dict,
)
from api.schemas import WebinarCreate, WebinarUpdate, AssignRequest, AssignmentUpdate
from db.models import (
    OutreachBucket, OutreachSender, Webinar, WebinarListAssignment, CopyUsageLog,
)
from db.session import get_db

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# WEBINARS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/webinars")
async def list_webinars(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(Webinar).where(Webinar.user_id == LLOYD_USER_ID)
        .options(selectinload(Webinar.assignments))
        .order_by(Webinar.number.desc())
    )
    webinars = result.scalars().all()
    return {"webinars": [webinar_dict(w) for w in webinars]}


@router.post("/webinars", status_code=201)
async def create_webinar(
    body: WebinarCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    existing = await db.execute(
        select(Webinar).where(Webinar.user_id == LLOYD_USER_ID, Webinar.number == body.number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Webinar number {body.number} already exists")

    webinar = Webinar(
        user_id=LLOYD_USER_ID,
        number=body.number,
        date=body.date,
        status="planning",
    )
    db.add(webinar)
    await db.flush()
    await db.refresh(webinar)
    return webinar_dict(webinar)


@router.put("/webinars/{webinar_id}")
async def update_webinar(
    webinar_id: str,
    body: WebinarUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(Webinar).where(Webinar.id == webinar_id, Webinar.user_id == LLOYD_USER_ID)
    )
    webinar = result.scalar_one_or_none()
    if not webinar:
        raise HTTPException(404, "Webinar not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(webinar, field, val)
    await db.flush()
    return webinar_dict(webinar)


# ═══════════════════════════════════════════════════════════════════════════
# WEBINAR ASSIGNMENTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/webinars/{webinar_id}/lists")
async def get_webinar_lists(
    webinar_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(WebinarListAssignment).where(
            WebinarListAssignment.webinar_id == webinar_id,
            WebinarListAssignment.user_id == LLOYD_USER_ID,
        )
        .options(
            selectinload(WebinarListAssignment.bucket),
            selectinload(WebinarListAssignment.sender),
            selectinload(WebinarListAssignment.title_copy),
            selectinload(WebinarListAssignment.desc_copy),
        )
        .order_by(WebinarListAssignment.display_order, WebinarListAssignment.created_at)
    )
    assignments = result.scalars().all()
    return {"assignments": [assignment_dict(a) for a in assignments]}


@router.post("/webinars/{webinar_id}/assign", status_code=201)
async def assign_bucket(
    webinar_id: str,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    # Validate webinar
    w_result = await db.execute(
        select(Webinar).where(Webinar.id == webinar_id, Webinar.user_id == LLOYD_USER_ID)
    )
    webinar = w_result.scalar_one_or_none()
    if not webinar:
        raise HTTPException(404, "Webinar not found")

    # Validate bucket
    b_result = await db.execute(
        select(OutreachBucket).where(OutreachBucket.id == body.bucket_id, OutreachBucket.user_id == LLOYD_USER_ID)
        .options(selectinload(OutreachBucket.copies))
    )
    bucket = b_result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(404, "Bucket not found")

    if bucket.remaining_contacts < body.volume:
        raise HTTPException(400, f"Volume {body.volume} exceeds bucket remaining {bucket.remaining_contacts}")

    # Validate sender
    s_result = await db.execute(
        select(OutreachSender).where(OutreachSender.id == body.sender_id, OutreachSender.user_id == LLOYD_USER_ID)
    )
    sender = s_result.scalar_one_or_none()
    if not sender:
        raise HTTPException(404, "Sender not found")

    # Find primary copies for this bucket
    title_copy = next((c for c in (bucket.copies or []) if c.copy_type == "title" and c.is_primary and not c.deleted_at), None)
    desc_copy = next((c for c in (bucket.copies or []) if c.copy_type == "description" and c.is_primary and not c.deleted_at), None)

    # Build description string
    countries = body.countries_override or ", ".join(bucket.countries or [])
    emp = body.emp_range_override or bucket.emp_range or ""
    desc_str = f"{bucket.name}, {emp} emp, {countries}"

    # Get next display order
    max_order_result = await db.execute(
        select(sa_func.max(WebinarListAssignment.display_order)).where(
            WebinarListAssignment.webinar_id == webinar_id
        )
    )
    next_order = (max_order_result.scalar() or 0) + 1

    # Create assignment
    assignment = WebinarListAssignment(
        user_id=LLOYD_USER_ID,
        webinar_id=webinar_id,
        bucket_id=body.bucket_id,
        sender_id=body.sender_id,
        description=desc_str,
        volume=body.volume,
        remaining=body.volume,
        accounts_used=body.accounts_used,
        send_per_account=body.send_per_account,
        days=body.days,
        title_copy_id=title_copy.id if title_copy else None,
        desc_copy_id=desc_copy.id if desc_copy else None,
        countries_override=body.countries_override,
        emp_range_override=body.emp_range_override,
        display_order=next_order,
    )
    db.add(assignment)

    # Decrement bucket remaining
    bucket.remaining_contacts -= body.volume

    # Log copy usage
    if title_copy:
        db.add(CopyUsageLog(bucket_copy_id=title_copy.id, assignment_id=assignment.id))
    if desc_copy:
        db.add(CopyUsageLog(bucket_copy_id=desc_copy.id, assignment_id=assignment.id))

    await db.flush()

    # Reload with relationships
    await db.refresh(assignment)
    reload_result = await db.execute(
        select(WebinarListAssignment).where(WebinarListAssignment.id == assignment.id)
        .options(
            selectinload(WebinarListAssignment.bucket),
            selectinload(WebinarListAssignment.sender),
            selectinload(WebinarListAssignment.title_copy),
            selectinload(WebinarListAssignment.desc_copy),
        )
    )
    assignment = reload_result.scalar_one()
    return assignment_dict(assignment)


@router.put("/assignments/{assignment_id}")
async def update_assignment(
    assignment_id: str,
    body: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(WebinarListAssignment).where(
            WebinarListAssignment.id == assignment_id,
            WebinarListAssignment.user_id == LLOYD_USER_ID,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(assignment, field, val)
    await db.flush()
    return assignment_dict(assignment)


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(WebinarListAssignment).where(
            WebinarListAssignment.id == assignment_id,
            WebinarListAssignment.user_id == LLOYD_USER_ID,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Assignment not found")

    # Restore bucket remaining
    if assignment.bucket_id:
        b_result = await db.execute(select(OutreachBucket).where(OutreachBucket.id == assignment.bucket_id))
        bucket = b_result.scalar_one_or_none()
        if bucket:
            bucket.remaining_contacts += assignment.volume

    # Delete usage logs
    await db.execute(
        delete(CopyUsageLog).where(CopyUsageLog.assignment_id == assignment_id)
    )

    await db.delete(assignment)
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# ACCOUNT TRACKING
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/webinars/{webinar_id}/accounts")
async def get_webinar_accounts(
    webinar_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    senders_result = await db.execute(
        select(OutreachSender).where(
            OutreachSender.user_id == LLOYD_USER_ID,
            OutreachSender.is_active.is_(True),
        )
    )
    senders = senders_result.scalars().all()

    usage_result = await db.execute(
        select(
            WebinarListAssignment.sender_id,
            sa_func.coalesce(sa_func.sum(WebinarListAssignment.accounts_used), 0).label("used"),
        ).where(
            WebinarListAssignment.webinar_id == webinar_id,
        ).group_by(WebinarListAssignment.sender_id)
    )
    usage_map = {row.sender_id: row.used for row in usage_result}

    return {
        "senders": [
            {
                "sender_id": s.id,
                "sender_name": s.name,
                "total_accounts": s.total_accounts,
                "accounts_used": usage_map.get(s.id, 0),
                "accounts_available": s.total_accounts - usage_map.get(s.id, 0),
            }
            for s in senders
        ]
    }
