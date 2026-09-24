"""Signup, login, sessions (CLAUDE.md §5, abuse cases 3, 5, 9, 10, 17, 21, 25)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app import db
from app.models import AuthSession, IdempotencyKey, User
from tests import helpers
from tests.helpers import auth, captcha, idem, new_phone, signup, signup_response


async def count_users() -> int:
    async with db.sessionmaker()() as s, s.begin():
        return (await s.execute(select(func.count()).select_from(User))).scalar_one()


async def test_signup_creates_pending_account(client):
    body = await signup(client, "9876543210")
    assert body["user"]["status"] == "PENDING_VERIFICATION"
    assert body["user"]["phone_masked"] == "98XXXXXX10"
    assert body["user"]["referral_code"] is None  # no code until verified
    assert body["tokens"]["token_type"] == "Bearer"
    assert "password" not in str(body)


async def test_signup_accepts_indian_number_formats(client):
    body = await signup(client, "+91 98765 43211")
    assert body["user"]["phone_masked"] == "98XXXXXX11"


async def test_signup_validation(client):
    captcha_id, answer = await captcha(client)
    r = await client.post(
        "/v1/auth/signup",
        json={"phone": "12345", "password": "short", "captcha_id": captcha_id, "captcha_answer": answer},
        headers=idem(),
    )
    assert r.status_code == 400
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert set(error["fields"]) == {"phone", "password"}
    assert error["request_id"]


async def test_signup_needs_idempotency_key(client):
    r = await signup_response(client, headers={"X-Other": "1"})
    assert r.status_code == 400
    assert "Idempotency-Key" in r.json()["error"]["fields"]


async def test_duplicate_signup_request_creates_one_account(client):
    """Abuse case 5 and 25: a retried signup never creates a second account."""
    phone, headers = new_phone(), idem()
    first = await signup_response(client, phone, headers=headers)
    # The retry reuses the key and body (and the now-consumed CAPTCHA).
    captcha_id, answer = await captcha(client)
    retry = await client.post(
        "/v1/auth/signup",
        json={"phone": phone, "password": "correct-horse-9", "captcha_id": captcha_id, "captcha_answer": "wrong"},
        headers=headers,
    )
    assert first.status_code == retry.status_code == 201
    assert first.json()["user"]["public_id"] == retry.json()["user"]["public_id"]
    assert first.json()["tokens"]["access_token"] != retry.json()["tokens"]["access_token"]
    assert await count_users() == 1


async def test_retry_with_different_details_is_rejected(client):
    headers = idem()
    await signup_response(client, new_phone(), headers=headers)
    r = await signup_response(client, new_phone(), headers=headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_retry_with_wrong_password_gets_no_tokens(client):
    phone, headers = new_phone(), idem()
    await signup_response(client, phone, headers=headers)
    r = await signup_response(client, phone, password="another-password", headers=headers)
    assert r.status_code == 409
    assert "tokens" not in r.text


async def test_idempotency_table_never_stores_tokens(client):
    body = await signup(client)
    async with db.sessionmaker()() as s, s.begin():
        rows = list((await s.execute(select(IdempotencyKey.response_body))).scalars())
    assert rows and all("tokens" not in row for row in rows)
    assert body["tokens"]["access_token"] not in str(rows)


async def test_captcha_is_single_use(client):
    """Abuse case 10: a solved CAPTCHA can't be replayed."""
    captcha_id, answer = await captcha(client)
    payload = {"phone": new_phone(), "password": "correct-horse-9", "captcha_id": captcha_id, "captcha_answer": answer}
    assert (await client.post("/v1/auth/signup", json=payload, headers=idem())).status_code == 201
    payload["phone"] = new_phone()
    replay = await client.post("/v1/auth/signup", json=payload, headers=idem())
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "CAPTCHA_INVALID"


async def test_wrong_captcha_answer(client):
    captcha_id, answer = await captcha(client)
    wrong = str(int(answer) + 1)
    r = await client.post(
        "/v1/auth/signup",
        json={"phone": new_phone(), "password": "correct-horse-9", "captcha_id": captcha_id, "captcha_answer": wrong},
        headers=idem(),
    )
    assert r.json()["error"]["code"] == "CAPTCHA_INVALID"


async def test_same_phone_signup_rate_limited(client):
    """Abuse case 3: the same phone can't be hammered."""
    phone = new_phone()
    codes = [(await signup_response(client, phone)).status_code for _ in range(4)]
    assert codes[:3] == [201, 201, 201]  # each replaces the unverified one
    assert codes[3] == 429


async def test_unverified_signup_is_replaced_not_duplicated(client):
    phone = new_phone()
    first = await signup(client, phone)
    second = await signup(client, phone)
    assert first["user"]["public_id"] != second["user"]["public_id"]
    assert await count_users() == 1
    # The replaced account's session no longer works.
    r = await client.get("/v1/me", headers=auth(first["tokens"]))
    assert r.status_code == 401


