"""Opaque random tokens. Only their SHA-256 hashes are stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def same(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)
