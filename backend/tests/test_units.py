"""Pure helpers: phone numbers, INR formatting, codes, encryption, ledger guards."""

from __future__ import annotations

import pytest
from cryptography.exceptions import InvalidTag

from app import ids
from app.money import format_inr, rupees_to_paise
from app.phone import mask_phone, normalize_indian_mobile
from app.security import crypto
from app.services import ledger


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("9876543210", "9876543210"),
        ("+91 98765 43210", "9876543210"),
        ("919876543210", "9876543210"),
        ("09876543210", "9876543210"),
        ("+91-98765-43210", "9876543210"),
        ("5876543210", None),  # Indian mobiles start with 6–9
        ("+1 9876543210", None),
        ("98765", None),
        ("", None),
        (None, None),
        ("98765432100", None),
    ],
)
def test_normalize_indian_mobile(raw, expected):
    assert normalize_indian_mobile(raw) == expected


def test_mask_phone():
    assert mask_phone("9876543210") == "98XXXXXX10"


@pytest.mark.parametrize(
    "paise, text",
    [
        (0, "₹0"),
        (100, "₹1"),
        (20000, "₹200"),
        (1250000, "₹12,500"),
        (1234550, "₹12,345.50"),
        (11577956_00, "₹1,15,77,956"),
        (1_000_00_00_000_00, "₹10,00,00,00,000"),  # ₹1,000 crore
        (-20000, "-₹200"),
        (5, "₹0.05"),
    ],
)
def test_format_inr(paise, text):
    assert format_inr(paise) == text


def test_money_refuses_floats():
    with pytest.raises(TypeError):
        format_inr(200.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        rupees_to_paise(1.5)  # type: ignore[arg-type]
    assert rupees_to_paise(200) == 20000


def test_codes():
    code = ids.new_public_id()
    assert len(code) == 8 and all(c in ids.ALPHABET for c in code)
    assert ids.normalize_code(f" {code.lower()[:4]} {code.lower()[4:]} ") == code
    assert ids.normalize_code("O0I1L5UA") is None  # ambiguous characters aren't used
    assert ids.normalize_code("SHORT") is None


def test_encryption_is_bound_to_purpose():
    blob = crypto.encrypt("123456784821", "bank:1")
    assert crypto.decrypt(blob, "bank:1") == "123456784821"
    assert blob != crypto.encrypt("123456784821", "bank:1")  # random nonce
    with pytest.raises(InvalidTag):
        crypto.decrypt(blob, "bank:2")  # copied to another user's row: fails


def test_fingerprints_are_stable_and_keyed():
    assert crypto.fingerprint("123", "bank") == crypto.fingerprint("123", "bank")
    assert crypto.fingerprint("123", "bank") != crypto.fingerprint("124", "bank")


async def test_ledger_refuses_unbalanced_postings():
    with pytest.raises(ValueError):
        await ledger.post(
            None,  # type: ignore[arg-type]
            kind="ADJUSTMENT",
            idempotency_key="x",
            postings=[ledger.Posting(1, 100), ledger.Posting(2, -99)],
            created_by="test",
        )
    with pytest.raises(ValueError):
        await ledger.post(
            None,  # type: ignore[arg-type]
            kind="ADJUSTMENT",
            idempotency_key="x",
            postings=[ledger.Posting(1, 100.0), ledger.Posting(2, -100.0)],  # type: ignore[arg-type]
            created_by="test",
        )
