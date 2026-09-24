"""Admin panel, public pages and request gates (CLAUDE.md §24, §27;
abuse cases 29, 30, 34 and 39)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pyotp
from sqlalchemy import select, text

from app import db, timeutil
from app.admin.auth import create_admin, totp_for
from app.models import AdminUser, AppSettings, Campaign
from tests import helpers
from tests.helpers import auth, fund_pool, idem, telegram_setup, verified_user


async def make_admin() -> tuple[str, str]:
    async with db.sessionmaker()() as s, s.begin():
        _, uri = await create_admin(s, "owner", "a-long-admin-password")
    return "a-long-admin-password", pyotp.parse_uri(uri).secret


async def admin_login(client) -> str:
    password, secret = await make_admin()
    r = await client.post("/admin/login", data={"username": "owner", "password": password, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 303, r.text
    client.cookies.set("ff_admin", r.cookies["ff_admin"], path="/admin")
    page = (await client.get("/admin/campaign")).text
    return re.search(r'name="csrf" value="([^"]+)"', page).group(1)


async def test_admin_needs_password_and_code(client):
    password, secret = await make_admin()
    bad_code = await client.post("/admin/login", data={"username": "owner", "password": password, "code": "000000"})
    bad_password = await client.post(
        "/admin/login", data={"username": "owner", "password": "wrong", "code": pyotp.TOTP(secret).now()}
    )
    for r in (bad_code, bad_password):
        assert r.status_code == 200 and "Those details didn" in r.text
        assert "ff_admin" not in r.cookies
    assert (await client.get("/admin", follow_redirects=False)).status_code == 303


async def test_totp_secret_is_encrypted():
    _, secret = await make_admin()
    async with db.sessionmaker()() as s, s.begin():
        admin = (await s.execute(select(AdminUser))).scalar_one()
        assert secret.encode() not in admin.totp_secret_ciphertext
        assert totp_for(admin).secret == secret


async def test_admin_forms_need_csrf(client):
    await admin_login(client)
    r = await client.post("/admin/settings", data={"company_name": "X", "csrf": "forged"})
    assert r.status_code == 403


async def test_admin_edits_campaign_and_it_is_audited(client):
    csrf = await admin_login(client)
    form = {
        "csrf": csrf,
        "name": "Future Fashion launch",
        "starts_at": "2026-09-01T00:00",
        "ends_at": "2026-12-31T23:59",
        "brand_reveal_at": "2026-12-21T00:00",
        "launch_at": "2026-12-31T00:00",
        "payout_opens_at": "2027-01-05T10:00",
        "brand_name": "",
        "level_1_reward_rupees": "250",
        "min_withdrawal_rupees": "500",
        "capacity": "50000000",
        "signups_open": "on",
    }
    r = await client.post("/admin/campaign", data=form)
    assert r.status_code == 303
    config = (await client.get("/v1/config")).json()
    assert config["rewards"]["levels"][0]["reward_per_user_paise"] == 25000
    assert [row["reward_per_user_paise"] for row in config["rewards"]["levels"][1:]] == [0, 0, 0]
    assert config["rewards"]["min_withdrawal_paise"] == 50000
    assert config["campaign"]["payout_opens_at"] == "2027-01-05T04:30:00Z"  # 10:00 IST
    async with db.sessionmaker()() as s, s.begin():
        actions = list((await s.execute(text("SELECT action FROM audit_log ORDER BY id"))).scalars())
    assert "campaign.updated" in actions


async def test_admin_cannot_set_the_member_count(client, telegram):
    """There is no admin control for the counter: it only moves when users verify."""
    csrf = await admin_login(client)
    setup = await telegram_setup(telegram, channels=0)
    await verified_user(client, setup)
    await client.post(
        "/admin/settings",
        data={"csrf": csrf, "company_name": "Future Fashion", "min_app_version": "1.0.0", "verified_count": "11577956"},
    )
    await client.post("/admin/campaign", data={"csrf": csrf, "verified_count": "11577956"})
    assert (await client.get("/v1/config")).json()["membership"]["verified_count"] == 1


async def test_legal_details_reach_the_app(client):
    """The app fills its bundled terms from these, so they must come through /v1/config."""
    config = (await client.get("/v1/config")).json()
    assert config["company_legal_name"] is None and config["support_email"] is None
    csrf = await admin_login(client)
    form = {
        "csrf": csrf,
        "company_name": "Future Fashion",
        "company_legal_name": "Future Fashion Private Limited",
        "support_email": "help@futurefashion.example",
        "min_app_version": "1.0.0",
    }
    assert (await client.post("/admin/settings", data=form)).status_code == 303
    from app.api.deps import reset_gate_cache

    reset_gate_cache()
    config = (await client.get("/v1/config")).json()
    assert config["company_legal_name"] == "Future Fashion Private Limited"
    assert config["support_email"] == "help@futurefashion.example"


async def test_funding_form_records_once(client):
    csrf = await admin_login(client)
    form = {"csrf": csrf, "amount_rupees": "1,00,000", "memo": "Board approval 12", "nonce": "fixed-nonce-1"}
    assert (await client.post("/admin/campaign/fund", data=form)).status_code == 303
    assert (await client.post("/admin/campaign/fund", data=form)).status_code == 303  # double submit
    async with db.sessionmaker()() as s, s.begin():
        pool = (await s.execute(text("SELECT balance_paise FROM ledger_accounts WHERE kind = 'PROMO_POOL'"))).scalar_one()
    assert pool == 1_00_000 * 100


async def test_payout_export_is_audited(client, telegram):
    csrf = await admin_login(client)
    setup = await telegram_setup(telegram, channels=0)
    await fund_pool()
    user = await verified_user(client, setup)
    await verified_user(client, setup, user["user"]["public_id"])
    timeutil.freeze(datetime(2026, 12, 31, 6, 0, tzinfo=UTC))
    await helpers.login(client, user)
    h = auth(user["tokens"])
    await client.post(
        "/v1/bank-details",
        json={"account_holder_name": "Ravi Kumar", "account_number": "123456784821", "ifsc": "HDFC0001234"},
        headers={**h, **idem()},
    )
    await client.post("/v1/withdrawals", json={"amount_paise": 20000}, headers={**h, **idem()})
    csrf = await admin_login_again(client)
    assert (await client.post("/admin/withdrawals/batch", data={"csrf": csrf})).status_code == 303
    csv_body = (await client.get("/admin/batches/1.csv")).text
    assert "123456784821" in csv_body and "200.00" in csv_body
    async with db.sessionmaker()() as s, s.begin():
        actions = list((await s.execute(text("SELECT action FROM audit_log"))).scalars())
    assert "payout.exported" in actions


async def admin_login_again(client) -> str:
    # The clock moved past the admin session lifetime; sign in again.
    async with db.sessionmaker()() as s, s.begin():
        admin = (await s.execute(select(AdminUser))).scalar_one()
        secret = totp_for(admin).secret
    r = await client.post(
        "/admin/login", data={"username": "owner", "password": "a-long-admin-password", "code": pyotp.TOTP(secret).now()}
    )
    client.cookies.set("ff_admin", r.cookies["ff_admin"], path="/admin")
    return re.search(r'name="csrf" value="([^"]+)"', (await client.get("/admin/campaign")).text).group(1)


async def test_admin_pages_render(client):
    await admin_login(client)
    for path in (
        "/admin",
        "/admin/campaign",
        "/admin/settings",
        "/admin/bots",
        "/admin/channels",
        "/admin/users",
        "/admin/withdrawals",
        "/admin/flags",
        "/admin/audit",
        "/admin/ledger",
    ):
        r = await client.get(path)
        assert r.status_code == 200, path
        assert r.headers["x-frame-options"] == "DENY"
    assert "The ledger balances" in (await client.get("/admin/ledger")).text


async def test_landing_page_and_download(client):
    """Abuse cases 29 and 30. Without the app, the page shows the code to copy
    and a download; with the app, "I already have the app" opens it with the
    code. Opening a link binds nothing: only signing up with the code does."""
    r = await client.get("/r/7q2k9mxa")
    assert r.status_code == 200 and "7Q2K9MXA" in r.text
    assert "Future Fashion" in r.text
    assert "intent://r/7Q2K9MXA#Intent;scheme=futurefashion;package=" in r.text
    assert 'href="/download"' in r.text
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(text("SELECT count(*) FROM users"))).scalar_one() == 0
    broken = await client.get("/r/<script>")
    assert broken.status_code == 200 and "<script>alert" not in broken.text
    assert "isn't complete" in broken.text and "intent://" not in broken.text
    assert (await client.get("/download")).status_code == 404  # no APK URL configured yet
    async with db.sessionmaker()() as s, s.begin():
        (await s.get(AppSettings, 1)).apk_download_url = "https://cdn.example/futurefashion-1.0.0.apk"
    r = await client.get("/download", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith(".apk")


async def test_health_and_assetlinks(client):
    assert (await client.get("/healthz")).json() == {"ok": True}
    assert (await client.get("/readyz")).json() == {"ok": True}
    assert (await client.get("/.well-known/assetlinks.json")).json() == []


async def test_maintenance_mode(client):
    """Abuse case 34: maintenance blocks the API but not the config the app needs."""
    body = await helpers.signup(client)
    async with db.sessionmaker()() as s, s.begin():
        settings = await s.get(AppSettings, 1)
        settings.maintenance_active = True
        settings.maintenance_message = "Back at 6 pm"
    from app.api.deps import reset_gate_cache

    reset_gate_cache()
    r = await client.get("/v1/me", headers=auth(body["tokens"]))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "MAINTENANCE"
    assert r.json()["error"]["message"] == "Back at 6 pm"
    config = (await client.get("/v1/config")).json()
    assert config["maintenance"]["active"] is True


async def test_old_app_must_upgrade(client):
    async with db.sessionmaker()() as s, s.begin():
        settings = await s.get(AppSettings, 1)
        settings.min_app_version = "1.2.0"
        settings.apk_download_url = "https://cdn.example/app.apk"
    from app.api.deps import reset_gate_cache

    reset_gate_cache()
    r = await client.get("/v1/captcha", headers={"X-App-Version": "1.1.9"})
    assert r.status_code == 426
    assert r.json()["error"]["download_url"] == "https://cdn.example/app.apk"
    assert (await client.get("/v1/captcha", headers={"X-App-Version": "1.2.0"})).status_code == 200


async def test_errors_never_leak_internals(client):
    r = await client.get("/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    r = await client.post("/v1/auth/login", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert "Traceback" not in r.text and "sqlalchemy" not in r.text.lower()
    assert r.headers["x-request-id"]


async def test_database_outage_is_a_clean_503(client, monkeypatch):
    """Abuse case 39: a database outage gives a retryable error, not a stack trace."""
    from sqlalchemy.exc import OperationalError

    from app.services import campaign

    async def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(campaign, "public_config", broken)
    r = await client.get("/v1/config")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "connection refused" not in r.text


async def test_campaign_row_exists():
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(select(Campaign))).scalar_one().level_1_reward_paise == 20000
