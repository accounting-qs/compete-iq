"""040_add_webinar_calendar_invites

Per-webinar "Added to Calendar" CSV ingestion. Two tables:

- webinar_calendar_uploads: one row per CSV upload (batch / status tracker).
- webinar_calendar_invites: one row per CSV record. Upsert key is
  (webinar_id, email): re-uploading the same email for the same webinar
  updates the row; the same email across different webinars yields
  independent rows.

matched_assignment_id is nullable; NULL = "No List Data" (no matching
contact in any of that webinar's assigned lists at insert time).

Revision ID: 040
Revises: 039
"""
from alembic import op


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS webinar_calendar_uploads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            webinar_id UUID NOT NULL REFERENCES webinars(id) ON DELETE CASCADE,
            file_name TEXT NOT NULL,
            storage_path TEXT,
            has_responses BOOLEAN NOT NULL DEFAULT false,
            total_rows INTEGER NOT NULL DEFAULT 0,
            processed_rows INTEGER NOT NULL DEFAULT 0,
            matched_count INTEGER NOT NULL DEFAULT 0,
            unmatched_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            progress INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            CONSTRAINT ck_wcu_status CHECK (
                status IN ('pending', 'uploading', 'processing', 'paused', 'complete', 'failed', 'cancelled')
            )
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wcu_user ON webinar_calendar_uploads (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wcu_webinar ON webinar_calendar_uploads (webinar_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wcu_created ON webinar_calendar_uploads (created_at DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS webinar_calendar_invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            upload_id UUID NOT NULL REFERENCES webinar_calendar_uploads(id) ON DELETE CASCADE,
            webinar_id UUID NOT NULL REFERENCES webinars(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            calendar_invited_date TIMESTAMPTZ,
            calendar_account TEXT,
            calendar_account_prefix TEXT,
            calendar_webinar_series INTEGER,
            calendar_invite_response TEXT,
            matched_assignment_id UUID REFERENCES webinar_list_assignments(id) ON DELETE SET NULL,
            matched_contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_wci_webinar_email UNIQUE (webinar_id, email)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wci_webinar_email ON webinar_calendar_invites (webinar_id, email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wci_webinar_assignment ON webinar_calendar_invites (webinar_id, matched_assignment_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wci_webinar_account ON webinar_calendar_invites (webinar_id, calendar_account)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wci_webinar_response ON webinar_calendar_invites (webinar_id, calendar_invite_response)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wci_upload ON webinar_calendar_invites (upload_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webinar_calendar_invites")
    op.execute("DROP TABLE IF EXISTS webinar_calendar_uploads")
