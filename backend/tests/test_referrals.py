"""Referral binding, the four-level table and rewards (CLAUDE.md §8–9;
abuse cases 1, 2, 7, 17, 18, 23, 24, 32, 33)."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Campaign, Job, ReferralReward, User
from app.services import rewards
from app.worker import run_ready_jobs
from tests import helpers
from tests.helpers import auth, fund_pool, signup, telegram_setup, verified_user


async def chain(client, setup, length: int) -> list[dict]:
    """A referred B referred C … Returns the users top-down."""
    users = [await verified_user(client, setup)]
    for _ in range(length - 1):
        users.append(await verified_user(client, setup, users[-1]["user"]["public_id"]))
    return users


async def summary(client, user) -> dict:
    return (await client.get("/v1/referrals/summary", headers=auth(user["tokens"]))).json()


async def reward_rows() -> list[tuple[str, str, int, int]]:
    async with db.sessionmaker()() as s, s.begin():
        rows = await s.execute(
            text(
                "SELECT b.public_id, src.public_id, r.level, r.amount_paise FROM referral_rewards r "
                "JOIN users b ON b.id = r.beneficiary_id JOIN users src ON src.id = r.source_user_id ORDER BY r.id"
            )
        )
        return [tuple(row) for row in rows]


async def test_only_direct_referrer_is_paid(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a, b, c, d, e = await chain(client, setup, 5)
    ids = [u["user"]["public_id"] for u in (a, b, c, d, e)]
    # Each verification paid exactly one reward: ₹200 to the direct referrer.
    assert await reward_rows() == [
        (ids[0], ids[1], 1, 20000),
        (ids[1], ids[2], 1, 20000),
        (ids[2], ids[3], 1, 20000),
        (ids[3], ids[4], 1, 20000),
    ]


async def test_four_level_table_shows_counts_and_zero_income(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    users = await chain(client, setup, 6)  # A…F: F is five levels below A
    await helpers.refresh(client, users[0])
    table = await summary(client, users[0])
    assert [row["level"] for row in table["levels"]] == [1, 2, 3, 4]
    assert [row["user_count"] for row in table["levels"]] == [1, 1, 1, 1]  # level 5 isn't tracked
    assert [row["reward_per_user_paise"] for row in table["levels"]] == [20000, 0, 0, 0]
    assert [row["total_reward_paise"] for row in table["levels"]] == [20000, 0, 0, 0]
    assert table["total_reward_paise"] == 20000
    assert table["total_user_count"] == 4


async def test_database_refuses_deeper_rewards_and_income(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a, b, c = await chain(client, setup, 3)
    async with db.sessionmaker()() as s:
        with pytest.raises(IntegrityError, match="only_level_one_pays"):
            async with s.begin():
                await s.execute(
                    text(
                        "INSERT INTO referral_rewards (beneficiary_id, source_user_id, level, amount_paise, campaign_id, ledger_transaction_id) "
                        "SELECT a.id, c.id, 2, 5000, 1, 1 FROM users a, users c WHERE a.public_id = :a AND c.public_id = :c"
                    ),
                    {"a": a["user"]["public_id"], "c": c["user"]["public_id"]},
                )
    assert (await summary(client, a))["levels"][1]["user_count"] == 1  # creates the snapshot row
    async with db.sessionmaker()() as s:
        with pytest.raises(IntegrityError, match="level_2_unpaid"):
            async with s.begin():
                await s.execute(text("UPDATE referral_snapshots SET level_2_income_paise = 5000"))


async def test_reward_is_credited_once(client, telegram):
    """Abuse cases 7 and 23: retries and concurrent calls never pay twice."""
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a, b = await chain(client, setup, 2)

    async def credit_again() -> None:
        async with db.sessionmaker()() as s, s.begin():
            user = (await s.execute(select(User).where(User.public_id == b["user"]["public_id"]))).scalar_one()
            await rewards.credit_for_verified_user(s, user)

    await asyncio.gather(*(credit_again() for _ in range(5)))
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(select(func.count()).select_from(ReferralReward))).scalar_one() == 1


async def test_no_rewards_when_pool_is_empty(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool(rupees=200)  # exactly one reward
    a, b, c = await chain(client, setup, 3)
    assert len(await reward_rows()) == 1
    config = (await client.get("/v1/config")).json()
    assert config["campaign"]["rewards_open"] is False


async def test_paused_or_ended_campaign_pays_nothing(client, telegram):
    """Abuse cases 32 and 33."""
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a = await verified_user(client, setup)
    async with db.sessionmaker()() as s, s.begin():
        (await s.execute(select(Campaign))).scalar_one().paused = True
    config = (await client.get("/v1/config")).json()
    assert config["campaign"]["status"] == "PAUSED"
    assert config["campaign"]["signups_open"] is False
    r = await helpers.signup_response(client, code=a["user"]["public_id"])
    assert r.json()["error"]["code"] == "SIGNUPS_CLOSED"


async def test_signups_close_at_capacity(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    async with db.sessionmaker()() as s, s.begin():
        (await s.execute(select(Campaign))).scalar_one().capacity = 1
    await verified_user(client, setup)
    r = await helpers.signup_response(client)
    assert r.json()["error"]["code"] == "SIGNUPS_CLOSED"


async def test_referrer_cannot_be_changed(client, telegram):
    """Abuse cases 1, 2 and 17: the referrer is fixed at signup."""
    setup = await telegram_setup(telegram, channels=0)
    a = await verified_user(client, setup)
    b = await verified_user(client, setup, a["user"]["public_id"])
    assert b["user"]["referred_by"] == a["user"]["public_id"]
    # There is no API to change it; the database also blocks self-reference.
    async with db.sessionmaker()() as s:
        with pytest.raises(IntegrityError, match="not_self_referred"):
            async with s.begin():
                await s.execute(text("UPDATE users SET referrer_id = id WHERE public_id = :p"), {"p": a["user"]["public_id"]})


async def test_referral_codes_are_normalised(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    a = await verified_user(client, setup)
    code = a["user"]["public_id"]
    assert (await client.get(f"/v1/referral-codes/{code.lower()}")).status_code == 200
    spaced = f" {code[:4]} {code[4:]} "
    r = await helpers.signup_response(client, code=spaced)
    assert r.status_code == 201
    assert r.json()["user"]["referred_by"] == code
    assert (await client.get("/v1/referral-codes/AB")).status_code == 404


async def test_direct_list_shows_level_one_only(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a, b, c = await chain(client, setup, 3)
    pending = await signup(client, helpers.new_phone(), a["user"]["public_id"])
    await helpers.refresh(client, a)
    items = (await client.get("/v1/referrals/direct", headers=auth(a["tokens"]))).json()["items"]
    assert [i["public_id"] for i in items] == [pending["user"]["public_id"], b["user"]["public_id"]]
    assert items[0]["status"] == "PENDING" and items[0]["reward_paise"] == 0
    assert items[1]["status"] == "VERIFIED" and items[1]["reward_paise"] == 20000
    assert all("X" in i["phone_masked"] for i in items)
    assert c["user"]["public_id"] not in str(items)  # level 2 is never listed
    table = await summary(client, a)
    assert table["level_1_pending_count"] == 1


async def test_direct_list_pagination(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    a = await verified_user(client, setup)
    for _ in range(5):
        await signup(client, helpers.new_phone(), a["user"]["public_id"])
        helpers.advance(timedelta(seconds=1))
    await helpers.refresh(client, a)
    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = (await client.get("/v1/referrals/direct", params=params, headers=auth(a["tokens"]))).json()
        seen += [i["public_id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 5


async def test_stale_snapshot_is_refreshed_by_the_worker(client, telegram):
    """Abuse case 24: a stale table is served with refresh_pending, then refreshed."""
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    a = await verified_user(client, setup)
    assert (await summary(client, a))["levels"][0]["user_count"] == 0
    await verified_user(client, setup, a["user"]["public_id"])
    await helpers.refresh(client, a)
    assert (await summary(client, a))["levels"][0]["user_count"] == 0  # same day: snapshot kept
    helpers.advance(timedelta(hours=25))
    await helpers.refresh(client, a)
    stale = await summary(client, a)
    assert stale["refresh_pending"] is True and stale["levels"][0]["user_count"] == 0
    await summary(client, a)  # asking again doesn't queue a second job
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(select(func.count()).select_from(Job))).scalar_one() == 1
    assert await run_ready_jobs(4) == 1
    fresh = await summary(client, a)
    assert fresh["refresh_pending"] is False
    assert fresh["levels"][0]["user_count"] == 1
    assert fresh["levels"][0]["total_reward_paise"] == 20000


async def test_config_is_truthful(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    config = (await client.get("/v1/config")).json()
    assert config["membership"] == {"verified_count": 0, "capacity": 50000000}
    assert config["promotion"]["allocation_paise"] is None
    assert config["campaign"]["brand_name"] is None
    await verified_user(client, setup)
    await verified_user(client, setup)
    assert (await client.get("/v1/config")).json()["membership"]["verified_count"] == 2


async def test_brand_name_hidden_until_reveal(client):
    async with db.sessionmaker()() as s, s.begin():
        (await s.execute(select(Campaign))).scalar_one().brand_name = "Maison Secret"
    assert (await client.get("/v1/config")).json()["campaign"]["brand_name"] is None
    helpers.advance(timedelta(days=81))  # past 21 December
    assert (await client.get("/v1/config")).json()["campaign"]["brand_name"] == "Maison Secret"


async def test_promotional_allocation_comes_from_the_ledger(client):
    async with db.sessionmaker()() as s, s.begin():
        (await s.execute(select(Campaign))).scalar_one().show_promo_allocation = True
    assert (await client.get("/v1/config")).json()["promotion"]["allocation_paise"] is None
    await fund_pool(rupees=5_00_000)
    assert (await client.get("/v1/config")).json()["promotion"]["allocation_paise"] == 5_00_000 * 100
