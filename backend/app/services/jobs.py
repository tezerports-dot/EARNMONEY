"""A small job queue in Postgres.

* ``enqueue`` runs inside the caller's transaction, so a job exists only if
  the work that asked for it committed.
* Workers claim jobs with ``FOR UPDATE SKIP LOCKED``: many workers, no double
  processing.
* Failures retry with exponential backoff plus jitter, then stop at
  ``max_attempts``.
* A job whose worker died is reclaimed after its lock expires.
* ``dedupe_key`` stops the same job being queued twice.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.models import Job

log = logging.getLogger("jobs")

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]

LOCK_SECONDS = 300
BASE_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 3600


async def enqueue(
    db: AsyncSession,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    run_at: datetime | None = None,
    max_attempts: int = 5,
) -> None:
    await db.execute(
        insert(Job)
        .values(
            kind=kind,
            payload=payload or {},
            dedupe_key=dedupe_key,
            run_at=run_at or timeutil.now(),
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(index_elements=[Job.dedupe_key])
    )


def backoff(attempt: int) -> timedelta:
    delay = min(BASE_BACKOFF_SECONDS * 2 ** (attempt - 1), MAX_BACKOFF_SECONDS)
    return timedelta(seconds=delay + random.uniform(0, delay / 2))


async def claim(db: AsyncSession, limit: int) -> list[Job]:
    """Claim up to ``limit`` ready jobs (including ones whose worker died)."""
    at = timeutil.now()
    rows = await db.execute(
        text(
            """
            UPDATE jobs SET status = 'RUNNING', attempts = attempts + 1, locked_until = :lock_until
            WHERE id IN (
                SELECT id FROM jobs
                WHERE (status = 'QUEUED' AND run_at <= :now)
                   OR (status = 'RUNNING' AND locked_until < :now)
                ORDER BY run_at
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
            """
        ),
        {"now": at, "lock_until": at + timedelta(seconds=LOCK_SECONDS), "limit": limit},
    )
    job_ids = [row[0] for row in rows]
    if not job_ids:
        return []
    return list((await db.execute(select(Job).where(Job.id.in_(job_ids)))).scalars())


async def finish(db: AsyncSession, job_id: int, error: str | None) -> None:
    job = (await db.execute(select(Job).where(Job.id == job_id).with_for_update())).scalar_one()
    at = timeutil.now()
    if error is None:
        job.status, job.finished_at, job.locked_until = "DONE", at, None
        return
    job.last_error = error[:500]
    job.locked_until = None
    if job.attempts >= job.max_attempts:
        job.status, job.finished_at = "FAILED", at
        log.error("job failed permanently", extra={"job_id": job.id, "kind": job.kind})
    else:
        job.status, job.run_at = "QUEUED", at + backoff(job.attempts)


async def queue_stats(db: AsyncSession) -> dict[str, int]:
    rows = await db.execute(text("SELECT status, count(*) FROM jobs GROUP BY status"))
    stats = {status: count for status, count in rows}
    oldest = (
        await db.execute(text("SELECT min(run_at) FROM jobs WHERE status = 'QUEUED' AND run_at <= :now"), {"now": timeutil.now()})
    ).scalar_one()
    stats["oldest_ready_age_seconds"] = int((timeutil.now() - oldest).total_seconds()) if oldest else 0
    return stats
