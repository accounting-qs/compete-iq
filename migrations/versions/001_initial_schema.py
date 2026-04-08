"""Initial schema — all 13 tables

Revision ID: 001
Revises:
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("display_name", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- competitors ---
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("handle", sa.String(), nullable=False),
        sa.Column("display_name", sa.String()),
        sa.Column("meta_page_id", sa.String()),
        sa.Column("is_tracked", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_competitors_user_handle", "competitors", ["user_id", "handle"])
    op.create_index("ix_competitors_user_id", "competitors", ["user_id"])

    # --- scrape_jobs ---
    op.create_table(
        "scrape_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", name="scrape_job_status"), nullable=False, server_default="pending"),
        sa.Column("apify_run_id", sa.String()),
        sa.Column("ads_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_ads_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scrape_jobs_competitor_id", "scrape_jobs", ["competitor_id"])
    op.create_index("ix_scrape_jobs_user_id", "scrape_jobs", ["user_id"])
    op.create_index("ix_scrape_jobs_status", "scrape_jobs", ["status"])

    # --- competitor_ads ---
    op.create_table(
        "competitor_ads",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ad_library_id", sa.String(), nullable=False, unique=True),
        sa.Column("ad_type", sa.Enum("video", "image", "carousel", name="ad_type"), nullable=False),
        sa.Column("ad_text", sa.Text()),
        sa.Column("video_cdn_url", sa.Text()),
        sa.Column("video_cdn_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("video_r2_key", sa.String()),
        sa.Column("carousel_image_r2_keys", postgresql.JSONB()),
        sa.Column("transcript", sa.Text()),
        sa.Column("on_screen_text", sa.Text()),
        sa.Column("angles", postgresql.JSONB()),
        sa.Column("processing_status", sa.Enum(
            "raw", "cdn_fetched", "downloading", "downloaded",
            "transcribing", "transcribed", "vision_extracting", "vision_extracted",
            "extracting", "extracted", "failed",
            name="ad_processing_status"
        ), nullable=False, server_default="raw"),
        sa.Column("raw_ad_payload", postgresql.JSONB()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_competitor_ads_competitor_id", "competitor_ads", ["competitor_id"])
    op.create_index("ix_competitor_ads_user_id", "competitor_ads", ["user_id"])
    op.create_index("ix_competitor_ads_processing_status", "competitor_ads", ["processing_status"])
    op.create_index("ix_competitor_ads_approved", "competitor_ads", ["user_id", "processing_status", "created_at"])

    # --- creative_concepts ---
    op.create_table(
        "creative_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_ad_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("competitor_ads.id", ondelete="SET NULL")),
        sa.Column("body_script", sa.Text()),
        sa.Column("caption", sa.Text()),
        sa.Column("approval_status", sa.Enum("pending", "in_progress", "approved", name="concept_approval_status"), nullable=False, server_default="pending"),
        sa.Column("production_status", sa.Enum("produced", "launched", "tested", name="concept_production_status")),
        sa.Column("tested_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_creative_concepts_source_ad_id", "creative_concepts", ["source_ad_id"])
    op.create_index("ix_creative_concepts_user_id", "creative_concepts", ["user_id"])
    op.create_index("ix_creative_concepts_approval_status", "creative_concepts", ["approval_status"])

    # --- generated_outputs ---
    op.create_table(
        "generated_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("concept_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("creative_concepts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_type", sa.Enum("hook", name="variant_type"), nullable=False, server_default="hook"),
        sa.Column("hook_number", sa.Integer(), nullable=False),
        sa.Column("hook_script", sa.Text()),
        sa.Column("caption_override", sa.Text()),
        sa.Column("variant_tracking_id", sa.String(), nullable=False, unique=True),
        sa.Column("meta_ad_id", sa.String()),
        sa.Column("performance_data", postgresql.JSONB()),
        sa.Column("ghl_funnel_data", postgresql.JSONB()),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_generated_outputs_concept_id", "generated_outputs", ["concept_id"])
    op.create_index("ix_generated_outputs_user_id", "generated_outputs", ["user_id"])
    op.create_index("ix_generated_outputs_meta_ad_id", "generated_outputs", ["meta_ad_id"])

    # --- generated_output_versions ---
    op.create_table(
        "generated_output_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("output_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("generated_outputs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("hook_script", sa.Text()),
        sa.Column("caption_override", sa.Text()),
        sa.Column("raw_claude_response", postgresql.JSONB()),
        sa.Column("prompt_version", sa.String(), nullable=False, server_default="v1"),
        sa.Column("generation_trigger", sa.Enum("initial", "chat_iteration", name="generation_trigger"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_output_version", "generated_output_versions", ["output_id", "version_number"])
    op.create_index("ix_generated_output_versions_output_id", "generated_output_versions", ["output_id"])

    # --- chat_sessions ---
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("concept_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("creative_concepts.id", ondelete="CASCADE")),
        sa.Column("variant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("generated_outputs.id", ondelete="CASCADE")),
        sa.Column("level", sa.Enum("concept", "variant", name="chat_session_level"), nullable=False),
        sa.Column("element_focus", sa.String(), nullable=False),
        sa.Column("messages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("(concept_id IS NULL) != (variant_id IS NULL)", name="ck_chat_sessions_exactly_one_fk"),
    )
    op.create_index("ix_chat_sessions_concept_id", "chat_sessions", ["concept_id"])
    op.create_index("ix_chat_sessions_variant_id", "chat_sessions", ["variant_id"])
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    # Partial unique indexes
    op.execute("""
        CREATE UNIQUE INDEX uix_chat_sessions_concept_element
        ON chat_sessions (concept_id, element_focus)
        WHERE concept_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uix_chat_sessions_variant_element
        ON chat_sessions (variant_id, element_focus)
        WHERE variant_id IS NOT NULL
    """)

    # --- copywriting_principles ---
    op.create_table(
        "copywriting_principles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("knowledge_type", sa.Enum("brand", "copy_general", "copy_format", "learned", name="knowledge_type"), nullable=False),
        sa.Column("format_scope", sa.Enum("ad", "vsl", "email", name="format_scope")),
        sa.Column("principle_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("times_applied", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_copywriting_principles_user_id", "copywriting_principles", ["user_id"])
    op.create_index("ix_copywriting_principles_knowledge_type", "copywriting_principles", ["knowledge_type"])
    op.create_index("ix_copywriting_principles_format_scope", "copywriting_principles", ["format_scope"])
    op.create_index("ix_copywriting_principles_is_active", "copywriting_principles", ["is_active"])

    # --- copy_feedback_log ---
    op.create_table(
        "copy_feedback_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("chat_session_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("chat_sessions.id", ondelete="SET NULL")),
        sa.Column("output_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("generated_output_versions.id", ondelete="SET NULL")),
        sa.Column("principle_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("copywriting_principles.id", ondelete="SET NULL")),
        sa.Column("feedback_text", sa.Text()),
        sa.Column("extracted_principle", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_copy_feedback_log_chat_session_id", "copy_feedback_log", ["chat_session_id"])
    op.create_index("ix_copy_feedback_log_output_version_id", "copy_feedback_log", ["output_version_id"])
    op.create_index("ix_copy_feedback_log_principle_id", "copy_feedback_log", ["principle_id"])
    op.create_index("ix_copy_feedback_log_user_id", "copy_feedback_log", ["user_id"])

    # --- monitoring_runs ---
    op.create_table(
        "monitoring_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.Enum("running", "completed", "failed", name="monitoring_run_status"), nullable=False, server_default="running"),
        sa.Column("competitors_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_ads_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notification_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_monitoring_runs_status", "monitoring_runs", ["status"])
    op.create_index("ix_monitoring_runs_created_at", "monitoring_runs", ["created_at"])

    # --- whatsapp_sessions ---
    op.create_table(
        "whatsapp_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("phone_number", sa.String(), nullable=False, unique=True),
        sa.Column("state", sa.Enum("idle", "awaiting_confirmation", "confirmed", "done", name="whatsapp_session_state"), nullable=False, server_default="idle"),
        sa.Column("context", postgresql.JSONB()),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_whatsapp_sessions_last_activity_at", "whatsapp_sessions", ["last_activity_at"])

    # --- cost_log ---
    op.create_table(
        "cost_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("operation_type", sa.Enum(
            "apify_scrape", "deepgram_transcription", "claude_vision",
            "claude_extraction", "claude_generation", "claude_chat", "r2_storage",
            name="cost_operation_type"
        ), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=False)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost_usd", sa.Float()),
        sa.Column("extra_data", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cost_log_user_id", "cost_log", ["user_id"])
    op.create_index("ix_cost_log_operation_type", "cost_log", ["operation_type"])
    op.create_index("ix_cost_log_created_at", "cost_log", ["created_at"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("cost_log")
    op.drop_table("whatsapp_sessions")
    op.drop_table("monitoring_runs")
    op.drop_table("copy_feedback_log")
    op.drop_table("copywriting_principles")
    op.drop_table("chat_sessions")
    op.drop_table("generated_output_versions")
    op.drop_table("generated_outputs")
    op.drop_table("creative_concepts")
    op.drop_table("competitor_ads")
    op.drop_table("scrape_jobs")
    op.drop_table("competitors")
    op.drop_table("users")

    # Drop ENUMs
    for enum in [
        "scrape_job_status", "ad_type", "ad_processing_status",
        "concept_approval_status", "concept_production_status",
        "variant_type", "generation_trigger", "chat_session_level",
        "knowledge_type", "format_scope", "monitoring_run_status",
        "whatsapp_session_state", "cost_operation_type",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
