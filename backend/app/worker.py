"""Background worker: runs queued jobs and the once-a-minute housekeeping.

Start with ``python -m app.cli worker``. Several workers can run at once:
jobs are claimed with SKIP LOCKED and housekeeping takes a Redis lock.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select, update

from app import db, timeutil
from app.models import IdempotencyKey, Job, LedgerAccount, TelegramVerificationSession, User
from app.redis_client import redis
from app.services import bots, campaign, jobs, referrals, wallet

log = logging.getLogger("worker")

UNLOCK_BATCH = 500
PENDING_CLEANUP_BATCH = 1000
HOUSEKEEPING_EVERY = 60


async def snapshot_refresh(session, payload: dict) -> None:
    await referrals.compute_snapshot(session, int(payload["user_id"]))


async def unlock_batch(session, payload: dict) -> None:
    """On the payout date, move every pending balance to available, in batches."""
    after = int(payload.get("after_account_id", 0))
    rows = list(
        (
            await session.execute(
                select(LedgerAccount.id, LedgerAccount.user_id)
                .where(LedgerAccount.kind == "USER_PENDING", LedgerAccount.balance_paise > 0, LedgerAccount.id > after)
                .order_by(LedgerAccount.id)
                .limit(UNLOCK_BATCH)
            )
        ).all()
    )
    for _, user_id in rows:
        user = await session.get(User, user_id)
        if user is not None:
            await wallet.unlock_if_open(session, user)
    if len(rows) == UNLOCK_BATCH:
        last = rows[-1][0]
        await jobs.enqueue(session, "unlock_batch", {"after_account_id": last}, dedupe_key=f"unlock:{last}")


HANDLERS = {"snapshot_refresh": snapshot_refresh, "unlock_batch": unlock_batch}


async def run_job(job: Job) -> None:
    error: str | None = None
    try:
        handler = HANDLERS.get(job.kind)
        if handler is None:
            raise ValueError(f"unknown job kind {job.kind}")
        async with db.sessionmaker()() as session, session.begin():
            await handler(session, job.payload)
    except Exception as exc:  # recorded on the job and retried with backoff
        log.warning("job error", extra={"job_id": job.id, "kind": job.kind, "error": type(exc).__name__})
        error = f"{type(exc).__name__}: {exc}"[:500]
    async with db.sessionmaker()() as session, session.begin():
        await jobs.finish(session, job.id, error)


async def run_ready_jobs(limit: int) -> int:
    async with db.sessionmaker()() as session, session.begin():
        claimed = await jobs.claim(session, limit)
    await asyncio.gather(*(run_job(job) for job in claimed))
    return len(claimed)


async def housekeeping() -> None:
    at = timeutil.now()
    async with db.sessionmaker()() as session, session.begin():
        # Unverified signups past their expiry free up the number.
        expired = list(
            (
                await session.execute(
                    select(User.id)
                    .where(User.status == "PENDING_VERIFICATION", User.pending_expires_at <= at)
                    .limit(PENDING_CLEANUP_BATCH)
                )
            ).scalars()
        )
        if expired:
            await session.execute(delete(User).where(User.id.in_(expired)))
        await session.execute(
            update(TelegramVerificationSession)
            .where(
                TelegramVerificationSession.status.in_(("OPEN", "IN_PROGRESS")),
                TelegramVerificationSession.expires_at <= at,
            )
            .values(status="EXPIRED")
        )
        await session.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at <= at))
        await session.execute(delete(Job).where(Job.status == "DONE", Job.finished_at <= at - timedelta(days=7)))
        current = await campaign.current_campaign(session)
        if at >= current.payout_opens_at:
            await jobs.enqueue(session, "unlock_batch", {"after_account_id": 0}, dedupe_key=f"unlock:start:{current.id}")
    async with db.sessionmaker()() as session, session.begin():
        await bots.recover(session)


async def run(concurrency: int = 4, poll_seconds: float = 1.0) -> None:
    log.info("worker started", extra={"concurrency": concurrency})
    next_housekeeping = 0.0
    loop = asyncio.get_running_loop()
    while True:
        if loop.time() >= next_housekeeping:
            if await redis().set("worker:housekeeping", "1", nx=True, ex=HOUSEKEEPING_EVERY - 5):
                try:
                    await housekeeping()
                except Exception:
                    log.exception("housekeeping failed")
            next_housekeeping = loop.time() + HOUSEKEEPING_EVERY
        try:
            ran = await run_ready_jobs(concurrency)
        except Exception:
            log.exception("job loop failed")
            ran = 0
        if ran == 0:
            await asyncio.sleep(poll_seconds)
