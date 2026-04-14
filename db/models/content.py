"""Content generation models: CreativeConcept, GeneratedOutput, versions, chat, feedback, monitoring, WhatsApp."""

from db.models._common import (
    Base, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer,
    JSONB, Mapped, Optional, String, Text, UUID, UniqueConstraint,
    datetime, func, gen_uuid, mapped_column, relationship,
)


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
    context: Mapped[Optional[dict]] = mapped_column(JSONB)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_whatsapp_sessions_last_activity_at", "last_activity_at"),
    )
