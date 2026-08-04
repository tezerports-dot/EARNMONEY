"""Public dashboard and admin panel routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from tests.conftest import join_both

TOKEN = "test-admin-token"


@pytest.fixture
def client():
    # https, because the session cookie is issued with Secure whenever
    # PUBLIC_BASE_URL is https — over plain http it would never come back.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def admin(client):
    response = client.post(
        "/admin/login", data={"token": TOKEN, "next": "/admin"}, follow_redirects=False
    )
    assert response.status_code == 303
    return client


def test_home_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Look up a member" in response.text


def test_search_redirects_to_the_user_page(client, world):
    referrer, _, _ = world
    response = client.get("/", params={"q": referrer["uid"]}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/u/{referrer['uid']}"


def test_search_accepts_a_uid_without_the_dash(client, world):
    referrer, _, _ = world
    response = client.get(
        "/", params={"q": referrer["uid"].replace("-", "").lower()}, follow_redirects=False
    )
    assert response.status_code == 303


def test_unknown_uid_reports_not_found(client):
    response = client.get("/", params={"q": "UID-ZZZZZZ"})
    assert response.status_code == 200
    assert "No account found" in response.text


def test_public_user_page_shows_the_breakdown(client, world):
    referrer, referred, _ = world
    join_both(5001)
    join_both(5002)
    db.record_activity(5001, "command", "/start")
    db.record_activity(5002, "callback", "tap")

    response = client.get(f"/u/{referrer['uid']}")
    assert response.status_code == 200
    assert referred["uid"] in response.text
    assert "₹5" in response.text  # one active level-1 referral at the default rate
    assert "Level 1" in response.text and "Level 2" in response.text


def test_public_page_never_exposes_bank_details_or_phone(client, world):
    referrer, _, _ = world
    db.save_bank_details(5001, "Alice Example", "123456789012", "HDFC0001234", "a@okhdfc")
    response = client.get(f"/u/{referrer['uid']}")
    assert response.status_code == 200
    assert "123456789012" not in response.text
    assert "HDFC0001234" not in response.text
    assert "hash-alice" not in response.text


def test_unknown_path_is_a_404_not_a_200(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "404" in response.text


def test_healthz(client):
    payload = client.get("/healthz").json()
    assert payload["status"] == "ok"
    assert payload["bots_running"] == 0


def test_admin_requires_login(client):
    response = client.get("/admin/users", follow_redirects=False)
    assert response.status_code == 303
    assert "/admin/login" in response.headers["location"]


def test_admin_rejects_a_wrong_token(client):
    response = client.post("/admin/login", data={"token": "nope", "next": "/admin"})
    assert response.status_code == 200
    assert "Wrong token" in response.text


def test_admin_pages_render(admin, world):
    for path in (
        "/admin",
        "/admin/bots",
        "/admin/chats",
        "/admin/users",
        "/admin/activity",
        "/admin/events",
        "/admin/bank",
        "/admin/withdrawals",
        "/admin/export",
        "/admin/settings",
    ):
        response = admin.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        # Guard against a silent bounce to the login form counting as a pass.
        assert 'action="/admin/login"' not in response.text, f"{path} redirected to login"
        assert "/admin/logout" in response.text


def test_admin_user_detail(admin, world):
    referrer, _, _ = world
    response = admin.get(f"/admin/users/{referrer['uid']}")
    assert response.status_code == 200
    assert referrer["uid"] in response.text


def test_admin_never_shows_a_full_bot_token(admin):
    db.add_bot(token="7654321:AAHsecretsecretsecretsecret", name="Main", role="main")
    response = admin.get("/admin/bots")
    assert response.status_code == 200
    assert "AAHsecretsecretsecretsecret" not in response.text
    assert "7654321:AAH...ret" in response.text


def test_admin_can_edit_settings(admin):
    admin.post("/admin/settings", data={"banned_words": "spam,scam", "flood_limit": "9"})
    assert db.get_setting("banned_words") == "spam,scam"
    assert db.get_setting_int("flood_limit", 0) == 9


def test_admin_can_edit_both_payout_rates(admin):
    from app import earnings

    admin.post("/admin/settings", data={"payout_level1": "8", "payout_level2": "2.5"})
    current = earnings.rates()
    assert current.level1 == 8.0
    assert current.level2 == 2.5


def test_a_non_numeric_payout_rate_is_rejected_not_coerced(admin):
    """Silently storing 0 would zero out everyone's earnings."""
    from app import earnings

    admin.post("/admin/settings", data={"payout_level1": "8"})
    response = admin.post(
        "/admin/settings", data={"payout_level1": "free money"}, follow_redirects=True
    )
    assert earnings.rates().level1 == 8.0
    assert "Ignored payout_level1" in response.text


def test_a_negative_payout_rate_is_rejected(admin):
    from app import earnings

    admin.post("/admin/settings", data={"payout_level2": "-5"})
    assert earnings.rates().level2 == 5.0


def test_flash_messages_survive_non_latin1_characters(admin):
    """Cookies are latin-1 only; these messages carry ₹ and em dashes."""
    from app.web.admin import _redirect

    response = _redirect("/admin", "Paid ₹20 — done.")
    assert response.status_code == 303

    admin.cookies.set("admin_flash", response.headers["set-cookie"].split("=")[1].split(";")[0])
    page = admin.get("/admin")
    assert "Paid ₹20 — done." in page.text


def test_logout_clears_the_session(admin):
    admin.get("/admin/logout", follow_redirects=False)
    response = admin.get("/admin/users", follow_redirects=False)
    assert response.status_code == 303


def test_expired_or_forged_cookies_are_rejected(client):
    client.cookies.set("admin_session", "admin.99999999999.forged-signature")
    response = client.get("/admin/users", follow_redirects=False)
    assert response.status_code == 303
