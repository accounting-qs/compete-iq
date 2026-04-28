"""Outreach sub-router: release contacts back to the bucket pool after a webinar.

Operators upload a CSV of emails that could not be contacted in time. We revert
those contacts (status `assigned` or `used` → `available`) so they can be
re-assigned to a future webinar. `WebinarListAssignment.volume` is left
untouched so the original "planned" number is preserved for plan-vs-actual
comparison on the statistics page.

Each released contact is recorded in `contact_release_log` for a future undo /
auth-aware audit trail.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.routers.outreach._helpers import LLOYD_USER_ID
from db.models import (
    Contact, ContactReleaseLog, OutreachBucket, Webinar, WebinarListAssignment,
)
from db.session import get_db


router = APIRouter()


class ReleaseRequest(BaseModel):
    emails: list[str]


def _normalize_email(raw: str) -> str | None:
    if not raw:
        return None
    e = raw.strip().lower()
    return e or None


@router.post("/webinars/{webinar_id}/releases", status_code=201)
async def release_contacts(
    webinar_id: str,
    body: ReleaseRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Release contacts in this webinar back to `available`.

    For each email in `body.emails` that maps to a contact assigned to one of
    this webinar's WebinarListAssignments and currently in status `assigned`
    or `used`: revert the contact (clear assignment_id, used_at, assigned_date;
    set status to `available`) and snapshot the prior state into
    `contact_release_log` under one shared `release_batch_id`.

    Bucket `remaining_contacts` is restored from the live `available` count for
    each touched bucket. Assignment `volume` is intentionally untouched so the
    planned-send number is preserved for statistics comparison.
    """
    w_result = await db.execute(
        select(Webinar).where(
            Webinar.id == webinar_id,
            Webinar.user_id == LLOYD_USER_ID,
        )
    )
    webinar = w_result.scalar_one_or_none()
    if not webinar:
        raise HTTPException(404, "Webinar not found")

    a_result = await db.execute(
        select(WebinarListAssignment).where(
            WebinarListAssignment.webinar_id == webinar_id,
            WebinarListAssignment.user_id == LLOYD_USER_ID,
        )
    )
    assignments_by_id: dict[str, WebinarListAssignment] = {
        a.id: a for a in a_result.scalars().all()
    }
    assignment_ids = list(assignments_by_id.keys())
    if not assignment_ids:
        return {
            "release_batch_id": None,
            "released": 0,
            "not_found": [],
            "already_available": [],
            "by_status": {"assigned": 0, "used": 0},
            "bucket_updates": {},
        }

    # Normalize + dedupe input emails, drop empties
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in body.emails:
        e = _normalize_email(raw)
        if e and e not in seen:
            seen.add(e)
            normalized.append(e)

    if not normalized:
        raise HTTPException(400, "No valid emails provided")

    # Find every contact (any user-status) matching these emails so we can
    # accurately classify "not found" vs "already available" vs "in another
    # webinar". `func.lower(Contact.email)` would work but we already store
    # emails lowercased on insert — match directly.
    c_result = await db.execute(
        select(Contact).where(
            Contact.user_id == LLOYD_USER_ID,
            Contact.email.in_(normalized),
        )
    )
    all_matches = list(c_result.scalars().all())

    by_email: dict[str, list[Contact]] = {}
    for c in all_matches:
        if c.email:
            by_email.setdefault(c.email, []).append(c)

    release_batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    released_contacts: list[Contact] = []
    by_status_count = {"assigned": 0, "used": 0}
    not_found: list[str] = []
    already_available: list[str] = []
    touched_bucket_ids: set[str] = set()

    for email in normalized:
        candidates = by_email.get(email)
        if not candidates:
            not_found.append(email)
            continue

        # Prefer a contact attached to this webinar that is assigned/used.
        target = next(
            (
                c for c in candidates
                if c.assignment_id in assignment_ids
                and c.outreach_status in ("assigned", "used")
            ),
            None,
        )
        if target is None:
            # Email exists for the user but not in this webinar's pool — either
            # already available, or assigned/used in a different webinar. We
            # only report "already available" so operators don't accidentally
            # think the system found their contact and silently did nothing.
            if any(c.outreach_status == "available" for c in candidates):
                already_available.append(email)
            else:
                not_found.append(email)
            continue

        prior_status = target.outreach_status
        prior_assignment_id = target.assignment_id
        prior_bucket_id = target.bucket_id
        prior_used_at = target.used_at

        target.outreach_status = "available"
        target.assignment_id = None
        target.assigned_date = None
        target.used_at = None

        db.add(ContactReleaseLog(
            user_id=LLOYD_USER_ID,
            webinar_id=webinar_id,
            release_batch_id=release_batch_id,
            released_at=now,
            released_by=None,
            contact_id=target.id,
            email=email,
            prior_status=prior_status,
            prior_assignment_id=prior_assignment_id,
            prior_bucket_id=prior_bucket_id,
            prior_used_at=prior_used_at,
        ))
        released_contacts.append(target)
        by_status_count[prior_status] += 1
        if prior_bucket_id:
            touched_bucket_ids.add(prior_bucket_id)

        # `assignment.remaining` tracks "claimed but not yet marked used"
        # (mark_contacts_used decrements it). Releasing an `assigned` contact
        # removes one from that pool. Releasing a `used` contact doesn't
        # touch it — it was already decremented at mark-used time.
        if prior_status == "assigned" and prior_assignment_id:
            asn = assignments_by_id.get(prior_assignment_id)
            if asn:
                asn.remaining = max(0, (asn.remaining or 0) - 1)

    # Reconcile bucket.remaining_contacts from the live available count rather
    # than incrementing — keeps the field self-healing if it ever drifts.
    bucket_updates: dict[str, int] = {}
    if touched_bucket_ids:
        await db.flush()  # so the status updates are visible to the count query
        from sqlalchemy import func as sa_func
        for bucket_id in touched_bucket_ids:
            cnt_result = await db.execute(
                select(sa_func.count()).where(
                    Contact.bucket_id == bucket_id,
                    Contact.outreach_status == "available",
                )
            )
            available_count = int(cnt_result.scalar() or 0)
            await db.execute(
                update(OutreachBucket)
                .where(OutreachBucket.id == bucket_id)
                .values(remaining_contacts=available_count)
            )
            bucket_updates[bucket_id] = available_count

    await db.flush()

    return {
        "release_batch_id": release_batch_id if released_contacts else None,
        "released": len(released_contacts),
        "not_found": not_found,
        "already_available": already_available,
        "by_status": by_status_count,
        "bucket_updates": bucket_updates,
    }


