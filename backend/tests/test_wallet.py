"""Wallet, bank details and withdrawals (CLAUDE.md §12–13, §22–23, §31;
abuse cases 8, 18–22, 26)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from app import db, timeutil
from app.models import BankAccount, LedgerAccount, WithdrawalRequest
from app.services import withdrawals
from app.worker import housekeeping, run_ready_jobs
from tests import helpers
from tests.helpers import auth, fund_pool, idem, telegram_setup, verified_user

PAYOUT_DAY = datetime(2026, 12, 31, 6, 0, tzinfo=UTC)  # 11:30 IST on 31 Dec
BANK = {"account_holder_name": "Ravi Kumar", "account_number": "123456784821", "ifsc": "hdfc0001234"}


async def earner(client, telegram, referrals: int = 2) -> dict:
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    user = await verified_user(client, setup)
    for _ in range(referrals):
        await verified_user(client, setup, user["user"]["public_id"])
    await helpers.refresh(client, user)
    return user


async def wallet(client, user) -> dict:
    return (await client.get("/v1/wallet", headers=auth(user["tokens"]))).json()


async def on_payout_day(client, user) -> None:
    timeutil.freeze(PAYOUT_DAY)
    await helpers.login(client, user)  # three months later: a new login


async def ledger_is_balanced() -> bool:
    async with db.sessionmaker()() as s, s.begin():
        total = (await s.execute(select(func.coalesce(func.sum(LedgerAccount.balance_paise), 0)))).scalar_one()
        mismatched = (
            await s.execute(
                text(
                    "SELECT count(*) FROM (SELECT a.id FROM ledger_accounts a LEFT JOIN ledger_entries e ON e.account_id = a.id "
                    "GROUP BY a.id HAVING a.balance_paise <> COALESCE(SUM(e.amount_paise), 0)) x"
                )
            )
        ).scalar_one()
    return total == 0 and mismatched == 0


async def test_rewards_are_pending_until_payout_date(client, telegram):
    user = await earner(client, telegram)
    w = await wallet(client, user)
    assert w["total_earned_paise"] == 40000
    assert w["pending_paise"] == 40000
    assert w["available_paise"] == 0
    assert w["payouts_open"] is False
    assert w["breakdown"] == [{"level": 1, "reward_count": 2, "amount_paise": 40000}]
    assert [e["kind"] for e in w["recent_entries"]] == ["REFERRAL_REWARD", "REFERRAL_REWARD"]
    assert all(e["direction"] == "CREDIT" and e["amount_paise"] == 20000 for e in w["recent_entries"])
    await client.post("/v1/bank-details", json=BANK, headers={**auth(user["tokens"]), **idem()})
    r = await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**auth(user["tokens"]), **idem()})
    assert r.json()["error"]["code"] == "PAYOUTS_NOT_OPEN"


async def test_unlock_on_payout_date(client, telegram):
    user = await earner(client, telegram)
    await on_payout_day(client, user)
    w = await wallet(client, user)
    assert (w["pending_paise"], w["available_paise"], w["payouts_open"]) == (0, 40000, True)
    assert w["recent_entries"][0]["kind"] == "REWARDS_UNLOCKED"
    # Reading again moves nothing twice.
    assert (await wallet(client, user))["available_paise"] == 40000
    assert await ledger_is_balanced()


async def test_worker_unlocks_everyone_on_payout_date(client, telegram):
    user = await earner(client, telegram)
    timeutil.freeze(PAYOUT_DAY)
    await housekeeping()
    await run_ready_jobs(4)
    async with db.sessionmaker()() as s, s.begin():
        pending = (
            await s.execute(select(func.sum(LedgerAccount.balance_paise)).where(LedgerAccount.kind == "USER_PENDING"))
        ).scalar_one()
    assert pending == 0
    await helpers.login(client, user)
    assert (await wallet(client, user))["available_paise"] == 40000


async def test_bank_details_are_masked_and_encrypted(client, telegram):
    user = await earner(client, telegram, referrals=0)
    r = await client.post("/v1/bank-details", json=BANK, headers={**auth(user["tokens"]), **idem()})
    assert r.status_code == 200
    body = r.json()
    assert body["account_number_masked"] == "XXXX XXXX 4821"
    assert body["ifsc"] == "HDFC0001234"
    assert "123456784821" not in r.text
    got = (await client.get("/v1/bank-details", headers=auth(user["tokens"]))).text
    assert "123456784821" not in got
    async with db.sessionmaker()() as s, s.begin():
        row = (await s.execute(select(BankAccount))).scalar_one()
        stored = (await s.execute(text("SELECT string_agg(details::text, ' ') FROM audit_log"))).scalar_one()
    assert b"123456784821" not in row.account_number_ciphertext
    assert "123456784821" not in stored  # never in the audit log either


async def test_bank_details_validation(client, telegram):
    user = await earner(client, telegram, referrals=0)
    r = await client.post(
        "/v1/bank-details",
        json={"account_holder_name": "1", "account_number": "12ab", "ifsc": "BAD"},
        headers={**auth(user["tokens"]), **idem()},
    )
    assert r.status_code == 400
    assert set(r.json()["error"]["fields"]) == {"account_holder_name", "account_number", "ifsc"}


async def test_withdrawal_rules(client, telegram):
    """Abuse cases 18–20: the server decides every amount."""
    user = await earner(client, telegram)
    await on_payout_day(client, user)
    h = auth(user["tokens"])

    r = await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **idem()})
    assert r.json()["error"]["code"] == "BANK_DETAILS_REQUIRED"
    await client.post("/v1/bank-details", json=BANK, headers={**h, **idem()})
    for amount, code in ((10000, "BELOW_MINIMUM"), (40001, "INSUFFICIENT_BALANCE")):
        r = await client.post("/v1/withdrawals", json={"amount_paise": amount}, headers={**h, **idem()})
        assert r.json()["error"]["code"] == code
    for bad in (200.5, "20000", -20000, 0, True):
        r = await client.post("/v1/withdrawals", json={"amount_paise": bad}, headers={**h, **idem()})
        assert r.json()["error"]["code"] == "VALIDATION_FAILED", bad

    ok = await client.post("/v1/withdrawals", json={"amount_paise": 30000}, headers={**h, **idem()})
    assert ok.status_code == 201
    assert ok.json()["status"] == "REQUESTED"
    assert ok.json()["bank_account_masked"] == "XXXX 4821"
    w = await wallet(client, user)
    assert (w["available_paise"], w["in_withdrawal_paise"]) == (10000, 30000)
    assert await ledger_is_balanced()


async def test_duplicate_withdrawal_request(client, telegram):
    """Abuse cases 8, 21 and 26: a retried request moves money once."""
    user = await earner(client, telegram)
    await on_payout_day(client, user)
    h = auth(user["tokens"])
    await client.post("/v1/bank-details", json=BANK, headers={**h, **idem()})
    key = idem()
    first = await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **key})
    retry = await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **key})
    assert first.status_code == retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]
    changed = await client.post("/v1/withdrawals", json={"amount_paise": 40000}, headers={**h, **key})
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(select(func.count()).select_from(WithdrawalRequest))).scalar_one() == 1


async def test_concurrent_withdrawals(client, telegram):
    """Abuse case 22: parallel requests can't both hold the same money."""
    user = await earner(client, telegram)
    await on_payout_day(client, user)
    h = auth(user["tokens"])
    await client.post("/v1/bank-details", json=BANK, headers={**h, **idem()})
    results = await asyncio.gather(
        *(
            client.post("/v1/withdrawals", json={"amount_paise": 40000}, headers={**h, **idem()}) for _ in range(5)
        )  # 5 = the hourly limit
    )
    assert sorted(r.status_code for r in results).count(201) == 1
    codes = {r.json()["error"]["code"] for r in results if r.status_code != 201}
    assert codes <= {"WITHDRAWAL_IN_PROGRESS", "INSUFFICIENT_BALANCE"}
    assert (await wallet(client, user))["available_paise"] == 0
    assert await ledger_is_balanced()


