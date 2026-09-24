"""Indian mobile numbers: one normal form for storage and comparison."""

from __future__ import annotations

import re

_MOBILE = re.compile(r"^[6-9][0-9]{9}$")
_SEPARATORS = re.compile(r"[\s\-().]")


def normalize_indian_mobile(raw: str | None) -> str | None:
    """Return the 10-digit number, or ``None`` if it isn't an Indian mobile.

    Accepts ``+91 98765 43210``, ``919876543210``, ``09876543210`` and
    ``9876543210``. Telegram sends contacts as ``919876543210`` or
    ``+919876543210``, so both signup and verification go through here.
    """
    if not raw:
        return None
    digits = _SEPARATORS.sub("", raw.strip())
    if digits.startswith("+"):
        if not digits.startswith("+91"):
            return None
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if _MOBILE.fullmatch(digits) else None


def mask_phone(phone: str) -> str:
    return f"{phone[:2]}XXXXXX{phone[-2:]}"
