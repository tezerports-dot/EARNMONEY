"""Operator commands.

python -m app.cli create-admin <username>   # prints the TOTP setup link once
python -m app.cli worker                    # background jobs
python -m app.cli check-ledger              # reconciliation
python -m app.cli ensure-app-role           # create/refresh the DML-only app role
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import func, select, text

from app import db, logging_setup
from app.admin.auth import create_admin
from app.config import get_settings
from app.models import LedgerAccount


async def _create_admin(username: str) -> int:
    password = getpass.getpass("Password (12+ characters): ")
    if len(password) < 12 or password != getpass.getpass("Repeat password: "):
        print("Passwords must match and be at least 12 characters.", file=sys.stderr)
        return 1
    async with db.sessionmaker()() as session, session.begin():
        _, uri = await create_admin(session, username, password)
    print("Admin created. Add this to an authenticator app now (it isn't shown again):")
    print(uri)
    return 0


async def _check_ledger() -> int:
    async with db.sessionmaker()() as session, session.begin():
        total = (await session.execute(select(func.coalesce(func.sum(LedgerAccount.balance_paise), 0)))).scalar_one()
        bad = (
            await session.execute(
                text(
                    "SELECT count(*) FROM (SELECT a.id FROM ledger_accounts a LEFT JOIN ledger_entries e "
                    "ON e.account_id = a.id GROUP BY a.id HAVING a.balance_paise <> COALESCE(SUM(e.amount_paise), 0)) x"
                )
            )
        ).scalar_one()
    print(f"sum of balances: {total} paise; accounts not matching their entries: {bad}")
    return 0 if total == 0 and bad == 0 else 2


async def _ensure_app_role() -> int:
    """Create or refresh the least-privilege role the app connects as, and grant
    it DML (no DDL, no DROP) on the schema. Run as the owner before migrations;
    ALTER DEFAULT PRIVILEGES then covers tables the migration is about to create.
    A blank FF_APP_DB_PASSWORD skips this (dev and tests connect as the owner)."""
    import asyncpg

    settings = get_settings()
    if not settings.app_db_password:
        print("FF_APP_DB_PASSWORD is blank; leaving database privileges as they are.")
        return 0
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        # Quote the identifier and password through Postgres itself, never by hand.
        ident = await conn.fetchval("SELECT quote_ident($1)", settings.app_db_user)
        literal = await conn.fetchval("SELECT quote_literal($1)", settings.app_db_password)
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", settings.app_db_user)
        role = f"{'ALTER' if exists else 'CREATE'} ROLE {ident} WITH LOGIN PASSWORD {literal} NOSUPERUSER NOCREATEDB NOCREATEROLE"
        await conn.execute(role)
        for statement in (
            f"GRANT USAGE ON SCHEMA public TO {ident}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ident}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ident}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ident}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {ident}",
        ):
            await conn.execute(statement)
    finally:
        await conn.close()
    print(f"App role {settings.app_db_user!r} is present with DML-only privileges.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin")
    create.add_argument("username")
    worker = sub.add_parser("worker")
    worker.add_argument("--concurrency", type=int, default=4)
    sub.add_parser("check-ledger")
    sub.add_parser("ensure-app-role")
    args = parser.parse_args()
    logging_setup.configure(get_settings().log_level)

    if args.command == "create-admin":
        return asyncio.run(_create_admin(args.username))
    if args.command == "check-ledger":
        return asyncio.run(_check_ledger())
    if args.command == "ensure-app-role":
        return asyncio.run(_ensure_app_role())
    from app import worker as worker_module

    asyncio.run(worker_module.run(args.concurrency))
    return 0


if __name__ == "__main__":
    sys.exit(main())
