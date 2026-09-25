"""Set up and drive the end-to-end environment (see e2e/run.sh).

    python e2e/stack.py reset          # fresh schema in the *_e2e database
    python e2e/stack.py setup          # bots, channels, admin, funded pool
    python e2e/stack.py open-payouts   # as an admin: payout date = now
    python e2e/stack.py pay-all UTR    # as an admin: batch and pay every request

It uses the same service functions as the admin panel, against the database in
FF_DATABASE_URL, and refuses any database whose name doesn't end in _e2e.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import db, timeutil  # noqa: E402
from app.admin.auth import create_admin  # noqa: E402
from app.models import Campaign, RequiredChannel, WithdrawalRequest  # noqa: E402
from app.services import bots, ledger, withdrawals  # noqa: E402
from sqlalchemy import select, update  # noqa: E402

CHANNELS = [(-1002000000001, "Future Fashion News"), (-1002000000002, "Future Fashion Launch")]
RUN_DIR = ROOT / "e2e" / ".run"


def check_database() -> str:
    url = os.environ["FF_DATABASE_URL"]
    name = urlparse(url.replace("+asyncpg", "")).path.lstrip("/")
    if not name.endswith("_e2e"):
        sys.exit(f"Refusing to use database {name!r}: end-to-end runs need a database ending in _e2e.")
    return url


def reset(url: str) -> None:
    import asyncpg
    from alembic import command
    from alembic.config import Config

    async def drop() -> None:
        conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        finally:
            await conn.close()

    asyncio.run(drop())
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")


async def setup() -> None:
    async with db.sessionmaker()() as s, s.begin():
        await bots.register(s, "e2e_verify:TOKEN", "VERIFIER")
        await bots.register(s, "e2e_watcher:TOKEN", "WATCHER")
        for chat_id, title in CHANNELS:
            s.add(RequiredChannel(title=title, chat_id=chat_id, invite_link=f"https://t.me/+e2e{abs(chat_id)}"))
        await ledger.transfer(
            s,
            kind="FUNDING",
            idempotency_key=f"funding:e2e:{uuid.uuid4()}",
            source=await ledger.system_account(s, "COMPANY_FUNDING"),
            destination=await ledger.system_account(s, "PROMO_POOL"),
            amount_paise=1_00_000 * 100,
            created_by="admin:e2e",
        )
        _, totp_uri = await create_admin(s, "e2e-admin", "e2e-admin-password")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "env.json").write_text(
        json.dumps({"channels": [c for c, _ in CHANNELS], "verifier": "e2e_verify_bot", "admin_totp_uri": totp_uri})
    )
    await db.dispose()


async def open_payouts() -> None:
    async with db.sessionmaker()() as s, s.begin():
        await s.execute(update(Campaign).values(payout_opens_at=timeutil.now() - timedelta(minutes=1)))
    await db.dispose()


async def pay_all(reference: str) -> None:
    async with db.sessionmaker()() as s, s.begin():
        await withdrawals.create_batch(s, "admin:e2e")
    async with db.sessionmaker()() as s, s.begin():
        processing = (await s.execute(select(WithdrawalRequest).where(WithdrawalRequest.status == "PROCESSING"))).scalars()
        public_ids = [w.public_id for w in processing]
    for public_id in public_ids:
        async with db.sessionmaker()() as s, s.begin():
            await withdrawals.mark_paid(s, "admin:e2e", public_id, reference)
    await db.dispose()


def main() -> None:
    url = check_database()
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "reset":
        reset(url)
    elif command == "setup":
        asyncio.run(setup())
    elif command == "open-payouts":
        asyncio.run(open_payouts())
    elif command == "pay-all":
        asyncio.run(pay_all(sys.argv[2]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
