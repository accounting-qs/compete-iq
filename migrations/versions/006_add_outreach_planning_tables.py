"""Add outreach planning tables: buckets, copies, senders, webinars, assignments, usage log, upload history

Revision ID: 006
Revises: 005
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. outreach_buckets ─────────────────────────────────────────────
    op.create_table(
        "outreach_buckets",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("total_contacts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remaining_contacts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("countries", postgresql.JSONB(), server_default="[]"),
        sa.Column("emp_range", sa.Text(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outreach_buckets_user_id", "outreach_buckets", ["user_id"])
    op.create_unique_constraint("uq_outreach_buckets_user_name", "outreach_buckets", ["user_id", "name"])

    # ── 2. bucket_copies ────────────────────────────────────────────────
    op.create_table(
        "bucket_copies",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bucket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("outreach_buckets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("copy_type", sa.String(20), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ai_feedback", sa.Text(), nullable=True),
        sa.Column("generation_batch_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("copy_type IN ('title', 'description')", name="ck_bucket_copies_type"),
    )
    op.create_index("ix_bucket_copies_bucket_type", "bucket_copies", ["bucket_id", "copy_type"])
    op.create_index("ix_bucket_copies_user_id", "bucket_copies", ["user_id"])
    op.create_index("ix_bucket_copies_batch", "bucket_copies", ["generation_batch_id"])

    # ── 3. outreach_senders ─────────────────────────────────────────────
    op.create_table(
        "outreach_senders",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("total_accounts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_per_account", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("days_per_webinar", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outreach_senders_user_id", "outreach_senders", ["user_id"])
    op.create_unique_constraint("uq_outreach_senders_user_name", "outreach_senders", ["user_id", "name"])

    # ── 4. webinars ─────────────────────────────────────────────────────
    op.create_table(
        "webinars",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="planning"),
        sa.Column("broadcast_id", sa.Text(), nullable=True),
        sa.Column("main_title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('planning', 'sent', 'archived')", name="ck_webinars_status"),
    )
    op.create_unique_constraint("uq_webinars_user_number", "webinars", ["user_id", "number"])
    op.create_index("ix_webinars_user_id", "webinars", ["user_id"])
    op.create_index("ix_webinars_status", "webinars", ["status"])

    # ── 5. webinar_list_assignments ──────────────────────────────────────
    op.create_table(
        "webinar_list_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("webinar_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("webinars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bucket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("outreach_buckets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sender_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("outreach_senders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("list_url", sa.Text(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remaining", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gcal_invited", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_per_account", sa.Integer(), nullable=True),
        sa.Column("days", sa.Integer(), nullable=True),
        sa.Column("title_copy_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("bucket_copies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("desc_copy_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("bucket_copies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("countries_override", sa.Text(), nullable=True),
        sa.Column("emp_range_override", sa.Text(), nullable=True),
        sa.Column("is_nonjoiners", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_no_list_data", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wla_webinar_id", "webinar_list_assignments", ["webinar_id"])
    op.create_index("ix_wla_bucket_id", "webinar_list_assignments", ["bucket_id"])
    op.create_index("ix_wla_sender_id", "webinar_list_assignments", ["sender_id"])
    op.create_index("ix_wla_webinar_sender", "webinar_list_assignments", ["webinar_id", "sender_id"])
    op.create_index("ix_wla_user_id", "webinar_list_assignments", ["user_id"])

    # ── 6. copy_usage_log ───────────────────────────────────────────────
    op.create_table(
        "copy_usage_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bucket_copy_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("bucket_copies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("webinar_list_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copy_usage_log_copy", "copy_usage_log", ["bucket_copy_id"])
    op.create_index("ix_copy_usage_log_assignment", "copy_usage_log", ["assignment_id"])

    # ── 7. upload_history ───────────────────────────────────────────────
    op.create_table(
        "upload_history",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("total_contacts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_buckets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bucket_summary", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('processing', 'complete', 'failed')", name="ck_upload_history_status"),
    )
    op.create_index("ix_upload_history_user_id", "upload_history", ["user_id"])


def downgrade() -> None:
    op.drop_table("upload_history")
    op.drop_table("copy_usage_log")
    op.drop_table("webinar_list_assignments")
    op.drop_table("webinars")
    op.drop_table("outreach_senders")
    op.drop_table("bucket_copies")
    op.drop_table("outreach_buckets")