async def test_invalid_referral_code(client):
    """Abuse cases 17 and 31."""
    r = await signup_response(client, code="NOPE0000")
    assert r.json()["error"]["code"] == "REFERRAL_CODE_INVALID"
    r = await signup_response(client, code="ZZZZZZZZ")
    assert r.json()["error"]["code"] == "REFERRAL_CODE_INVALID"


async def test_unverified_users_cannot_refer(client):
    pending = await signup(client)
    r = await signup_response(client, code=pending["user"]["public_id"])
    assert r.json()["error"]["code"] == "REFERRAL_CODE_INVALID"


async def test_login_and_generic_errors(client):
    phone = new_phone()
    await signup(client, phone)
    ok = await client.post("/v1/auth/login", json={"phone": phone, "password": "correct-horse-9"})
    assert ok.status_code == 200
    assert ok.json()["user"]["status"] == "PENDING_VERIFICATION"

    wrong = await client.post("/v1/auth/login", json={"phone": phone, "password": "wrong-password"})
    unknown = await client.post("/v1/auth/login", json={"phone": new_phone(), "password": "wrong-password"})
    assert wrong.status_code == unknown.status_code == 401
    # Same code and message: a login can't reveal whether a number is registered.
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_login_brute_force(client):
    """Abuse case 9: CAPTCHA after 3 failures, lockout after 10."""
    phone = new_phone()
    await signup(client, phone)
    bad = {"phone": phone, "password": "wrong-password"}
    for _ in range(3):
        assert (await client.post("/v1/auth/login", json=bad)).json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = await client.post("/v1/auth/login", json=bad)
    assert r.json()["error"]["code"] == "CAPTCHA_REQUIRED"
    for _ in range(7):
        captcha_id, answer = await captcha(client)
        await client.post("/v1/auth/login", json={**bad, "captcha_id": captcha_id, "captcha_answer": answer})
    captcha_id, answer = await captcha(client)
    locked = await client.post(
        "/v1/auth/login", json={"phone": phone, "password": "correct-horse-9", "captcha_id": captcha_id, "captcha_answer": answer}
    )
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0


async def test_expired_pending_account_cannot_log_in(client):
    phone = new_phone()
    await signup(client, phone)
    helpers.advance(timedelta(hours=25))
    r = await client.post("/v1/auth/login", json={"phone": phone, "password": "correct-horse-9"})
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_refresh_rotates_and_detects_reuse(client):
    """Abuse case 21: replaying an old refresh token ends the whole login."""
    body = await signup(client)
    old = body["tokens"]
    r = await client.post("/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert r.status_code == 200
    new = r.json()["tokens"]
    assert new["refresh_token"] != old["refresh_token"]
    assert (await client.get("/v1/me", headers=auth(old))).status_code == 401
    assert (await client.get("/v1/me", headers=auth(new))).status_code == 200

    replay = await client.post("/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert replay.json()["error"]["code"] == "SESSION_EXPIRED"
    # The attacker's replay also logged out the rotated session.
    assert (await client.get("/v1/me", headers=auth(new))).status_code == 401


async def test_access_token_expires(client):
    body = await signup(client)
    helpers.advance(timedelta(minutes=16))
    r = await client.get("/v1/me", headers=auth(body["tokens"]))
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_logout(client):
    body = await signup(client)
    assert (await client.post("/v1/auth/logout", headers=auth(body["tokens"]))).status_code == 204
    assert (await client.get("/v1/me", headers=auth(body["tokens"]))).status_code == 401
    r = await client.post("/v1/auth/refresh", json={"refresh_token": body["tokens"]["refresh_token"]})
    assert r.status_code == 401
    async with db.sessionmaker()() as s, s.begin():
        assert (await s.execute(select(func.count()).select_from(User))).scalar_one() == 1  # account kept
        live = (
            await s.execute(select(func.count()).select_from(AuthSession).where(AuthSession.revoked_at.is_(None)))
        ).scalar_one()
    assert live == 0


async def test_pending_user_cannot_use_verified_endpoints(client):
    body = await signup(client)
    for path in ("/v1/wallet", "/v1/referrals/summary", "/v1/dashboard", "/v1/bank-details", "/v1/withdrawals"):
        r = await client.get(path, headers=auth(body["tokens"]))
        assert r.status_code == 403, path
        assert r.json()["error"]["code"] == "ACCOUNT_NOT_VERIFIED"


async def test_bad_tokens(client):
    for header in ("Bearer nope", "Basic abc", "Bearer ", "Bearer " + "x" * 500):
        r = await client.get("/v1/me", headers={"Authorization": header})
        assert r.status_code == 401
