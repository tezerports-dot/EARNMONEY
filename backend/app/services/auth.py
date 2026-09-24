"""Signup and login."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, ids, timeutil
from app.config import get_settings
from app.models import User
from app.phone import mask_phone, normalize_indian_mobile
from app.security import captcha, passwords, ratelimit
from app.services import audit, campaign, idempotency, referrals, sessions, users

PASSWORD_MIN, PASSWORD_MAX = 8, 128


@dataclass
class SignupInput:
    phone: str
    password: str
    referral_code: str | None
    captcha_id: str | None
    captcha_answer: str | None


def _validate(phone_raw: str, password: str) -> str:
    fields: dict[str, str] = {}
    phone = normalize_indian_mobile(phone_raw)
    if phone is None:
        fields["phone"] = "Enter a 10-digit Indian mobile number."
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        fields["password"] = f"Use {PASSWORD_MIN} to {PASSWORD_MAX} characters."
    if fields:
        raise errors.ValidationFailed(fields=fields)
    assert phone is not None
    return phone


async def _replay_signup(db: AsyncSession, phone: str, password: str, user_agent: str | None) -> tuple[int, dict]:
    """A retry of a signup that already succeeded.

    Tokens are never stored with the idempotency record, so the retry proves
    the password again and gets a fresh session.
    """
    async with db.begin():
        user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if user is None or not await passwords.verify_password(user.password_hash, password):
        raise errors.IdempotencyKeyReused()
    async with db.begin():
        user = await db.get(User, user.id)
        assert user is not None
        issued = await sessions.issue(db, user, user_agent)
        return 201, {"user": await users.me_json(db, user), "tokens": issued.as_json()}


async def signup(
    db: AsyncSession, data: SignupInput, *, idempotency_key: str, ip: str, user_agent: str | None
) -> tuple[int, dict]:
    phone = _validate(data.phone, data.password)
    payload = {"phone": phone, "referral_code": (data.referral_code or "").strip().upper() or None}

    # A retry of a completed signup is answered before limits and the
    # single-use CAPTCHA, which the first attempt already consumed.
    async with db.begin():
        replay = await idempotency.lookup(db, "signup", idempotency_key, payload)
    if replay:
        return await _replay_signup(db, phone, data.password, user_agent)

    await ratelimit.hit(ratelimit.SIGNUP_IP, ip)
    await ratelimit.hit(ratelimit.SIGNUP_PHONE, phone)
    await captcha.verify(data.captcha_id, data.captcha_answer)
    password_hash = await passwords.hash_password(data.password)

    replayed = False
    try:
        async with db.begin():
            if await idempotency.begin(db, "signup", idempotency_key, payload):
                replayed = True  # a concurrent duplicate finished first
            else:
                if not (await campaign.gates(db)).signups_open:
                    raise errors.SignupsClosed()

                referrer = await referrals.find_referrer(db, data.referral_code) if payload["referral_code"] else None

                existing = (
                    await db.execute(select(User).where(User.phone == phone).with_for_update())
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.status != "PENDING_VERIFICATION":
                        raise errors.PhoneUnavailable()
                    # An unverified signup holds no rights: only the real owner
                    # of the number can finish Telegram verification. Replacing
                    # it stops anyone reserving someone else's number.
                    await audit.record(db, "system", "user.pending_replaced", f"user:{existing.public_id}", ip=ip)
                    await db.execute(delete(User).where(User.id == existing.id))
                    await db.flush()

                user = User(
                    public_id=ids.new_public_id(),
                    phone=phone,
                    password_hash=password_hash,
                    status="PENDING_VERIFICATION",
                    referrer_id=referrer.id if referrer else None,
                    pending_expires_at=timeutil.now() + timedelta(hours=get_settings().pending_account_hours),
                )
                db.add(user)
                await db.flush()
                if referrer:
                    await referrals.bind(db, user, referrer)
                issued = await sessions.issue(db, user, user_agent)
                await audit.record(
                    db,
                    f"user:{user.public_id}",
                    "user.signed_up",
                    f"user:{user.public_id}",
                    {"phone": mask_phone(phone), "referred_by": referrer.public_id if referrer else None},
                    ip=ip,
                )
                me = await users.me_json(db, user)
                await idempotency.complete(db, "signup", idempotency_key, 201, {"user": me})
                return 201, {"user": me, "tokens": issued.as_json()}
    except IntegrityError as exc:
        # Two different signups for one number at the same moment, or (very
        # rarely) a public id collision. Neither created anything.
        if "phone" in str(exc.orig):
            raise errors.PhoneUnavailable() from exc
        raise errors.ServiceUnavailable() from exc
    assert replayed
    return await _replay_signup(db, phone, data.password, user_agent)


async def login(
    db: AsyncSession,
    phone_raw: str,
    password: str,
    captcha_id: str | None,
    captcha_answer: str | None,
    *,
    ip: str,
    user_agent: str | None,
) -> dict:
    await ratelimit.hit(ratelimit.LOGIN_IP, ip)
    phone = normalize_indian_mobile(phone_raw)
    if phone is None or not password or len(password) > PASSWORD_MAX:
        await passwords.verify_password(None, password or "x")
        raise errors.InvalidCredentials()

    failures, ttl = await ratelimit.login_failures(phone)
    if failures >= ratelimit.LOGIN_LOCK_AFTER:
        raise errors.RateLimited(retry_after=ttl)
    if failures >= ratelimit.LOGIN_CAPTCHA_AFTER:
        await captcha.verify(captcha_id, captcha_answer)

    async with db.begin():
        user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if (
        user is not None
        and user.status == "PENDING_VERIFICATION"
        and user.pending_expires_at is not None
        and user.pending_expires_at <= timeutil.now()
    ):
        user = None  # expired signups behave as if they never existed
    ok = await passwords.verify_password(user.password_hash if user else None, password)
    if not ok or user is None:
        await ratelimit.record_login_failure(phone)
        raise errors.InvalidCredentials()
    if user.status == "SUSPENDED":
        raise errors.AccountSuspended()
    await ratelimit.clear_login_failures(phone)
    new_hash = await passwords.hash_password(password) if passwords.needs_rehash(user.password_hash) else None

    async with db.begin():
        user = await db.get(User, user.id)
        assert user is not None
        if new_hash:
            user.password_hash = new_hash
        issued = await sessions.issue(db, user, user_agent)
        await audit.record(db, f"user:{user.public_id}", "user.logged_in", f"user:{user.public_id}", ip=ip)
        return {"user": await users.me_json(db, user), "tokens": issued.as_json()}
