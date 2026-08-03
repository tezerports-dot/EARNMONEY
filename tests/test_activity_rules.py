"""The three-part activity rule and the money that depends on it."""

from __future__ import annotations

from app import db, earnings
from tests.conftest import join_both


def test_membership_alone_is_not_active(world, month):
    _, referred, _ = world
    join_both(int(referred["id"]))

    status = earnings.status_for(db.get_user(5002), month)
    assert status.in_group and status.in_channel
    assert status.interactions == 0
    assert status.active is False
    assert "no interaction" in status.reason


def test_interaction_without_both_chats_is_not_active(world, month):
    _, referred, _ = world
    db.set_membership(5002, -100_1, "group", "member")  # group only
    db.record_activity(5002, "callback", "menu:earnings")

    status = earnings.status_for(db.get_user(5002), month)
    assert status.has_interaction
    assert status.active is False
    assert "not in channel" in status.reason


def test_one_interaction_plus_both_memberships_is_active(world, month):
    _, referred, _ = world
    join_both(5002)
    db.record_activity(5002, "callback", "menu:earnings")

    assert earnings.status_for(db.get_user(5002), month).active is True


def test_activity_is_per_person_per_month_not_per_click(world, month):
    """A thousand taps still pay ten rupees once."""
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    for index in range(1000):
        db.record_activity(5002, "callback", f"tap-{index}")

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 1
    assert report.amount == earnings.RATE
    assert earnings.status_for(db.get_user(5002), month).interactions == 1000


def test_leaving_either_chat_drops_the_referral_immediately(world, month):
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "callback", "tap")
    assert earnings.report_for(db.get_user(5001), month).amount == earnings.RATE

    db.set_membership(5002, -100_2, "channel", "left")

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 0
    assert report.amount == 0
    # The interaction is still on record; only membership changed.
    assert earnings.status_for(db.get_user(5002), month).interactions == 1


def test_rejoining_restores_the_referral_with_past_interactions(world, month):
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "callback", "tap")
    db.set_membership(5002, -100_2, "channel", "left")
    assert earnings.report_for(db.get_user(5001), month).amount == 0

    db.set_membership(5002, -100_2, "channel", "member")

    assert earnings.report_for(db.get_user(5001), month).amount == earnings.RATE


def test_inactive_referrer_earns_nothing_even_with_active_referrals(world, month):
    referrer, _, _ = world
    join_both(5002)
    db.record_activity(5002, "callback", "tap")
    # The referrer never joined and never interacted.

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 1
    assert report.gross == earnings.RATE
    assert report.payable is False
    assert report.amount == 0


def test_unverified_referral_never_counts(world, month):
    referrer, _, _ = world
    db.set_user_fields(5002, verified=0)
    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "callback", "tap")

    report = earnings.report_for(db.get_user(5001), month)
    assert report.active_referrals == 0
    assert "not verified" in report.rows[0].status.reason


def test_duplicate_and_banned_referrals_never_count(world, month):
    referrer, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "callback", "tap")

    db.set_user_fields(5002, duplicate=1)
    assert earnings.report_for(db.get_user(5001), month).active_referrals == 0

    db.set_user_fields(5002, duplicate=0, banned=1)
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
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "callback", "tap")

    this_month = current_month()
    next_month = shift_month(this_month, 1)

    assert earnings.report_for(db.get_user(5001), this_month).amount == earnings.RATE
    # Memberships carry over, interactions do not.
    assert earnings.report_for(db.get_user(5001), next_month).amount == 0


def test_daily_dedupe_keeps_one_group_message_row_per_day(world):
    join_both(5002)
    for _ in range(50):
        db.record_activity(5002, "group_message", "-1001", once_per_day=True)
    assert db.activity_count(5002, earnings.current_month()) == 1
