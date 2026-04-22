"""025_ghl_sync_progress

Add expected_total column to ghl_sync_run so the UI can show
contacts_synced / expected_total + ETA while a sync is running.

Revision ID: 025
Revises: 024
"""
from alembic import op


revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ghl_sync_run ADD COLUMN IF NOT EXISTS expected_total INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE ghl_sync_run DROP COLUMN IF EXISTS expected_total")
