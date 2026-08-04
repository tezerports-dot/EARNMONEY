"""Validation for the one-time bank details submission."""

from __future__ import annotations

import re

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCOUNT_RE = re.compile(r"^\d{9,18}$")
UPI_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,64}@[a-zA-Z][a-zA-Z0-9]{1,32}$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{2,69}$")


def clean_name(raw: str) -> tuple[str | None, str]:
    value = " ".join((raw or "").split())
    if not NAME_RE.match(value):
        return None, (
            "Name must be 3-70 characters, letters only (spaces, dots, hyphens "
            "and apostrophes are allowed). It must match the name on the bank "
            "account exactly."
        )
    return value, ""


def clean_account_number(raw: str) -> tuple[str | None, str]:
    value = re.sub(r"[\s-]", "", raw or "")
    if not ACCOUNT_RE.match(value):
        return None, "Account number must be 9 to 18 digits, no letters or symbols."
    return value, ""


def clean_ifsc(raw: str) -> tuple[str | None, str]:
    value = re.sub(r"\s", "", (raw or "")).upper()
    if not IFSC_RE.match(value):
        return None, (
            "IFSC must be 11 characters: 4 letters, then 0, then 6 letters or "
            "digits. Example: HDFC0001234."
        )
    return value, ""


def clean_upi(raw: str) -> tuple[str | None, str]:
    value = re.sub(r"\s", "", (raw or ""))
    if not UPI_RE.match(value):
        return None, "UPI id must look like name@bank, for example rahul@okhdfcbank."
    return value, ""


def mask_account(number: str) -> str:
    text = (number or "").strip()
    return text if len(text) <= 4 else "*" * (len(text) - 4) + text[-4:]
