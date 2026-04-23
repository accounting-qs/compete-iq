"""Blocklist model: emails excluded from outreach.

Sources: 'ghl_dnd' (GHL unsubscribe date set), 'wg_unsub' (WebinarGeek
unsubscribed), 'manual' (added via UI), 'csv' (bulk import).
"""

from db.models._common import (
    Base, DateTime, Index, Mapped, Optional, String, Text, UniqueConstraint, UUID,
    datetime, func, gen_uuid, mapped_column,
)


class BlocklistEntry(Base):
    __tablename__ = "blocklist"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    source_ref: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "email", name="uq_blocklist_user_email"),
        Index("ix_blocklist_email", "email"),
        Index("ix_blocklist_user", "user_id"),
    )