async def test_bank_details_locked_during_withdrawal(client, telegram):
    user = await earner(client, telegram)
    await on_payout_day(client, user)
    h = auth(user["tokens"])
    await client.post("/v1/bank-details", json=BANK, headers={**h, **idem()})
    await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **idem()})
    r = await client.post("/v1/bank-details", json={**BANK, "account_number": "999999999999"}, headers={**h, **idem()})
    assert r.json()["error"]["code"] == "BANK_DETAILS_LOCKED"
    assert (await client.get("/v1/bank-details", headers=h)).json()["locked"] is True


async def test_admin_marks_paid_and_failed(client, telegram):
    user = await earner(client, telegram)
    await on_payout_day(client, user)
    h = auth(user["tokens"])
    await client.post("/v1/bank-details", json=BANK, headers={**h, **idem()})
    first = (await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **idem()})).json()

    async with db.sessionmaker()() as s, s.begin():
        batch = await withdrawals.create_batch(s, "admin:test")
        assert batch is not None and batch.request_count == 1
    async with db.sessionmaker()() as s, s.begin():
        await withdrawals.mark_failed(s, "admin:test", first["id"].removeprefix("WD-"), "Account closed")
    w = await wallet(client, user)
    assert (w["available_paise"], w["in_withdrawal_paise"]) == (40000, 0)
    assert w["recent_entries"][0]["kind"] == "WITHDRAWAL_RETURNED"

    second = (await client.post("/v1/withdrawals", json={"amount_paise": 40000}, headers={**h, **idem()})).json()
    async with db.sessionmaker()() as s, s.begin():
        await withdrawals.create_batch(s, "admin:test")
    async with db.sessionmaker()() as s, s.begin():
        await withdrawals.mark_paid(s, "admin:test", second["id"].removeprefix("WD-"), "UTR123456")
    history = (await client.get("/v1/withdrawals", headers=h)).json()["items"]
    assert [(i["status"], i["bank_reference"]) for i in history] == [("PAID", "UTR123456"), ("FAILED", None)]
    w = await wallet(client, user)
    assert (w["available_paise"], w["withdrawn_paise"], w["total_earned_paise"]) == (0, 40000, 40000)
    assert await ledger_is_balanced()


async def test_users_only_see_their_own_money(client, telegram):
    """IDOR: nothing takes a user id, so one user can't read another's data."""
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a = await verified_user(client, setup)
    b = await verified_user(client, setup, a["user"]["public_id"])
    wa, wb = await wallet(client, a), await wallet(client, b)
    assert wa["total_earned_paise"] == 20000 and wb["total_earned_paise"] == 0
    await helpers.refresh(client, b)
    direct = (await client.get("/v1/referrals/direct", headers=auth(b["tokens"]))).json()["items"]
    assert direct == []


async def test_auth_is_checked_before_the_idempotency_header(client):
    """Security probe: an unauthenticated POST is 401, not a 400 about a missing
    Idempotency-Key. Auth runs before request validation, so the endpoint's
    requirements aren't revealed to anyone who isn't logged in."""
    for path, body in [("/v1/bank-details", BANK), ("/v1/withdrawals", {"amount_paise": 20000})]:
        # No Authorization header, and no Idempotency-Key either.
        r = await client.post(path, json=body)
        assert r.status_code == 401, (path, r.status_code, r.text)
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"
