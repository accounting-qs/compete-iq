"""
Generation router — POST /generate/calendar-event (streaming + non-streaming)
"""
from __future__ import annotations

from anthropic import RateLimitError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from db.session import get_db
from services.generation import generate_calendar_blocker, stream_calendar_blocker

router = APIRouter()

# Hardcoded to Lloyd's user_id — single-tenant for now
LLOYD_USER_ID = "9baf8117-db65-4f30-87a5-a76cf4f23d82"


class CalendarBlockerRequest(BaseModel):
    segment: str = Field(..., description="Target segment, e.g. 'B2B SaaS founders', 'Financial Advisors'")
    sub_niche: str | None = Field(None, description="Optional sub-niche, e.g. 'process mining SaaS'")
    topic: str | None = Field(None, description="Webinar topic — defaults to AI-powered webinar growth system")
    client_story: str | None = Field(None, description="Optional verbatim client proof story to use")


@router.post("/calendar-event")
async def generate_calendar_event(
    request: CalendarBlockerRequest,
    stream: bool = Query(False, description="Set true for SSE streaming"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Generate 3 calendar blocker variants (A/B/C) for a target segment.

    Returns JSON with title + description for each variant.
    Set ?stream=true for Server-Sent Events streaming (recommended for UI).
    """
    if stream:
        return StreamingResponse(
            stream_calendar_blocker(
                db=db,
                user_id=LLOYD_USER_ID,
                segment=request.segment,
                sub_niche=request.sub_niche,
                topic=request.topic,
                client_story=request.client_story,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # Disables Nginx buffering for Railway
            },
        )

    try:
        result = await generate_calendar_blocker(
            db=db,
            user_id=LLOYD_USER_ID,
            segment=request.segment,
            sub_niche=request.sub_niche,
            topic=request.topic,
            client_story=request.client_story,
        )
        return result
    except RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit hit — wait a moment and try again.")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
