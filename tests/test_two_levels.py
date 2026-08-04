"""The two-level payout structure.

The scenario throughout is the one the rates were designed around::

    A ──▶ B ──▶ C, D, E

A earns level 1 on B and level 2 on C, D and E.
B earns level 1 on C, D and E.
Nobody earns three levels deep.
"""

from __future__ import annotations

import pytest

from app import db, earnings
from tests.conftest import join_both

L1_DEFAULT = 5.0
L2_DEFAULT = 5.0


def _member(user_id: int, username: str, referrer_uid: str | None, pair_id: int):
    """A verified, placed user who is active this month."""
    db.create_user(user_id, username, username.title(), referrer_uid)
    db.set_user_fields(
        user_id, verified=1, phone_hash=f"hash-{username}", pair_id=pair_id
    )
    join_both(user_id)
    db.record_activity(user_id, "callback", "tap")
    return db.get_user(user_id)


@pytest.fixture
def chain(world):
    """A → B → {C, D, E}, everyone verified, placed and active."""
    alice, bob, pair = world
    pair_id = int(pair["pair_id"])

    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "command", "/start")

    carol = _member(5003, "carol", str(bob["uid"]), pair_id)
    dave = _member(5004, "dave", str(bob["uid"]), pair_id)
    erin = _member(5005, "erin", str(bob["uid"]), pair_id)
    return db.get_user(5001), db.get_user(5002), (carol, dave, erin)


# --------------------------------------------------------------------------- #
# the structure
# --------------------------------------------------------------------------- #

def test_default_rates_are_five_and_five():
    current = earnings.rates()
    assert current.level1 == L1_DEFAULT
    assert current.level2 == L2_DEFAULT
    assert current.total == 10.0


def test_a_earns_level1_on_b_and_level2_on_bs_referrals(chain, month):
    alice, _, _ = chain
    report = earnings.report_for(alice, month)

    assert report.active_referrals == 1        # B
    assert report.active_indirect == 3         # C, D, E
    assert report.level1_amount == L1_DEFAULT
    assert report.level2_amount == 3 * L2_DEFAULT
    assert report.amount == L1_DEFAULT + 3 * L2_DEFAULT  # 5 + 15 = 20


def test_b_earns_level1_on_their_own_three_referrals(chain, month):
    _, bob, _ = chain
    report = earnings.report_for(bob, month)

    assert report.active_referrals == 3
    assert report.active_indirect == 0         # C, D and E have referred nobody
    assert report.amount == 3 * L1_DEFAULT     # 15


def test_the_simplest_chain_pays_the_top_both_levels(world, month):
    """A refers B, B refers C: A gets 5 for B and 5 for C."""
    alice, bob, pair = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "command", "/start")
    _member(5003, "carol", str(bob["uid"]), int(pair["pair_id"]))

    report = earnings.report_for(db.get_user(5001), month)
    assert report.amount == L1_DEFAULT + L2_DEFAULT  # 10
    assert earnings.report_for(db.get_user(5002), month).amount == L1_DEFAULT


def test_earnings_stop_at_two_levels(chain, month):
    """A great-grandchild pays their parent and grandparent, never A."""
    alice, _, (carol, _, _) = chain
    frank = _member(5006, "frank", str(carol["uid"]), int(alice["pair_id"]))

    a_report = earnings.report_for(db.get_user(5001), month)
    assert frank["uid"] not in [row.user["uid"] for row in a_report.rows]
    assert a_report.amount == L1_DEFAULT + 3 * L2_DEFAULT  # unchanged by Frank

    # Frank pays Carol at level 1 and Bob at level 2.
    assert earnings.report_for(db.get_user(5003), month).amount == L1_DEFAULT
    bob = earnings.report_for(db.get_user(5002), month)
    assert bob.active_indirect == 1
    assert bob.amount == 3 * L1_DEFAULT + L2_DEFAULT


def test_level2_rows_name_the_member_who_introduced_them(chain, month):
    alice, bob, _ = chain
    report = earnings.report_for(alice, month)
    assert {row.via_uid for row in report.level2_rows} == {bob["uid"]}
    assert all(row.via_uid is None for row in report.level1_rows)


# --------------------------------------------------------------------------- #
# activity still gates every level
# --------------------------------------------------------------------------- #

def test_an_inactive_level2_member_pays_nobody(chain, month):
    alice, bob, (carol, _, _) = chain
    db.set_membership(int(carol["id"]), -100_2, "channel", "left")

    a_report = earnings.report_for(db.get_user(5001), month)
    assert a_report.active_indirect == 2
    assert a_report.amount == L1_DEFAULT + 2 * L2_DEFAULT

    b_report = earnings.report_for(db.get_user(5002), month)
    assert b_report.active_referrals == 2
    assert b_report.amount == 2 * L1_DEFAULT


