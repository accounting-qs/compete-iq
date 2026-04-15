"""011_add_primary_picked_by_user

Track whether a primary variant was explicitly picked by the user
vs auto-assigned during generation.

Revision ID: 011
Revises: 010
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bucket_copies",
        sa.Column("primary_picked_by_user", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("bucket_copies", "primary_picked_by_user")
