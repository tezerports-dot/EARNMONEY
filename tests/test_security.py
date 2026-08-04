"""Things that must stay true or someone loses money or privacy."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db, earnings
from app.bots.manager import mask_token, redact
from app.main import app
from app.timeutil import current_month
from app.web import auth
from tests.conftest import join_both

TOKEN = "test-admin-token"


@pytest.fixture
def client():
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def admin(client):
    client.post("/admin/login", data={"token": TOKEN, "next": "/admin"},
                follow_redirects=False)
    return client


@pytest.fixture(autouse=True)
def clear_lockouts():
    auth._attempts.clear()
    yield
    auth._attempts.clear()


# --------------------------------------------------------------------------- #
# authentication
# --------------------------------------------------------------------------- #

def test_every_admin_route_refuses_an_anonymous_caller(client):
    """A missed auth check on one route would expose everything behind it."""
    reads = [
        "/admin", "/admin/bots", "/admin/chats", "/admin/users", "/admin/activity",
        "/admin/events", "/admin/bank", "/admin/withdrawals", "/admin/export",
        "/admin/settings", "/admin/export/download", "/admin/users/UID-AAAAAA",
    ]
    writes = [
        "/admin/bots/add", "/admin/bots/1/start", "/admin/bots/1/stop",
        "/admin/bots/1/edit", "/admin/bots/1/delete", "/admin/chats/add",
        "/admin/chats/1/delete", "/admin/pairs/add", "/admin/pairs/1/edit",
        "/admin/pairs/1/default", "/admin/pairs/1/primary", "/admin/pairs/1/delete",
        "/admin/users/1/ban", "/admin/users/1/unban", "/admin/users/1/duplicate",
        "/admin/bank/prompt", "/admin/withdrawals/1/approve", "/admin/settings",
        "/admin/notify-test",
    ]
    for path in reads:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, f"GET {path} was not protected"
        assert "/admin/login" in response.headers.get("location", "")
    for path in writes:
        response = client.post(path, data={}, follow_redirects=False)
        assert response.status_code in (303, 422), f"POST {path} was not protected"
        if response.status_code == 303:
            assert "/admin/login" in response.headers.get("location", "")


def test_login_locks_out_after_repeated_failures(client):
    for _ in range(auth.MAX_ATTEMPTS):
        client.post("/admin/login", data={"token": "wrong", "next": "/admin"})

    response = client.post("/admin/login", data={"token": "wrong", "next": "/admin"})
    assert "Too many failed attempts" in response.text

    # Even the correct token is refused while the lockout stands.
    response = client.post("/admin/login", data={"token": TOKEN, "next": "/admin"},
                           follow_redirects=False)
    assert response.status_code == 200
    assert "Too many failed attempts" in response.text


def test_a_successful_login_clears_the_failure_counter(client):
    for _ in range(auth.MAX_ATTEMPTS - 1):
        client.post("/admin/login", data={"token": "wrong", "next": "/admin"})
    response = client.post("/admin/login", data={"token": TOKEN, "next": "/admin"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert auth._attempts == {}


def test_login_does_not_redirect_off_site(admin):
    """An open redirect turns a login link into a phishing hop."""
    for hostile in (
        "https://evil.example.com",
        "//evil.example.com",
        "/etc/passwd",
        "javascript:alert(1)",
    ):
        response = admin.get(f"/admin/login?next={hostile}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"


def test_a_forged_session_cookie_is_rejected(client):
    for forged in (
        "admin.99999999999.notasignature",
        "admin.99999999999.",
        "admin..sig",
        "garbage",
        "",
    ):
        client.cookies.set("admin_session", forged)
        response = client.get("/admin/users", follow_redirects=False)
        assert response.status_code == 303, f"{forged!r} was accepted"


def test_a_cookie_cannot_be_extended_past_its_expiry():
    """The signature covers the expiry, so the timestamp cannot be edited."""
    valid = auth.make_cookie()
    subject, expires, signature = valid.split(".")
    forged = f"{subject}.{int(expires) + 100_000}.{signature}"
    assert auth.valid_cookie(valid) is True
    assert auth.valid_cookie(forged) is False


def _settings_with(**overrides):
    """Settings is a frozen dataclass, so replace it wholesale."""
    import dataclasses

    return dataclasses.replace(auth.settings, **overrides)


def test_rotating_the_session_secret_invalidates_every_cookie(monkeypatch):
    cookie = auth.make_cookie()
    assert auth.valid_cookie(cookie) is True

    monkeypatch.setattr(auth, "settings", _settings_with(session_secret="rotated"))
    assert auth.valid_cookie(cookie) is False


def test_an_empty_admin_token_never_authenticates(monkeypatch):
    """A blank ADMIN_TOKEN must lock the door, not open it."""
    monkeypatch.setattr(auth, "settings", _settings_with(admin_token=""))
    assert auth.check_password("") is False
    assert auth.check_password("anything") is False


# --------------------------------------------------------------------------- #
# secrets and personal data
# --------------------------------------------------------------------------- #

def test_bot_tokens_are_masked_and_redacted():
    token = "7654321:AAHverysecretvaluehere123"
    assert token not in mask_token(token)
    assert "verysecretvaluehere123" not in mask_token(token)

    leaked = f"Unauthorized: https://api.telegram.org/bot{token}/getMe"
    assert token not in redact(leaked, token)
    assert "verysecretvaluehere123" not in redact(leaked, token)


def test_a_bot_error_never_stores_the_token(admin):
    token = "7654321:AAHverysecretvaluehere123"
    bot_id = db.add_bot(token=token, name="Main", role="main")
    db.update_bot(bot_id, last_error=redact(f"boom {token}", token))

    response = admin.get("/admin/bots")
    assert "AAHverysecretvaluehere123" not in response.text
    assert "verysecretvaluehere123" not in db.get_bot(bot_id)["last_error"]


def test_the_public_site_leaks_no_personal_data(client, world):
    referrer, _, _ = world
    join_both(5001)
    db.record_activity(5001)
    db.save_bank_details(5001, "Alice Example", "0012345678901234", "HDFC0001234",
                         "alice@okhdfcbank")

    for path in ("/", f"/u/{referrer['uid']}", "/leaderboard", "/how-it-works"):
        body = client.get(path).text
        assert "0012345678901234" not in body, f"account number leaked on {path}"
        assert "HDFC0001234" not in body, f"IFSC leaked on {path}"
        assert "alice@okhdfcbank" not in body, f"UPI leaked on {path}"
        assert "hash-alice" not in body, f"phone hash leaked on {path}"
        assert "5001" not in body, f"Telegram id leaked on {path}"


def test_healthz_publishes_no_counts(client, world):
    payload = client.get("/healthz").json()
    assert set(payload) == {"status", "bots_running", "month"}


def test_phone_numbers_are_never_stored_in_any_column(world):
    from app.ids import hash_phone

    number = "+91 98765 43210"
    db.set_user_fields(5001, phone_hash=hash_phone(number))

    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = 5001").fetchone()
    blob = b"".join(
        str(value).encode() if not isinstance(value, bytes) else value
        for value in tuple(row)
        if value is not None
    )
    assert b"9876543210" not in blob
    assert b"+91" not in blob


# --------------------------------------------------------------------------- #
# money
# --------------------------------------------------------------------------- #

def test_bank_details_cannot_be_changed_once_set(world):
    """The payout destination is fixed to the public ID for good."""
    assert db.save_bank_details(5001, "Alice", "111111111111", "HDFC0001234", "a@ok")
    assert not db.save_bank_details(5001, "Attacker", "999999999999", "SBIN0000123", "b@ok")

    stored = db.get_bank_details(5001)
    assert stored["account_number"] == "111111111111"
    assert stored["full_name"] == "Alice"


def test_only_one_withdrawal_per_user_per_month_even_under_a_race(world):
    month = current_month()
    assert db.create_withdrawal(5001, month, 20.0) is not None
    assert db.create_withdrawal(5001, month, 999.0) is None

    # And the schema refuses it even if the guard were bypassed.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO withdrawals(user_id, month, amount, status, created_at)"
            " VALUES (?, ?, ?, 'pending', ?)",
            (5001, int(month.replace("-", "")), 999.0, 0),
        )
    assert db.get_withdrawal(5001, month)["amount"] == 20.0


def test_a_self_referral_pays_nobody_anything_extra(world, month):
    """A self-loop must not make someone their own downline, at either level.

    Before this was guarded, setting referred_by to your own UID put you in
    your own level 1 *and* duplicated every real referral into your level 2.
    """
    alice, bob, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    db.record_activity(5002)
    honest = earnings.report_for(db.get_user(5001), month).amount

    db.set_user_fields(5001, referred_by=str(alice["uid"]))

    report = earnings.report_for(db.get_user(5001), month)
    assert alice["uid"] not in [row.user["uid"] for row in report.rows]
    seen = [row.user["uid"] for row in report.rows]
    assert len(seen) == len(set(seen)), "a member was counted at both levels"
    assert report.amount == honest


def test_payouts_come_from_sql_counts_not_the_displayed_rows(world, month):
    """A member with a huge downline must still be paid exactly right."""
    alice, bob, pair = world
    pair_id = int(pair["pair_id"])
    join_both(5001)
    db.record_activity(5001)

    for index in range(60):
        uid = 6000 + index
        db.create_user(uid, referred_by=str(alice["uid"]))
        db.set_flags(uid, verified=True)
        db.assign_pair(uid, pair_id)
        join_both(uid)
        db.record_activity(uid)

    # Render only 10 rows, but pay for all 61 active direct referrals.
    report = earnings.report_for(db.get_user(5001), month, row_limit=10)
    assert len(report.level1_rows) == 10
    assert report.truncated is True
    # 61 direct referrals exist, but bob never joined, so 60 are payable.
    assert report.total_referrals == 61
    assert report.active_referrals == 60
    assert report.level1_amount == 60 * earnings.rates().level1


def test_banned_and_duplicate_accounts_are_worth_nothing(world, month):
    alice, _, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001)
    db.record_activity(5002)
    assert earnings.report_for(db.get_user(5001), month).amount > 0

    db.set_flags(5002, banned=True)
    assert earnings.report_for(db.get_user(5001), month).amount == 0

    db.set_flags(5002, banned=False, duplicate=True)
    assert earnings.report_for(db.get_user(5001), month).amount == 0


# --------------------------------------------------------------------------- #
# input handling
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "hostile",
    [
        "UID-A' OR '1'='1",
        "'; DROP TABLE users; --",
        "UID-<script>alert(1)</script>",
        "../../etc/passwd",
        "%00",
    ],
)
def test_hostile_search_input_is_handled(client, admin, hostile, world):
    """Parameterised queries and UID normalisation, not string building."""
    assert client.get("/", params={"q": hostile}).status_code == 200
    assert admin.get("/admin/users", params={"q": hostile}).status_code == 200
    assert db.count_users() >= 2  # the table is still there


def test_uid_normalisation_rejects_anything_that_is_not_a_uid():
    from app.ids import normalise_uid

    for hostile in ("' OR 1=1", "UID-'; --", "<script>", "UID-TOOLONGXX", "", None):
        assert normalise_uid(hostile) is None


def test_rendered_pages_escape_hostile_settings(admin):
    """Settings are admin-authored, but must not become stored XSS."""
    db.set_setting("banned_words", "<script>alert('xss')</script>")
    response = admin.get("/admin/settings")
    assert "<script>alert('xss')</script>" not in response.text
    assert "&lt;script&gt;" in response.text
