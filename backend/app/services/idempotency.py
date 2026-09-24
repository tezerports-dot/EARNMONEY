"""Idempotency keys for mutations that move money or create identity.

The key row is written in the same database transaction as the effect, so a
stored response always matches committed data:

* first request inserts the row, does the work, stores the response, commits;
* a retry finds the committed row and gets the stored response back;
* a concurrent duplicate waits on the row lock, then does the same;
* if the first request fails, its row rolls back with it and a retry runs again.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, timeutil
from app.models import IdempotencyKey

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,100}$")
RETENTION = timedelta(hours=24)


@dataclass
class Replay:
    status: int
    body: dict[str, Any]


def validate_key(key: str | None) -> str:
    if not key or not KEY_PATTERN.fullmatch(key):
        raise errors.ValidationFailed(
            "Missing or invalid Idempotency-Key header.", fields={"Idempotency-Key": "Send a UUID per action."}
        )
    return key


def _hash(payload: dict[str, Any]) -> bytes:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).digest()


async def lookup(db: AsyncSession, scope: str, key: str, payload: dict[str, Any]) -> Replay | None:
    """Read-only check for a completed request, used before expensive or
    single-use steps (rate limits, CAPTCHA) so a retry doesn't trip them."""
    existing = (
        await db.execute(select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key))
    ).scalar_one_or_none()
    if existing is None:
        return None
    if existing.request_hash != _hash(payload):
        raise errors.IdempotencyKeyReused()
    if existing.response_status is None:
        raise errors.RequestInProgress()
    return Replay(existing.response_status, existing.response_body or {})


async def begin(db: AsyncSession, scope: str, key: str, payload: dict[str, Any]) -> Replay | None:
    """Claim ``(scope, key)`` inside the caller's transaction.

    Returns a ``Replay`` when this exact request was already completed.
    """
    request_hash = _hash(payload)
    inserted = await db.execute(
        insert(IdempotencyKey)
        .values(scope=scope, key=key, request_hash=request_hash, expires_at=timeutil.now() + RETENTION)
        .on_conflict_do_nothing()
        .returning(IdempotencyKey.key)
    )
    if inserted.scalar_one_or_none() is not None:
        return None
    existing = (
        await db.execute(select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key))
    ).scalar_one()
    if existing.request_hash != request_hash:
        raise errors.IdempotencyKeyReused()
    if existing.response_status is None:
        raise errors.RequestInProgress()
    return Replay(existing.response_status, existing.response_body or {})


async def complete(db: AsyncSession, scope: str, key: str, status: int, body: dict[str, Any]) -> None:
    row = (await db.execute(select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == key))).scalar_one()
    row.response_status = status
    row.response_body = body
