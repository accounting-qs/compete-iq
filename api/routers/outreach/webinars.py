"""Outreach sub-router: Webinars + Assignments CRUD + Account tracking."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import require_auth
from api.routers.outreach._helpers import (
    LLOYD_USER_ID, webinar_dict, assignment_dict, copy_dict,
)
from api.schemas import WebinarCreate, WebinarUpdate, AssignRequest, AssignmentUpdate
from db.models import (
    OutreachBucket, OutreachSender, Webinar, WebinarListAssignment, CopyUsageLog,
    Contact,
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

    # Default registration_link and unsubscribe_link from the latest webinar
    latest_result = await db.execute(
        select(Webinar).where(Webinar.user_id == LLOYD_USER_ID)
        .order_by(Webinar.number.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()

    webinar = Webinar(
        user_id=LLOYD_USER_ID,
        number=body.number,
        date=body.date,
        status="planning",
        registration_link=latest.registration_link if latest else None,
        unsubscribe_link=latest.unsubscribe_link if latest else None,
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


@router.delete("/webinars/{webinar_id}")
async def delete_webinar(
    webinar_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(Webinar).where(Webinar.id == webinar_id, Webinar.user_id == LLOYD_USER_ID)
        .options(selectinload(Webinar.assignments))
    )
    webinar = result.scalar_one_or_none()
    if not webinar:
        raise HTTPException(404, "Webinar not found")

    # Release 'assigned' contacts back to 'available' for all assignments
    assignment_ids = [a.id for a in (webinar.assignments or [])]
    total_released = 0
    if assignment_ids:
        release_result = await db.execute(
            update(Contact)
            .where(Contact.assignment_id.in_(assignment_ids), Contact.outreach_status == "assigned")
            .values(assignment_id=None, outreach_status="available", assigned_date=None)
        )
        total_released = release_result.rowcount

        # Clear assignment_id on 'used' contacts (keep status as 'used')
        await db.execute(
            update(Contact)
            .where(Contact.assignment_id.in_(assignment_ids), Contact.outreach_status == "used")
            .values(assignment_id=None)
        )

    # Restore bucket remaining counts
    if total_released > 0:
        # Group released by bucket
        for a in (webinar.assignments or []):
            if a.bucket_id:
                b_result = await db.execute(
                    select(sa_func.count()).where(
                        Contact.bucket_id == a.bucket_id,
                        Contact.outreach_status == "available",
                    )
                )
                actual_available = b_result.scalar() or 0
                await db.execute(
                    update(OutreachBucket)
                    .where(OutreachBucket.id == a.bucket_id)
                    .values(remaining_contacts=actual_available)
                )

    # Delete copy usage logs for all assignments
    if assignment_ids:
        await db.execute(
            delete(CopyUsageLog).where(CopyUsageLog.assignment_id.in_(assignment_ids))
        )

    # Delete webinar (CASCADE will delete assignments)
    await db.delete(webinar)
    await db.flush()

    return {"deleted": True, "released": total_released}


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

    # Count available contacts in this bucket (not assigned or used)
    available_count_result = await db.execute(
        select(sa_func.count()).where(
            Contact.bucket_id == body.bucket_id,
            Contact.outreach_status == "available",
        )
    )
    available_count = available_count_result.scalar() or 0

    if available_count < body.volume:
        raise HTTPException(
            400,
            f"Volume {body.volume} exceeds available contacts ({available_count})",
        )

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
    await db.flush()  # get assignment.id

    # Claim available contacts in a single SQL statement (no Python round-trip).
    # Single UPDATE ... WHERE id IN (SELECT ... LIMIT N) — runs entirely in Postgres.
    claim_subq = (
        select(Contact.id)
        .where(
            Contact.bucket_id == body.bucket_id,
            Contact.outreach_status == "available",
        )
        .limit(body.volume)
    )
    claim_result = await db.execute(
        update(Contact)
        .where(Contact.id.in_(claim_subq))
        .values(
            assignment_id=assignment.id,
            outreach_status="assigned",
            assigned_date=webinar.date,
        )
    )
    claimed = claim_result.rowcount

    # Update bucket remaining counter
    bucket.remaining_contacts = max(0, available_count - claimed)

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
    resp = assignment_dict(assignment)
    resp["bucket_remaining"] = bucket.remaining_contacts
    return resp


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

    # Reload with relationships so assignment_dict can serialize them
    result = await db.execute(
        select(WebinarListAssignment).where(WebinarListAssignment.id == assignment_id)
        .options(
            selectinload(WebinarListAssignment.bucket),
            selectinload(WebinarListAssignment.sender),
            selectinload(WebinarListAssignment.title_copy),
            selectinload(WebinarListAssignment.desc_copy),
        )
    )
    assignment = result.scalar_one()
    return assignment_dict(assignment)


@router.delete("/assignments/{assignment_id}")
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

    # Release 'assigned' contacts back to 'available' (not 'used' — those stay used)
    release_result = await db.execute(
        update(Contact)
        .where(Contact.assignment_id == assignment_id, Contact.outreach_status == "assigned")
        .values(assignment_id=None, outreach_status="available", assigned_date=None)
    )
    released = release_result.rowcount

    # Clear assignment_id on 'used' contacts too (assignment is being deleted)
    # but keep their outreach_status as 'used'
    await db.execute(
        update(Contact)
        .where(Contact.assignment_id == assignment_id, Contact.outreach_status == "used")
        .values(assignment_id=None)
    )

    # Restore bucket remaining — only the released (previously assigned, not yet used) ones
    bucket_id = assignment.bucket_id
    bucket_remaining = None
    if bucket_id and released > 0:
        b_result = await db.execute(select(OutreachBucket).where(OutreachBucket.id == bucket_id))
        bucket = b_result.scalar_one_or_none()
        if bucket:
            bucket.remaining_contacts += released
            bucket_remaining = bucket.remaining_contacts

    # Delete usage logs + assignment in parallel deletes
    await db.execute(
        delete(CopyUsageLog).where(CopyUsageLog.assignment_id == assignment_id)
    )

    await db.delete(assignment)
    await db.flush()

    return {
        "released": released,
        "bucket_id": bucket_id,
        "bucket_remaining": bucket_remaining,
    }


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


# ═══════════════════════════════════════════════════════════════════════════
# ASSIGNMENT CONTACTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/assignments/{assignment_id}/contacts")
async def get_assignment_contacts(
    assignment_id: str,
    status: str = Query("assigned", regex="^(assigned|used|all)$"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    # Verify assignment belongs to user
    asgn_result = await db.execute(
        select(WebinarListAssignment)
        .where(WebinarListAssignment.id == assignment_id, WebinarListAssignment.user_id == LLOYD_USER_ID)
        .options(selectinload(WebinarListAssignment.bucket), selectinload(WebinarListAssignment.webinar))
    )
    assignment = asgn_result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Assignment not found")

    q = select(Contact).where(
        Contact.assignment_id == assignment_id,
        Contact.user_id == LLOYD_USER_ID,
    )
    if status != "all":
        q = q.where(Contact.outreach_status == status)
    q = q.order_by(Contact.first_name, Contact.email)

    result = await db.execute(q)
    contacts = result.scalars().all()

    # Count by status for the filter badges
    count_result = await db.execute(
        select(Contact.outreach_status, sa_func.count()).where(
            Contact.assignment_id == assignment_id,
            Contact.user_id == LLOYD_USER_ID,
        ).group_by(Contact.outreach_status)
    )
    counts = {row[0]: row[1] for row in count_result}

    return {
        "assignment": {
            "id": assignment.id,
            "bucket_name": assignment.bucket.name if assignment.bucket else None,
            "list_name": assignment.list_name,
            "webinar_number": assignment.webinar.number if assignment.webinar else None,
            "webinar_date": assignment.webinar.date.isoformat() if assignment.webinar and assignment.webinar.date else None,
            "volume": assignment.volume,
        },
        "contacts": [
            {
                "id": c.id,
                "email": c.email,
                "first_name": c.first_name,
                "outreach_status": c.outreach_status,
                "used_at": c.used_at.isoformat() if c.used_at else None,
            }
            for c in contacts
        ],
        "counts": {
            "assigned": counts.get("assigned", 0),
            "used": counts.get("used", 0),
            "total": sum(counts.values()),
        },
    }


class MarkUsedRequest(BaseModel):
    contact_ids: list[str]


@router.put("/assignments/{assignment_id}/contacts/mark-used")
async def mark_contacts_used(
    assignment_id: str,
    body: MarkUsedRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    # Verify assignment belongs to user
    asgn_result = await db.execute(
        select(WebinarListAssignment).where(
            WebinarListAssignment.id == assignment_id,
            WebinarListAssignment.user_id == LLOYD_USER_ID,
        )
    )
    if not asgn_result.scalar_one_or_none():
        raise HTTPException(404, "Assignment not found")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Contact)
        .where(
            Contact.id.in_(body.contact_ids),
            Contact.assignment_id == assignment_id,
            Contact.user_id == LLOYD_USER_ID,
            Contact.outreach_status == "assigned",
        )
        .values(outreach_status="used", used_at=now)
    )
    await db.flush()

    return {"marked": result.rowcount}
