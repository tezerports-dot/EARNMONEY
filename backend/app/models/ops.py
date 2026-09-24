from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, one_of, pk, timestamp_column

JOB_STATUSES = ("QUEUED", "RUNNING", "DONE", "FAILED")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_recent", text("id DESC")),
        Index("ix_audit_log_target", "target"),
    )

    id: Mapped[int] = pk()
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = timestamp_column()


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        PrimaryKeyConstraint("scope", "key", name="pk_idempotency_keys"),
        Index("ix_idempotency_keys_expiry", "expires_at"),
    )

    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(one_of("status", JOB_STATUSES), name="status"),
        Index("ix_jobs_ready", "run_at", postgresql_where=text("status = 'QUEUED'")),
        Index("ix_jobs_running", "locked_until", postgresql_where=text("status = 'RUNNING'")),
    )

    id: Mapped[int] = pk()
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    dedupe_key: Mapped[str | None] = mapped_column(String(150), unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="QUEUED")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = timestamp_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RiskFlag(Base):
    __tablename__ = "risk_flags"
    __table_args__ = (Index("ix_risk_flags_user", "user_id"), Index("ix_risk_flags_open", "created_at", postgresql_where=text("resolved_at IS NULL")))

    id: Mapped[int] = pk()
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = timestamp_column()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(80))
