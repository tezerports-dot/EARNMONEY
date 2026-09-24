"""Telegram verification (CLAUDE.md §6; abuse cases 6, 11–16, 27, 36–38)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import db
from app.models import MembershipCounter, ReferralReward, TelegramBot, User
from app.services import bots
from app.telegram.client import TelegramError
from tests import helpers
from tests.helpers import (
    auth,
    callback,
    join_request,
    message,
    new_phone,
    new_telegram_id,
    own_contact,
    post_update,
    signup,
    telegram_setup,
)


async def open_session(client, body) -> str:
    r = await client.post("/v1/telegram/verification-session", headers=auth(body["tokens"]))
    assert r.status_code == 200, r.text
    return r.json()["deep_link"].split("start=")[1]


async def status(client, body) -> dict:
    return (await client.get("/v1/telegram/verification-session", headers=auth(body["tokens"]))).json()


async def verified_count() -> int:
    async with db.sessionmaker()() as s, s.begin():
        return (await s.execute(select(MembershipCounter.verified_count))).scalar_one()


async def test_full_flow_verifies_account(client, telegram):
    setup = await telegram_setup(telegram)
    phone = new_phone()
    body = await signup(client, phone)
    session = (await client.post("/v1/telegram/verification-session", headers=auth(body["tokens"]))).json()
    assert session["status"] == "OPEN"
    assert session["bot_username"] == "verify1_bot"
    assert session["channel_count"] == 2
    token = session["deep_link"].split("start=")[1]

    tg = new_telegram_id()
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    markup = setup.verifier.fake.last_markup(tg)
    labels = [b["text"] for row in markup["inline_keyboard"] for b in row]
    assert labels[:2] == ["JOIN 1", "JOIN 2"]  # small JOIN buttons, links not pasted in text
    assert (await status(client, body))["status"] == "IN_PROGRESS"

    for chat_id in setup.channels:
        await post_update(client, setup.watcher, join_request(tg, chat_id))
    await post_update(client, setup.verifier, callback(tg))
    assert setup.verifier.fake.last_markup(tg)["keyboard"][0][0]["request_contact"] is True

    await post_update(client, setup.verifier, message(tg, contact=own_contact(tg, phone)))
    assert "verified" in setup.verifier.fake.sent_texts(tg)[-1]
    assert (await status(client, body))["status"] == "COMPLETED"
    me = (await client.get("/v1/me", headers=auth(body["tokens"]))).json()
    assert me["status"] == "ACTIVE"
    assert me["referral_code"] == me["public_id"]
    assert await verified_count() == 1
    # Join requests are recorded, never approved by the bots.
    assert not [m for m, _ in setup.watcher.fake.calls if m == "approveChatJoinRequest"]
    # No bot message ever contains the stored phone number.
    assert all(phone not in t for t in setup.verifier.fake.sent_texts())


async def test_join_request_missing(client, telegram):
    """Abuse case 13/15: no request (or a cancelled one) means no progress."""
    setup = await telegram_setup(telegram)
    body = await signup(client)
    token = await open_session(client, body)
    tg = new_telegram_id()
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    await post_update(client, setup.watcher, join_request(tg, setup.channels[0]))
    await post_update(client, setup.verifier, callback(tg))
    assert "Channel 2" in setup.verifier.fake.sent_texts(tg)[-1]
    assert (await status(client, body))["issue"] == "CHANNELS_MISSING"


async def test_already_joined_member_counts(client, telegram):
    """Abuse case 14: someone already in the channel has nothing to request."""
    setup = await telegram_setup(telegram, channels=1)
    phone = new_phone()
    body = await signup(client, phone)
    token = await open_session(client, body)
    tg = new_telegram_id()
    telegram.members[(setup.channels[0], tg)] = "member"
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    await post_update(client, setup.verifier, callback(tg))
    await post_update(client, setup.verifier, message(tg, contact=own_contact(tg, phone)))
    assert (await status(client, body))["status"] == "COMPLETED"


async def test_pending_requests_can_be_required_to_be_approved(client, telegram):
    setup = await telegram_setup(telegram, channels=1)
    async with db.sessionmaker()() as s, s.begin():
        from app.models import AppSettings

        settings = await s.get(AppSettings, 1)
        settings.accept_pending_join_requests = False
    body = await signup(client)
    token = await open_session(client, body)
    tg = new_telegram_id()
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    await post_update(client, setup.watcher, join_request(tg, setup.channels[0]))
    await post_update(client, setup.verifier, callback(tg))
    assert (await status(client, body))["issue"] == "CHANNELS_MISSING"
    telegram.members[(setup.channels[0], tg)] = "member"  # admin approved it
    await post_update(client, setup.verifier, callback(tg))
    assert (await status(client, body))["issue"] is None


async def test_someone_elses_contact_is_rejected(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    phone = new_phone()
    body = await signup(client, phone)
    token = await open_session(client, body)
    tg = new_telegram_id()
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    # A forwarded contact card carries another user's id (or none).
    await post_update(client, setup.verifier, message(tg, contact={"phone_number": f"91{phone}", "first_name": "X", "user_id": tg + 1}))
    await post_update(client, setup.verifier, message(tg, contact={"phone_number": f"91{phone}", "first_name": "X"}))
    assert (await status(client, body))["status"] == "IN_PROGRESS"
    assert "your own number" in setup.verifier.fake.sent_texts(tg)[-1]


async def test_phone_mismatch_then_limit(client, telegram):
    """Abuse case 12: mismatches get a safe retry, then the link closes."""
    setup = await telegram_setup(telegram, channels=0)
    phone = new_phone()
    body = await signup(client, phone)
    token = await open_session(client, body)
    tg = new_telegram_id()
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    other = new_phone()
    await post_update(client, setup.verifier, message(tg, contact=own_contact(tg, other)))
    assert (await status(client, body))["issue"] == "PHONE_MISMATCH"
    assert "Attempts left: 2" in setup.verifier.fake.sent_texts(tg)[-1]
    await post_update(client, setup.verifier, message(tg, contact=own_contact(tg, other)))
    await post_update(client, setup.verifier, message(tg, contact=own_contact(tg, other)))
    s = await status(client, body)
    assert s["status"] == "FAILED" and s["issue"] == "PHONE_MISMATCH_LIMIT"
    # Not trapped: a new link can be requested.
    fresh = (await client.post("/v1/telegram/verification-session", headers=auth(body["tokens"]))).json()
    assert fresh["status"] == "OPEN"
    assert fresh["deep_link"].split("start=")[1] != token


async def test_telegram_account_linked_to_another_user(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    first = await helpers.verified_user(client, setup)
    tg = (await _telegram_id_of(first["user"]["public_id"]))
    phone = new_phone()
    second = await signup(client, phone)
    token = await open_session(client, second)
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    await post_update(client, setup.verifier, message(tg, contact=own_contact(tg, phone)))
    s = await status(client, second)
    assert s["status"] == "IN_PROGRESS" and s["issue"] == "TELEGRAM_ALREADY_LINKED"


async def _telegram_id_of(public_id: str) -> int:
    async with db.sessionmaker()() as s, s.begin():
        return (await s.execute(select(User.telegram_user_id).where(User.public_id == public_id))).scalar_one()


async def test_switching_telegram_account(client, telegram):
    """Abuse case 16: the link rebinds to the new account, which must match."""
    setup = await telegram_setup(telegram, channels=0)
    phone = new_phone()
    body = await signup(client, phone)
    token = await open_session(client, body)
    first_tg, second_tg = new_telegram_id(), new_telegram_id()
    await post_update(client, setup.verifier, message(first_tg, f"/start {token}"))
    await post_update(client, setup.verifier, message(second_tg, f"/start {token}"))
    await post_update(client, setup.verifier, message(first_tg, contact=own_contact(first_tg, phone)))
    assert (await status(client, body))["status"] == "IN_PROGRESS"
    await post_update(client, setup.verifier, message(second_tg, contact=own_contact(second_tg, phone)))
    assert (await status(client, body))["status"] == "COMPLETED"
    assert await _telegram_id_of(body["user"]["public_id"]) == second_tg


async def test_duplicate_verification_callback_counts_once(client, telegram):
    """Abuse cases 6 and 23: repeated contact updates never double-count."""
    setup = await telegram_setup(telegram, channels=0)
    await helpers.fund_pool()
    referrer = await helpers.verified_user(client, setup)
    phone = new_phone()
    body = await signup(client, phone, referrer["user"]["public_id"])
    token = await open_session(client, body)
    tg = new_telegram_id()
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    for _ in range(3):
        await post_update(client, setup.verifier, message(tg, contact=own_contact(tg, phone)))
    assert await verified_count() == 2
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(select(func.count()).select_from(ReferralReward))).scalar_one() == 1


async def test_expired_link(client, telegram):
    """Abuse cases 11 and 27: an old link is refused; the app can get a new one."""
    setup = await telegram_setup(telegram, channels=0)
    body = await signup(client)
    token = await open_session(client, body)
    helpers.advance(timedelta(minutes=31))
    tg = new_telegram_id()
    await post_update(client, setup.verifier, message(tg, f"/start {token}"))
    assert "isn't valid anymore" in setup.verifier.fake.sent_texts(tg)[-1]
    await helpers.refresh(client, body)
    assert (await status(client, body))["status"] == "EXPIRED"
    assert (await client.post("/v1/telegram/verification-session", headers=auth(body["tokens"]))).json()["status"] == "OPEN"


async def test_reopening_returns_same_session(client, telegram):
    await telegram_setup(telegram, channels=0)
    body = await signup(client)
    first = await open_session(client, body)
    assert await open_session(client, body) == first


async def test_webhook_rejects_wrong_secret(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    r = await post_update(client, setup.verifier, message(1, "/start x"), secret="not-the-secret")
    assert r.status_code == 401
    r = await client.post("/telegram/webhook/unknown-bot", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "x"})
    assert r.status_code == 401
    assert not setup.verifier.fake.sent_texts()


async def test_verified_user_gets_generic_replies(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    user = await helpers.verified_user(client, setup)
    tg = await _telegram_id_of(user["user"]["public_id"])
    await post_update(client, setup.verifier, message(tg, "hello"))
    assert "already verified" in setup.verifier.fake.sent_texts(tg)[-1]


async def test_message_flood_is_ignored(client, telegram):
    setup = await telegram_setup(telegram, channels=0)
    tg = new_telegram_id()
    for _ in range(25):
        await post_update(client, setup.verifier, message(tg, "spam"))
    assert len(setup.verifier.fake.sent_texts(tg)) == 20


async def test_no_healthy_bot(client, telegram):
    """Abuse case 38: every bot down gives a clear, retryable error."""
    body = await signup(client)
    r = await client.post("/v1/telegram/verification-session", headers=auth(body["tokens"]))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "VERIFICATION_UNAVAILABLE"


async def test_rate_limited_bot_is_skipped(client, telegram):
    """Abuse case 37: a bot Telegram throttles is taken out of rotation until it recovers."""
    setup = await telegram_setup(telegram, channels=0)
    await helpers.register_bot(telegram, "verify2")
    setup.verifier.fake.fail_with = TelegramError("Too Many Requests", code=429, retry_after=60)
    async with db.sessionmaker()() as s, s.begin():
        bot = await s.get(TelegramBot, setup.verifier.db_id)
        with pytest.raises(TelegramError):
            await bots.call(bot, "sendMessage", chat_id=1, text="x")
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.get(TelegramBot, setup.verifier.db_id)).health == "RATE_LIMITED"
    for _ in range(5):
        user = await signup(client)
        r = await client.post("/v1/telegram/verification-session", headers=auth(user["tokens"]))
        assert r.json()["bot_username"] == "verify2_bot"
    helpers.advance(timedelta(seconds=61))
    picked = set()
    for _ in range(20):
        user = await signup(client)
        picked.add((await client.post("/v1/telegram/verification-session", headers=auth(user["tokens"]))).json()["bot_username"])
    assert picked == {"verify1_bot", "verify2_bot"}
