"""Registration, placement, duplicate handling and payout requests."""

from __future__ import annotations

import asyncio

import pytest

from app import bank, db, ids
from app.bots.services import handle_duplicate
from app.timeutil import current_month, month_bounds, shift_month


# --------------------------------------------------------------------------- #
# identifiers
# --------------------------------------------------------------------------- #

def test_uid_shape_and_uniqueness():
    seen = {ids.random_uid() for _ in range(2000)}
    assert len(seen) > 1990  # collisions are possible but must be rare
    for uid in list(seen)[:20]:
        assert ids.UID_RE.match(uid)


def test_uid_allocation_retries_past_a_collision(monkeypatch, world):
    """36^6 is 2.18 billion, so collisions are ordinary at scale, not fatal."""
    taken = str(db.get_user(5001)["uid"])
    handed_out = [taken, taken, "UID-FRESH1"]

    monkeypatch.setattr(ids, "random_uid", lambda: handed_out.pop(0))
    monkeypatch.setattr("app.db.random_uid", lambda: handed_out.pop(0))

    created = db.create_user(9001)
    assert created["uid"] == "UID-FRESH1"
    assert handed_out == []  # both duplicates were tried and rejected


def test_uid_normalisation_accepts_every_spelling():
    assert ids.normalise_uid("UID-A1B2C3") == "UID-A1B2C3"
    assert ids.normalise_uid("uida1b2c3") == "UID-A1B2C3"
    assert ids.normalise_uid(" A1B2C3 ") == "UID-A1B2C3"
    assert ids.normalise_uid("nonsense!") is None
    assert ids.normalise_uid("") is None


def test_referral_payload_round_trip():
    uid = "UID-A1B2C3"
    payload = ids.referral_payload(uid)
    assert payload == "ref_UIDA1B2C3"
    assert ids.parse_referral_payload(payload) == uid
    assert ids.parse_referral_payload("ref_UID-A1B2C3") == uid
    assert ids.parse_referral_payload(None) is None


def test_phone_hash_ignores_formatting_but_separates_numbers():
    assert ids.hash_phone("+91 98765-43210") == ids.hash_phone("919876543210")
    assert ids.hash_phone("919876543210") != ids.hash_phone("919876543211")
    assert isinstance(ids.hash_phone("919876543210"), bytes)
    assert len(ids.hash_phone("919876543210")) == ids.PHONE_HASH_BYTES
    with pytest.raises(ValueError):
        ids.hash_phone("no digits here")


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #

def test_start_is_idempotent_and_never_rewrites_a_referrer(world):
    referrer, _, _ = world
    first = db.create_user(7001, referred_by=str(referrer["uid"]))
    again = db.create_user(7001, referred_by="UID-ZZZZZZ")

    assert first["uid"] == again["uid"]
    assert again["referred_by"] == referrer["uid"]
    assert db.count_users("id = 7001") == 1


def test_a_late_referrer_can_still_be_recorded(world):
    referrer, _, _ = world
    db.create_user(7002)
    db.create_user(7002, referred_by=str(referrer["uid"]))
    assert db.get_user(7002)["referred_by"] == referrer["uid"]


def test_one_phone_hash_cannot_belong_to_two_accounts(world):
    import sqlite3

    db.create_user(7003)
    with pytest.raises(sqlite3.IntegrityError):
        db.set_user_fields(7003, phone_hash=b"hash-alice-0000")  # already Alice's


def test_duplicate_is_flagged_banned_and_detached_from_its_referrer(world):
    referrer, _, _ = world
    duplicate = db.create_user(7004, referred_by=str(referrer["uid"]))
    assert len(db.referrals_of(str(referrer["uid"]))) == 2

    asyncio.run(handle_duplicate(duplicate, referrer))

    row = db.get_user(7004)
    assert db.has_flag(row, db.F_DUPLICATE)
    assert db.has_flag(row, db.F_BANNED)
    assert not db.has_flag(row, db.F_VERIFIED)
    assert row["referred_by"] is None
    assert row["pair_id"] is None
    # It has vanished from the referrer's list entirely.
    assert [r["id"] for r in db.referrals_of(str(referrer["uid"]))] == [5002]


# --------------------------------------------------------------------------- #
# placement
# --------------------------------------------------------------------------- #

def test_placement_prefers_the_referrers_pair(world):
    _, _, pair = world
    db.add_chat(chat_id=-200_1, bot_id=1, chat_type="group", title="Group B")
    db.add_chat(chat_id=-200_2, bot_id=1, chat_type="channel", title="Channel B")
    other = db.create_pair("Set B", -200_1, -200_2)
    db.set_default_pair(other)  # default points elsewhere on purpose

    chosen = db.choose_pair(referrer_pair_id=int(pair["pair_id"]))
    assert int(chosen["pair_id"]) == int(pair["pair_id"])


