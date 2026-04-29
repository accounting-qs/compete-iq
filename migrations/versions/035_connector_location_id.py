"""035_connector_location_id

Add `location_id` column to connector_credentials so the GHL connector can
store the pair of values it needs (api_key + location_id) instead of being
configured exclusively via env vars.

Revision ID: 035
Revises: 034
"""
from alembic import op


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE connector_credentials ADD COLUMN IF NOT EXISTS location_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE connector_credentials DROP COLUMN IF EXISTS location_id")
