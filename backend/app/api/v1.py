"""The v1 API the app uses. Shapes are documented in docs/API.md."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors
from app.api.deps import Auth, app_gate, auth, client_ip, idempotency_key, user_agent, verified
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.security import captcha, ratelimit
from app.security.crypto import fingerprint
from app.services import (
    auth as auth_service,
)
from app.services import (
    bank,
    campaign,
    idempotency,
    referrals,
    sessions,
    users,
    verification,
    wallet,
    withdrawals,
)
from app.services.auth import SignupInput

public = APIRouter(prefix="/v1")
router = APIRouter(prefix="/v1", dependencies=[Depends(app_gate)])

NO_STORE = {"Cache-Control": "no-store"}


def ok(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers=NO_STORE)


# --- Public -------------------------------------------------------------------


@public.get("/config")
async def get_config(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    await ratelimit.hit(ratelimit.CONFIG, client_ip(request))
    async with db.begin():
        body = await campaign.public_config(db)
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=30"})


@router.get("/captcha")
async def get_captcha(request: Request) -> JSONResponse:
    await ratelimit.hit(ratelimit.CAPTCHA, client_ip(request))
    return ok(await captcha.create())


@router.get("/referral-codes/{code}")
async def check_referral_code(code: str, request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    await ratelimit.hit(ratelimit.REFERRAL_CHECK, client_ip(request))
    try:
        async with db.begin():
            await referrals.find_referrer(db, code[:20])
    except errors.ReferralCodeInvalid as exc:
        raise errors.ReferralCodeUnknown() from exc
    return ok({"valid": True})


# --- Auth ---------------------------------------------------------------------


class SignupBody(BaseModel):
    phone: str = Field(max_length=20)
    password: str = Field(max_length=200)
    referral_code: str | None = Field(default=None, max_length=20)
    captcha_id: str | None = Field(default=None, max_length=64)
    captcha_answer: str | None = Field(default=None, max_length=10)


class LoginBody(BaseModel):
    phone: str = Field(max_length=20)
    password: str = Field(max_length=200)
    captcha_id: str | None = Field(default=None, max_length=64)
    captcha_answer: str | None = Field(default=None, max_length=10)


class RefreshBody(BaseModel):
    refresh_token: str = Field(max_length=200)


@router.post("/auth/signup")
async def signup(
    body: SignupBody,
    request: Request,
    key: str = Depends(idempotency_key),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    status, payload = await auth_service.signup(
        db,
        SignupInput(body.phone, body.password, body.referral_code, body.captcha_id, body.captcha_answer),
        idempotency_key=key,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    return ok(payload, status)


@router.post("/auth/login")
async def login(body: LoginBody, request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    payload = await auth_service.login(
        db,
        body.phone,
        body.password,
        body.captcha_id,
        body.captcha_answer,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    return ok(payload)


@router.post("/auth/refresh")
async def refresh(body: RefreshBody, request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    await ratelimit.hit(ratelimit.REFRESH, body.refresh_token[-16:])
    async with db.begin():
        issued = await sessions.refresh(db, body.refresh_token, user_agent(request))
        tokens = issued.as_json() if issued else None
    if tokens is None:
        raise errors.SessionExpired()  # reuse detected: the revocation is committed
    return ok({"tokens": tokens})


@router.post("/auth/logout", status_code=204)
async def logout(ctx: Auth = Depends(auth), db: AsyncSession = Depends(get_db)) -> Response:
    async with db.begin():
        await sessions.revoke_family(db, ctx.session.family_id)
    return Response(status_code=204, headers=NO_STORE)


@router.get("/me")
async def me(ctx: Auth = Depends(auth), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    await ratelimit.hit(ratelimit.USER_READS, ctx.user.id)
    async with db.begin():
        user = await db.get(User, ctx.user.id, populate_existing=True)
        assert user is not None
        return ok(await users.me_json(db, user))


# --- Telegram verification -------------------------------------------------------


@router.post("/telegram/verification-session")
async def open_verification(ctx: Auth = Depends(auth), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    async with db.begin():
        user = await db.get(User, ctx.user.id, populate_existing=True)
        assert user is not None
        return ok(await verification.open_session(db, user))


@router.get("/telegram/verification-session")
async def get_verification(ctx: Auth = Depends(auth), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    await ratelimit.hit(ratelimit.USER_READS, ctx.user.id)
    async with db.begin():
        return ok(await verification.current_session(db, ctx.user))


# --- Verified users -----------------------------------------------------------------


def referral_link(code: str) -> str:
    return f"{get_settings().public_base_url}/r/{code}"


@router.get("/dashboard")
async def dashboard(ctx: Auth = Depends(verified), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    async with db.begin():
        w = await wallet.summary(db, ctx.user)
        level_1 = await referrals.direct_count(db, ctx.user.id)
        return ok(
            {
                "user": await users.me_json(db, ctx.user),
                "wallet": {
                    "total_earned_paise": w["total_earned_paise"],
                    "pending_paise": w["pending_paise"],
                    "available_paise": w["available_paise"],
                },
                "referrals": {
                    "level_1_count": level_1,
                    "level_1_pending_count": await referrals.level_one_pending_count(db, ctx.user.id),
                },
                "share": {"referral_code": ctx.user.public_id, "referral_link": referral_link(ctx.user.public_id)},
            }
        )


@router.get("/referrals/summary")
async def referral_summary(ctx: Auth = Depends(verified), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    async with db.begin():
        return ok(await referrals.summary(db, ctx.user))


@router.get("/referrals/direct")
async def referral_direct(
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, max_length=200),
    ctx: Auth = Depends(verified),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    async with db.begin():
        return ok(await referrals.direct_referrals(db, ctx.user, limit, cursor))


@router.get("/referral/share")
async def referral_share(ctx: Auth = Depends(verified), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    code = ctx.user.public_id
    return ok(
        {
            "referral_code": code,
            "referral_link": referral_link(code),
            "apk_download_url": f"{get_settings().public_base_url}/download",
        }
    )


@router.get("/wallet")
async def get_wallet(ctx: Auth = Depends(verified), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    async with db.begin():
        return ok(await wallet.summary(db, ctx.user))


@router.get("/wallet/entries")
async def wallet_entries(
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, max_length=40),
    ctx: Auth = Depends(verified),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    async with db.begin():
        return ok(await wallet.entries_page(db, ctx.user, limit, cursor))


class BankBody(BaseModel):
    account_holder_name: str = Field(max_length=100)
    account_number: str = Field(max_length=30)
    ifsc: str = Field(max_length=20)


@router.get("/bank-details")
async def get_bank(ctx: Auth = Depends(verified), db: AsyncSession = Depends(get_db)) -> JSONResponse:
    async with db.begin():
        return ok(await bank.details_json(db, ctx.user))


@router.post("/bank-details")
async def save_bank(
    body: BankBody,
    ctx: Auth = Depends(verified),
    key: str = Depends(idempotency_key),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    scope = f"bank:{ctx.user.id}"
    # The account number enters the request fingerprint only as a keyed hash,
    # so the idempotency table never holds it.
    payload = {
        "name": body.account_holder_name,
        "number": fingerprint(body.account_number, "idem").hex(),
        "ifsc": body.ifsc.upper(),
    }
    async with db.begin():
        replay = await idempotency.lookup(db, scope, key, payload)
    if replay:
        return ok(replay.body, replay.status)
    await ratelimit.hit(ratelimit.BANK_UPDATES, ctx.user.id)
    async with db.begin():
        replay = await idempotency.begin(db, scope, key, payload)
        if replay:
            return ok(replay.body, replay.status)
        result = await bank.save(db, ctx.user, body.account_holder_name, body.account_number, body.ifsc)
        await idempotency.complete(db, scope, key, 200, result)
    return ok(result)


class WithdrawalBody(BaseModel):
    amount_paise: int = Field(strict=True, gt=0, le=10**13)


@router.get("/withdrawals")
async def list_withdrawals(
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None, max_length=200),
    ctx: Auth = Depends(verified),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    async with db.begin():
        return ok(await withdrawals.history(db, ctx.user, limit, cursor))


@router.post("/withdrawals")
async def create_withdrawal(
    body: WithdrawalBody,
    ctx: Auth = Depends(verified),
    key: str = Depends(idempotency_key),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    scope = f"withdrawal:{ctx.user.id}"
    payload = {"amount_paise": body.amount_paise}
    async with db.begin():
        replay = await idempotency.lookup(db, scope, key, payload)
    if replay:
        return ok(replay.body, replay.status)
    await ratelimit.hit(ratelimit.WITHDRAWALS, ctx.user.id)
    async with db.begin():
        replay = await idempotency.begin(db, scope, key, payload)
        if replay:
            return ok(replay.body, replay.status)
        result = await withdrawals.create(db, ctx.user, body.amount_paise)
        await idempotency.complete(db, scope, key, 201, result)
    return ok(result, 201)
