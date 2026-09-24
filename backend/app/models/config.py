from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, pk, timestamp_column


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint("level_1_reward_paise > 0", name="reward_positive"),
        CheckConstraint("min_withdrawal_paise > 0", name="min_withdrawal_positive"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        CheckConstraint("starts_at < ends_at", name="dates_ordered"),
        Index("uq_campaigns_current", "is_current", unique=True, postgresql_where=text("is_current")),
    )

    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    brand_reveal_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    launch_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payout_opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(100))
    level_1_reward_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    min_withdrawal_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    capacity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signups_open: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    show_promo_allocation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()


class AppSettings(Base):
    """A single row (id = 1) of settings the admin can change at run time."""

    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint(
            "announcement_tone IS NULL OR announcement_tone IN ('info', 'success', 'warning')",
            name="announcement_tone",
        ),
        CheckConstraint("ads_min_interstitial_interval_seconds >= 60", name="interstitial_interval"),
        CheckConstraint("verification_session_minutes BETWEEN 5 AND 1440", name="session_minutes"),
        CheckConstraint("max_contact_mismatches BETWEEN 1 AND 10", name="mismatch_limit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="Future Fashion")
    company_legal_name: Mapped[str | None] = mapped_column(String(200))
    company_address: Mapped[str | None] = mapped_column(Text)
    support_email: Mapped[str | None] = mapped_column(String(200))
    support_url: Mapped[str | None] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(Text)
    privacy_url: Mapped[str | None] = mapped_column(Text)
    min_app_version: Mapped[str] = mapped_column(String(20), nullable=False, server_default="1.0.0")
    apk_download_url: Mapped[str | None] = mapped_column(Text)
    maintenance_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    maintenance_message: Mapped[str | None] = mapped_column(String(300))
    maintenance_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    announcement_text: Mapped[str | None] = mapped_column(String(300))
    announcement_tone: Mapped[str | None] = mapped_column(Text)
    ads_banner_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    ads_interstitial_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    ads_rewarded_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    ads_min_interstitial_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="300")
    accept_pending_join_requests: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    verification_session_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    max_contact_mismatches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    updated_at: Mapped[datetime] = timestamp_column()


class MembershipCounter(Base):
    """Real number of verified users. Only the verification transaction changes it."""

    __tablename__ = "membership_counter"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("verified_count >= 0", name="non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="1")
    verified_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = timestamp_column()
