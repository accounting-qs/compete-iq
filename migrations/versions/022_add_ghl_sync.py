"""022_add_ghl_sync

GoHighLevel sync: contacts, opportunities, sync-run log, settings.

Revision ID: 022
Revises: 021
"""
from alembic import op


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ghl_contact (
            ghl_contact_id TEXT PRIMARY KEY,
            email TEXT,
            date_added TIMESTAMPTZ,
            calendar_invite_response_history TEXT,
            calendar_webinar_series_history TEXT,
            calendar_webinar_series_non_joiners TEXT,
            is_booked_call TEXT,
            booked_call_webinar_series INTEGER,
            webinar_registration_in_form_date DATE,
            cold_calendar_unsubscribe_date DATE,
            has_sms_click_tag BOOLEAN NOT NULL DEFAULT FALSE,
            tags JSONB,
            raw_custom_fields JSONB,
            created_at_ghl TIMESTAMPTZ,
            updated_at_ghl TIMESTAMPTZ,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_contact_email ON ghl_contact (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_contact_booked_series ON ghl_contact (booked_call_webinar_series)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_contact_self_reg_date ON ghl_contact (webinar_registration_in_form_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_contact_unsub_date ON ghl_contact (cold_calendar_unsubscribe_date)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ghl_opportunity (
            ghl_opportunity_id TEXT PRIMARY KEY,
            ghl_contact_id TEXT,
            pipeline_stage_id TEXT,
            monetary_value NUMERIC(12, 2),
            call1_appointment_status TEXT,
            call1_appointment_date TIMESTAMPTZ,
            webinar_source_number INTEGER,
            lead_quality TEXT,
            projected_deal_size_option TEXT,
            projected_deal_size_value INTEGER,
            raw_custom_fields JSONB,
            created_at_ghl TIMESTAMPTZ,
            updated_at_ghl TIMESTAMPTZ,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_opp_webinar ON ghl_opportunity (webinar_source_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_opp_contact ON ghl_opportunity (ghl_contact_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_opp_stage ON ghl_opportunity (pipeline_stage_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_opp_lead_quality ON ghl_opportunity (lead_quality)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ghl_sync_run (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sync_type VARCHAR(32) NOT NULL,
            trigger VARCHAR(16) NOT NULL DEFAULT 'scheduled',
            status VARCHAR(16) NOT NULL DEFAULT 'running',
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            duration_seconds INTEGER,
            contacts_synced INTEGER NOT NULL DEFAULT 0,
            opportunities_synced INTEGER NOT NULL DEFAULT 0,
            errors_count INTEGER NOT NULL DEFAULT 0,
            error_details JSONB
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_sync_run_started ON ghl_sync_run (started_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ghl_sync_run_status ON ghl_sync_run (status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ghl_sync_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            incremental_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            incremental_interval_hours INTEGER NOT NULL DEFAULT 3,
            weekly_full_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            weekly_full_day_of_week VARCHAR(3) NOT NULL DEFAULT 'wed',
            weekly_full_hour_local INTEGER NOT NULL DEFAULT 4,
            weekly_full_timezone TEXT NOT NULL DEFAULT 'America/Chicago',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Seed singleton row
    op.execute("INSERT INTO ghl_sync_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ghl_sync_settings")
    op.execute("DROP TABLE IF EXISTS ghl_sync_run")
    op.execute("DROP TABLE IF EXISTS ghl_opportunity")
    op.execute("DROP TABLE IF EXISTS ghl_contact")
