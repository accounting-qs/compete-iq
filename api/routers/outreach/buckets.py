"""Outreach sub-router: Buckets + Bucket Copies CRUD."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sa_func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import require_auth
from api.routers.outreach._helpers import LLOYD_USER_ID, bucket_dict, copy_dict
from api.schemas import BucketCreate, BucketUpdate, CopyCreate, CopyGenerateRequest, CopyUpdate, CopyRegenerateRequest
from db.models import OutreachBucket, BucketCopy, Contact, WebinarListAssignment
from db.session import get_db
from services.generation import generate_bucket_copies, regenerate_bucket_copy

logger = logging.getLogger(__name__)

router = APIRouter()




# ═══════════════════════════════════════════════════════════════════════════
# BUCKETS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/buckets")
async def list_buckets(
    include: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    q = select(OutreachBucket).where(
        OutreachBucket.user_id == LLOYD_USER_ID,
        OutreachBucket.deleted_at.is_(None),
    ).order_by(OutreachBucket.remaining_contacts.desc())
    if include == "copies":
        q = q.options(selectinload(OutreachBucket.copies))
    result = await db.execute(q)
    buckets = result.scalars().all()

    # Compute actual total/remaining from contacts table
    bucket_ids = [b.id for b in buckets]
    if bucket_ids:
        count_result = await db.execute(
            select(
                Contact.bucket_id,
                sa_func.count().label("total"),
                sa_func.count().filter(Contact.outreach_status == "available").label("available"),
            )
            .where(Contact.bucket_id.in_(bucket_ids))
            .group_by(Contact.bucket_id)
        )
        count_map = {row.bucket_id: (row.total, row.available) for row in count_result}

        # Sync stored counters with actual counts
        for b in buckets:
            total, available = count_map.get(b.id, (0, 0))
            if b.total_contacts != total or b.remaining_contacts != available:
                b.total_contacts = total
                b.remaining_contacts = available
        await db.flush()

    # When including copies, also fetch which copy IDs are actively assigned
    assigned_copy_ids: set[str] = set()
    if include == "copies" and bucket_ids:
        assigned_result = await db.execute(
            select(WebinarListAssignment.title_copy_id, WebinarListAssignment.desc_copy_id)
            .where(
                WebinarListAssignment.user_id == LLOYD_USER_ID,
                WebinarListAssignment.bucket_id.in_(bucket_ids),
            )
        )
        for row in assigned_result:
            if row.title_copy_id:
                assigned_copy_ids.add(row.title_copy_id)
            if row.desc_copy_id:
                assigned_copy_ids.add(row.desc_copy_id)

    return {"buckets": [bucket_dict(b, include_copies=(include == "copies"), assigned_copy_ids=assigned_copy_ids) for b in buckets]}


@router.post("/buckets", status_code=201)
async def create_bucket(
    body: BucketCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    existing = await db.execute(
        select(OutreachBucket).where(
            OutreachBucket.user_id == LLOYD_USER_ID,
            OutreachBucket.name == body.name,
            OutreachBucket.deleted_at.is_(None),
        )
    )
    bucket = existing.scalar_one_or_none()
    if bucket:
        bucket.total_contacts += body.total_contacts
        bucket.remaining_contacts += (body.remaining_contacts or body.total_contacts)
        if body.countries:
            existing_countries = set(bucket.countries or [])
            existing_countries.update(body.countries)
            bucket.countries = list(existing_countries)
        if body.emp_range and not bucket.emp_range:
            bucket.emp_range = body.emp_range
        if body.industry and not bucket.industry:
            bucket.industry = body.industry
    else:
        bucket = OutreachBucket(
            user_id=LLOYD_USER_ID,
            name=body.name,
            industry=body.industry,
            total_contacts=body.total_contacts,
            remaining_contacts=body.remaining_contacts or body.total_contacts,
            countries=body.countries,
            emp_range=body.emp_range,
            source_file=body.source_file,
        )
        db.add(bucket)
    await db.flush()
    return bucket_dict(bucket)


@router.put("/buckets/{bucket_id}")
async def update_bucket(
    bucket_id: str,
    body: BucketUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(OutreachBucket).where(OutreachBucket.id == bucket_id, OutreachBucket.user_id == LLOYD_USER_ID)
    )
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(404, "Bucket not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(bucket, field, val)
    await db.flush()
    return bucket_dict(bucket)


# ═══════════════════════════════════════════════════════════════════════════
# BUCKET COPIES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/buckets/{bucket_id}/copies")
async def get_bucket_copies(
    bucket_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(BucketCopy).where(
            BucketCopy.bucket_id == bucket_id,
            BucketCopy.user_id == LLOYD_USER_ID,
            BucketCopy.deleted_at.is_(None),
        ).order_by(BucketCopy.copy_type, BucketCopy.variant_index)
    )
    copies = result.scalars().all()
    titles = [copy_dict(c) for c in copies if c.copy_type == "title"]
    descriptions = [copy_dict(c) for c in copies if c.copy_type == "description"]
    return {"bucket_id": bucket_id, "titles": titles, "descriptions": descriptions}


@router.post("/buckets/{bucket_id}/copies", status_code=201)
async def create_copy(
    bucket_id: str,
    body: CopyCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(OutreachBucket).where(OutreachBucket.id == bucket_id, OutreachBucket.user_id == LLOYD_USER_ID)
    )
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(404, "Bucket not found")

    max_idx_result = await db.execute(
        select(sa_func.max(BucketCopy.variant_index)).where(
            BucketCopy.bucket_id == bucket_id,
            BucketCopy.copy_type == body.copy_type,
        )
    )
    max_idx = max_idx_result.scalar()
    next_idx = (max_idx + 1) if max_idx is not None else 0

    copy = BucketCopy(
        user_id=LLOYD_USER_ID,
        bucket_id=bucket_id,
        copy_type=body.copy_type,
        variant_index=next_idx,
        text=body.text,
        is_primary=False,
    )
    db.add(copy)
    await db.flush()
    return copy_dict(copy)


@router.post("/buckets/{bucket_id}/copies/generate", status_code=201)
async def generate_copies(
    bucket_id: str,
    body: CopyGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(OutreachBucket).where(OutreachBucket.id == bucket_id, OutreachBucket.user_id == LLOYD_USER_ID)
    )
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(404, "Bucket not found")

    batch_id = str(uuid.uuid4())
    generated_titles = []
    generated_descs = []

    types_to_gen = []
    if body.copy_type in ("title", "both"):
        types_to_gen.append("title")
    if body.copy_type in ("description", "both"):
        types_to_gen.append("description")

    for copy_type in types_to_gen:
        # Un-primary old copies
        old_copies = await db.execute(
            select(BucketCopy).where(
                BucketCopy.bucket_id == bucket_id,
                BucketCopy.copy_type == copy_type,
                BucketCopy.deleted_at.is_(None),
            )
        )
        for old in old_copies.scalars().all():
            old.is_primary = False

        # Get max variant_index so new copies continue the sequence
        max_idx_result = await db.execute(
            select(sa_func.max(BucketCopy.variant_index)).where(
                BucketCopy.bucket_id == bucket_id,
                BucketCopy.copy_type == copy_type,
            )
        )
        max_idx = max_idx_result.scalar() or -1

        # Generate copies via AI brain
        try:
            texts = await generate_bucket_copies(
                db=db,
                user_id=LLOYD_USER_ID,
                bucket_name=bucket.name,
                industry=bucket.industry,
                countries=bucket.countries,
                emp_range=bucket.emp_range,
                copy_type=copy_type,
                count=body.variant_count,
            )
        except ValueError as e:
            logger.error("AI generation failed for bucket %s: %s", bucket.name, e)
            raise HTTPException(422, f"Generation failed: {e}")

        for i, text in enumerate(texts):
            copy = BucketCopy(
                user_id=LLOYD_USER_ID,
                bucket_id=bucket_id,
                copy_type=copy_type,
                variant_index=max_idx + 1 + i,
                text=text,
                is_primary=(i == 0),
                generation_batch_id=batch_id,
            )
            db.add(copy)
            if copy_type == "title":
                generated_titles.append(copy)
            else:
                generated_descs.append(copy)

    await db.flush()

    return {
        "bucket_id": bucket_id,
        "batch_id": batch_id,
        "titles": [copy_dict(c) for c in generated_titles],
        "descriptions": [copy_dict(c) for c in generated_descs],
    }


@router.put("/copies/{copy_id}")
async def update_copy(
    copy_id: str,
    body: CopyUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(BucketCopy).where(BucketCopy.id == copy_id, BucketCopy.user_id == LLOYD_USER_ID)
    )
    copy = result.scalar_one_or_none()
    if not copy:
        raise HTTPException(404, "Copy not found")

    if body.text is not None:
        copy.text = body.text

    if body.is_primary is True:
        await db.execute(
            update(BucketCopy).where(
                BucketCopy.bucket_id == copy.bucket_id,
                BucketCopy.copy_type == copy.copy_type,
                BucketCopy.id != copy_id,
                BucketCopy.deleted_at.is_(None),
            ).values(is_primary=False, primary_picked_by_user=False)
        )
        copy.is_primary = True
        copy.primary_picked_by_user = True

    await db.flush()
    return copy_dict(copy)


@router.post("/copies/{copy_id}/regenerate", status_code=201)
async def regenerate_copy(
    copy_id: str,
    body: CopyRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(BucketCopy).where(BucketCopy.id == copy_id, BucketCopy.user_id == LLOYD_USER_ID)
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(404, "Copy not found")

    original.ai_feedback = body.feedback

    bucket_result = await db.execute(select(OutreachBucket).where(OutreachBucket.id == original.bucket_id))
    bucket = bucket_result.scalar_one_or_none()

    max_idx_result = await db.execute(
        select(sa_func.max(BucketCopy.variant_index)).where(
            BucketCopy.bucket_id == original.bucket_id,
            BucketCopy.copy_type == original.copy_type,
        )
    )
    max_idx = max_idx_result.scalar() or 0

    # Regenerate via AI brain with feedback
    try:
        text = await regenerate_bucket_copy(
            db=db,
            user_id=LLOYD_USER_ID,
            original_text=original.text,
            copy_type=original.copy_type,
            feedback=body.feedback,
            bucket_name=bucket.name if bucket else "Unknown",
            industry=bucket.industry if bucket else None,
        )
    except ValueError as e:
        logger.error("AI regeneration failed: %s", e)
        raise HTTPException(422, f"Regeneration failed: {e}")

    new_copy = BucketCopy(
        user_id=LLOYD_USER_ID,
        bucket_id=original.bucket_id,
        copy_type=original.copy_type,
        variant_index=max_idx + 1,
        text=text,
        is_primary=False,
        ai_feedback=body.feedback,
        generation_batch_id=original.generation_batch_id,
    )
    db.add(new_copy)
    await db.flush()
    return copy_dict(new_copy)


@router.delete("/copies/{copy_id}", status_code=204)
async def delete_copy(
    copy_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(BucketCopy).where(BucketCopy.id == copy_id, BucketCopy.user_id == LLOYD_USER_ID)
    )
    copy = result.scalar_one_or_none()
    if not copy:
        raise HTTPException(404, "Copy not found")

    was_primary = copy.is_primary
    copy.deleted_at = datetime.utcnow()
    copy.is_primary = False

    if was_primary:
        next_result = await db.execute(
            select(BucketCopy).where(
                BucketCopy.bucket_id == copy.bucket_id,
                BucketCopy.copy_type == copy.copy_type,
                BucketCopy.id != copy_id,
                BucketCopy.deleted_at.is_(None),
            ).order_by(BucketCopy.variant_index).limit(1)
        )
        next_copy = next_result.scalar_one_or_none()
        if next_copy:
            next_copy.is_primary = True

    await db.flush()
