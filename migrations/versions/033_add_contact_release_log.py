"""033_add_contact_release_log

Audit table for "release unused contacts" — one row per contact released back
to the bucket pool after a webinar. Captures prior status so a future
authentication layer can attribute releases to a user and offer undo.

Revision ID: 033
Revises: 032
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_release_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("webinar_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("webinars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("release_batch_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("released_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("prior_status", sa.String(20), nullable=False),
        sa.Column("prior_assignment_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("prior_bucket_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("prior_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("prior_status IN ('assigned', 'used')", name="ck_release_log_prior_status"),
    )
    op.create_index("ix_release_log_user", "contact_release_log", ["user_id"])
    op.create_index("ix_release_log_webinar", "contact_release_log", ["webinar_id"])
    op.create_index("ix_release_log_batch", "contact_release_log", ["release_batch_id"])
    op.create_index("ix_release_log_email", "contact_release_log", ["user_id", "email"])


def downgrade() -> None:
    op.drop_index("ix_release_log_email", table_name="contact_release_log")
    op.drop_index("ix_release_log_batch", table_name="contact_release_log")
    op.drop_index("ix_release_log_webinar", table_name="contact_release_log")
    op.drop_index("ix_release_log_user", table_name="contact_release_log")
    op.drop_table("contact_release_log")
