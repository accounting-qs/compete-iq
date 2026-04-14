"""Outreach sub-router: CSV Uploads + Background Import."""
import asyncio
import csv
import io
import os
import traceback
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, func as sa_func, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import pool

from api.auth import require_auth
from api.routers.outreach._helpers import LLOYD_USER_ID
from api.schemas import ImportStartCreate
from db.models import UploadHistory, ContactCustomField, Contact, OutreachBucket
from db.session import get_db

router = APIRouter()

# Supabase Storage config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
CSV_BUCKET = "csv-uploads"

# Database URL for background tasks (can't share request-scoped sessions)
_BG_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if _BG_DATABASE_URL.startswith("postgres://"):
    _BG_DATABASE_URL = _BG_DATABASE_URL.replace("postgres://", "postgresql://", 1)
if "postgresql+asyncpg://" not in _BG_DATABASE_URL:
    _BG_DATABASE_URL = _BG_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_bg_engine = create_async_engine(_BG_DATABASE_URL, poolclass=pool.NullPool) if _BG_DATABASE_URL else None

# Store background task references so they aren't garbage-collected
_active_import_tasks: dict[str, asyncio.Task] = {}

# Import control: pause/cancel state per upload_id
_import_pause_events: dict[str, asyncio.Event] = {}   # set=running, clear=paused
_import_cancel_flags: dict[str, bool] = {}


def _parse_csv_line(line: str) -> list[str]:
    """Parse a single CSV line handling quoted fields and escaped quotes ("")."""
    reader = csv.reader(io.StringIO(line))
    for row in reader:
        return [cell.strip() for cell in row]
    return []


