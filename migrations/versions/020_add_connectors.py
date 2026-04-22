"""020_add_connectors

WebinarGeek connector: credentials, cached webinars list, synced subscribers.

Revision ID: 020
Revises: 019
"""
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS connector_credentials (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider VARCHAR(50) NOT NULL UNIQUE,
            api_key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS webinargeek_webinars (
            broadcast_id VARCHAR(64) PRIMARY KEY,
            webinar_id VARCHAR(64),
            name TEXT NOT NULL,
            starts_at TIMESTAMPTZ,
            raw JSONB,
            last_synced_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS webinargeek_subscribers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broadcast_id VARCHAR(64) NOT NULL REFERENCES webinargeek_webinars(broadcast_id) ON DELETE CASCADE,
            subscriber_id VARCHAR(64),
            email TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            company TEXT,
            job_title TEXT,
            phone TEXT,
            city TEXT,
            country TEXT,
            timezone TEXT,
            registration_source TEXT,
            subscribed_at TIMESTAMPTZ,
            unsubscribed_at TIMESTAMPTZ,
            unsubscribe_source TEXT,
            watched_live BOOLEAN,
            watched_replay BOOLEAN,
            start_time TIMESTAMPTZ,
            end_time TIMESTAMPTZ,
            minutes_viewing INTEGER,
            viewing_country TEXT,
            viewing_device TEXT,
            watch_link TEXT,
            raw JSONB,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (broadcast_id, email)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wg_subs_broadcast ON webinargeek_subscribers (broadcast_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wg_subs_email ON webinargeek_subscribers (email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webinargeek_subscribers")
    op.execute("DROP TABLE IF EXISTS webinargeek_webinars")
    op.execute("DROP TABLE IF EXISTS connector_credentials")
