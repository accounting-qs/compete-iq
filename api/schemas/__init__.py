"""
Pydantic schemas for the outreach API.
Shared across all outreach sub-routers.
"""

import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Buckets ────────────────────────────────────────────────────────────────

class BucketCreate(BaseModel):
    name: str
    industry: str | None = None
    total_contacts: int = 0
    remaining_contacts: int | None = None
    countries: list[str] = []
    emp_range: str | None = None
    source_file: str | None = None

class BucketUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    total_contacts: int | None = None
    remaining_contacts: int | None = None
    countries: list[str] | None = None
    emp_range: str | None = None


# ── Copies ─────────────────────────────────────────────────────────────────

class CopyGenerateRequest(BaseModel):
    copy_type: str = Field(..., pattern="^(title|description|both)$")
    variant_count: int = Field(3, ge=1, le=10)

class CopyUpdate(BaseModel):
    text: str | None = None
    is_primary: bool | None = None

class CopyRegenerateRequest(BaseModel):
    feedback: str


# ── Senders ────────────────────────────────────────────────────────────────

class SenderCreate(BaseModel):
    name: str
    total_accounts: int = 0
    send_per_account: int = 50
    days_per_webinar: int = 5
    color: str | None = None

class SenderUpdate(BaseModel):
    name: str | None = None
    total_accounts: int | None = None
    send_per_account: int | None = None
    days_per_webinar: int | None = None
    color: str | None = None
    is_active: bool | None = None


# ── Webinars ───────────────────────────────────────────────────────────────

class WebinarCreate(BaseModel):
    number: int
    date: datetime.date

class WebinarUpdate(BaseModel):
    number: int | None = None
    date: Optional[datetime.date] = None
    status: str | None = None
    broadcast_id: str | None = None
    main_title: str | None = None
    registration_link: str | None = None
    unsubscribe_link: str | None = None


# ── Assignments ────────────────────────────────────────────────────────────

class AssignRequest(BaseModel):
    bucket_id: str
    sender_id: str
    volume: int
    accounts_used: int = 0
    send_per_account: int | None = None
    days: int | None = None
    countries_override: str | None = None
    emp_range_override: str | None = None

class AssignmentUpdate(BaseModel):
    title_copy_id: str | None = None
    desc_copy_id: str | None = None
    accounts_used: int | None = None
    volume: int | None = None
    remaining: int | None = None
    list_url: str | None = None
    gcal_invited: int | None = None


# ── Uploads ────────────────────────────────────────────────────────────────

class UploadFileResponse(BaseModel):
    id: str
    file_name: str
    storage_path: str
    total_rows: int
    headers: list[str]
    preview_rows: list[list[str]]

class ImportStartCreate(BaseModel):
    field_mappings: dict[str, str]  # CSV header -> system field
    duplicate_mode: str = "ignore"  # "ignore" | "overwrite"


# ── Custom Fields ──────────────────────────────────────────────────────────

class CustomFieldCreate(BaseModel):
    field_name: str
    field_type: str = "text"  # text, number, date, boolean
