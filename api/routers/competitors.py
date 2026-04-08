"""
Competitors router — thin HTTP wrapper over services.competitors.
All routes require bearer auth.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from db.session import get_db
from services import competitors as competitors_svc

router = APIRouter(dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CompetitorCreate(BaseModel):
    handle: str
    display_name: str | None = None
    meta_page_id: str | None = None


class CompetitorUpdate(BaseModel):
    display_name: str | None = None
    is_tracked: bool | None = None


class CompetitorResponse(BaseModel):
    id: str
    handle: str
    display_name: str | None
    meta_page_id: str | None
    is_tracked: bool
    last_scraped_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[CompetitorResponse])
async def list_competitors(db: AsyncSession = Depends(get_db)):
    """List all active (non-deleted) competitors."""
    user = await competitors_svc.get_user(db)
    if not user:
        raise HTTPException(status_code=500, detail="No user found — seed the users table first")
    return await competitors_svc.list_competitors(db, user.id)


@router.post("/", response_model=CompetitorResponse, status_code=status.HTTP_201_CREATED)
async def create_competitor(payload: CompetitorCreate, db: AsyncSession = Depends(get_db)):
    """Create a new competitor."""
    user = await competitors_svc.get_user(db)
    if not user:
        raise HTTPException(status_code=500, detail="No user found — seed the users table first")
    try:
        competitor, _ = await competitors_svc.create_competitor(
            db, user.id, payload.handle, payload.display_name, payload.meta_page_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return competitor


@router.patch("/{competitor_id}", response_model=CompetitorResponse)
async def update_competitor(
    competitor_id: str,
    payload: CompetitorUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update competitor display name or tracking status."""
    competitor = await competitors_svc.update_competitor(
        db, competitor_id, payload.display_name, payload.is_tracked
    )
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    return competitor


@router.delete("/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competitor(competitor_id: str, db: AsyncSession = Depends(get_db)):
    """Soft delete a competitor."""
    deleted = await competitors_svc.soft_delete_competitor(db, competitor_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
