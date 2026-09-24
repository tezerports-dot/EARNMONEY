"""The Postgres job queue under load (CLAUDE.md §9, §20; abuse case 40).

A backlog never blocks the API: the referral table is served from the last
snapshot with ``refresh_pending`` (test_referrals). These tests cover the
queue itself: bounded batches, no double processing, backoff, recovery.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app import db, worker
from app.models import Job
from app.services import jobs
from tests import helpers


def recording_handler(seen: list[int], fail: bool = False):
    async def handler(session, payload: dict) -> None:
        seen.append(payload["n"])
        if fail:
            raise RuntimeError("downstream unavailable")

    return handler


async def enqueue(kind: str, count: int, max_attempts: int = 5) -> None:
    async with db.sessionmaker()() as s, s.begin():
        for n in range(count):
            await jobs.enqueue(s, kind, {"n": n}, max_attempts=max_attempts)


async def stats() -> dict[str, int]:
    async with db.sessionmaker()() as s, s.begin():
        return await jobs.queue_stats(s)


async def test_backlog_is_worked_in_bounded_batches(monkeypatch):
    seen: list[int] = []
    monkeypatch.setitem(worker.HANDLERS, "test_ok", recording_handler(seen))
    await enqueue("test_ok", 10)
    helpers.advance(timedelta(seconds=30))
    assert (await stats())["oldest_ready_age_seconds"] == 30  # what monitoring watches

    assert await worker.run_ready_jobs(4) == 4  # a worker never takes more than its concurrency
    assert (await stats())["QUEUED"] == 6
    while await worker.run_ready_jobs(4):
        pass
    assert sorted(seen) == list(range(10))  # every job exactly once
    assert (await stats()) == {"DONE": 10, "oldest_ready_age_seconds": 0}


async def test_same_job_is_queued_once():
    async with db.sessionmaker()() as s, s.begin():
        for _ in range(3):
            await jobs.enqueue(s, "snapshot_refresh", {"user_id": 1}, dedupe_key="snapshot:1:2026-10-01")
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(select(func.count()).select_from(Job))).scalar_one() == 1


async def test_parallel_workers_never_share_a_job():
    await enqueue("test_ok", 6)
    maker = db.sessionmaker()
    async with maker() as first, first.begin():
        claimed_first = {job.id for job in await jobs.claim(first, 4)}
        async with maker() as second, second.begin():
            # The first worker hasn't committed yet: SKIP LOCKED passes over its rows.
            claimed_second = {job.id for job in await jobs.claim(second, 4)}
    assert len(claimed_first) == 4 and len(claimed_second) == 2
    assert not claimed_first & claimed_second


async def test_failing_job_backs_off_then_stops(monkeypatch):
    seen: list[int] = []
    monkeypatch.setitem(worker.HANDLERS, "test_fail", recording_handler(seen, fail=True))
    await enqueue("test_fail", 1, max_attempts=3)
    assert await worker.run_ready_jobs(4) == 1
    assert await worker.run_ready_jobs(4) == 0  # waiting out its backoff, not hammering
    for _ in range(2):
        helpers.advance(timedelta(hours=1))
        assert await worker.run_ready_jobs(4) == 1
    helpers.advance(timedelta(hours=1))
    assert await worker.run_ready_jobs(4) == 0
    async with db.sessionmaker()() as s, s.begin():
        job = (await s.execute(select(Job))).scalar_one()
    assert (job.status, job.attempts, len(seen)) == ("FAILED", 3, 3)
    assert job.last_error == "RuntimeError: downstream unavailable"


async def test_job_of_a_dead_worker_is_picked_up_again(monkeypatch):
    seen: list[int] = []
    monkeypatch.setitem(worker.HANDLERS, "test_ok", recording_handler(seen))
    await enqueue("test_ok", 1)
    async with db.sessionmaker()() as s, s.begin():
        assert len(await jobs.claim(s, 1)) == 1  # claimed, then the worker "crashes"
    assert await worker.run_ready_jobs(4) == 0  # still locked
    helpers.advance(timedelta(seconds=jobs.LOCK_SECONDS + 1))
    assert await worker.run_ready_jobs(4) == 1
    async with db.sessionmaker()() as s, s.begin():
        job = (await s.execute(select(Job))).scalar_one()
    assert (job.status, job.attempts, seen) == ("DONE", 2, [0])
