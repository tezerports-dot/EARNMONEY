"""Field encryption (AES-256-GCM) and keyed fingerprints (HMAC-SHA256).

Each ciphertext is bound to a purpose string (for example ``bank:42``) so a
value copied into another row or column fails to decrypt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_VERSION = b"\x01"


def encrypt(plaintext: str, purpose: str) -> bytes:
    nonce = os.urandom(12)
    sealed = AESGCM(get_settings().encryption_key_bytes).encrypt(nonce, plaintext.encode(), purpose.encode())
    return _VERSION + nonce + sealed


def decrypt(blob: bytes, purpose: str) -> str:
    if not blob or blob[:1] != _VERSION:
        raise ValueError("unknown ciphertext version")
    nonce, sealed = blob[1:13], blob[13:]
    return AESGCM(get_settings().encryption_key_bytes).decrypt(nonce, sealed, purpose.encode()).decode()


def fingerprint(value: str, purpose: str) -> bytes:
    return hmac.new(get_settings().hmac_key_bytes, f"{purpose}:{value}".encode(), hashlib.sha256).digest()


def derived_token(purpose: str, length: int = 32) -> str:
    """A stable secret token derived from ``purpose`` (for example ``vs:42``)."""
    raw = hmac.new(get_settings().hmac_key_bytes, purpose.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")[:length]
