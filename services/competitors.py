"""
Competitors service — all business logic for competitor CRUD.
Routes call these functions; they never touch the DB directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Competitor, User

logger = logging.getLogger(__name__)


async def get_user(db: AsyncSession) -> User | None:
    """Get the single user (Phase 1: single-user system)."""
    result = await db.execute(select(User).limit(1))
    return result.scalar_one_or_none()


async def list_competitors(db: AsyncSession, user_id: str) -> list[Competitor]:
    """List all active (non-deleted) competitors for a user."""
    result = await db.execute(
        select(Competitor)
        .where(Competitor.user_id == user_id, Competitor.deleted_at.is_(None))
        .order_by(Competitor.display_name)
    )
    return list(result.scalars().all())


async def get_competitor(db: AsyncSession, competitor_id: str) -> Competitor | None:
    """Get a single active competitor by ID."""
    result = await db.execute(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def create_competitor(
    db: AsyncSession,
    user_id: str,
    handle: str,
    display_name: str | None = None,
    meta_page_id: str | None = None,
) -> tuple[Competitor, bool]:
    """
    Create or restore a competitor. Returns (competitor, was_restored).
    Raises ValueError if competitor already exists and is active.
    """
    result = await db.execute(
        select(Competitor).where(
            Competitor.user_id == user_id,
            Competitor.handle == handle,
        )
    )
    existing = result.scalar_one_or_none()

    if existing and existing.deleted_at is None:
        raise ValueError(f"Competitor '{handle}' already exists")

    if existing and existing.deleted_at is not None:
        existing.deleted_at = None
        existing.display_name = display_name or existing.display_name
        existing.meta_page_id = meta_page_id or existing.meta_page_id
        existing.is_tracked = True
        await db.commit()
        await db.refresh(existing)
        return existing, True

    competitor = Competitor(
        user_id=user_id,
        handle=handle,
        display_name=display_name,
        meta_page_id=meta_page_id,
        is_tracked=True,
    )
    db.add(competitor)
    await db.commit()
    await db.refresh(competitor)
    return competitor, False


async def update_competitor(
    db: AsyncSession,
    competitor_id: str,
    display_name: str | None = None,
    is_tracked: bool | None = None,
) -> Competitor | None:
    """Update a competitor. Returns None if not found."""
    competitor = await get_competitor(db, competitor_id)
    if not competitor:
        return None

    if display_name is not None:
        competitor.display_name = display_name
    if is_tracked is not None:
        competitor.is_tracked = is_tracked

    await db.commit()
    await db.refresh(competitor)
    return competitor


async def soft_delete_competitor(db: AsyncSession, competitor_id: str) -> bool:
    """Soft delete a competitor. Returns False if not found."""
    competitor = await get_competitor(db, competitor_id)
    if not competitor:
        return False

    competitor.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def get_or_create_competitor_by_handle(
    db: AsyncSession,
    user_id: str,
    handle: str,
    display_name: str | None = None,
    meta_page_id: str | None = None,
) -> Competitor:
    """Get existing competitor by handle, or create new one. Used by WhatsApp flow."""
    result = await db.execute(
        select(Competitor).where(Competitor.handle == handle)
    )
    competitor = result.scalar_one_or_none()

    if competitor:
        return competitor

    competitor = Competitor(
        user_id=user_id,
        handle=handle,
        display_name=display_name,
        meta_page_id=meta_page_id,
        is_tracked=True,
    )
    db.add(competitor)
    await db.commit()
    await db.refresh(competitor)
    return competitor
