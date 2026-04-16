"""015_add_copy_generation_jobs

Add a bucket_copy_generation_jobs table to track async/background copy
generation per (bucket, copy_type). Lets generation survive browser
navigation: frontend polls status, rather than awaiting a long HTTP call.

Revision ID: 015
Revises: 014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bucket_copy_generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bucket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("outreach_buckets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("copy_type", sa.String(20), nullable=False),
        sa.Column("variant_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("copy_type IN ('title', 'description')", name="ck_copy_gen_jobs_type"),
        sa.CheckConstraint("status IN ('pending', 'generating', 'done', 'failed')", name="ck_copy_gen_jobs_status"),
    )
    op.create_index("ix_copy_gen_jobs_user", "bucket_copy_generation_jobs", ["user_id"])
    op.create_index("ix_copy_gen_jobs_bucket_type", "bucket_copy_generation_jobs", ["bucket_id", "copy_type"])
    op.create_index("ix_copy_gen_jobs_status", "bucket_copy_generation_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_copy_gen_jobs_status", table_name="bucket_copy_generation_jobs")
    op.drop_index("ix_copy_gen_jobs_bucket_type", table_name="bucket_copy_generation_jobs")
    op.drop_index("ix_copy_gen_jobs_user", table_name="bucket_copy_generation_jobs")
    op.drop_table("bucket_copy_generation_jobs")
