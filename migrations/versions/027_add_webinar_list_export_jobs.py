"""027_add_webinar_list_export_jobs

Track background CSV export jobs per webinar, so the build survives browser
navigation: frontend polls status, then downloads the ready CSV.

Revision ID: 027
Revises: 026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webinar_list_export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("webinar_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("webinars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("contact_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("csv_content", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="ck_wle_jobs_status"),
    )
    op.create_index("ix_wle_jobs_user", "webinar_list_export_jobs", ["user_id"])
    op.create_index("ix_wle_jobs_webinar", "webinar_list_export_jobs", ["webinar_id"])
    op.create_index("ix_wle_jobs_status", "webinar_list_export_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_wle_jobs_status", table_name="webinar_list_export_jobs")
    op.drop_index("ix_wle_jobs_webinar", table_name="webinar_list_export_jobs")
    op.drop_index("ix_wle_jobs_user", table_name="webinar_list_export_jobs")
    op.drop_table("webinar_list_export_jobs")
