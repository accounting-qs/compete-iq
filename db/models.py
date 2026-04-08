"""
CompeteIQ — SQLAlchemy ORM Models (19 tables)
All tables: UUID PKs, user_id FK, created_at + updated_at server defaults.
Soft deletes on: competitors, competitor_ads, creative_concepts, generated_outputs,
                 format_brains, content_runs, content_pieces.

Legacy tables (creative_concepts, generated_outputs, etc.) back the WhatsApp ad flow.
Multi-format tables (universal_brain, format_brains, content_*) back the Content Studio.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


def gen_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# competitors
# ---------------------------------------------------------------------------
class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    handle: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String)
    meta_page_id: Mapped[Optional[str]] = mapped_column(String)
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "handle", name="uq_competitors_user_handle"),
        Index("ix_competitors_user_id", "user_id"),
    )

    ads: Mapped[list["CompetitorAd"]] = relationship(back_populates="competitor")
    scrape_jobs: Mapped[list["ScrapeJob"]] = relationship(back_populates="competitor")


# ---------------------------------------------------------------------------
# scrape_jobs
# ---------------------------------------------------------------------------
class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    competitor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed", name="scrape_job_status"),
        default="pending", nullable=False
    )
    apify_run_id: Mapped[Optional[str]] = mapped_column(String)
    ads_found: Mapped[int] = mapped_column(Integer, default=0)
    new_ads_detected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_scrape_jobs_competitor_id", "competitor_id"),
        Index("ix_scrape_jobs_user_id", "user_id"),
        Index("ix_scrape_jobs_status", "status"),
    )

    competitor: Mapped["Competitor"] = relationship(back_populates="scrape_jobs")


# ---------------------------------------------------------------------------
# competitor_ads
# ---------------------------------------------------------------------------
class CompetitorAd(Base):
    __tablename__ = "competitor_ads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    competitor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    ad_library_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    ad_type: Mapped[str] = mapped_column(
        Enum("video", "image", "carousel", name="ad_type"),
        nullable=False
    )
    ad_text: Mapped[Optional[str]] = mapped_column(Text)
    video_cdn_url: Mapped[Optional[str]] = mapped_column(Text)
    video_cdn_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    video_r2_key: Mapped[Optional[str]] = mapped_column(String)
    carousel_image_r2_keys: Mapped[Optional[dict]] = mapped_column(JSONB)
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    on_screen_text: Mapped[Optional[str]] = mapped_column(Text)
    angles: Mapped[Optional[dict]] = mapped_column(JSONB)
    processing_status: Mapped[str] = mapped_column(
        Enum(
            "raw", "cdn_fetched", "downloading", "downloaded",
            "transcribing", "transcribed", "vision_extracting", "vision_extracted",
            "extracting", "extracted", "failed",
            name="ad_processing_status"
        ),
        default="raw", nullable=False
    )
    raw_ad_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_competitor_ads_competitor_id", "competitor_id"),
        Index("ix_competitor_ads_user_id", "user_id"),
        Index("ix_competitor_ads_processing_status", "processing_status"),
        Index("ix_competitor_ads_approved", "user_id", "processing_status", "created_at"),
    )

    competitor: Mapped["Competitor"] = relationship(back_populates="ads")
    creative_concepts: Mapped[list["CreativeConcept"]] = relationship(back_populates="source_ad")


# ---------------------------------------------------------------------------
# creative_concepts
# ---------------------------------------------------------------------------
class CreativeConcept(Base):
    __tablename__ = "creative_concepts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_ad_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("competitor_ads.id", ondelete="SET NULL"))
    body_script: Mapped[Optional[str]] = mapped_column(Text)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(
        Enum("pending", "in_progress", "approved", name="concept_approval_status"),
        default="pending", nullable=False
    )
    production_status: Mapped[Optional[str]] = mapped_column(
        Enum("produced", "launched", "tested", name="concept_production_status")
    )
    tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_creative_concepts_source_ad_id", "source_ad_id"),
        Index("ix_creative_concepts_user_id", "user_id"),
        Index("ix_creative_concepts_approval_status", "approval_status"),
    )

    source_ad: Mapped[Optional["CompetitorAd"]] = relationship(back_populates="creative_concepts")
    generated_outputs: Mapped[list["GeneratedOutput"]] = relationship(back_populates="concept")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="concept",
        primaryjoin="ChatSession.concept_id == CreativeConcept.id"
    )


# ---------------------------------------------------------------------------
# generated_outputs
# ---------------------------------------------------------------------------
class GeneratedOutput(Base):
    __tablename__ = "generated_outputs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    concept_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("creative_concepts.id", ondelete="CASCADE"), nullable=False)
    variant_type: Mapped[str] = mapped_column(
        Enum("hook", name="variant_type"),
        default="hook", nullable=False
    )
    hook_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=Contrarian, 2=Result, 3=Pain
    hook_script: Mapped[Optional[str]] = mapped_column(Text)
    caption_override: Mapped[Optional[str]] = mapped_column(Text)
    variant_tracking_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    meta_ad_id: Mapped[Optional[str]] = mapped_column(String)
    performance_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    ghl_funnel_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_generated_outputs_concept_id", "concept_id"),
        Index("ix_generated_outputs_user_id", "user_id"),
        Index("ix_generated_outputs_meta_ad_id", "meta_ad_id"),
    )

    concept: Mapped["CreativeConcept"] = relationship(back_populates="generated_outputs")
    versions: Mapped[list["GeneratedOutputVersion"]] = relationship(back_populates="output")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="variant",
        primaryjoin="ChatSession.variant_id == GeneratedOutput.id"
    )


# ---------------------------------------------------------------------------
# generated_output_versions
# ---------------------------------------------------------------------------
class GeneratedOutputVersion(Base):
    __tablename__ = "generated_output_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    output_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("generated_outputs.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    hook_script: Mapped[Optional[str]] = mapped_column(Text)
    caption_override: Mapped[Optional[str]] = mapped_column(Text)
    raw_claude_response: Mapped[Optional[dict]] = mapped_column(JSONB)
    prompt_version: Mapped[str] = mapped_column(String, default="v1", nullable=False)
    generation_trigger: Mapped[str] = mapped_column(
        Enum("initial", "chat_iteration", name="generation_trigger"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("output_id", "version_number", name="uq_output_version"),
        Index("ix_generated_output_versions_output_id", "output_id"),
    )

    output: Mapped["GeneratedOutput"] = relationship(back_populates="versions")
    feedback_logs: Mapped[list["CopyFeedbackLog"]] = relationship(back_populates="output_version")


# ---------------------------------------------------------------------------
# chat_sessions
# ---------------------------------------------------------------------------
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    concept_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("creative_concepts.id", ondelete="CASCADE"))
    variant_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("generated_outputs.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(
        Enum("concept", "variant", name="chat_session_level"),
        nullable=False
    )
    element_focus: Mapped[str] = mapped_column(String, nullable=False)  # 'body', 'caption', 'hook', 'production_brief'
    messages: Mapped[dict] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "(concept_id IS NULL) != (variant_id IS NULL)",
            name="ck_chat_sessions_exactly_one_fk"
        ),
        # Partial unique indexes: one session per element per concept/variant
        Index(
            "uix_chat_sessions_concept_element",
            "concept_id", "element_focus",
            unique=True,
            postgresql_where="concept_id IS NOT NULL"
        ),
        Index(
            "uix_chat_sessions_variant_element",
            "variant_id", "element_focus",
            unique=True,
            postgresql_where="variant_id IS NOT NULL"
        ),
        Index("ix_chat_sessions_user_id", "user_id"),
        Index("ix_chat_sessions_concept_id", "concept_id"),
        Index("ix_chat_sessions_variant_id", "variant_id"),
    )

    concept: Mapped[Optional["CreativeConcept"]] = relationship(
        back_populates="chat_sessions",
        primaryjoin="ChatSession.concept_id == CreativeConcept.id",
        foreign_keys="[ChatSession.concept_id]"
    )
    variant: Mapped[Optional["GeneratedOutput"]] = relationship(
        back_populates="chat_sessions",
        primaryjoin="ChatSession.variant_id == GeneratedOutput.id",
        foreign_keys="[ChatSession.variant_id]"
    )
    feedback_logs: Mapped[list["CopyFeedbackLog"]] = relationship(back_populates="chat_session")


# ---------------------------------------------------------------------------
# copywriting_principles  (the brain — universal + format principles unified)
# ---------------------------------------------------------------------------
class CopywritingPrinciple(Base):
    __tablename__ = "copywriting_principles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    # format_brain_id NULL = universal brain principle; non-NULL = format-specific
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="CASCADE"))
    knowledge_type: Mapped[str] = mapped_column(
        Enum("brand", "copy_general", "copy_format", "learned", name="knowledge_type"),
        nullable=False
    )
    # Widened from Enum to String — supports any format_key ('calendar_blocker', 'vsl', etc.)
    format_scope: Mapped[Optional[str]] = mapped_column(String)
    principle_text: Mapped[str] = mapped_column(Text, nullable=False)
    # authored = written in Brain Editor / Notion; feedback_promoted = promoted from iteration; notion_synced = pulled from Notion
    source: Mapped[Optional[str]] = mapped_column(String)
    category: Mapped[Optional[str]] = mapped_column(String)              # 'hook', 'body', 'cta', 'tone', etc.
    display_order: Mapped[Optional[int]] = mapped_column(Integer)        # ordering within a category
    notion_page_id: Mapped[Optional[str]] = mapped_column(String, unique=True)  # dedup key for Notion sync
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    times_applied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # NULL = active, timestamp = archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "source IN ('authored', 'feedback_promoted', 'notion_synced')",
            name="ck_copywriting_principles_source"
        ),
        Index("ix_copywriting_principles_user_id", "user_id"),
        Index("ix_copywriting_principles_format_brain_id", "format_brain_id"),
        Index("ix_copywriting_principles_knowledge_type", "knowledge_type"),
        Index("ix_copywriting_principles_format_scope", "format_scope"),
        Index("ix_copywriting_principles_category", "category"),
        Index("ix_copywriting_principles_is_active", "is_active"),
        Index("ix_copywriting_principles_deleted_at", "deleted_at"),
    )

    feedback_logs: Mapped[list["CopyFeedbackLog"]] = relationship(back_populates="principle")


# ---------------------------------------------------------------------------
# copy_feedback_log
# ---------------------------------------------------------------------------
class CopyFeedbackLog(Base):
    __tablename__ = "copy_feedback_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    chat_session_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("chat_sessions.id", ondelete="SET NULL"))
    output_version_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("generated_output_versions.id", ondelete="SET NULL"))
    principle_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("copywriting_principles.id", ondelete="SET NULL"))
    feedback_text: Mapped[Optional[str]] = mapped_column(Text)
    extracted_principle: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_copy_feedback_log_chat_session_id", "chat_session_id"),
        Index("ix_copy_feedback_log_output_version_id", "output_version_id"),
        Index("ix_copy_feedback_log_principle_id", "principle_id"),
        Index("ix_copy_feedback_log_user_id", "user_id"),
    )

    chat_session: Mapped[Optional["ChatSession"]] = relationship(back_populates="feedback_logs")
    output_version: Mapped[Optional["GeneratedOutputVersion"]] = relationship(back_populates="feedback_logs")
    principle: Mapped[Optional["CopywritingPrinciple"]] = relationship(back_populates="feedback_logs")


# ---------------------------------------------------------------------------
# monitoring_runs
# ---------------------------------------------------------------------------
class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(
        Enum("running", "completed", "failed", name="monitoring_run_status"),
        default="running", nullable=False
    )
    competitors_checked: Mapped[int] = mapped_column(Integer, default=0)
    new_ads_found: Mapped[int] = mapped_column(Integer, default=0)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_monitoring_runs_status", "status"),
        Index("ix_monitoring_runs_created_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# whatsapp_sessions
# ---------------------------------------------------------------------------
class WhatsAppSession(Base):
    __tablename__ = "whatsapp_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    phone_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    state: Mapped[str] = mapped_column(
        Enum(
            "idle", "searching", "awaiting_handle", "awaiting_confirmation", "confirmed", "done",
            name="whatsapp_session_state"
        ),
        default="idle", nullable=False
    )
    context: Mapped[Optional[dict]] = mapped_column(JSONB)  # candidate competitors, submitted URL, selected IDs
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # No explicit ix_whatsapp_sessions_phone_number — unique=True already creates one
        Index("ix_whatsapp_sessions_last_activity_at", "last_activity_at"),
    )


# ---------------------------------------------------------------------------
# cost_log
# ---------------------------------------------------------------------------
class CostLog(Base):
    __tablename__ = "cost_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    operation_type: Mapped[str] = mapped_column(
        Enum(
            "apify_scrape", "deepgram_transcription", "claude_vision",
            "claude_extraction", "claude_generation", "claude_chat", "r2_storage",
            name="cost_operation_type"
        ),
        nullable=False
    )
    entity_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False))  # ID of the ad, concept, output etc.
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column()
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB)  # renamed from 'metadata' — reserved by SQLAlchemy
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_cost_log_user_id", "user_id"),
        Index("ix_cost_log_operation_type", "operation_type"),
        Index("ix_cost_log_created_at", "created_at"),
    )


# ===========================================================================
# MULTI-FORMAT CONTENT ENGINE (Migration 003)
# ===========================================================================

# ---------------------------------------------------------------------------
# universal_brain — one row per user, stores QS business context/ICP/voice
# ---------------------------------------------------------------------------
class UniversalBrain(Base):
    __tablename__ = "universal_brain"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    brain_content: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_universal_brain_user_id"),
        Index("ix_universal_brain_user_id", "user_id"),
    )


# ---------------------------------------------------------------------------
# format_brains — one row per format per user (facebook_ad, event_description, vsl, ...)
# ---------------------------------------------------------------------------
class FormatBrain(Base):
    __tablename__ = "format_brains"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format_key: Mapped[str] = mapped_column(String, nullable=False)   # 'facebook_ad', 'event_description', 'vsl'
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    brain_content: Mapped[Optional[str]] = mapped_column(Text)          # format-specific rules for prompt injection
    output_schema: Mapped[Optional[dict]] = mapped_column(JSONB)        # [{key, label, type}, ...] sub-field definitions
    example_outputs: Mapped[Optional[dict]] = mapped_column(JSONB)      # array of example outputs for few-shot prompting
    brain_quality: Mapped[str] = mapped_column(String, server_default="'empty'", nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("brain_quality IN ('empty', 'partial', 'ready')", name="ck_format_brains_quality"),
        UniqueConstraint("user_id", "format_key", name="uq_format_brains_user_format"),
        Index("ix_format_brains_user_id", "user_id"),
        Index("ix_format_brains_format_key", "format_key"),
    )

    runs: Mapped[list["ContentRun"]] = relationship(back_populates="format_brain")
    pieces: Mapped[list["ContentPiece"]] = relationship(back_populates="format_brain")
    source_examples: Mapped[list["SourceExample"]] = relationship(back_populates="format_brain")


# ---------------------------------------------------------------------------
# content_runs — a generation session (single or batch)
# ---------------------------------------------------------------------------
class ContentRun(Base):
    __tablename__ = "content_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String, server_default="'pending'", nullable=False)
    input_type: Mapped[str] = mapped_column(String, nullable=False)    # 'url', 'text', 'batch'
    raw_input: Mapped[Optional[dict]] = mapped_column(JSONB)           # {url, text, items:[{industry, segment, context}]}
    items_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generating', 'completed', 'failed')",
            name="ck_content_runs_status"
        ),
        CheckConstraint(
            "input_type IN ('url', 'text', 'batch')",
            name="ck_content_runs_input_type"
        ),
        Index("ix_content_runs_user_id", "user_id"),
        Index("ix_content_runs_format_brain_id", "format_brain_id"),
        Index("ix_content_runs_status", "status"),
        Index("ix_content_runs_created_at", "created_at"),
    )

    format_brain: Mapped[Optional["FormatBrain"]] = relationship(back_populates="runs")
    pieces: Mapped[list["ContentPiece"]] = relationship(back_populates="run")


# ---------------------------------------------------------------------------
# content_pieces — individual generated output within a run
# ---------------------------------------------------------------------------
class ContentPiece(Base):
    __tablename__ = "content_pieces"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("content_runs.id", ondelete="CASCADE"), nullable=False)
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="SET NULL"))
    source_competitor_ad_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("competitor_ads.id", ondelete="SET NULL"))
    input_item: Mapped[Optional[dict]] = mapped_column(JSONB)          # {industry, segment, context, url} — input that produced this piece
    sub_fields: Mapped[Optional[dict]] = mapped_column(JSONB)          # {title: '...', description: '...'} — current version content
    status: Mapped[str] = mapped_column(String, server_default="'draft'", nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('generating', 'draft', 'locked')",
            name="ck_content_pieces_status"
        ),
        Index("ix_content_pieces_user_id", "user_id"),
        Index("ix_content_pieces_run_id", "run_id"),
        Index("ix_content_pieces_format_brain_id", "format_brain_id"),
        Index("ix_content_pieces_status", "status"),
        Index("ix_content_pieces_source_ad_id", "source_competitor_ad_id"),
        Index("ix_content_pieces_library", "user_id", "status", "created_at"),  # Library view composite
    )

    run: Mapped["ContentRun"] = relationship(back_populates="pieces")
    format_brain: Mapped[Optional["FormatBrain"]] = relationship(back_populates="pieces")
    versions: Mapped[list["ContentPieceVersion"]] = relationship(back_populates="piece")


# ---------------------------------------------------------------------------
# content_piece_versions — immutable version history with feedback
# ---------------------------------------------------------------------------
class ContentPieceVersion(Base):
    __tablename__ = "content_piece_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    piece_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("content_pieces.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sub_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)    # snapshot of all sub-fields at this version
    feedback_text: Mapped[Optional[str]] = mapped_column(Text)         # what Lloyd typed to trigger this version
    active_sub_field: Mapped[Optional[str]] = mapped_column(String)    # which sub-field was targeted (NULL = whole piece)
    brain_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # was feedback promoted to brain?
    prompt_version: Mapped[str] = mapped_column(String, default="v1", nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("piece_id", "version_number", name="uq_content_piece_version"),
        Index("ix_content_piece_versions_piece_id", "piece_id"),
    )

    piece: Mapped["ContentPiece"] = relationship(back_populates="versions")


# ---------------------------------------------------------------------------
# brain_updates — audit log of brain changes + confirmation flow
# ---------------------------------------------------------------------------
class BrainUpdate(Base):
    __tablename__ = "brain_updates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    brain_type: Mapped[str] = mapped_column(String, nullable=False)    # 'universal' or 'format'
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="SET NULL"))
    trigger_text: Mapped[Optional[str]] = mapped_column(Text)          # what Lloyd said that triggered this
    proposed_changes: Mapped[Optional[dict]] = mapped_column(JSONB)    # structured diff: [{action, principle_text, category}, ...]
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))   # NULL until Lloyd confirms
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))     # NULL until changes written to brain
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "brain_type IN ('universal', 'format')",
            name="ck_brain_updates_brain_type"
        ),
        Index("ix_brain_updates_user_id", "user_id"),
        Index("ix_brain_updates_format_brain_id", "format_brain_id"),
        Index("ix_brain_updates_brain_type", "brain_type"),
        Index("ix_brain_updates_confirmed_at", "confirmed_at"),
    )


# ---------------------------------------------------------------------------
# source_examples — individually addressable examples per format brain
# Replaces format_brains.example_outputs (JSONB blob, now deprecated)
# ---------------------------------------------------------------------------
class SourceExample(Base):
    __tablename__ = "source_examples"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format_brain_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)           # verbatim working example
    source_url: Mapped[Optional[str]] = mapped_column(String)            # origin URL if applicable
    notion_page_id: Mapped[Optional[str]] = mapped_column(String, unique=True)  # dedup key for Notion sync
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_source_examples_user_id", "user_id"),
        Index("ix_source_examples_format_brain_id", "format_brain_id"),
        Index("ix_source_examples_deleted_at", "deleted_at"),
    )

    format_brain: Mapped["FormatBrain"] = relationship(back_populates="source_examples")


# ---------------------------------------------------------------------------
# case_studies — verbatim client results, Notion-synced, read-only by system
# ---------------------------------------------------------------------------
class CaseStudy(Base):
    __tablename__ = "case_studies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String)
    client_name: Mapped[Optional[str]] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text, nullable=False)           # verbatim — never modified by system
    notion_page_id: Mapped[Optional[str]] = mapped_column(String, unique=True)  # dedup key for Notion sync
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_case_studies_user_id", "user_id"),
        Index("ix_case_studies_notion_page_id", "notion_page_id"),
    )
