"""011_add_primary_picked_by_user

Track whether a primary variant was explicitly picked by the user
vs auto-assigned during generation.

Revision ID: 011
Revises: 010
"""
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE bucket_copies ADD COLUMN IF NOT EXISTS primary_picked_by_user BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.drop_column("bucket_copies", "primary_picked_by_user")
