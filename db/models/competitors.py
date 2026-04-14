"""Competitor intelligence models: Competitor, ScrapeJob, CompetitorAd."""

from db.models._common import (
    Base, Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSONB,
    Mapped, Optional, String, Text, UUID, UniqueConstraint,
    datetime, func, gen_uuid, mapped_column, relationship,
)


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
