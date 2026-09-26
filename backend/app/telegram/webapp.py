"""Validate the ``initData`` a Telegram Mini App sends us.

Telegram signs the launch parameters with the bot's token, so a valid signature
proves the caller really opened the Mini App from that bot inside Telegram and
tells us which Telegram user they are. The algorithm is Telegram's:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app import timeutil


@dataclass(frozen=True)
class WebAppInit:
    telegram_user_id: int
    start_param: str | None
    auth_date: int


class InitDataInvalid(Exception):
    """The initData is missing, malformed, unsigned or too old."""


def validate(init_data: str, bot_token: str, *, max_age_seconds: int) -> WebAppInit:
    if not init_data or len(init_data) > 4096:
        raise InitDataInvalid("empty or oversized initData")
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", "")
    if not received_hash or "user" not in fields or "auth_date" not in fields:
        raise InitDataInvalid("missing hash, user or auth_date")

    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataInvalid("bad signature")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        telegram_user_id = int(user["id"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise InitDataInvalid("unreadable fields") from exc

    age = int(timeutil.now().timestamp()) - auth_date
    if auth_date <= 0 or age > max_age_seconds or age < -300:
        raise InitDataInvalid("stale auth_date")

    start_param = fields.get("start_param") or None
    return WebAppInit(telegram_user_id=telegram_user_id, start_param=start_param, auth_date=auth_date)
