"""Fraud signals (CLAUDE.md §7; abuse case 4).

The app collects no device identifiers. One person running many accounts is
limited instead by one account per phone number and one per Telegram account
(test_auth, test_verification), and flagged when accounts share a bank
account or a referrer's friends verify in a sudden burst. A flag never
punishes anyone automatically: it holds payouts until an admin looks.
"""

from __future__ import annotations

from sqlalchemy import select

from app import db, timeutil
from app.models import RiskFlag, User
from app.services import risk, withdrawals
from tests import helpers
from tests.helpers import auth, fund_pool, idem, telegram_setup, verified_user
from tests.test_wallet import BANK, PAYOUT_DAY


async def flags() -> dict[str, set[str]]:
    async with db.sessionmaker()() as s, s.begin():
        rows = await s.execute(
            select(User.public_id, RiskFlag.kind).join(User, User.id == RiskFlag.user_id).where(RiskFlag.resolved_at.is_(None))
        )
        found: dict[str, set[str]] = {}
        for public_id, kind in rows:
            found.setdefault(public_id, set()).add(kind)
        return found


async def resolve(public_id: str) -> None:
    async with db.sessionmaker()() as s, s.begin():
        user = (await s.execute(select(User).where(User.public_id == public_id))).scalar_one()
        for flag in (await s.execute(select(RiskFlag).where(RiskFlag.user_id == user.id))).scalars():
            flag.resolved_at, flag.resolved_by = timeutil.now(), "admin:test"


async def test_shared_bank_account_holds_payouts_until_reviewed(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a = await verified_user(client, setup)
    b = await verified_user(client, setup)
    for referrer in (a, b):
        await verified_user(client, setup, referrer["user"]["public_id"])

    timeutil.freeze(PAYOUT_DAY)
    for user in (a, b):
        await helpers.login(client, user)
        h = auth(user["tokens"])
        assert (await client.post("/v1/bank-details", json=BANK, headers={**h, **idem()})).status_code == 200
        r = await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **idem()})
        assert r.status_code == 201
        # Users see an ordinary request; risk signals are never exposed.
        assert "flag" not in r.text.lower() and "risk" not in r.text.lower()

    ids = {a["user"]["public_id"], b["user"]["public_id"]}
    assert await flags() == {public_id: {"SHARED_BANK_ACCOUNT"} for public_id in ids}
    async with db.sessionmaker()() as s, s.begin():
        assert await withdrawals.create_batch(s, "admin:test") is None  # both held

    await resolve(a["user"]["public_id"])
    async with db.sessionmaker()() as s, s.begin():
        batch = await withdrawals.create_batch(s, "admin:test")
        assert batch is not None and batch.request_count == 1
    statuses = {}
    for user in (a, b):
        items = (await client.get("/v1/withdrawals", headers=auth(user["tokens"]))).json()["items"]
        statuses[user["user"]["public_id"]] = items[0]["status"]
    assert statuses == {a["user"]["public_id"]: "PROCESSING", b["user"]["public_id"]: "REQUESTED"}


async def test_referral_burst_is_flagged_but_still_paid(client, telegram, monkeypatch):
    monkeypatch.setattr(risk, "REFERRAL_BURST_THRESHOLD", 3)
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a = await verified_user(client, setup)
    for _ in range(2):
        await verified_user(client, setup, a["user"]["public_id"])
    assert await flags() == {}
    await verified_user(client, setup, a["user"]["public_id"])
    assert await flags() == {a["user"]["public_id"]: {"REFERRAL_BURST"}}
    await helpers.refresh(client, a)
    wallet = (await client.get("/v1/wallet", headers=auth(a["tokens"]))).json()
    assert wallet["total_earned_paise"] == 3 * 20000  # a flag asks for a look; it takes nothing away


async def test_suspended_users_withdrawals_are_held(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a = await verified_user(client, setup)
    await verified_user(client, setup, a["user"]["public_id"])
    timeutil.freeze(PAYOUT_DAY)
    await helpers.login(client, a)
    h = auth(a["tokens"])
    await client.post("/v1/bank-details", json=BANK, headers={**h, **idem()})
    assert (await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **idem()})).status_code == 201

    async with db.sessionmaker()() as s, s.begin():
        user = (await s.execute(select(User).where(User.public_id == a["user"]["public_id"]))).scalar_one()
        user.status = "SUSPENDED"
    async with db.sessionmaker()() as s, s.begin():
        assert await withdrawals.create_batch(s, "admin:test") is None
    async with db.sessionmaker()() as s, s.begin():
        user = (await s.execute(select(User).where(User.public_id == a["user"]["public_id"]))).scalar_one()
        user.status = "ACTIVE"
    async with db.sessionmaker()() as s, s.begin():
        batch = await withdrawals.create_batch(s, "admin:test")
        assert batch is not None and batch.request_count == 1
