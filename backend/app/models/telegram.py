from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, one_of, pk, timestamp_column

BOT_ROLES = ("VERIFIER", "WATCHER")
BOT_HEALTH = ("HEALTHY", "RATE_LIMITED", "FAILING")
SESSION_STATUSES = ("OPEN", "IN_PROGRESS", "COMPLETED", "EXPIRED", "FAILED", "SUPERSEDED")
OPEN_SESSION_STATUSES = ("OPEN", "IN_PROGRESS")


class TelegramBot(Base):
    __tablename__ = "telegram_bots"
    __table_args__ = (
        CheckConstraint(one_of("role", BOT_ROLES), name="role"),
        CheckConstraint(one_of("health", BOT_HEALTH), name="health"),
        CheckConstraint("weight BETWEEN 1 AND 100", name="weight_range"),
    )

    id: Mapped[int] = pk()
    ref: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    telegram_bot_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    token_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    webhook_secret_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    health: Mapped[str] = mapped_column(Text, nullable=False, server_default="HEALTHY")
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    weight: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = timestamp_column()


class RequiredChannel(Base):
    __tablename__ = "required_channels"

    id: Mapped[int] = pk()
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    invite_link: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = timestamp_column()


class TelegramVerificationSession(Base):
    __tablename__ = "telegram_verification_sessions"
    __table_args__ = (
        CheckConstraint(one_of("status", SESSION_STATUSES), name="status"),
        Index(
            "uq_telegram_verification_sessions_one_open",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
        ),
        Index(
            "ix_telegram_verification_sessions_tg_user",
            "telegram_user_id",
            postgresql_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
        ),
        Index("ix_telegram_verification_sessions_user_recent", "user_id", text("id DESC")),
    )

    id: Mapped[int] = pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("telegram_bots.id"), nullable=False)
    # SHA-256 of the /start token. The token is derived from the id with HMAC,
    # so it is never stored.
    token_hash: Mapped[bytes | None] = mapped_column(LargeBinary, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="OPEN")
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    channels_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mismatch_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    issue: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramJoinRequest(Base):
    __tablename__ = "telegram_join_requests"
    __table_args__ = (PrimaryKeyConstraint("telegram_user_id", "chat_id", name="pk_telegram_join_requests"),)

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TelegramVerification(Base):
    __tablename__ = "telegram_verifications"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("telegram_verification_sessions.id"), nullable=False)
    bot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("telegram_bots.id"), nullable=False)
    channel_states: Mapped[list] = mapped_column(JSONB, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
