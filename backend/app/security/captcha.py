"""A small arithmetic check for signup and repeated login failures.

It only slows down scripts. Rate limits and Telegram phone verification are
the real protection. Each CAPTCHA works once, right or wrong, so answers
can't be replayed.
"""

from __future__ import annotations

import secrets

from app import errors
from app.redis_client import redis

TTL_SECONDS = 300


def _question() -> tuple[str, int]:
    a, b = secrets.randbelow(9) + 2, secrets.randbelow(9) + 2
    if secrets.randbelow(2):
        return f"{a} + {b} = ?", a + b
    high, low = max(a, b), min(a, b)
    return f"{high} − {low} = ?", high - low


async def create() -> dict:
    captcha_id = f"c_{secrets.token_urlsafe(16)}"
    question, answer = _question()
    await redis().set(f"captcha:{captcha_id}", str(answer), ex=TTL_SECONDS)
    return {"captcha_id": captcha_id, "question": question, "expires_in_seconds": TTL_SECONDS}


async def verify(captcha_id: str | None, answer: str | None) -> None:
    if not captcha_id or answer is None:
        raise errors.CaptchaRequired()
    # GETDEL: the stored answer is gone after this read, whatever the outcome.
    expected = await redis().getdel(f"captcha:{captcha_id[:64]}")
    given = answer.strip()
    if expected is None or not given.isdigit() or not secrets.compare_digest(given, expected):
        raise errors.CaptchaInvalid()
