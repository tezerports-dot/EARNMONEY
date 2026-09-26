"""Public identifiers. Database ids never leave the server."""

from __future__ import annotations

import secrets

# No 0/O, 1/I/L or U, so codes survive being read aloud or typed from a photo.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"

PUBLIC_ID_LENGTH = 8
REFERENCE_LENGTH = 10


def new_public_id() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(PUBLIC_ID_LENGTH))


def new_reference() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(REFERENCE_LENGTH))


def normalize_code(raw: str) -> str | None:
    """Referral codes are case-insensitive and may be pasted with spaces."""
    code = "".join(raw.split()).upper()
    if len(code) != PUBLIC_ID_LENGTH or any(ch not in ALPHABET for ch in code):
        return None
    return code
