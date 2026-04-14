"""007_add_contacts_tables

Add contact_custom_fields and contacts tables for Phase 8:
individual contact storage with custom field support and duplicate handling.

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── contact_custom_fields ────────────────────────────────────────────
    op.create_table(
        "contact_custom_fields",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_custom_fields_user_name", "contact_custom_fields", ["user_id", "field_name"]
    )
    op.create_index("ix_custom_fields_user_id", "contact_custom_fields", ["user_id"])

    # ── contacts ─────────────────────────────────────────────────────────
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("upload_history.id", ondelete="SET NULL")),
        sa.Column("bucket_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("outreach_buckets.id", ondelete="SET NULL")),

        # Core identity
        sa.Column("contact_id", sa.Text()),
        sa.Column("first_name", sa.Text()),
        sa.Column("last_name", sa.Text()),
        sa.Column("email", sa.Text()),
        sa.Column("company_website", sa.Text()),

        # Enrichment
        sa.Column("bucket_name", sa.Text()),
        sa.Column("classification", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("reasoning", sa.Text()),
        sa.Column("cost", sa.Float()),
        sa.Column("status", sa.Text()),

        # Source metadata
        sa.Column("lead_list_name", sa.Text()),
        sa.Column("segment_name", sa.Text()),
        sa.Column("created_date", sa.Text()),
        sa.Column("industry", sa.Text()),
        sa.Column("employee_range", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("database_provider", sa.Text()),
        sa.Column("scraper", sa.Text()),

        # Custom fields as JSONB
        sa.Column("custom_data", postgresql.JSONB(), server_default="{}"),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_contacts_user_email", "contacts", ["user_id", "email"])
    op.create_index("ix_contacts_user_id", "contacts", ["user_id"])
    op.create_index("ix_contacts_bucket_id", "contacts", ["bucket_id"])
    op.create_index("ix_contacts_upload_id", "contacts", ["upload_id"])
    op.create_index("ix_contacts_email", "contacts", ["user_id", "email"])


def downgrade() -> None:
    op.drop_table("contacts")
    op.drop_table("contact_custom_fields")
