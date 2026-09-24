"""Argon2id password hashing, run off the event loop."""

from __future__ import annotations

from functools import lru_cache

import anyio
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings


@lru_cache
def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(time_cost=s.argon2_time_cost, memory_cost=s.argon2_memory_kib, parallelism=s.argon2_parallelism)


@lru_cache
def _dummy_hash() -> str:
    # Checked against when the phone number is unknown, so a wrong number
    # takes as long as a wrong password.
    return _hasher().hash("not-a-real-password-used-for-timing")


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hasher().hash, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    target = password_hash or _dummy_hash()

    def check() -> bool:
        try:
            return _hasher().verify(target, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    ok = await anyio.to_thread.run_sync(check)
    return ok and password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    return _hasher().check_needs_rehash(password_hash)