def test_an_inactive_middle_member_keeps_their_downline_in_as_level2(chain, month):
    """B going inactive costs B, not A's level-2 income.

    Each member is judged on their own activity, so C, D and E still count
    for A even though the person who introduced them stopped participating.
    """
    alice, bob, _ = chain
    db.set_membership(int(bob["id"]), -100_1, "group", "left")

    a_report = earnings.report_for(db.get_user(5001), month)
    assert a_report.active_referrals == 0      # B no longer counts at level 1
    assert a_report.active_indirect == 3       # C, D, E are unaffected
    assert a_report.amount == 3 * L2_DEFAULT

    b_report = earnings.report_for(db.get_user(5002), month)
    assert b_report.gross == 3 * L1_DEFAULT
    assert b_report.payable is False
    assert b_report.amount == 0


def test_an_inactive_earner_is_paid_nothing_at_either_level(chain, month):
    alice, _, _ = chain
    db.set_membership(5001, -100_1, "group", "left")

    report = earnings.report_for(db.get_user(5001), month)
    assert report.gross == L1_DEFAULT + 3 * L2_DEFAULT
    assert report.payable is False
    assert report.amount == 0
    assert "not in group" in report.blocked_reason


def test_unverified_and_banned_members_count_at_neither_level(chain, month):
    alice, _, (carol, dave, _) = chain
    db.set_user_fields(int(carol["id"]), verified=0)
    db.set_user_fields(int(dave["id"]), banned=1)

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_indirect == 1
    assert report.amount == L1_DEFAULT + L2_DEFAULT


def test_a_reciprocal_referral_never_makes_someone_their_own_downline(world, month):
    """A refers B; if A then also gets recorded as B's referral, A is not
    allowed to appear in A's own level 2."""
    alice, bob, _ = world
    db.set_user_fields(5001, referred_by_uid=str(bob["uid"]))

    level2 = db.level2_referrals_of(str(alice["uid"]))
    assert str(alice["uid"]) not in [row["uid"] for row in level2]

    report = earnings.report_for(db.get_user(5001), month)
    assert alice["uid"] not in [row.user["uid"] for row in report.rows]


# --------------------------------------------------------------------------- #
# rates are data, not constants
# --------------------------------------------------------------------------- #

def test_changing_the_rates_changes_the_payout_immediately(chain, month):
    alice, _, _ = chain
    assert earnings.report_for(db.get_user(5001), month).amount == 20.0

    db.set_setting("payout_level1", "12")
    db.set_setting("payout_level2", "3")

    report = earnings.report_for(db.get_user(5001), month)
    assert report.level1_amount == 12.0
    assert report.level2_amount == 9.0
    assert report.amount == 21.0


def test_a_zero_level2_rate_turns_the_scheme_back_into_one_level(chain, month):
    db.set_setting("payout_level2", "0")
    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_indirect == 3        # still tracked and displayed
    assert report.level2_amount == 0.0
    assert report.amount == L1_DEFAULT


def test_fractional_rates_survive_the_round_trip(chain, month):
    db.set_setting("payout_level1", "2.5")
    db.set_setting("payout_level2", "1.25")
    report = earnings.report_for(db.get_user(5001), month)
    assert report.amount == pytest.approx(2.5 + 3 * 1.25)


def test_a_corrupt_rate_setting_falls_back_instead_of_crashing(chain, month):
    db.set_setting("payout_level1", "not a number")
    assert earnings.rates().level1 == L1_DEFAULT
    assert earnings.report_for(db.get_user(5001), month).amount == 20.0


# --------------------------------------------------------------------------- #
# totals and withdrawals
# --------------------------------------------------------------------------- #

def test_month_totals_count_both_levels(chain, month):
    totals = earnings.month_totals(month)
    assert totals["active_referred"] == 4     # B (under A) + C, D, E (under B)
    assert totals["active_indirect"] == 3     # C, D, E (under A)
    # A: 5 + 15 = 20, B: 15. Nothing double-counted across earners.
    assert totals["total_inr"] == 35.0


def test_leaderboard_ranks_by_total_earnings(chain, month):
    board = earnings.leaderboard(month)
    uids = [user["uid"] for user, _ in board]
    assert uids[0] == db.get_user(5001)["uid"]   # A: ₹20
    assert uids[1] == db.get_user(5002)["uid"]   # B: ₹15


def test_a_withdrawal_is_created_for_the_full_two_level_amount(chain, month):
    alice, _, _ = chain
    report = earnings.report_for(alice, month)
    row = db.create_withdrawal(int(alice["id"]), month, report.amount)
    assert row["amount"] == 20.0
