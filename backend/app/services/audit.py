"""Append-only audit trail. Never pass secrets, full phone or bank numbers."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

log = logging.getLogger("audit")


async def record(
    db: AsyncSession,
    actor: str,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    db.add(AuditLog(actor=actor, action=action, target=target, details=details or {}, ip=ip))
    log.info("audit", extra={"actor": actor, "action": action, "target": target})
