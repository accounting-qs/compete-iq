"""021_expand_wg_webinars

Add broadcast stats columns to webinargeek_webinars so the Broadcasts
table in the Connectors UI can show subscriber/viewer counts + status
without a live API round-trip per row.

Revision ID: 021
Revises: 020
"""
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE webinargeek_webinars ADD COLUMN IF NOT EXISTS internal_title TEXT")
    op.execute("ALTER TABLE webinargeek_webinars ADD COLUMN IF NOT EXISTS duration_seconds INTEGER")
    op.execute("ALTER TABLE webinargeek_webinars ADD COLUMN IF NOT EXISTS subscriptions_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE webinargeek_webinars ADD COLUMN IF NOT EXISTS live_viewers_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE webinargeek_webinars ADD COLUMN IF NOT EXISTS replay_viewers_count INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE webinargeek_webinars ADD COLUMN IF NOT EXISTS has_ended BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE webinargeek_webinars ADD COLUMN IF NOT EXISTS cancelled BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    for col in ("cancelled", "has_ended", "replay_viewers_count",
                "live_viewers_count", "subscriptions_count",
                "duration_seconds", "internal_title"):
        op.execute(f"ALTER TABLE webinargeek_webinars DROP COLUMN IF EXISTS {col}")
