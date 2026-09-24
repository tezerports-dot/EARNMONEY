"""Shared steps for tests: sign up, run the Telegram flow, move the clock."""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from httpx import AsyncClient

from app import db, timeutil
from app.models import RequiredChannel
from app.redis_client import redis
from app.services import bots
from tests.fakes import FakeBot, FakeTelegram

_update_ids = itertools.count(1000)
_phones = itertools.count(9000000001)
_telegram_ids = itertools.count(5_000_001)


def new_phone() -> str:
    return str(next(_phones))


def new_telegram_id() -> int:
    return next(_telegram_ids)


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def idem() -> dict:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def reset_ip_limits() -> None:
    """Every test request comes from one address; bulk-signup tests would
    otherwise trip the per-IP limits, which have their own tests."""
    keys = [k async for k in redis().scan_iter("rl:*_ip:*")]
    if keys:
        await redis().delete(*keys)


async def captcha(client: AsyncClient) -> tuple[str, str]:
    body = (await client.get("/v1/captcha")).json()
    answer = await redis().get(f"captcha:{body['captcha_id']}")
    return body["captcha_id"], answer


async def signup_response(
    client: AsyncClient,
    phone: str | None = None,
    code: str | None = None,
    password: str = "correct-horse-9",
    headers: dict | None = None,
):
    await reset_ip_limits()
    captcha_id, answer = await captcha(client)
    return await client.post(
        "/v1/auth/signup",
        json={
            "phone": phone or new_phone(),
            "password": password,
            "referral_code": code,
            "captcha_id": captcha_id,
            "captcha_answer": answer,
        },
        headers=headers or idem(),
    )


async def signup(client: AsyncClient, phone: str | None = None, code: str | None = None) -> dict:
    response = await signup_response(client, phone, code)
    assert response.status_code == 201, response.text
    return response.json()


def advance(delta: timedelta) -> datetime:
    at = timeutil.now() + delta
    timeutil.freeze(at)
    return at


@dataclass
class Bot:
    fake: FakeBot
    ref: str
    secret: str
    db_id: int


async def register_bot(telegram: FakeTelegram, name: str, role: str = "VERIFIER") -> Bot:
    token = f"{name}:TESTTOKEN"
    async with db.sessionmaker()() as session, session.begin():
        bot = await bots.register(session, token, role)
        ref, bot_id = bot.ref, bot.id
    fake = telegram.bots[token]
    assert fake.webhook_secret
    return Bot(fake=fake, ref=ref, secret=fake.webhook_secret, db_id=bot_id)


async def add_channel(chat_id: int, title: str) -> None:
    async with db.sessionmaker()() as session, session.begin():
        session.add(RequiredChannel(title=title, chat_id=chat_id, invite_link=f"https://t.me/+join{abs(chat_id)}"))


@dataclass
class TelegramSetup:
    verifier: Bot
    watcher: Bot
    channels: list[int]


async def telegram_setup(telegram: FakeTelegram, channels: int = 2) -> TelegramSetup:
    verifier = await register_bot(telegram, "verify1")
    watcher = await register_bot(telegram, "watcher", "WATCHER")
    chat_ids = [-1001000000000 - i for i in range(channels)]
    for i, chat_id in enumerate(chat_ids, 1):
        await add_channel(chat_id, f"Channel {i}")
    return TelegramSetup(verifier, watcher, chat_ids)


async def post_update(client: AsyncClient, bot: Bot, update: dict, secret: str | None = None):
    update = {"update_id": next(_update_ids), **update}
    return await client.post(
        f"/telegram/webhook/{bot.ref}",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret if secret is not None else bot.secret},
    )


def message(tg_id: int, text: str | None = None, contact: dict | None = None) -> dict:
    body: dict = {"message_id": 1, "from": {"id": tg_id, "is_bot": False, "first_name": "T"}, "chat": {"id": tg_id, "type": "private"}, "date": 0}
    if text is not None:
        body["text"] = text
    if contact is not None:
        body["contact"] = contact
    return {"message": body}


def callback(tg_id: int, data: str = "vs:check") -> dict:
    return {"callback_query": {"id": "cb1", "from": {"id": tg_id, "is_bot": False, "first_name": "T"}, "data": data}}


def join_request(tg_id: int, chat_id: int) -> dict:
    return {"chat_join_request": {"chat": {"id": chat_id, "type": "channel"}, "from": {"id": tg_id, "is_bot": False, "first_name": "T"}, "date": 1790000000}}


def own_contact(tg_id: int, phone: str) -> dict:
    return {"phone_number": f"91{phone}", "first_name": "T", "user_id": tg_id}


async def verify(
    client: AsyncClient, setup: TelegramSetup, signed_up: dict, phone: str, tg_id: int | None = None
) -> int:
    """Run the whole Telegram flow for a signed-up user; returns their Telegram id."""
    tg_id = tg_id or new_telegram_id()
    session = await client.post("/v1/telegram/verification-session", headers=auth(signed_up["tokens"]))
    assert session.status_code == 200, session.text
    token = session.json()["deep_link"].split("start=")[1]
    await post_update(client, setup.verifier, message(tg_id, f"/start {token}"))
    for chat_id in setup.channels:
        await post_update(client, setup.watcher, join_request(tg_id, chat_id))
    await post_update(client, setup.verifier, callback(tg_id))
    await post_update(client, setup.verifier, message(tg_id, contact=own_contact(tg_id, phone)))
    return tg_id


async def verified_user(client: AsyncClient, setup: TelegramSetup, code: str | None = None) -> dict:
    """Sign up and verify; returns the signup body plus ``phone``."""
    phone = new_phone()
    body = await signup(client, phone, code)
    await verify(client, setup, body, phone)
    me = (await client.get("/v1/me", headers=auth(body["tokens"]))).json()
    assert me["status"] == "ACTIVE", me
    return {**body, "phone": phone, "user": me}


async def fund_pool(rupees: int = 1_00_000) -> None:
    """Record promotional funding, as an admin would. Rewards need it."""
    from app.services import ledger

    async with db.sessionmaker()() as session, session.begin():
        await ledger.transfer(
            session,
            kind="FUNDING",
            idempotency_key=f"funding:test:{uuid.uuid4()}",
            source=await ledger.system_account(session, "COMPANY_FUNDING"),
            destination=await ledger.system_account(session, "PROMO_POOL"),
            amount_paise=rupees * 100,
            created_by="test",
        )


async def refresh(client: AsyncClient, body: dict) -> dict:
    """Swap in fresh tokens, as the app does after its access token expires."""
    r = await client.post("/v1/auth/refresh", json={"refresh_token": body["tokens"]["refresh_token"]})
    assert r.status_code == 200, r.text
    body["tokens"] = r.json()["tokens"]
    return body
