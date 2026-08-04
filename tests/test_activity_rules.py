"""The three-part activity rule and the money that depends on it."""

from __future__ import annotations

from app import db, earnings
from app.timeutil import current_month
from tests.conftest import join_both


def test_membership_alone_is_not_active(world, month):
    _, referred, _ = world
    join_both(int(referred["id"]))

    status = earnings.status_for(db.get_user(5002), month)
    assert status.in_group and status.in_channel
    assert status.has_interaction is False
    assert status.active is False
    assert "no interaction" in status.reason


def test_interaction_without_both_chats_is_not_active(world, month):
    _, referred, _ = world
    db.set_membership(5002, -100_1, True)  # group only
    db.record_activity(5002)

    status = earnings.status_for(db.get_user(5002), month)
    assert status.has_interaction
    assert status.active is False
    assert "not in channel" in status.reason


def test_one_interaction_plus_both_memberships_is_active(world, month):
    _, referred, _ = world
    join_both(5002)
    db.record_activity(5002)

    assert earnings.status_for(db.get_user(5002), month).active is True


def test_activity_is_per_person_per_month_not_per_click(world, month):
    """A thousand taps still pay ten rupees once."""
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    for index in range(1000):
        db.record_activity(5002)

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 1
    assert report.amount == earnings.rates().level1
    assert earnings.status_for(db.get_user(5002), month).has_interaction is True


def test_leaving_either_chat_drops_the_referral_immediately(world, month):
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    db.record_activity(5002)
    assert earnings.report_for(db.get_user(5001), month).amount == earnings.rates().level1

    db.set_membership(5002, -100_2, False)

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 0
    assert report.amount == 0
    # The interaction is still on record; only membership changed.
    assert earnings.status_for(db.get_user(5002), month).has_interaction is True


def test_rejoining_restores_the_referral_with_past_interactions(world, month):
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    db.record_activity(5002)
    db.set_membership(5002, -100_2, False)
    assert earnings.report_for(db.get_user(5001), month).amount == 0

    db.set_membership(5002, -100_2, True)

    assert earnings.report_for(db.get_user(5001), month).amount == earnings.rates().level1


def test_inactive_referrer_earns_nothing_even_with_active_referrals(world, month):
    referrer, _, _ = world
    join_both(5002)
    db.record_activity(5002)
    # The referrer never joined and never interacted.

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 1
    assert report.gross == earnings.rates().level1
    assert report.payable is False
    assert report.amount == 0


def test_unverified_referral_never_counts(world, month):
    referrer, _, _ = world
    db.set_flags(5002, verified=False)
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    db.record_activity(5002)

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 0
    assert "not verified" in report.rows[0].status.reason


def test_duplicate_and_banned_referrals_never_count(world, month):
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    db.record_activity(5002)

    db.set_flags(5002, duplicate=True)
    assert earnings.report_for(db.get_user(5001), month).active_referrals == 0

    db.set_flags(5002, duplicate=False, banned=True)
    assert earnings.report_for(db.get_user(5001), month).active_referrals == 0


def test_activity_belongs_to_the_ist_month_not_the_utc_one():
    """23:00 UTC on the 31st is already the 1st in India."""
    from app.timeutil import month_key

    assert month_key("2026-03-31T19:00:00Z") == "2026-04"  # 00:30 IST, 1 April
    assert month_key("2026-03-31T18:00:00Z") == "2026-03"  # 23:30 IST, 31 March


def test_next_month_needs_a_new_interaction(world):
    from app.timeutil import current_month, shift_month

    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    db.record_activity(5002)

    this_month = current_month()
    next_month = shift_month(this_month, 1)

    assert earnings.report_for(db.get_user(5001), this_month).amount == earnings.rates().level1
    # Memberships carry over, interactions do not.
    assert earnings.report_for(db.get_user(5001), next_month).amount == 0


def test_repeat_activity_writes_nothing_after_the_first(world):
    """The reason there is no activity log: taps after the first are free."""
    join_both(5002)
    assert db.record_activity(5002) is True     # first tap of the month writes
    for _ in range(50):
        assert db.record_activity(5002) is False  # the rest do not
    assert db.was_active_in(db.get_user(5002), current_month()) is True
