"""The Telegram Mini App launch gate: only the account's own verified Telegram
can pass it, a modified app can't skip it, and a misconfiguration never traps
users (CLAUDE.md §6, §15; the 'one Telegram per account' rule)."""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

from sqlalchemy import text

from app import db, timeutil
from app.api.deps import reset_gate_cache
from app.telegram.webapp import InitDataInvalid, validate
from tests import helpers
from tests.helpers import auth, fund_pool, telegram_setup

WATCHER_TOKEN = "watcher:TESTTOKEN"


def init_data(bot_token: str, tg_id: int, *, start_param: str | None = None, auth_date: int | None = None) -> str:
    """Build a Mini App initData string signed like Telegram signs it."""
    at = auth_date if auth_date is not None else int(timeutil.now().timestamp())
    fields = {"user": json.dumps({"id": tg_id, "first_name": "T"}), "auth_date": str(at)}
    if start_param:
        fields["start_param"] = start_param
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


async def enable_gate(short_name: str = "app") -> None:
    async with db.sessionmaker()() as s, s.begin():
        await s.execute(
            text("UPDATE app_settings SET launch_gate_enabled = true, miniapp_short_name = :n WHERE id = 1"),
            {"n": short_name},
        )
    reset_gate_cache()


async def signup_and_verify(client, setup) -> tuple[dict, str, int]:
    phone = helpers.new_phone()
    body = await helpers.signup(client, phone)
    tg_id = await helpers.verify(client, setup, body, phone)
    body["phone"] = phone
    return body, phone, tg_id


def nonce_from(deep_link: str) -> str:
    assert "startapp=" in deep_link, deep_link
    return deep_link.split("startapp=")[1]


async def test_init_data_validation():
    good = init_data(WATCHER_TOKEN, 777, start_param="abc")
    parsed = validate(good, WATCHER_TOKEN, max_age_seconds=3600)
    assert parsed.telegram_user_id == 777 and parsed.start_param == "abc"
    # Wrong token, tampered hash and a stale auth_date are all rejected.
    for bad in (
        (good, "other:TOKEN"),
        (good.replace("hash=", "hash=00") if "hash=" in good else good, WATCHER_TOKEN),
    ):
        try:
            validate(bad[0], bad[1], max_age_seconds=3600)
            raise AssertionError("expected InitDataInvalid")
        except InitDataInvalid:
            pass
    old = init_data(WATCHER_TOKEN, 777, auth_date=int(timeutil.now().timestamp()) - 4000)
    try:
        validate(old, WATCHER_TOKEN, max_age_seconds=3600)
        raise AssertionError("expected stale rejection")
    except InitDataInvalid:
        pass


async def test_gate_blocks_then_opens(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    user, _, tg_id = await signup_and_verify(client, setup)
    h = auth(user["tokens"])

    # Off by default: data flows and status reports "passed".
    assert (await client.get("/v1/dashboard", headers=h)).status_code == 200
    assert (await client.post("/v1/launch/status", headers=h)).json() == {"enabled": False, "passed": True}

    await enable_gate()
    # Now the data endpoint is blocked until the Mini App is completed.
    blocked = await client.get("/v1/dashboard", headers=h)
    assert blocked.status_code == 428 and blocked.json()["error"]["code"] == "LAUNCH_GATE_REQUIRED"
    assert (await client.post("/v1/launch/status", headers=h)).json() == {"enabled": True, "passed": False}

    challenge = (await client.post("/v1/launch/challenge", headers=h)).json()
    assert challenge["enabled"] is True and "watcher_bot/app?startapp=" in challenge["deep_link"]
    nonce = nonce_from(challenge["deep_link"])

    # The Mini App proves the Telegram identity and records the pass.
    done = await client.post(
        "/miniapp/complete", json={"init_data": init_data(WATCHER_TOKEN, tg_id, start_param=nonce), "nonce": nonce}
    )
    assert done.status_code == 200 and done.json() == {"ok": True}
    assert (await client.post("/v1/launch/status", headers=h)).json() == {"enabled": True, "passed": True}
    assert (await client.get("/v1/dashboard", headers=h)).status_code == 200


async def test_only_your_own_telegram_passes_your_gate(client, telegram):
    """A user can't pass their gate from a different Telegram account, and a
    Telegram account not linked to any verified account is refused."""
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    alice, _, alice_tg = await signup_and_verify(client, setup)
    bob, _, bob_tg = await signup_and_verify(
        client,
        setup,
    )
    await enable_gate()

    # Alice starts her crossing, but Bob's Telegram tries to complete it.
    challenge = (await client.post("/v1/launch/challenge", headers=auth(alice["tokens"]))).json()
    nonce = nonce_from(challenge["deep_link"])
    mismatch = await client.post(
        "/miniapp/complete", json={"init_data": init_data(WATCHER_TOKEN, bob_tg, start_param=nonce), "nonce": nonce}
    )
    assert mismatch.status_code == 403 and mismatch.json()["error"]["code"] == "LAUNCH_GATE_MISMATCH"
    # Alice still hasn't passed.
    assert (await client.post("/v1/launch/status", headers=auth(alice["tokens"]))).json()["passed"] is False

    # An unknown Telegram id (nobody's verified account) is refused too.
    unknown = await client.post(
        "/miniapp/complete", json={"init_data": init_data(WATCHER_TOKEN, 999000001, start_param=nonce), "nonce": nonce}
    )
    assert unknown.status_code == 403 and unknown.json()["error"]["code"] == "LAUNCH_GATE_MISMATCH"


async def test_forged_init_data_is_refused(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    user, _, tg_id = await signup_and_verify(client, setup)
    await enable_gate()
    nonce = nonce_from((await client.post("/v1/launch/challenge", headers=auth(user["tokens"]))).json()["deep_link"])
    # initData signed with the wrong token can't be forged into a pass.
    forged = await client.post(
        "/miniapp/complete", json={"init_data": init_data("not:thewatcher", tg_id, start_param=nonce), "nonce": nonce}
    )
    assert forged.status_code == 400 and forged.json()["error"]["code"] == "LAUNCH_GATE_INVALID"
    assert (await client.post("/v1/launch/status", headers=auth(user["tokens"]))).json()["passed"] is False