def test_placement_falls_back_to_the_default_pair(world):
    _, _, pair = world
    chosen = db.choose_pair(referrer_pair_id=None)
    assert int(chosen["pair_id"]) == int(pair["pair_id"])


def test_a_full_pair_is_skipped_for_the_least_loaded_one(world):
    _, _, pair = world
    db.update_pair(int(pair["pair_id"]), capacity=2)  # alice + bob fill it
    pair = db.get_pair(int(pair["pair_id"]))

    db.add_chat(chat_id=-200_1, bot_id=1, chat_type="group", title="Group B")
    db.add_chat(chat_id=-200_2, bot_id=1, chat_type="channel", title="Channel B")
    spare = db.create_pair("Set B", -200_1, -200_2)

    chosen = db.choose_pair(referrer_pair_id=int(pair["pair_id"]))
    assert int(chosen["pair_id"]) == spare


def test_a_closed_pair_is_never_chosen(world):
    _, _, pair = world
    db.update_pair(int(pair["pair_id"]), closed=1)
    assert db.choose_pair(referrer_pair_id=int(pair["pair_id"])) is None


def test_an_incomplete_pair_is_never_chosen():
    db.add_chat(chat_id=-300_1, bot_id=1, chat_type="group", title="Lonely group")
    db.create_pair("Half a set", -300_1, None)
    assert db.choose_pair(referrer_pair_id=None) is None


# --------------------------------------------------------------------------- #
# bank details
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value,ok",
    [("HDFC0001234", True), ("SBIN0000123", True), ("HDFC1001234", False),
     ("HDF0001234", False), ("hdfc0001234", True), ("HDFC0001234X", False)],
)
def test_ifsc_validation(value, ok):
    cleaned, error = bank.clean_ifsc(value)
    assert (cleaned is not None) is ok
    assert ok or error


@pytest.mark.parametrize(
    "value,ok",
    [("123456789", True), ("123456789012345678", True), ("12345678", False),
     ("1234567890123456789", False), ("12345678a", False), ("1234 5678 9012", True)],
)
def test_account_number_validation(value, ok):
    cleaned, _ = bank.clean_account_number(value)
    assert (cleaned is not None) is ok


@pytest.mark.parametrize(
    "value,ok",
    [("rahul@okhdfcbank", True), ("a.b-c_1@paytm", True), ("noatsign", False),
     ("@okaxis", False), ("x@1bank", False)],
)
def test_upi_validation(value, ok):
    cleaned, _ = bank.clean_upi(value)
    assert (cleaned is not None) is ok


def test_bank_details_can_only_be_submitted_once(world):
    assert db.save_bank_details(5001, "Alice", "123456789012", "HDFC0001234", "a@okhdfc")
    assert not db.save_bank_details(5001, "Someone Else", "999999999999", "SBIN0000123", "b@ok")

    stored = db.get_bank_details(5001)
    assert stored["full_name"] == "Alice"
    assert stored["account_number"] == "123456789012"


def test_account_numbers_are_masked_for_display():
    assert bank.mask_account("123456789012") == "********9012"
    assert bank.mask_account("1234") == "1234"


# --------------------------------------------------------------------------- #
# withdrawals
# --------------------------------------------------------------------------- #

def test_one_withdrawal_per_user_per_month(world):
    month = current_month()
    assert db.create_withdrawal(5001, month, 10.0) is not None
    assert db.create_withdrawal(5001, month, 50.0) is None
    # A different month is a different request.
    assert db.create_withdrawal(5001, shift_month(month, -1), 20.0) is not None


def test_withdrawal_status_transitions_are_recorded(world):
    month = current_month()
    row = db.create_withdrawal(5001, month, 10.0)
    db.set_withdrawal_status(int(row["id"]), "approved")
    assert db.get_withdrawal(5001, month)["status"] == "approved"

    db.set_withdrawal_status(int(row["id"]), "paid", note="NEFT ref 123")
    stored = db.get_withdrawal(5001, month)
    assert stored["status"] == "paid"
    assert stored["processed_at"]
    assert stored["note"] == "NEFT ref 123"


# --------------------------------------------------------------------------- #
# month boundaries
# --------------------------------------------------------------------------- #

def test_month_bounds_are_ist_midnight_to_ist_midnight():
    start, end = month_bounds("2026-02")
    assert start.isoformat() == "2026-02-01T00:00:00+05:30"
    assert end.isoformat() == "2026-03-01T00:00:00+05:30"
    # Which is 18:30 UTC on the last day of the previous month.
    assert start.utctimetuple().tm_hour == 18


def test_month_arithmetic_wraps_the_year():
    assert shift_month("2026-12", 1) == "2027-01"
    assert shift_month("2026-01", -1) == "2025-12"
    assert shift_month("2026-06", 12) == "2027-06"
