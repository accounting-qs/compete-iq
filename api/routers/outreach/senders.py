"""Outreach sub-router: Senders CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.routers.outreach._helpers import LLOYD_USER_ID, sender_dict
from api.schemas import SenderCreate, SenderUpdate
from db.models import OutreachSender
from db.session import get_db

router = APIRouter()


@router.get("/senders")
async def list_senders(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(OutreachSender).where(
            OutreachSender.user_id == LLOYD_USER_ID,
            OutreachSender.is_active.is_(True),
        ).order_by(OutreachSender.display_order)
    )
    senders = result.scalars().all()
    return {"senders": [sender_dict(s) for s in senders]}


@router.post("/senders", status_code=201)
async def create_sender(
    body: SenderCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    max_order = await db.execute(
        select(sa_func.max(OutreachSender.display_order)).where(OutreachSender.user_id == LLOYD_USER_ID)
    )
    next_order = (max_order.scalar() or 0) + 1

    sender = OutreachSender(
        user_id=LLOYD_USER_ID,
        name=body.name,
        total_accounts=body.total_accounts,
        send_per_account=body.send_per_account,
        days_per_webinar=body.days_per_webinar,
        color=body.color,
        display_order=next_order,
    )
    db.add(sender)
    await db.flush()
    return sender_dict(sender)


@router.put("/senders/{sender_id}")
async def update_sender(
    sender_id: str,
    body: SenderUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(OutreachSender).where(OutreachSender.id == sender_id, OutreachSender.user_id == LLOYD_USER_ID)
    )
    sender = result.scalar_one_or_none()
    if not sender:
        raise HTTPException(404, "Sender not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(sender, field, val)
    await db.flush()
    return sender_dict(sender)
