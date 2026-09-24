"""Test setup: a real PostgreSQL and Redis, a fake Telegram, a movable clock.

Tests need a running PostgreSQL and Redis. Point them elsewhere with
FF_TEST_DATABASE_URL / FF_TEST_REDIS_URL (CI uses service containers).
"""

from __future__ import annotations

import os

os.environ.setdefault("FF_ENV", "test")
os.environ["FF_DATABASE_URL"] = os.environ.get(
    "FF_TEST_DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:5432/ff_test"
)
os.environ["FF_REDIS_URL"] = os.environ.get("FF_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ["FF_PUBLIC_BASE_URL"] = "https://futurefashion.test"
os.environ["FF_ARGON2_TIME_COST"] = "1"
os.environ["FF_ARGON2_MEMORY_KIB"] = "8192"
os.environ["FF_ARGON2_PARALLELISM"] = "1"
os.environ["FF_LOG_LEVEL"] = "WARNING"

from collections.abc import AsyncIterator  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app import db as app_db  # noqa: E402
from app import timeutil  # noqa: E402
from app.api import deps  # noqa: E402
from app.main import app  # noqa: E402
from app.redis_client import redis  # noqa: E402
from app.telegram import client as telegram_client  # noqa: E402
from tests.fakes import FakeTelegram  # noqa: E402

TABLES_TO_KEEP = {"alembic_version"}

SEED_SQL = [
    "INSERT INTO app_settings (id) VALUES (1)",
    "INSERT INTO membership_counter (id, verified_count) VALUES (1, 0)",
    "INSERT INTO ledger_accounts (kind) VALUES ('COMPANY_FUNDING'), ('PROMO_POOL'), ('WITHDRAWAL_CLEARING'), ('PAYOUT_SETTLED')",
    """INSERT INTO campaigns (name, starts_at, ends_at, brand_reveal_at, launch_at, payout_opens_at,
                              level_1_reward_paise, min_withdrawal_paise, capacity)
       VALUES ('Future Fashion launch', '2026-09-01 00:00:00+05:30', '2026-12-31 23:59:59+05:30',
               '2026-12-21 00:00:00+05:30', '2026-12-31 00:00:00+05:30', '2026-12-31 00:00:00+05:30',
               20000, 20000, 50000000)""",
]


def _migrate(url: str) -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def database() -> AsyncIterator[None]:
    url = os.environ["FF_DATABASE_URL"]
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()
    import anyio

    await anyio.to_thread.run_sync(_migrate, url)
    yield
    await app_db.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    engine = app_db.engine()
    async with engine.begin() as conn:
        tables = [
            row[0]
            for row in await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            if row[0] not in TABLES_TO_KEEP
        ]
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        for statement in SEED_SQL:
            await conn.execute(text(statement))
    await redis().flushdb()
    deps.reset_gate_cache()
    # A fixed "now" inside the campaign, before the payout date.
    timeutil.freeze(datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
    yield
    timeutil.freeze(None)


@pytest.fixture
def telegram(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    fake = FakeTelegram()
    monkeypatch.setattr(telegram_client, "client_factory", fake.api)
    return fake


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-App-Version": "1.0.0"}) as c:
        yield c
