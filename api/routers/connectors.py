"""
Connectors router — WebinarGeek integration.

Endpoints:
  Credentials:
    GET    /connectors/webinargeek
    PUT    /connectors/webinargeek
    DELETE /connectors/webinargeek

  Broadcasts (cached):
    GET    /connectors/webinargeek/webinars?limit=&offset=&q=
    POST   /connectors/webinargeek/webinars/refresh
    POST   /connectors/webinargeek/webinars/sync-all   (sync subscribers for all)
    POST   /connectors/webinargeek/webinars/{broadcast_id}/sync

  Subscribers (cached):
    GET    /connectors/webinargeek/subscribers?broadcast_id=&q=&limit=&offset=
    GET    /connectors/webinargeek/subscribers/export?broadcast_id=   (CSV)
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, delete, or_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.routers.outreach._helpers import LLOYD_USER_ID
from db.models import BlocklistEntry, ConnectorCredential, WebinarGeekWebinar, WebinarGeekSubscriber
from db.session import get_db
from integrations import webinargeek_client as wg
from integrations import openai_client as oai
from integrations import ghl_client as ghl

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])

PROVIDER = "webinargeek"
OPENAI_PROVIDER = "openai"
GHL_PROVIDER = "ghl"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CredentialStatus(BaseModel):
    configured: bool
    api_key_masked: Optional[str] = None


class SetCredentialRequest(BaseModel):
    api_key: str


class GhlCredentialStatus(BaseModel):
    configured: bool
    api_key_masked: Optional[str] = None
    location_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    source: str  # "db" | "env" | "none"


class SetGhlCredentialRequest(BaseModel):
    api_key: str
    location_id: str
    pipeline_id: Optional[str] = None


class BroadcastOut(BaseModel):
    broadcast_id: str
    name: str
    internal_title: Optional[str] = None
    starts_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    subscriptions_count: int = 0
    live_viewers_count: int = 0
    replay_viewers_count: int = 0
    has_ended: bool = False
    cancelled: bool = False
    last_synced_at: Optional[datetime] = None
    synced_subscriber_count: int = 0


class BroadcastListResponse(BaseModel):
    broadcasts: list[BroadcastOut]
    total: int


class RefreshResponse(BaseModel):
    count: int


class SyncResponse(BaseModel):
    broadcast_id: str
    total: int


class SyncAllResponse(BaseModel):
    broadcasts_synced: int
    total_subscribers: int
    errors: list[str] = []


class SubscriberOut(BaseModel):
    id: str
    broadcast_id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    registration_source: Optional[str] = None
    subscribed_at: Optional[datetime] = None
    watched_live: Optional[bool] = None
    watched_replay: Optional[bool] = None
    minutes_viewing: Optional[int] = None
    viewing_device: Optional[str] = None
    viewing_country: Optional[str] = None


class SubscriberListResponse(BaseModel):
    subscribers: list[SubscriberOut]
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


def _subscriber_values(broadcast_id: str, s: dict) -> dict:
    """Map WebinarGeek subscription record → our column layout."""
    wd = s.get("watch_duration")
    minutes = int(wd // 60) if isinstance(wd, (int, float)) else None
    return {
        "broadcast_id": broadcast_id,
        "subscriber_id": str(s.get("id")) if s.get("id") is not None else None,
        "email": (s.get("email") or "").strip(),
        "first_name": s.get("firstname"),
        "last_name": s.get("surname"),
        "company": s.get("company"),
        "job_title": s.get("job_title"),
        "phone": s.get("phone"),
        "city": s.get("city"),
        "country": s.get("country"),
        "timezone": s.get("time_zone"),
        "registration_source": s.get("registration_source"),
        "subscribed_at": wg.unix_to_dt(s.get("created_at")),
        "unsubscribed_at": wg.unix_to_dt(s.get("unsubscribed_at")),
        "unsubscribe_source": s.get("unsubscription_source"),
        "watched_live": s.get("watched_live"),
        "watched_replay": s.get("watched_replay"),
        "start_time": wg.unix_to_dt(s.get("watch_start")),
        "end_time": wg.unix_to_dt(s.get("watch_end")),
        "minutes_viewing": minutes,
        "viewing_country": s.get("viewing_country"),
        "viewing_device": s.get("viewing_device"),
        "watch_link": s.get("watch_link"),
        "raw": s,
        "synced_at": datetime.now(timezone.utc),
    }


async def _sync_one_broadcast(db: AsyncSession, api_key: str, broadcast_id: str) -> int:
    subs = await wg.list_subscriptions(api_key, broadcast_id)
    blocklist_rows: list[dict] = []
    for s in subs:
        values = _subscriber_values(broadcast_id, s)
        if not values["email"]:
            continue
        stmt = pg_insert(WebinarGeekSubscriber).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["broadcast_id", "email"],
            set_={k: v for k, v in values.items() if k not in ("broadcast_id", "email")},
        )
        await db.execute(stmt)
        if values.get("unsubscribed_at"):
            blocklist_rows.append({
                "user_id": LLOYD_USER_ID,
                "email": values["email"].lower(),
                "source": "wg_unsub",
                "reason": values.get("unsubscribe_source") or "WebinarGeek unsubscribed",
                "source_ref": values.get("subscriber_id"),
            })
    if blocklist_rows:
        seen: set[str] = set()
        deduped = []
        for r in blocklist_rows:
            if r["email"] in seen:
                continue
            seen.add(r["email"])
            deduped.append(r)
        bl_stmt = pg_insert(BlocklistEntry).values(deduped).on_conflict_do_nothing(
            index_elements=["user_id", "email"]
        )
        try:
            await db.execute(bl_stmt)
        except Exception as exc:
            logger.warning("Failed to upsert blocklist from WG broadcast %s: %s", broadcast_id, exc)
    return len(subs)


# ---------------------------------------------------------------------------
# Credentials
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
# OpenAI credentials (used by case-study URL importer)
# ---------------------------------------------------------------------------
@router.get("/openai", response_model=CredentialStatus)
async def get_openai_status(db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(ConnectorCredential).where(ConnectorCredential.provider == OPENAI_PROVIDER)
    )).scalar_one_or_none()
    if not row:
        return CredentialStatus(configured=False)
    return CredentialStatus(configured=True, api_key_masked=_mask(row.api_key))


@router.put("/openai", response_model=CredentialStatus)
async def set_openai_credential(body: SetCredentialRequest, db: AsyncSession = Depends(get_db)):
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    try:
        ok = await oai.verify_api_key(api_key)
    except oai.OpenAIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid OpenAI API key")

    stmt = pg_insert(ConnectorCredential).values(provider=OPENAI_PROVIDER, api_key=api_key)
    stmt = stmt.on_conflict_do_update(
        index_elements=["provider"],
        set_={"api_key": api_key, "updated_at": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)
    return CredentialStatus(configured=True, api_key_masked=_mask(api_key))


@router.delete("/openai")
async def delete_openai_credential(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(ConnectorCredential).where(ConnectorCredential.provider == OPENAI_PROVIDER))
    return {"deleted": True}


# ---------------------------------------------------------------------------
# GoHighLevel credentials (used by the GHL sync engine + statistics)
# ---------------------------------------------------------------------------
@router.get("/ghl", response_model=GhlCredentialStatus)
async def get_ghl_status(db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(ConnectorCredential).where(ConnectorCredential.provider == GHL_PROVIDER)
    )).scalar_one_or_none()
    from config import settings as _settings
    if row and row.api_key and row.location_id:
        return GhlCredentialStatus(
            configured=True,
            api_key_masked=_mask(row.api_key),
            location_id=row.location_id,
            pipeline_id=row.pipeline_id or _settings.GHL_PIPELINE_ID,
            source="db",
        )
    # Env fallback — keeps the UI honest about where the key is coming from
    if _settings.GHL_API_KEY and _settings.GHL_LOCATION_ID:
        return GhlCredentialStatus(
            configured=True,
            api_key_masked=_mask(_settings.GHL_API_KEY),
            location_id=_settings.GHL_LOCATION_ID,
            pipeline_id=_settings.GHL_PIPELINE_ID,
            source="env",
        )
    return GhlCredentialStatus(configured=False, source="none")


@router.put("/ghl", response_model=GhlCredentialStatus)
async def set_ghl_credential(body: SetGhlCredentialRequest, db: AsyncSession = Depends(get_db)):
    api_key = body.api_key.strip()
    location_id = body.location_id.strip()
    pipeline_id = body.pipeline_id.strip() if body.pipeline_id else None
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    if not location_id:
        raise HTTPException(status_code=400, detail="location_id is required")

    ok, err = await ghl.verify_credentials(api_key, location_id)
    if not ok:
        # 400 for bad creds, 502 for upstream/network issues. We don't have
        # a clean way to tell them apart from verify_credentials' return,
        # so use 400 for any verified failure — caller shows the message.
        raise HTTPException(status_code=400, detail=err or "Failed to verify GHL credentials")

    stmt = pg_insert(ConnectorCredential).values(
        provider=GHL_PROVIDER,
        api_key=api_key,
        location_id=location_id,
        pipeline_id=pipeline_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["provider"],
        set_={
            "api_key": api_key,
            "location_id": location_id,
            "pipeline_id": pipeline_id,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)
    return GhlCredentialStatus(
        configured=True,
        api_key_masked=_mask(api_key),
        location_id=location_id,
        pipeline_id=pipeline_id,
        source="db",
    )


@router.delete("/ghl")
async def delete_ghl_credential(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(ConnectorCredential).where(ConnectorCredential.provider == GHL_PROVIDER))
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Broadcasts
# ---------------------------------------------------------------------------
@router.get("/webinargeek/webinars", response_model=BroadcastListResponse)
async def list_broadcasts(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    base = select(WebinarGeekWebinar)
    count_base = select(func.count()).select_from(WebinarGeekWebinar)
    if q:
        like = f"%{q}%"
        base = base.where(or_(
            WebinarGeekWebinar.name.ilike(like),
            WebinarGeekWebinar.internal_title.ilike(like),
            WebinarGeekWebinar.broadcast_id.ilike(like),
        ))
        count_base = count_base.where(or_(
            WebinarGeekWebinar.name.ilike(like),
            WebinarGeekWebinar.internal_title.ilike(like),
            WebinarGeekWebinar.broadcast_id.ilike(like),
        ))

    total = (await db.execute(count_base)).scalar_one()

    rows = (await db.execute(
        base.order_by(WebinarGeekWebinar.starts_at.desc().nullslast())
            .limit(limit).offset(offset)
    )).scalars().all()

    synced_counts = dict((await db.execute(
        select(WebinarGeekSubscriber.broadcast_id, func.count())
        .group_by(WebinarGeekSubscriber.broadcast_id)
    )).all())

    return BroadcastListResponse(
        broadcasts=[
            BroadcastOut(
                broadcast_id=r.broadcast_id,
                name=r.name,
                internal_title=r.internal_title,
                starts_at=r.starts_at,
                duration_seconds=r.duration_seconds,
                subscriptions_count=r.subscriptions_count,
                live_viewers_count=r.live_viewers_count,
                replay_viewers_count=r.replay_viewers_count,
                has_ended=r.has_ended,
                cancelled=r.cancelled,
                last_synced_at=r.last_synced_at,
                synced_subscriber_count=synced_counts.get(r.broadcast_id, 0),
            )
            for r in rows
        ],
        total=total,
    )


@router.post("/webinargeek/webinars/refresh", response_model=RefreshResponse)
async def refresh_broadcasts(db: AsyncSession = Depends(get_db)):
    """
    Refresh strategy:
      1) GET /webinars      → build {broadcast_id → webinar meta} map
                              (gives us internal_title / "136", "137" etc.)
      2) GET /broadcasts    → flat paginated list with all stats
         Enrich each broadcast with its webinar meta, upsert.
    """
    api_key = await _get_api_key(db)
    try:
        webinars = await wg.list_webinars(api_key)
        broadcasts = await wg.list_broadcasts(api_key)
    except wg.WebinarGeekError as e:
        raise HTTPException(status_code=502, detail=str(e))

    meta = wg.build_broadcast_meta(webinars)
    unknown_meta = {"webinar_id": None, "webinar_title": "", "internal_title": ""}

    total = 0
    for b in broadcasts:
        broadcast_id = str(b.get("id") or "")
        if not broadcast_id:
            continue
        m = meta.get(broadcast_id, unknown_meta)
        values = {
            "broadcast_id": broadcast_id,
            "webinar_id": str(m["webinar_id"]) if m["webinar_id"] is not None else None,
            "name": m["webinar_title"] or f"Broadcast {broadcast_id}",
            "internal_title": m["internal_title"] or None,
            "starts_at": wg.unix_to_dt(b.get("date")),
            "duration_seconds": b.get("duration"),
            "subscriptions_count": b.get("subscriptions_count") or 0,
            "live_viewers_count": b.get("live_viewers_count") or 0,
            "replay_viewers_count": b.get("replay_viewers_count") or 0,
            "has_ended": bool(b.get("has_ended")),
            "cancelled": bool(b.get("cancelled")),
            "raw": b,
            "updated_at": datetime.now(timezone.utc),
        }
        stmt = pg_insert(WebinarGeekWebinar).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["broadcast_id"],
            set_={k: v for k, v in values.items() if k != "broadcast_id"},
        )
        await db.execute(stmt)
        total += 1

    return RefreshResponse(count=total)


@router.post("/webinargeek/webinars/{broadcast_id}/sync", response_model=SyncResponse)
async def sync_broadcast_subscribers(broadcast_id: str, db: AsyncSession = Depends(get_db)):
    api_key = await _get_api_key(db)
    wb = (await db.execute(
        select(WebinarGeekWebinar).where(WebinarGeekWebinar.broadcast_id == broadcast_id)
    )).scalar_one_or_none()
    if not wb:
        raise HTTPException(status_code=404, detail="Broadcast not cached — refresh first")

    try:
        await _sync_one_broadcast(db, api_key, broadcast_id)
    except wg.WebinarGeekError as e:
        raise HTTPException(status_code=502, detail=str(e))

    wb.last_synced_at = datetime.now(timezone.utc)
    total = (await db.execute(
        select(func.count()).where(WebinarGeekSubscriber.broadcast_id == broadcast_id)
    )).scalar_one()
    return SyncResponse(broadcast_id=broadcast_id, total=total)


@router.post("/webinargeek/webinars/sync-all", response_model=SyncAllResponse)
async def sync_all_broadcasts(db: AsyncSession = Depends(get_db)):
    api_key = await _get_api_key(db)
    rows = (await db.execute(select(WebinarGeekWebinar))).scalars().all()

    errors: list[str] = []
    synced = 0
    total_subs = 0
    now = datetime.now(timezone.utc)
    for r in rows:
        try:
            count = await _sync_one_broadcast(db, api_key, r.broadcast_id)
            r.last_synced_at = now
            synced += 1
            total_subs += count
        except wg.WebinarGeekError as e:
            errors.append(f"{r.broadcast_id}: {e}")
            logger.warning("sync-all: broadcast %s failed: %s", r.broadcast_id, e)

    return SyncAllResponse(
        broadcasts_synced=synced,
        total_subscribers=total_subs,
        errors=errors[:20],
    )


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------
def _subscriber_query(broadcast_id: Optional[str], q: Optional[str]):
    stmt = select(WebinarGeekSubscriber)
    count_stmt = select(func.count()).select_from(WebinarGeekSubscriber)
    if broadcast_id:
        stmt = stmt.where(WebinarGeekSubscriber.broadcast_id == broadcast_id)
        count_stmt = count_stmt.where(WebinarGeekSubscriber.broadcast_id == broadcast_id)
    if q:
        like = f"%{q}%"
        cond = or_(
            WebinarGeekSubscriber.email.ilike(like),
            WebinarGeekSubscriber.first_name.ilike(like),
            WebinarGeekSubscriber.last_name.ilike(like),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    return stmt, count_stmt


@router.get("/webinargeek/subscribers", response_model=SubscriberListResponse)
async def list_subscribers(
    broadcast_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt, count_stmt = _subscriber_query(broadcast_id, q)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(
        stmt.order_by(WebinarGeekSubscriber.subscribed_at.desc().nullslast())
            .limit(limit).offset(offset)
    )).scalars().all()
    return SubscriberListResponse(
        subscribers=[
            SubscriberOut(
                id=r.id,
                broadcast_id=r.broadcast_id,
                email=r.email,
                first_name=r.first_name,
                last_name=r.last_name,
                registration_source=r.registration_source,
                subscribed_at=r.subscribed_at,
                watched_live=r.watched_live,
                watched_replay=r.watched_replay,
                minutes_viewing=r.minutes_viewing,
                viewing_device=r.viewing_device,
                viewing_country=r.viewing_country,
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/webinargeek/subscribers/export")
async def export_subscribers(
    broadcast_id: Optional[str] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt, _ = _subscriber_query(broadcast_id, q)
    rows = (await db.execute(
        stmt.order_by(WebinarGeekSubscriber.subscribed_at.desc().nullslast())
    )).scalars().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "email", "first_name", "last_name", "broadcast_id",
        "registered_at", "source", "watched_live", "watched_replay",
        "minutes_viewing", "device", "country", "timezone", "company", "job_title",
    ])
    for r in rows:
        w.writerow([
            r.email, r.first_name or "", r.last_name or "", r.broadcast_id,
            r.subscribed_at.isoformat() if r.subscribed_at else "",
            r.registration_source or "",
            "" if r.watched_live is None else ("yes" if r.watched_live else "no"),
            "" if r.watched_replay is None else ("yes" if r.watched_replay else "no"),
            r.minutes_viewing if r.minutes_viewing is not None else "",
            r.viewing_device or "", r.viewing_country or "",
            r.timezone or "", r.company or "", r.job_title or "",
        ])

    buf.seek(0)
    fn = f"webinargeek_subscribers_{broadcast_id or 'all'}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )
