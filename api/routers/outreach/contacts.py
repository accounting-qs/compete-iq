"""Outreach sub-router: Custom Fields."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.routers.outreach._helpers import LLOYD_USER_ID
from api.schemas import CustomFieldCreate
from db.models import ContactCustomField
from db.session import get_db

router = APIRouter()


@router.get("/custom-fields")
async def list_custom_fields(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(ContactCustomField)
        .where(ContactCustomField.user_id == LLOYD_USER_ID)
        .order_by(ContactCustomField.display_order)
    )
    fields = result.scalars().all()
    return {
        "fields": [
            {
                "id": f.id,
                "field_name": f.field_name,
                "field_type": f.field_type,
                "display_order": f.display_order,
            }
            for f in fields
        ]
    }


@router.post("/custom-fields", status_code=201)
async def create_custom_field(
    body: CustomFieldCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    existing = await db.execute(
        select(ContactCustomField).where(
            ContactCustomField.user_id == LLOYD_USER_ID,
            ContactCustomField.field_name == body.field_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Custom field '{body.field_name}' already exists")

    max_order = await db.execute(
        select(sa_func.max(ContactCustomField.display_order))
        .where(ContactCustomField.user_id == LLOYD_USER_ID)
    )
    next_order = (max_order.scalar() or 0) + 1

    field = ContactCustomField(
        user_id=LLOYD_USER_ID,
        field_name=body.field_name,
        field_type=body.field_type,
        display_order=next_order,
    )
    db.add(field)
    await db.flush()

    return {
        "id": field.id,
        "field_name": field.field_name,
        "field_type": field.field_type,
        "display_order": field.display_order,
    }
