"""
Ads router — thin HTTP wrapper over services.ads.
All routes require bearer auth.
Pre-signed R2 URLs generated fresh on every request — never stored in DB.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from db.session import get_db
from services import ads as ads_svc
from services import competitors as competitors_svc
from processing.pipeline import process_ads_batch
from config import settings

router = APIRouter(dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AdResponse(BaseModel):
    id: str
    ad_library_id: str
    ad_type: str
    ad_text: str | None
    transcript: str | None
    on_screen_text: str | None
    angles: dict | None
    processing_status: str
    video_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ScrapeRequest(BaseModel):
    ad_ids: list[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/competitor/{competitor_id}", response_model=list[dict])
async def list_ads_for_competitor(
    competitor_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Ad Browser — list all ads for a competitor."""
    competitor = await competitors_svc.get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    return await ads_svc.list_ads_for_competitor(db, competitor_id)


@router.get("/library", response_model=list[dict])
async def list_library(
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = None,
):
    """My Library — all scraped ads across all competitors."""
    user = await competitors_svc.get_user(db)
    if not user:
        raise HTTPException(status_code=500, detail="No user found")
    return await ads_svc.list_library(db, user.id, status_filter)


@router.get("/{ad_id}", response_model=dict)
async def get_ad(ad_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single ad with fresh pre-signed URL."""
    result = await ads_svc.get_ad(db, ad_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad not found")
    return result


@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED)
async def scrape_ads(
    payload: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger pipeline processing for a list of ad IDs."""
    if not payload.ad_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No ad IDs provided")
    if len(payload.ad_ids) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Max 20 ads per scrape request")

    user = await competitors_svc.get_user(db)
    if not user:
        raise HTTPException(status_code=500, detail="No user found")

    try:
        validated_ids = await ads_svc.validate_scrape_request(db, user.id, payload.ad_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    background_tasks.add_task(process_ads_batch, db, validated_ids)
    return {"status": "processing", "count": len(validated_ids)}


@router.post("/refresh/{competitor_id}", status_code=status.HTTP_202_ACCEPTED)
async def refresh_competitor_ads(
    competitor_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Re-scrape a competitor's full ad profile."""
    competitor = await competitors_svc.get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")

    background_tasks.add_task(
        ads_svc.scrape_and_notify,
        competitor_id=competitor_id,
        handle=competitor.handle,
        from_=settings.LLOYD_WHATSAPP_NUMBER,
    )
    return {"status": "refreshing", "handle": competitor.handle}
