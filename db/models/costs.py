"""Cost tracking model: CostLog."""

from db.models._common import (
    Base, DateTime, Enum, ForeignKey, Index, Integer, JSONB,
    Mapped, Optional, UUID,
    datetime, func, gen_uuid, mapped_column,
)


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
    entity_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False))
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column()
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_cost_log_user_id", "user_id"),
        Index("ix_cost_log_operation_type", "operation_type"),
        Index("ix_cost_log_created_at", "created_at"),
    )
