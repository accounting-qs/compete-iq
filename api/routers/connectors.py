"""
Connectors router — WebinarGeek integration.

Endpoints:
  GET    /connectors/webinargeek           -> {configured: bool, api_key_masked}
  PUT    /connectors/webinargeek           -> set/update API key
  DELETE /connectors/webinargeek           -> remove API key
  POST   /connectors/webinargeek/webinars/refresh -> fetch broadcasts from WG API
  GET    /connectors/webinargeek/webinars  -> cached list for dropdown
  POST   /connectors/webinargeek/webinars/{broadcast_id}/sync -> sync subscribers
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from db.models import ConnectorCredential, WebinarGeekWebinar, WebinarGeekSubscriber
from db.session import get_db
from integrations import webinargeek_client as wg

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])

PROVIDER = "webinargeek"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CredentialStatus(BaseModel):
    configured: bool
    api_key_masked: Optional[str] = None


class SetCredentialRequest(BaseModel):
    api_key: str


class WebinarOut(BaseModel):
    broadcast_id: str
    name: str
    starts_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    subscriber_count: int = 0


class WebinarListResponse(BaseModel):
    webinars: list[WebinarOut]


class RefreshResponse(BaseModel):
    count: int


class SyncResponse(BaseModel):
    broadcast_id: str
    inserted: int
    updated: int
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


async def _get_api_key(db: AsyncSession) -> str:
    row = (await db.execute(
        select(ConnectorCredential).where(ConnectorCredential.provider == PROVIDER)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=400, detail="WebinarGeek API key not configured")
    return row.api_key


# ---------------------------------------------------------------------------
# Credential endpoints
# ---------------------------------------------------------------------------
@router.get("/webinargeek", response_model=CredentialStatus)
async def get_credential_status(db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(ConnectorCredential).where(ConnectorCredential.provider == PROVIDER)
    )).scalar_one_or_none()
    if not row:
        return CredentialStatus(configured=False)
    return CredentialStatus(configured=True, api_key_masked=_mask(row.api_key))


@router.put("/webinargeek", response_model=CredentialStatus)
async def set_credential(body: SetCredentialRequest, db: AsyncSession = Depends(get_db)):
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        ok = await wg.verify_api_key(api_key)
    except wg.WebinarGeekError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid WebinarGeek API key")

    stmt = pg_insert(ConnectorCredential).values(provider=PROVIDER, api_key=api_key)
    stmt = stmt.on_conflict_do_update(
        index_elements=["provider"],
        set_={"api_key": api_key, "updated_at": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)
    return CredentialStatus(configured=True, api_key_masked=_mask(api_key))


@router.delete("/webinargeek")
async def delete_credential(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(ConnectorCredential).where(ConnectorCredential.provider == PROVIDER))
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Webinars list
# ---------------------------------------------------------------------------
@router.get("/webinargeek/webinars", response_model=WebinarListResponse)
async def list_cached_webinars(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(WebinarGeekWebinar).order_by(WebinarGeekWebinar.starts_at.desc().nullslast())
    )).scalars().all()

    counts = dict((await db.execute(
        select(WebinarGeekSubscriber.broadcast_id, func.count())
        .group_by(WebinarGeekSubscriber.broadcast_id)
    )).all())

    return WebinarListResponse(webinars=[
        WebinarOut(
            broadcast_id=r.broadcast_id,
            name=r.name,
            starts_at=r.starts_at,
            last_synced_at=r.last_synced_at,
            subscriber_count=counts.get(r.broadcast_id, 0),
        )
        for r in rows
    ])


@router.post("/webinargeek/webinars/refresh", response_model=RefreshResponse)
async def refresh_webinars(db: AsyncSession = Depends(get_db)):
    api_key = await _get_api_key(db)

    try:
        webinars = await wg.list_webinars(api_key)
    except wg.WebinarGeekError as e:
        raise HTTPException(status_code=502, detail=str(e))

    total = 0
    for w in webinars:
        webinar_id = w.get("id")
        name = w.get("title") or w.get("name") or f"Webinar {webinar_id}"
        if not webinar_id:
            continue
        try:
            broadcasts = await wg.list_broadcasts(api_key, webinar_id)
        except wg.WebinarGeekError as e:
            logger.warning("Failed to fetch broadcasts for webinar %s: %s", webinar_id, e)
            continue

        for b in broadcasts:
            broadcast_id = str(b.get("id") or "")
            if not broadcast_id:
                continue
            starts_at = wg.parse_dt(b.get("starts_at") or b.get("start_date") or b.get("start_at"))
            stmt = pg_insert(WebinarGeekWebinar).values(
                broadcast_id=broadcast_id,
                webinar_id=str(webinar_id),
                name=name,
                starts_at=starts_at,
                raw=b,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["broadcast_id"],
                set_={
                    "webinar_id": str(webinar_id),
                    "name": name,
                    "starts_at": starts_at,
                    "raw": b,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await db.execute(stmt)
            total += 1

    return RefreshResponse(count=total)


# ---------------------------------------------------------------------------
# Subscriber sync
# ---------------------------------------------------------------------------
@router.post("/webinargeek/webinars/{broadcast_id}/sync", response_model=SyncResponse)
async def sync_subscribers(broadcast_id: str, db: AsyncSession = Depends(get_db)):
    api_key = await _get_api_key(db)

    wb = (await db.execute(
        select(WebinarGeekWebinar).where(WebinarGeekWebinar.broadcast_id == broadcast_id)
    )).scalar_one_or_none()
    if not wb:
        raise HTTPException(status_code=404, detail="Broadcast not found — refresh webinars first")

    try:
        subs = await wg.list_subscribers(api_key, broadcast_id)
    except wg.WebinarGeekError as e:
        raise HTTPException(status_code=502, detail=str(e))

    inserted = 0
    updated = 0
    for s in subs:
        email = (s.get("email") or "").strip()
        if not email:
            continue

        values = {
            "broadcast_id": broadcast_id,
            "subscriber_id": str(s.get("id")) if s.get("id") is not None else None,
            "email": email,
            "first_name": s.get("first_name"),
            "last_name": s.get("last_name"),
            "company": s.get("company"),
            "job_title": s.get("job_title") or s.get("function"),
            "phone": s.get("phone"),
            "city": s.get("city"),
            "country": s.get("country"),
            "timezone": s.get("timezone"),
            "registration_source": s.get("registration_source") or s.get("source"),
            "subscribed_at": wg.parse_dt(s.get("subscribed_at") or s.get("created_at")),
            "unsubscribed_at": wg.parse_dt(s.get("unsubscribed_at")),
            "unsubscribe_source": s.get("unsubscription_source") or s.get("unsubscribe_source"),
            "watched_live": wg.coerce_bool(s.get("watched_live") or s.get("watched")),
            "watched_replay": wg.coerce_bool(s.get("watched_replay")),
            "start_time": wg.parse_dt(s.get("start_time") or s.get("join_time")),
            "end_time": wg.parse_dt(s.get("end_time") or s.get("leave_time")),
            "minutes_viewing": s.get("minutes_viewing_time") or s.get("minutes_viewing"),
            "viewing_country": s.get("viewing_country"),
            "viewing_device": s.get("viewing_device"),
            "watch_link": s.get("watch_link"),
            "raw": s,
            "synced_at": datetime.now(timezone.utc),
        }

        stmt = pg_insert(WebinarGeekSubscriber).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["broadcast_id", "email"],
            set_={k: v for k, v in values.items() if k not in ("broadcast_id", "email")},
        )
        result = await db.execute(stmt)
        # result.rowcount is 1 for both insert & update in PG upsert; use returning for better metrics if needed
        if result.rowcount and result.rowcount > 0:
            # Can't reliably distinguish; count all as processed
            inserted += 1

    wb.last_synced_at = datetime.now(timezone.utc)

    total = (await db.execute(
        select(func.count()).where(WebinarGeekSubscriber.broadcast_id == broadcast_id)
    )).scalar_one()

    return SyncResponse(broadcast_id=broadcast_id, inserted=inserted, updated=updated, total=total)
