"""Public user identifiers and phone hashing."""

from __future__ import annotations

import hashlib
import re
import secrets

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
UID_LENGTH = 6
UID_RE = re.compile(r"^UID-[0-9A-Z]{%d}$" % UID_LENGTH)


def random_uid() -> str:
    """A random ``UID-XXXXXX`` where X is base36 (uppercase)."""
    body = "".join(secrets.choice(ALPHABET) for _ in range(UID_LENGTH))
    return f"UID-{body}"


def normalise_uid(raw: str | None) -> str | None:
    """Accept ``uid-abc123``/``UIDABC123``/``UID-ABC123`` and canonicalise it.

    Telegram deep-link payloads are easier to read without the dash, so both
    spellings must resolve to the same stored UID.
    """
    if not raw:
        return None
    text = raw.strip().upper().replace(" ", "")
    if text.startswith("UID-"):
        candidate = text
    elif text.startswith("UID"):
        candidate = f"UID-{text[3:]}"
    else:
        candidate = f"UID-{text}"
    return candidate if UID_RE.match(candidate) else None


def hash_phone(phone: str) -> str:
    """SHA-256 of the digits of a phone number. Raw numbers are never stored."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        raise ValueError("empty phone number")
    return hashlib.sha256(digits.encode("utf-8")).hexdigest()


def referral_payload(uid: str) -> str:
    """Deep-link payload for a referral link (no dash: shorter and safer)."""
    return "ref_" + uid.replace("-", "")


def parse_referral_payload(payload: str | None) -> str | None:
    """Extract a canonical UID out of a ``/start`` payload."""
    if not payload:
        return None
    text = payload.strip()
    for prefix in ("ref_", "ref-", "ref"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return normalise_uid(text)
