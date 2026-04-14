"""008_upgrade_upload_history

Add progress tracking, field_mappings, storage_path columns to upload_history.
Drop and recreate since no important data exists.

Revision ID: 008
Revises: 007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old constraint
    op.drop_constraint("ck_upload_history_status", "upload_history", type_="check")

    # Add new columns
    op.add_column("upload_history", sa.Column("storage_path", sa.Text()))
    op.add_column("upload_history", sa.Column("field_mappings", postgresql.JSONB()))
    op.add_column("upload_history", sa.Column("duplicate_mode", sa.String(20), nullable=False, server_default="ignore"))
    op.add_column("upload_history", sa.Column("progress", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("upload_history", sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("upload_history", sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("upload_history", sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("upload_history", sa.Column("overwritten_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("upload_history", sa.Column("error_message", sa.Text()))

    # Update default status from 'processing' to 'pending'
    op.alter_column("upload_history", "status", server_default="pending")

    # Add new constraint with expanded status options
    op.create_check_constraint(
        "ck_upload_history_status", "upload_history",
        "status IN ('pending', 'uploading', 'processing', 'complete', 'failed')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_upload_history_status", "upload_history", type_="check")

    op.drop_column("upload_history", "error_message")
    op.drop_column("upload_history", "overwritten_count")
    op.drop_column("upload_history", "skipped_count")
    op.drop_column("upload_history", "inserted_count")
    op.drop_column("upload_history", "processed_rows")
    op.drop_column("upload_history", "progress")
    op.drop_column("upload_history", "duplicate_mode")
    op.drop_column("upload_history", "field_mappings")
    op.drop_column("upload_history", "storage_path")

    op.alter_column("upload_history", "status", server_default="processing")
    op.create_check_constraint(
        "ck_upload_history_status", "upload_history",
        "status IN ('processing', 'complete', 'failed')"
    )