@router.get("/uploads")
async def list_uploads(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    result = await db.execute(
        select(UploadHistory).where(UploadHistory.user_id == LLOYD_USER_ID)
        .order_by(UploadHistory.created_at.desc())
    )
    uploads = result.scalars().all()
    return {
        "uploads": [
            {
                "id": u.id,
                "file_name": u.file_name,
                "total_contacts": u.total_contacts,
                "total_buckets": u.total_buckets,
                "bucket_summary": u.bucket_summary,
                "status": u.status,
                "progress": u.progress,
                "processed_rows": u.processed_rows,
                "inserted_count": u.inserted_count,
                "skipped_count": u.skipped_count,
                "overwritten_count": u.overwritten_count,
                "error_message": u.error_message,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in uploads
        ]
    }


@router.post("/uploads/file", status_code=201)
async def upload_csv_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Step 1: Upload CSV to Supabase Storage.
    Returns upload_id, headers, and preview rows for the mapping UI.
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")

    contents = await file.read()
    file_size = len(contents)

    # Upload to Supabase Storage
    storage_path = f"{LLOYD_USER_ID}/{int(datetime.utcnow().timestamp())}_{file.filename}"
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/{CSV_BUCKET}/{storage_path}",
            headers={
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "text/csv",
            },
            content=contents,
            timeout=120.0,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(500, f"Failed to upload to Storage: {resp.text}")

    # Parse headers + preview rows
    text = contents.decode("utf-8", errors="replace")
    lines = text.split("\n")
    lines = [l.strip() for l in lines if l.strip()]
    total_rows = len(lines) - 1

    headers = _parse_csv_line(lines[0])
    preview_rows = [_parse_csv_line(lines[i]) for i in range(1, min(6, len(lines)))]

    # Create upload record
    upload = UploadHistory(
        user_id=LLOYD_USER_ID,
        file_name=file.filename,
        storage_path=storage_path,
        total_contacts=total_rows,
        status="uploading",
    )
    db.add(upload)
    await db.flush()

    return {
        "id": upload.id,
        "file_name": file.filename,
        "storage_path": storage_path,
        "total_rows": total_rows,
        "file_size": file_size,
        "headers": headers,
        "preview_rows": preview_rows,
    }


@router.post("/uploads/{upload_id}/import", status_code=202)
async def start_import(
    upload_id: str,
    body: ImportStartCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Step 2: Start background import after user maps columns.
    Returns immediately while import processes in background.
    """
    result = await db.execute(
        select(UploadHistory).where(UploadHistory.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(404, "Upload not found")

    upload.field_mappings = body.field_mappings
    upload.duplicate_mode = body.duplicate_mode
    upload.status = "processing"
    upload.progress = 0

    # Upsert custom fields
    for csv_header, target in body.field_mappings.items():
        if target.startswith("custom:"):
            field_name = target[7:]
            existing_field = await db.execute(
                select(ContactCustomField).where(
                    ContactCustomField.user_id == LLOYD_USER_ID,
                    ContactCustomField.field_name == field_name,
                )
            )
            if not existing_field.scalar_one_or_none():
                db.add(ContactCustomField(
                    user_id=LLOYD_USER_ID,
                    field_name=field_name,
                    field_type="text",
                ))

    await db.flush()

    # Set up control state
    pause_event = asyncio.Event()
    pause_event.set()  # start running (not paused)
    _import_pause_events[upload_id] = pause_event
    _import_cancel_flags[upload_id] = False

    def _cleanup(t):
        _active_import_tasks.pop(upload_id, None)
        _import_pause_events.pop(upload_id, None)
        _import_cancel_flags.pop(upload_id, None)

    task = asyncio.create_task(
        _process_csv_import(upload_id, upload.storage_path, body.field_mappings, body.duplicate_mode)
    )
    _active_import_tasks[upload_id] = task
    task.add_done_callback(_cleanup)

    return {"id": upload_id, "status": "processing"}


@router.post("/uploads/{upload_id}/pause", status_code=200)
async def pause_import(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Pause a running import. The import will finish its current batch then wait."""
    if upload_id not in _active_import_tasks:
        raise HTTPException(404, "No active import for this upload")

    event = _import_pause_events.get(upload_id)
    if not event:
        raise HTTPException(404, "No active import for this upload")

    event.clear()  # clear = paused

    result = await db.execute(select(UploadHistory).where(UploadHistory.id == upload_id))
    upload = result.scalar_one_or_none()
    if upload:
        upload.status = "paused"
        await db.flush()

    return {"id": upload_id, "status": "paused"}


@router.post("/uploads/{upload_id}/resume", status_code=200)
async def resume_import(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Resume a paused import."""
    if upload_id not in _active_import_tasks:
        raise HTTPException(404, "No active import for this upload")

    event = _import_pause_events.get(upload_id)
    if not event:
        raise HTTPException(404, "No active import for this upload")

    event.set()  # set = running

    result = await db.execute(select(UploadHistory).where(UploadHistory.id == upload_id))
    upload = result.scalar_one_or_none()
    if upload:
        upload.status = "processing"
        await db.flush()

    return {"id": upload_id, "status": "processing"}


@router.post("/uploads/{upload_id}/cancel", status_code=200)
async def cancel_import(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Cancel a running or paused import. Already-inserted rows remain in the database."""
    if upload_id not in _active_import_tasks:
        raise HTTPException(404, "No active import for this upload")

    _import_cancel_flags[upload_id] = True
    # If paused, unpause so the loop can exit
    event = _import_pause_events.get(upload_id)
    if event:
        event.set()

    result = await db.execute(select(UploadHistory).where(UploadHistory.id == upload_id))
    upload = result.scalar_one_or_none()
    if upload:
        upload.status = "cancelled"
        await db.flush()

    return {"id": upload_id, "status": "cancelled"}


@router.get("/uploads/{upload_id}/status")
async def get_upload_status(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Poll this endpoint to track import progress."""
    result = await db.execute(
        select(UploadHistory).where(UploadHistory.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(404, "Upload not found")

    return {
        "id": upload.id,
        "file_name": upload.file_name,
        "status": upload.status,
        "progress": upload.progress,
        "total_rows": upload.total_contacts,
        "processed_rows": upload.processed_rows,
        "inserted_count": upload.inserted_count,
        "skipped_count": upload.skipped_count,
        "overwritten_count": upload.overwritten_count,
        "error_message": upload.error_message,
        "bucket_summary": upload.bucket_summary,
    }


@router.get("/uploads/{upload_id}/headers")
async def get_upload_headers(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """Re-fetch CSV headers from Storage for uploads awaiting mapping."""
    result = await db.execute(
        select(UploadHistory).where(UploadHistory.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(404, "Upload not found")
    if not upload.storage_path:
        raise HTTPException(400, "No storage path — CSV may have been cleaned up")

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/storage/v1/object/{CSV_BUCKET}/{upload.storage_path}",
            headers={
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Range": "bytes=0-8191",
            },
            timeout=30.0,
        )
        if resp.status_code not in (200, 206):
            raise HTTPException(500, "Failed to read CSV from Storage")

    text = resp.text
    lines = text.split("\n")
    lines = [l.strip() for l in lines if l.strip()]

    headers = _parse_csv_line(lines[0])
    preview_rows = [_parse_csv_line(lines[i]) for i in range(1, min(6, len(lines)))]

    return {
        "id": upload.id,
        "file_name": upload.file_name,
        "storage_path": upload.storage_path,
        "total_rows": upload.total_contacts,
        "headers": headers,
        "preview_rows": preview_rows,
    }


@router.delete("/uploads/{upload_id}", status_code=200)
async def delete_upload(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
):
    """
    Delete an upload and its associated data.
    - uploading/pending: delete CSV from Storage + upload record
    - complete/failed: delete all contacts with this upload_id + upload record
    - processing: reject (409) — can't delete while import is running
    """
    result = await db.execute(
        select(UploadHistory).where(UploadHistory.id == upload_id)
    )
    upload = result.scalar_one_or_none()
    if not upload:
        raise HTTPException(404, "Upload not found")

    if upload.status in ("processing", "paused"):
        # Cancel the import first if it's still running
        if upload_id in _active_import_tasks:
            _import_cancel_flags[upload_id] = True
            event = _import_pause_events.get(upload_id)
            if event:
                event.set()
            # Wait briefly for task to finish
            task = _active_import_tasks.get(upload_id)
            if task:
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    task.cancel()

    deleted_contacts = 0

    if upload.status in ("complete", "failed", "cancelled"):
        count_result = await db.execute(
            select(sa_func.count()).select_from(Contact).where(Contact.upload_id == upload_id)
        )
        deleted_contacts = count_result.scalar() or 0

        await db.execute(
            delete(Contact).where(Contact.upload_id == upload_id)
        )

    if upload.storage_path:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{SUPABASE_URL}/storage/v1/object/{CSV_BUCKET}/{upload.storage_path}",
                    headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                    timeout=30.0,
                )
        except Exception:
            pass

    await db.execute(
        delete(UploadHistory).where(UploadHistory.id == upload_id)
    )

    return {
        "id": upload_id,
        "deleted_contacts": deleted_contacts,
        "message": f"Upload deleted. {deleted_contacts} contacts removed." if deleted_contacts else "Upload deleted.",
    }


# ── Background import task ────────────────────────────────────────────────

async def _process_csv_import(
    upload_id: str,
    storage_path: str,
    field_mappings: dict,
    duplicate_mode: str,
):
    """Background task: download CSV from Storage, parse, bulk insert."""
    engine = _bg_engine
    if not engine:
        print(f"[IMPORT] FAILED: no DATABASE_URL configured")
        return

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/storage/v1/object/{CSV_BUCKET}/{storage_path}",
                headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                timeout=120.0,
            )
            if resp.status_code != 200:
                raise Exception(f"Failed to download CSV: {resp.status_code}")

        csv_text = resp.text
        reader = csv.reader(io.StringIO(csv_text))
        all_rows = list(reader)

        if len(all_rows) < 2:
            raise Exception("CSV file is empty or has no data rows")

        csv_headers = [h.strip() for h in all_rows[0]]
        data_rows = all_rows[1:]
        data_rows = [r for r in data_rows if any(cell.strip() for cell in r)]
        total_rows = len(data_rows)

        async with engine.begin() as conn:
            await conn.execute(
                update(UploadHistory.__table__)
                .where(UploadHistory.__table__.c.id == upload_id)
                .values(total_contacts=total_rows, status="processing")
            )

        col_map: dict[int, str] = {}
        for csv_header, target in field_mappings.items():
            if target == "skip" or not target:
                continue
            try:
                idx = csv_headers.index(csv_header)
            except ValueError:
                continue
            col_map[idx] = target

        STANDARD_FIELDS = {
            "contact_id", "first_name", "last_name", "email", "company_website",
            "bucket_name", "classification", "confidence", "reasoning", "cost",
            "status", "lead_list_name", "segment_name", "created_date",
            "industry", "employee_range", "country", "database_provider", "scraper",
        }
        FLOAT_FIELDS = {"confidence", "cost"}

        bucket_names: set[str] = set()
        bucket_target_idx = next((idx for idx, t in col_map.items() if t == "bucket"), None)
        if bucket_target_idx is not None:
            for parsed in data_rows:
                val = parsed[bucket_target_idx].strip() if bucket_target_idx < len(parsed) else ""
                if val:
                    bucket_names.add(val)

        bucket_cache: dict[str, str] = {}
        if bucket_names:
            async with engine.begin() as conn:
                result = await conn.execute(
                    select(OutreachBucket.__table__.c.id, OutreachBucket.__table__.c.name).where(
                        OutreachBucket.__table__.c.user_id == LLOYD_USER_ID,
                        OutreachBucket.__table__.c.name.in_(bucket_names),
                        OutreachBucket.__table__.c.deleted_at.is_(None),
                    )
                )
                for row in result:
                    bucket_cache[row.name] = row.id

                missing = bucket_names - set(bucket_cache.keys())
                if missing:
                    new_buckets = [
                        {"id": str(uuid.uuid4()), "user_id": LLOYD_USER_ID,
                         "name": bname, "total_contacts": 0, "remaining_contacts": 0}
                        for bname in missing
                    ]
                    await conn.execute(OutreachBucket.__table__.insert().values(new_buckets))
                    for b in new_buckets:
                        bucket_cache[b["name"]] = b["id"]

        BATCH_SIZE = 2000
        PROGRESS_INTERVAL = 5000
        inserted = 0
        skipped = 0
        overwritten = 0
        processed = 0
        last_progress_at = 0

        for batch_start in range(0, total_rows, BATCH_SIZE):
            # Check for cancel
            if _import_cancel_flags.get(upload_id, False):
                print(f"[IMPORT] Cancelled: {upload_id} at row {batch_start}")
                async with engine.begin() as conn:
                    await conn.execute(
                        update(UploadHistory.__table__)
                        .where(UploadHistory.__table__.c.id == upload_id)
                        .values(status="cancelled", processed_rows=processed,
                                inserted_count=inserted, skipped_count=skipped,
                                overwritten_count=overwritten)
                    )
                return

            # Check for pause — wait until resumed
            pause_event = _import_pause_events.get(upload_id)
            if pause_event and not pause_event.is_set():
                print(f"[IMPORT] Paused: {upload_id} at row {batch_start}")
                await pause_event.wait()
                # Re-check cancel after resume
                if _import_cancel_flags.get(upload_id, False):
                    print(f"[IMPORT] Cancelled after pause: {upload_id}")
                    async with engine.begin() as conn:
                        await conn.execute(
                            update(UploadHistory.__table__)
                            .where(UploadHistory.__table__.c.id == upload_id)
                            .values(status="cancelled", processed_rows=processed,
                                    inserted_count=inserted, skipped_count=skipped,
                                    overwritten_count=overwritten)
                        )
                    return
                print(f"[IMPORT] Resumed: {upload_id}")

            batch_rows = data_rows[batch_start:batch_start + BATCH_SIZE]
            rows_to_insert = []

            for parsed in batch_rows:
                contact: dict = {
                    "id": str(uuid.uuid4()),
                    "user_id": LLOYD_USER_ID,
                    "upload_id": upload_id,
                    "bucket_id": None,
                    "custom_data": {},
                }
                for f in STANDARD_FIELDS:
                    contact[f] = None

                custom_data: dict = {}
                for col_idx, target in col_map.items():
                    value = parsed[col_idx].strip() if col_idx < len(parsed) else ""
                    if not value:
                        continue
                    if target == "bucket":
                        contact["bucket_name"] = value
                        contact["bucket_id"] = bucket_cache.get(value)
                    elif target in FLOAT_FIELDS:
                        try:
                            contact[target] = float(value)
                        except (ValueError, TypeError):
                            contact[target] = None
                    elif target.startswith("custom:"):
                        custom_data[target[7:]] = value
                    else:
                        contact[target] = value

                if custom_data:
                    contact["custom_data"] = custom_data
                rows_to_insert.append(contact)

            if not rows_to_insert:
                processed += len(batch_rows)
                continue

            async with engine.begin() as conn:
                try:
                    stmt = pg_insert(Contact.__table__).values(rows_to_insert)
                    if duplicate_mode == "overwrite":
                        set_cols = {
                            c.name: getattr(stmt.excluded, c.name)
                            for c in Contact.__table__.columns
                            if c.name not in ("id", "user_id", "email", "created_at")
                        }
                        stmt = stmt.on_conflict_do_update(constraint="uq_contacts_user_email", set_=set_cols)
                        result = await conn.execute(stmt)
                        overwritten += result.rowcount
                    else:
                        stmt = stmt.on_conflict_do_nothing(constraint="uq_contacts_user_email")
                        result = await conn.execute(stmt)
                        batch_inserted = result.rowcount
                        inserted += batch_inserted
                        skipped += len(rows_to_insert) - batch_inserted
                except Exception as e:
                    print(f"[IMPORT] Batch error at row {batch_start}: {e}")
                    traceback.print_exc()
                    skipped += len(rows_to_insert)

            processed += len(batch_rows)

            if processed - last_progress_at >= PROGRESS_INTERVAL or processed >= total_rows:
                last_progress_at = processed
                progress_pct = min(99, int((processed / total_rows) * 100))
                async with engine.begin() as conn:
                    await conn.execute(
                        update(UploadHistory.__table__)
                        .where(UploadHistory.__table__.c.id == upload_id)
                        .values(progress=progress_pct, processed_rows=processed,
                                inserted_count=inserted, skipped_count=skipped,
                                overwritten_count=overwritten)
                    )
            await asyncio.sleep(0)

        # Recalculate bucket counts
        async with engine.begin() as conn:
            touched_bucket_ids = list(bucket_cache.values()) if bucket_cache else []
            if touched_bucket_ids:
                bucket_counts = await conn.execute(
                    select(Contact.__table__.c.bucket_id,
                           sa_func.count(Contact.__table__.c.id).label("cnt"))
                    .where(Contact.__table__.c.user_id == LLOYD_USER_ID,
                           Contact.__table__.c.bucket_id.in_(touched_bucket_ids))
                    .group_by(Contact.__table__.c.bucket_id)
                )
                count_map = {row.bucket_id: row.cnt for row in bucket_counts}
            else:
                count_map = {}

            buckets_result = await conn.execute(
                select(OutreachBucket.__table__.c.id, OutreachBucket.__table__.c.name,
                       OutreachBucket.__table__.c.countries, OutreachBucket.__table__.c.emp_range)
                .where(OutreachBucket.__table__.c.user_id == LLOYD_USER_ID,
                       OutreachBucket.__table__.c.deleted_at.is_(None))
            )
            bucket_summary = []
            for b in buckets_result:
                if b.id in count_map:
                    await conn.execute(
                        update(OutreachBucket.__table__)
                        .where(OutreachBucket.__table__.c.id == b.id)
                        .values(total_contacts=count_map[b.id], remaining_contacts=count_map[b.id])
                    )
                real_count = count_map.get(b.id, 0)
                bucket_summary.append({"name": b.name, "count": real_count,
                    "countries": b.countries or [], "empRanges": [b.emp_range] if b.emp_range else [],
                    "avgConfidence": 0})

            await conn.execute(
                update(UploadHistory.__table__)
                .where(UploadHistory.__table__.c.id == upload_id)
                .values(status="complete", progress=100, processed_rows=total_rows,
                        inserted_count=inserted, skipped_count=skipped, overwritten_count=overwritten,
                        total_buckets=len(bucket_summary),
                        bucket_summary=sorted(bucket_summary, key=lambda x: x["count"], reverse=True))
            )

        # Cleanup CSV from Storage
        try:
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{SUPABASE_URL}/storage/v1/object/{CSV_BUCKET}/{storage_path}",
                    headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                    timeout=30.0,
                )
            print(f"[IMPORT] Cleaned up: {storage_path}")
        except Exception:
            print(f"[IMPORT] Warning: cleanup failed for {storage_path}")

        print(f"[IMPORT] Done: {upload_id} — {inserted} inserted, {skipped} skipped, {overwritten} overwritten")

    except Exception as e:
        print(f"[IMPORT] FAILED: {upload_id} — {e}")
        traceback.print_exc()
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    update(UploadHistory.__table__)
                    .where(UploadHistory.__table__.c.id == upload_id)
                    .values(status="failed", error_message=str(e)[:500])
                )
        except Exception:
            pass
