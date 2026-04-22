"""026_ghl_contact_extra_fields

Add fallback/auxiliary GHL custom fields on ghl_contact for more robust
metric computation (less reliance on regex-parsing free-text history fields).

Adds:
- calendar_invite_response_prefix (TEXT)  — narrower variant of history
- calendar_invite_response_prefix_non_joiners (TEXT)
- webinar_registration_number (INTEGER)  — numeric counterpart of in_form_date
- zoom_webinar_series_latest (INTEGER)
- zoom_webinar_series_registered_total_count (INTEGER)
- zoom_webinar_series_attended_total_count (INTEGER)
- zoom_time_in_session_minutes (INTEGER)
- zoom_viewing_time_in_minutes_total (INTEGER)
- zoom_attended (TEXT)
- book_campaign_source (TEXT)
- book_campaign_medium (TEXT)
- book_campaign_name (TEXT)
- registration_campaign_source (TEXT)
- registration_campaign_medium (TEXT)
- registration_campaign_name (TEXT)

Revision ID: 026
Revises: 025
"""
from alembic import op


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


COLUMNS = [
    ("calendar_invite_response_prefix", "TEXT"),
    ("calendar_invite_response_prefix_non_joiners", "TEXT"),
    ("webinar_registration_number", "INTEGER"),
    ("zoom_webinar_series_latest", "INTEGER"),
    ("zoom_webinar_series_registered_total_count", "INTEGER"),
    ("zoom_webinar_series_attended_total_count", "INTEGER"),
    ("zoom_time_in_session_minutes", "INTEGER"),
    ("zoom_viewing_time_in_minutes_total", "INTEGER"),
    ("zoom_attended", "TEXT"),
    ("book_campaign_source", "TEXT"),
    ("book_campaign_medium", "TEXT"),
    ("book_campaign_name", "TEXT"),
    ("registration_campaign_source", "TEXT"),
    ("registration_campaign_medium", "TEXT"),
    ("registration_campaign_name", "TEXT"),
]


def upgrade() -> None:
    for name, typ in COLUMNS:
        op.execute(f"ALTER TABLE ghl_contact ADD COLUMN IF NOT EXISTS {name} {typ}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_contact_webinar_reg_num ON ghl_contact (webinar_registration_number)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ghl_contact_webinar_reg_num")
    for name, _ in COLUMNS:
        op.execute(f"ALTER TABLE ghl_contact DROP COLUMN IF EXISTS {name}")
