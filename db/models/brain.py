"""Brain models: CopywritingPrinciple, UniversalBrain, FormatBrain, ContentRun/Piece/Version, BrainUpdate, SourceExample, CaseStudy."""

from db.models._common import (
    Base, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index,
    Integer, JSONB, Mapped, Optional, String, Text, UUID, UniqueConstraint,
    datetime, func, gen_uuid, mapped_column, relationship,
)


class CopywritingPrinciple(Base):
    __tablename__ = "copywriting_principles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="CASCADE"))
    knowledge_type: Mapped[str] = mapped_column(
        Enum("brand", "copy_general", "copy_format", "learned", name="knowledge_type"),
        nullable=False
    )
    format_scope: Mapped[Optional[str]] = mapped_column(String)
    principle_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String)
    category: Mapped[Optional[str]] = mapped_column(String)
    display_order: Mapped[Optional[int]] = mapped_column(Integer)
    notion_page_id: Mapped[Optional[str]] = mapped_column(String, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    times_applied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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


class FormatBrain(Base):
    __tablename__ = "format_brains"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format_key: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    brain_content: Mapped[Optional[str]] = mapped_column(Text)
    output_schema: Mapped[Optional[dict]] = mapped_column(JSONB)
    example_outputs: Mapped[Optional[dict]] = mapped_column(JSONB)
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


class ContentRun(Base):
    __tablename__ = "content_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String, server_default="'pending'", nullable=False)
    input_type: Mapped[str] = mapped_column(String, nullable=False)
    raw_input: Mapped[Optional[dict]] = mapped_column(JSONB)
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


class ContentPiece(Base):
    __tablename__ = "content_pieces"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("content_runs.id", ondelete="CASCADE"), nullable=False)
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="SET NULL"))
    source_competitor_ad_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("competitor_ads.id", ondelete="SET NULL"))
    input_item: Mapped[Optional[dict]] = mapped_column(JSONB)
    sub_fields: Mapped[Optional[dict]] = mapped_column(JSONB)
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
        Index("ix_content_pieces_library", "user_id", "status", "created_at"),
    )

    run: Mapped["ContentRun"] = relationship(back_populates="pieces")
    format_brain: Mapped[Optional["FormatBrain"]] = relationship(back_populates="pieces")
    versions: Mapped[list["ContentPieceVersion"]] = relationship(back_populates="piece")


class ContentPieceVersion(Base):
    __tablename__ = "content_piece_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    piece_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("content_pieces.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sub_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    feedback_text: Mapped[Optional[str]] = mapped_column(Text)
    active_sub_field: Mapped[Optional[str]] = mapped_column(String)
    brain_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, default="v1", nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("piece_id", "version_number", name="uq_content_piece_version"),
        Index("ix_content_piece_versions_piece_id", "piece_id"),
    )

    piece: Mapped["ContentPiece"] = relationship(back_populates="versions")


class BrainUpdate(Base):
    __tablename__ = "brain_updates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    brain_type: Mapped[str] = mapped_column(String, nullable=False)
    format_brain_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="SET NULL"))
    trigger_text: Mapped[Optional[str]] = mapped_column(Text)
    proposed_changes: Mapped[Optional[dict]] = mapped_column(JSONB)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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


class SourceExample(Base):
    __tablename__ = "source_examples"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    format_brain_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("format_brains.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String)
    notion_page_id: Mapped[Optional[str]] = mapped_column(String, unique=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_source_examples_user_id", "user_id"),
        Index("ix_source_examples_format_brain_id", "format_brain_id"),
        Index("ix_source_examples_deleted_at", "deleted_at"),
    )

    format_brain: Mapped["FormatBrain"] = relationship(back_populates="source_examples")


class CaseStudy(Base):
    __tablename__ = "case_studies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String)
    client_name: Mapped[Optional[str]] = mapped_column(String)
    industry: Mapped[Optional[str]] = mapped_column(String)
    tags: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    source_url: Mapped[Optional[str]] = mapped_column(String)
    structured: Mapped[Optional[dict]] = mapped_column(JSONB)
    notion_page_id: Mapped[Optional[str]] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_case_studies_user_id", "user_id"),
        Index("ix_case_studies_notion_page_id", "notion_page_id"),
        Index("ix_case_studies_industry", "industry"),
        Index("ix_case_studies_source_url", "source_url"),
    )
