"""Add multi-format content engine tables

New tables:
  - universal_brain      (one row per user — QS business context document)
  - format_brains        (one row per format — rules, output schema, examples)
  - content_runs         (a generation session, single or batch)
  - content_pieces       (individual generated output within a run)
  - content_piece_versions (immutable version history with feedback)
  - brain_updates        (audit log of brain changes + confirmation flow)

Also: remove duplicate index on whatsapp_sessions.phone_number.

Existing tables (creative_concepts, generated_outputs, etc.) are preserved
as legacy — they back the WhatsApp ad flow and are not touched here.

Revision ID: 003
Revises: 002
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------------
    # Remove duplicate index on whatsapp_sessions.phone_number
    # (unique=True on the column already creates an index)
    # ---------------------------------------------------------------------------
    # Use raw SQL with IF EXISTS — the named index may not exist if the original
    # schema used unique=True (which creates an implicit index, not a named one).
    op.execute("DROP INDEX IF EXISTS ix_whatsapp_sessions_phone_number")

    # ---------------------------------------------------------------------------
    # universal_brain — one row per user, update in place
    # ---------------------------------------------------------------------------
    op.create_table(
        "universal_brain",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brain_content", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_universal_brain_user_id", "universal_brain", ["user_id"])
    op.create_index("ix_universal_brain_user_id", "universal_brain", ["user_id"])

    # ---------------------------------------------------------------------------
    # format_brains — one row per format per user
    # ---------------------------------------------------------------------------
    op.create_table(
        "format_brains",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format_key", sa.String(), nullable=False),  # 'facebook_ad', 'event_description', 'vsl'
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("brain_content", sa.Text()),            # format-specific rules for prompt injection
        sa.Column("output_schema", postgresql.JSONB()),   # [{key, label, type}, ...] — sub-field definitions
        sa.Column("example_outputs", postgresql.JSONB()), # array of example outputs for few-shot prompting
        sa.Column("brain_quality", sa.String(), nullable=False, server_default="'empty'"),  # 'empty','partial','ready'
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("brain_quality IN ('empty', 'partial', 'ready')", name="ck_format_brains_quality"),
    )
    op.create_unique_constraint("uq_format_brains_user_format", "format_brains", ["user_id", "format_key"])
    op.create_index("ix_format_brains_user_id", "format_brains", ["user_id"])
    op.create_index("ix_format_brains_format_key", "format_brains", ["format_key"])

    # ---------------------------------------------------------------------------
    # content_runs — a generation session (single or batch)
    # ---------------------------------------------------------------------------
    op.create_table(
        "content_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format_brain_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("format_brains.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(), nullable=False, server_default="'pending'"),
        sa.Column("input_type", sa.String(), nullable=False),  # 'url', 'text', 'batch'
        sa.Column("raw_input", postgresql.JSONB()),  # full input: {url, text, items:[{industry, segment, context}]}
        sa.Column("items_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'generating', 'completed', 'failed')",
            name="ck_content_runs_status"
        ),
        sa.CheckConstraint(
            "input_type IN ('url', 'text', 'batch')",
            name="ck_content_runs_input_type"
        ),
    )
    op.create_index("ix_content_runs_user_id", "content_runs", ["user_id"])
    op.create_index("ix_content_runs_format_brain_id", "content_runs", ["format_brain_id"])
    op.create_index("ix_content_runs_status", "content_runs", ["status"])
    op.create_index("ix_content_runs_created_at", "content_runs", ["created_at"])

    # ---------------------------------------------------------------------------
    # content_pieces — individual generated output within a run
    # ---------------------------------------------------------------------------
    op.create_table(
        "content_pieces",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("content_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format_brain_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("format_brains.id", ondelete="SET NULL")),
        sa.Column("input_item", postgresql.JSONB()),     # {industry, segment, context, url} — the input that produced this piece
        sa.Column("sub_fields", postgresql.JSONB()),     # {title: '...', description: '...'} — current version content
        sa.Column("status", sa.String(), nullable=False, server_default="'draft'"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_competitor_ad_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("competitor_ads.id", ondelete="SET NULL")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('generating', 'draft', 'locked')",
            name="ck_content_pieces_status"
        ),
    )
    op.create_index("ix_content_pieces_user_id", "content_pieces", ["user_id"])
    op.create_index("ix_content_pieces_run_id", "content_pieces", ["run_id"])
    op.create_index("ix_content_pieces_format_brain_id", "content_pieces", ["format_brain_id"])
    op.create_index("ix_content_pieces_status", "content_pieces", ["status"])
    op.create_index("ix_content_pieces_source_ad_id", "content_pieces", ["source_competitor_ad_id"])
    # Composite for Library view: user + status + created_at
    op.create_index("ix_content_pieces_library", "content_pieces", ["user_id", "status", "created_at"])

    # ---------------------------------------------------------------------------
    # content_piece_versions — immutable version history
    # ---------------------------------------------------------------------------
    op.create_table(
        "content_piece_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("piece_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("content_pieces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("sub_fields", postgresql.JSONB(), nullable=False),  # snapshot of all sub-fields at this version
        sa.Column("feedback_text", sa.Text()),      # what Lloyd typed to trigger this version
        sa.Column("active_sub_field", sa.String()), # which sub-field was targeted (NULL = whole piece)
        sa.Column("brain_promoted", sa.Boolean(), nullable=False, server_default="false"),  # feedback → brain?
        sa.Column("prompt_version", sa.String(), nullable=False, server_default="'v1'"),
        sa.Column("model_used", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_content_piece_version", "content_piece_versions", ["piece_id", "version_number"]
    )
    op.create_index("ix_content_piece_versions_piece_id", "content_piece_versions", ["piece_id"])

    # ---------------------------------------------------------------------------
    # brain_updates — audit log of brain changes + confirmation flow
    # ---------------------------------------------------------------------------
    op.create_table(
        "brain_updates",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("brain_type", sa.String(), nullable=False),  # 'universal' or 'format'
        sa.Column("format_brain_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("format_brains.id", ondelete="SET NULL")),
        sa.Column("trigger_text", sa.Text()),       # what Lloyd said that triggered this
        sa.Column("proposed_changes", sa.Text()),   # what the system proposed
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),  # NULL until Lloyd confirms
        sa.Column("applied_at", sa.DateTime(timezone=True)),    # NULL until changes written to brain
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "brain_type IN ('universal', 'format')",
            name="ck_brain_updates_brain_type"
        ),
    )
    op.create_index("ix_brain_updates_user_id", "brain_updates", ["user_id"])
    op.create_index("ix_brain_updates_format_brain_id", "brain_updates", ["format_brain_id"])
    op.create_index("ix_brain_updates_brain_type", "brain_updates", ["brain_type"])
    op.create_index("ix_brain_updates_confirmed_at", "brain_updates", ["confirmed_at"])


def downgrade() -> None:
    op.drop_table("brain_updates")
    op.drop_table("content_piece_versions")
    op.drop_table("content_pieces")
    op.drop_table("content_runs")
    op.drop_table("format_brains")
    op.drop_table("universal_brain")

    # Restore the duplicate index (matches original migration 001)
    op.create_index("ix_whatsapp_sessions_phone_number", "whatsapp_sessions", ["phone_number"])
