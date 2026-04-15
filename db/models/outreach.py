"""Outreach campaign planning models: OutreachBucket, BucketCopy, OutreachSender, Webinar, WebinarListAssignment, CopyUsageLog."""

from db.models._common import (
    Base, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Integer, JSONB, Mapped, Optional, String, Text, UUID, UniqueConstraint,
    datetime, func, gen_uuid, mapped_column, relationship,
)


class OutreachBucket(Base):
    __tablename__ = "outreach_buckets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(Text)
    total_contacts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    remaining_contacts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    countries: Mapped[Optional[dict]] = mapped_column(JSONB, server_default="[]")
    emp_range: Mapped[Optional[str]] = mapped_column(Text)
    source_file: Mapped[Optional[str]] = mapped_column(Text)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    copies: Mapped[list["BucketCopy"]] = relationship(back_populates="bucket", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_outreach_buckets_user_name"),
        Index("ix_outreach_buckets_user_id", "user_id"),
    )


class BucketCopy(Base):
    __tablename__ = "bucket_copies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    bucket_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("outreach_buckets.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    copy_type: Mapped[str] = mapped_column(String(20), nullable=False)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    primary_picked_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ai_feedback: Mapped[Optional[str]] = mapped_column(Text)
    generation_batch_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    bucket: Mapped["OutreachBucket"] = relationship(back_populates="copies")

    __table_args__ = (
        CheckConstraint("copy_type IN ('title', 'description')", name="ck_bucket_copies_type"),
        Index("ix_bucket_copies_bucket_type", "bucket_id", "copy_type"),
        Index("ix_bucket_copies_user_id", "user_id"),
        Index("ix_bucket_copies_batch", "generation_batch_id"),
    )


class OutreachSender(Base):
    __tablename__ = "outreach_senders"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    total_accounts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    send_per_account: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    days_per_webinar: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    color: Mapped[Optional[str]] = mapped_column(String(20))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_outreach_senders_user_name"),
        Index("ix_outreach_senders_user_id", "user_id"),
    )


class Webinar(Base):
    __tablename__ = "webinars"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="planning")
    broadcast_id: Mapped[Optional[str]] = mapped_column(Text)
    main_title: Mapped[Optional[str]] = mapped_column(Text)
    registration_link: Mapped[Optional[str]] = mapped_column(Text)
    unsubscribe_link: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assignments: Mapped[list["WebinarListAssignment"]] = relationship(back_populates="webinar", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("user_id", "number", name="uq_webinars_user_number"),
        CheckConstraint("status IN ('planning', 'sent', 'archived')", name="ck_webinars_status"),
        Index("ix_webinars_user_id", "user_id"),
        Index("ix_webinars_status", "status"),
    )


class WebinarListAssignment(Base):
    __tablename__ = "webinar_list_assignments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    webinar_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("webinars.id", ondelete="CASCADE"), nullable=False)
    bucket_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("outreach_buckets.id", ondelete="SET NULL"))
    sender_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("outreach_senders.id", ondelete="SET NULL"))
    description: Mapped[Optional[str]] = mapped_column(Text)
    list_url: Mapped[Optional[str]] = mapped_column(Text)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    remaining: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    gcal_invited: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    accounts_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    send_per_account: Mapped[Optional[int]] = mapped_column(Integer)
    days: Mapped[Optional[int]] = mapped_column(Integer)
    title_copy_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("bucket_copies.id", ondelete="SET NULL"))
    desc_copy_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("bucket_copies.id", ondelete="SET NULL"))
    countries_override: Mapped[Optional[str]] = mapped_column(Text)
    emp_range_override: Mapped[Optional[str]] = mapped_column(Text)
    is_nonjoiners: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_no_list_data: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    webinar: Mapped["Webinar"] = relationship(back_populates="assignments")
    bucket: Mapped[Optional["OutreachBucket"]] = relationship()
    sender: Mapped[Optional["OutreachSender"]] = relationship()
    title_copy: Mapped[Optional["BucketCopy"]] = relationship(foreign_keys=[title_copy_id])
    desc_copy: Mapped[Optional["BucketCopy"]] = relationship(foreign_keys=[desc_copy_id])

    __table_args__ = (
        Index("ix_wla_webinar_id", "webinar_id"),
        Index("ix_wla_bucket_id", "bucket_id"),
        Index("ix_wla_sender_id", "sender_id"),
        Index("ix_wla_webinar_sender", "webinar_id", "sender_id"),
        Index("ix_wla_user_id", "user_id"),
    )


class CopyUsageLog(Base):
    __tablename__ = "copy_usage_log"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    bucket_copy_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("bucket_copies.id", ondelete="CASCADE"), nullable=False)
    assignment_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("webinar_list_assignments.id", ondelete="CASCADE"), nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_copy_usage_log_copy", "bucket_copy_id"),
        Index("ix_copy_usage_log_assignment", "assignment_id"),
    )
