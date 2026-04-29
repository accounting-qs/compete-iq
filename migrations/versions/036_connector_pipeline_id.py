"""036_connector_pipeline_id

Add `pipeline_id` column to connector_credentials so the GHL connector
can store the pipeline used for opportunity streaming. Optional — GHL
contact sync works without it; opportunity sync needs it.

Revision ID: 036
Revises: 035
"""
from alembic import op


revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE connector_credentials ADD COLUMN IF NOT EXISTS pipeline_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE connector_credentials DROP COLUMN IF EXISTS pipeline_id")