@router.get("/webinars/{webinar_id}/releases")
async def list_releases(
    webinar_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """List release batches for this webinar (newest first)."""
    w_result = await db.execute(
        select(Webinar.id).where(
            Webinar.id == webinar_id,
            Webinar.user_id == LLOYD_USER_ID,
        )
    )
    if not w_result.scalar_one_or_none():
        raise HTTPException(404, "Webinar not found")

    from sqlalchemy import func as sa_func
    r = await db.execute(
        select(
            ContactReleaseLog.release_batch_id,
            sa_func.min(ContactReleaseLog.released_at).label("released_at"),
            sa_func.count().label("count"),
            sa_func.count().filter(ContactReleaseLog.prior_status == "used").label("used_count"),
            sa_func.count().filter(ContactReleaseLog.prior_status == "assigned").label("assigned_count"),
        )
        .where(
            ContactReleaseLog.webinar_id == webinar_id,
            ContactReleaseLog.user_id == LLOYD_USER_ID,
        )
        .group_by(ContactReleaseLog.release_batch_id)
        .order_by(sa_func.min(ContactReleaseLog.released_at).desc())
    )
    batches = [
        {
            "release_batch_id": row.release_batch_id,
            "released_at": row.released_at.isoformat() if row.released_at else None,
            "count": int(row.count or 0),
            "used_count": int(row.used_count or 0),
            "assigned_count": int(row.assigned_count or 0),
        }
        for row in r.all()
    ]
    return {"batches": batches}
