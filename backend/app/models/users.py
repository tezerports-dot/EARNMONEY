from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, one_of, pk, timestamp_column

USER_STATUSES = ("PENDING_VERIFICATION", "ACTIVE", "SUSPENDED")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(one_of("status", USER_STATUSES), name="status"),
        CheckConstraint("phone ~ '^[6-9][0-9]{9}$'", name="phone_format"),
        CheckConstraint("referrer_id IS NULL OR referrer_id <> id", name="not_self_referred"),
        Index("ix_users_referrer_recent", "referrer_id", text("created_at DESC"), text("id DESC")),
        Index(
            "ix_users_pending_expiry",
            "pending_expires_at",
            postgresql_where=text("status = 'PENDING_VERIFICATION'"),
        ),
        # Migration 0002: counting a referrer's unverified friends.
        Index(
            "ix_users_referrer_pending",
            "referrer_id",
            "pending_expires_at",
            postgresql_where=text("status = 'PENDING_VERIFICATION'"),
        ),
    )

    id: Mapped[int] = pk()
    public_id: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING_VERIFICATION")
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    pending_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = timestamp_column()


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_family", "family_id"), Index("ix_auth_sessions_user", "user_id"))

    id: Mapped[int] = pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    access_token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = timestamp_column()


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = pk()
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = timestamp_column()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = pk()
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()
