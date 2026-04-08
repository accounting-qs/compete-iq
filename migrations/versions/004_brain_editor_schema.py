"""Brain Editor schema — principles, examples, case studies

Changes:
  copywriting_principles:
    - Add format_brain_id FK (NULL = universal brain, non-NULL = format brain)
    - Add category, display_order, notion_page_id, deleted_at columns
    - Add source check constraint (authored | feedback_promoted | notion_synced)
    - Widen format_scope from Enum to VARCHAR (supports any format_key string)
    - Add missing indexes

  brain_updates:
    - Change proposed_changes from Text to JSONB (structured diff for Brain Editor UI)

  New tables:
    - source_examples  (individually addressable examples per format brain)
    - case_studies     (verbatim client results, Notion-synced, read-only)

  Note: format_brains.brain_content and example_outputs are DEPRECATED but not
  dropped here — kept as nullable columns until data migration is confirmed complete.

Revision ID: 004
Revises: 003
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # copywriting_principles — add new columns (all nullable — migration safe)
    # -----------------------------------------------------------------------
    op.add_column("copywriting_principles",
        sa.Column("format_brain_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("format_brains.id", ondelete="CASCADE"),
                  nullable=True)
    )
    op.add_column("copywriting_principles",
        sa.Column("category", sa.String(), nullable=True)
    )
    op.add_column("copywriting_principles",
        sa.Column("display_order", sa.Integer(), nullable=True)
    )
    op.add_column("copywriting_principles",
        sa.Column("notion_page_id", sa.String(), nullable=True)
    )
    op.add_column("copywriting_principles",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Unique constraint on notion_page_id — dedup key for Notion sync upserts
    op.create_unique_constraint(
        "uq_copywriting_principles_notion_page_id",
        "copywriting_principles",
        ["notion_page_id"]
    )

    # Check constraint on source — replaces free-text field with controlled values
    op.create_check_constraint(
        "ck_copywriting_principles_source",
        "copywriting_principles",
        "source IN ('authored', 'feedback_promoted', 'notion_synced') OR source IS NULL"
    )

    # Widen format_scope from Enum('ad','vsl','email') to VARCHAR
    # DB is empty so safe to drop-and-recreate rather than ALTER TYPE
    op.drop_column("copywriting_principles", "format_scope")
    op.add_column("copywriting_principles",
        sa.Column("format_scope", sa.String(), nullable=True)
    )

    # New indexes
    op.create_index(
        "ix_copywriting_principles_format_brain_id",
        "copywriting_principles", ["format_brain_id"]
    )
    op.create_index(
        "ix_copywriting_principles_category",
        "copywriting_principles", ["category"]
    )
    op.create_index(
        "ix_copywriting_principles_deleted_at",
        "copywriting_principles", ["deleted_at"]
    )

    # Drop the now-unused format_scope enum type
    op.execute("DROP TYPE IF EXISTS format_scope")

    # -----------------------------------------------------------------------
    # brain_updates — proposed_changes: Text → JSONB
    # Stores structured diffs: [{action, principle_text, category}, ...]
    # DB is empty so safe to drop-and-recreate
    # -----------------------------------------------------------------------
    op.drop_column("brain_updates", "proposed_changes")
    op.add_column("brain_updates",
        sa.Column("proposed_changes", postgresql.JSONB(), nullable=True)
    )

    # -----------------------------------------------------------------------
    # source_examples — individually addressable examples per format brain
    # Replaces format_brains.example_outputs (JSONB blob, now deprecated)
    # -----------------------------------------------------------------------
    op.create_table(
        "source_examples",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format_brain_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("format_brains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("notion_page_id", sa.String(), nullable=True, unique=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_examples_user_id", "source_examples", ["user_id"])
    op.create_index("ix_source_examples_format_brain_id", "source_examples", ["format_brain_id"])
    op.create_index("ix_source_examples_deleted_at", "source_examples", ["deleted_at"])

    # -----------------------------------------------------------------------
    # case_studies — verbatim client results, Notion-synced, read-only by system
    # No soft delete — Notion is source of truth, re-sync restores if deleted
    # -----------------------------------------------------------------------
    op.create_table(
        "case_studies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("client_name", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("notion_page_id", sa.String(), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_case_studies_user_id", "case_studies", ["user_id"])
    op.create_index("ix_case_studies_notion_page_id", "case_studies", ["notion_page_id"])


def downgrade() -> None:
    # Drop new tables
    op.drop_table("case_studies")
    op.drop_table("source_examples")

    # Revert brain_updates.proposed_changes to Text
    op.drop_column("brain_updates", "proposed_changes")
    op.add_column("brain_updates",
        sa.Column("proposed_changes", sa.Text(), nullable=True)
    )

    # Revert copywriting_principles changes
    op.drop_index("ix_copywriting_principles_deleted_at", "copywriting_principles")
    op.drop_index("ix_copywriting_principles_category", "copywriting_principles")
    op.drop_index("ix_copywriting_principles_format_brain_id", "copywriting_principles")
    op.drop_constraint("uq_copywriting_principles_notion_page_id", "copywriting_principles")
    op.drop_constraint("ck_copywriting_principles_source", "copywriting_principles")
    op.drop_column("copywriting_principles", "deleted_at")
    op.drop_column("copywriting_principles", "notion_page_id")
    op.drop_column("copywriting_principles", "display_order")
    op.drop_column("copywriting_principles", "category")
    op.drop_column("copywriting_principles", "format_brain_id")
    op.drop_column("copywriting_principles", "format_scope")

    # Restore format_scope as Enum
    op.execute("CREATE TYPE format_scope AS ENUM ('ad', 'vsl', 'email')")
    op.add_column("copywriting_principles",
        sa.Column("format_scope",
                  postgresql.ENUM("ad", "vsl", "email", name="format_scope", create_type=False),
                  nullable=True)
    )
