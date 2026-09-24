"""Fixed-window rate limits in Redis.

Keys look like ``rl:<scope>:<subject>``. The subject is a user id, phone,
Telegram id or client IP, never anything that must stay secret.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import errors
from app.redis_client import redis

# INCR the counter and start its window on first use, atomically.
_HIT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


@dataclass(frozen=True)
class Limit:
    scope: str
    limit: int
    window_seconds: int


# Defaults from docs/API.md. Mobile carriers put many users behind one IP,
# so IP limits are generous and phone/user limits do the precise work.
CONFIG = Limit("config_ip", 120, 60)
CAPTCHA = Limit("captcha_ip", 20, 60)
REFERRAL_CHECK = Limit("refcheck_ip", 30, 60)
SIGNUP_PHONE = Limit("signup_phone", 3, 3600)
SIGNUP_IP = Limit("signup_ip", 30, 3600)
LOGIN_IP = Limit("login_ip", 60, 60)
REFRESH = Limit("refresh_family", 30, 60)
VERIFICATION_SESSIONS = Limit("vsession_user", 10, 86400)
USER_READS = Limit("reads_user", 120, 60)
BANK_UPDATES = Limit("bank_user", 5, 86400)
WITHDRAWALS = Limit("withdraw_user", 5, 3600)
TELEGRAM_MESSAGES = Limit("tg_user", 20, 60)
ADMIN_LOGIN_IP = Limit("admin_login_ip", 10, 900)

# Login failures per phone: CAPTCHA from the 3rd, locked from the 10th.
LOGIN_FAILURES_WINDOW = 3600
LOGIN_CAPTCHA_AFTER = 3
LOGIN_LOCK_AFTER = 10


async def hit(limit: Limit, subject: str | int) -> None:
    """Count one attempt; raise ``RateLimited`` once the window is full."""
    count, ttl = await redis().eval(_HIT, 1, f"rl:{limit.scope}:{subject}", limit.window_seconds)
    if int(count) > limit.limit:
        raise errors.RateLimited(retry_after=max(int(ttl), 1))


async def login_failures(phone: str) -> tuple[int, int]:
    key = f"rl:login_fail:{phone}"
    pipe = redis().pipeline()
    pipe.get(key)
    pipe.ttl(key)
    value, ttl = await pipe.execute()
    return int(value or 0), max(int(ttl), 1)


async def record_login_failure(phone: str) -> None:
    await redis().eval(_HIT, 1, f"rl:login_fail:{phone}", LOGIN_FAILURES_WINDOW)


async def clear_login_failures(phone: str) -> None:
    await redis().delete(f"rl:login_fail:{phone}")
