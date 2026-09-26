"""Admin panel pages. Every change is audit-logged.

The admin can change campaign dates, the level-1 reward amount, bots,
channels, settings and payouts. There is deliberately no control for
the membership count or for paying levels 2–4.
"""

from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors, ids, timeutil
from app.admin.auth import COOKIE, AdminContext, AdminLoginRequired, CsrfFailed, current_admin, sign_in
from app.api.deps import client_ip, reset_gate_cache
from app.config import get_settings
from app.db import get_db
from app.models import (
    AdminSession,
    AppSettings,
    BankAccount,
    LedgerAccount,
    PayoutBatch,
    ReferralEdge,
    ReferralReward,
    ReferralSnapshot,
    RequiredChannel,
    RiskFlag,
    TelegramBot,
    User,
    WithdrawalRequest,
)
from app.models.ops import AuditLog
from app.money import format_inr
from app.phone import mask_phone, normalize_indian_mobile
from app.security import crypto, ratelimit
from app.services import audit, bots, campaign, jobs, ledger, referrals, sessions, withdrawals
from app.services import bank as bank_service
from app.telegram.client import TelegramError

router = APIRouter(prefix="/admin", include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["inr"] = format_inr
templates.env.filters["ist"] = lambda at: at.astimezone(timeutil.IST).strftime("%d %b %Y, %H:%M IST") if at else "—"
templates.env.filters["mask"] = mask_phone

DONE_MESSAGES = {
    "saved": "Saved.",
    "funded": "Funding recorded in the ledger.",
    "bot_added": "Bot added and its webhook registered.",
    "bot_updated": "Bot updated.",
    "channel_added": "Channel added.",
    "channel_updated": "Channel updated.",
    "batch": "Batch created. Export it, pay it at the bank, then mark each withdrawal.",
    "no_requests": "There are no requested withdrawals to batch.",
    "paid": "Marked as paid.",
    "failed": "Marked as failed; the money is back in the user's available balance.",
    "suspended": "User suspended and signed out everywhere.",
    "unsuspended": "User restored.",
    "resolved": "Flag resolved.",
}


def page(request: Request, name: str, ctx: AdminContext | None, **data) -> HTMLResponse:
    done = request.query_params.get("done")
    return templates.TemplateResponse(
        request,
        name,
        {
            "admin": ctx.admin if ctx else None,
            "csrf": ctx.session.csrf_token if ctx else "",
            "notice": DONE_MESSAGES.get(done or ""),
            **data,
        },
        headers={"Cache-Control": "no-store"},
    )


def back(path: str, done: str) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    return RedirectResponse(f"/admin{path}{separator}done={done}", status_code=303)


def _ist_input(at: datetime | None) -> str:
    return at.astimezone(timeutil.IST).strftime("%Y-%m-%dT%H:%M") if at else ""


def _parse_ist(value: str) -> datetime:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%dT%H:%M").replace(tzinfo=timeutil.IST)
    except ValueError as exc:
        raise errors.ValidationFailed(f"“{value}” isn't a valid date and time.") from exc


def _rupees(value: str, label: str) -> int:
    cleaned = value.replace(",", "").strip()
    if not cleaned.isdigit():
        raise errors.ValidationFailed(f"{label} must be a whole number of rupees.")
    return int(cleaned) * 100


def _int(value: str, label: str) -> int:
    cleaned = value.replace(",", "").strip()
    if not cleaned.isdigit():
        raise errors.ValidationFailed(f"{label} must be a whole number.")
    return int(cleaned)


# --- Sign in ------------------------------------------------------------------


@router.get("/login")
async def login_form(request: Request) -> HTMLResponse:
    return page(request, "login.html", None, error=None)


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(max_length=64),
    password: str = Form(max_length=200),
    code: str = Form(max_length=10),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await ratelimit.hit(ratelimit.ADMIN_LOGIN_IP, client_ip(request))
    except errors.RateLimited:
        return page(request, "login.html", None, error="Too many attempts. Wait 15 minutes.")
    async with db.begin():
        result = await sign_in(db, username, password, code)
        if result is not None:
            await audit.record(db, f"admin:{username}", "admin.signed_in", ip=client_ip(request))
        else:
            await audit.record(
                db, "anonymous", "admin.sign_in_failed", details={"username": username[:64]}, ip=client_ip(request)
            )
    if result is None:
        return page(request, "login.html", None, error="Those details didn't work.")
    _, token = result
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=get_settings().is_production_like,
        samesite="strict",
        max_age=get_settings().admin_session_hours * 3600,
        path="/admin",
    )
    return response


@router.post("/logout")
async def logout(ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)) -> Response:
    async with db.begin():
        await db.execute(update(AdminSession).where(AdminSession.id == ctx.session.id).values(revoked_at=timeutil.now()))
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(COOKIE, path="/admin")
    return response


# --- Dashboard ------------------------------------------------------------------


@router.get("")
async def dashboard(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        c = await campaign.current_campaign(db)
        g = await campaign.gates(db, c)
        at = timeutil.now()
        pending = (
            await db.execute(
                select(func.count()).select_from(User).where(User.status == "PENDING_VERIFICATION", User.pending_expires_at > at)
            )
        ).scalar_one()
        suspended = (await db.execute(select(func.count()).select_from(User).where(User.status == "SUSPENDED"))).scalar_one()
        funded = await campaign.funded_total(db)
        pool = await campaign.pool_balance(db)
        by_status = dict(
            (await db.execute(select(WithdrawalRequest.status, func.count()).group_by(WithdrawalRequest.status))).all()
        )
        bot_rows = (await db.execute(select(TelegramBot).order_by(TelegramBot.role, TelegramBot.id))).scalars().all()
        open_flags = (
            await db.execute(select(func.count()).select_from(RiskFlag).where(RiskFlag.resolved_at.is_(None)))
        ).scalar_one()
        queue = await jobs.queue_stats(db)
        return page(
            request,
            "dashboard.html",
            ctx,
            campaign=c,
            gates=g,
            verified=await campaign.verified_count(db),
            pending=pending,
            suspended=suspended,
            funded=funded,
            pool=pool,
            rewarded=funded - pool,
            withdrawals=by_status,
            bots=bot_rows,
            open_flags=open_flags,
            queue=queue,
        )


@router.get("/reports")
async def reports_page(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Every headline number in one place: members, rewards, money, withdrawals,
    the referral spread, and recent sign-ups. Read-only aggregates."""
    async with db.begin():
        c = await campaign.current_campaign(db)
        at = timeutil.now()

        users_by_status = dict((await db.execute(select(User.status, func.count()).group_by(User.status))).all())
        total_users = sum(users_by_status.values())
        verified_count = await campaign.verified_count(db)

        reward_count, reward_total = (
            await db.execute(
                select(func.count(), func.coalesce(func.sum(ReferralReward.amount_paise), 0)).where(
                    ReferralReward.status == "CREDITED"
                )
            )
        ).one()

        async def account_sum(kind: str) -> int:
            return int(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(LedgerAccount.balance_paise), 0)).where(LedgerAccount.kind == kind)
                    )
                ).scalar_one()
            )

        pending_money = await account_sum("USER_PENDING")
        available_money = await account_sum("USER_AVAILABLE")
        funded = await campaign.funded_total(db)
        pool = await campaign.pool_balance(db)

        withdrawals_by_status = {
            status: (int(count), int(total))
            for status, count, total in (
                await db.execute(
                    select(
                        WithdrawalRequest.status,
                        func.count(),
                        func.coalesce(func.sum(WithdrawalRequest.amount_paise), 0),
                    ).group_by(WithdrawalRequest.status)
                )
            ).all()
        }

        edges_by_level = dict(
            (
                await db.execute(
                    select(ReferralEdge.level, func.count())
                    .where(ReferralEdge.status == "QUALIFIED")
                    .group_by(ReferralEdge.level)
                )
            ).all()
        )

        since = at - timedelta(days=7)
        signups_7d = (await db.execute(select(func.count()).select_from(User).where(User.created_at >= since))).scalar_one()
        verified_7d = (await db.execute(select(func.count()).select_from(User).where(User.verified_at >= since))).scalar_one()

        direct_qualified = (
            (ReferralEdge.ancestor_id == User.id) & (ReferralEdge.level == 1) & (ReferralEdge.status == "QUALIFIED")
        )
        top_referrers = (
            await db.execute(
                select(User.public_id, func.count(ReferralEdge.descendant_id).label("n"))
                .join(ReferralEdge, direct_qualified)
                .group_by(User.public_id)
                .order_by(func.count(ReferralEdge.descendant_id).desc())
                .limit(10)
            )
        ).all()

        return page(
            request,
            "reports.html",
            ctx,
            c=c,
            total_users=total_users,
            users_by_status=users_by_status,
            verified_count=verified_count,
            reward_count=int(reward_count),
            reward_total=int(reward_total),
            reward_each=c.level_1_reward_paise,
            pending_money=pending_money,
            available_money=available_money,
            funded=funded,
            pool=pool,
            spent=funded - pool,
            withdrawals_by_status=withdrawals_by_status,
            edges_by_level=edges_by_level,
            levels=campaign.reward_per_level(c),
            signups_7d=signups_7d,
            verified_7d=verified_7d,
            top_referrers=top_referrers,
        )


# --- Campaign ---------------------------------------------------------------------


@router.get("/campaign")
async def campaign_form(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        c = await campaign.current_campaign(db)
        return page(
            request,
            "campaign.html",
            ctx,
            c=c,
            dates={
                "starts_at": _ist_input(c.starts_at),
                "ends_at": _ist_input(c.ends_at),
                "brand_reveal_at": _ist_input(c.brand_reveal_at),
                "launch_at": _ist_input(c.launch_at),
                "payout_opens_at": _ist_input(c.payout_opens_at),
            },
            funded=await campaign.funded_total(db),
            pool=await campaign.pool_balance(db),
            nonce=secrets.token_urlsafe(12),
            error=None,
        )


@router.post("/campaign")
async def campaign_save(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    form = await request.form()
    try:
        values = {
            "name": str(form.get("name", "")).strip()[:100] or "Future Fashion launch",
            "starts_at": _parse_ist(str(form.get("starts_at", ""))),
            "ends_at": _parse_ist(str(form.get("ends_at", ""))),
            "brand_reveal_at": _parse_ist(str(form.get("brand_reveal_at", ""))),
            "launch_at": _parse_ist(str(form.get("launch_at", ""))),
            "payout_opens_at": _parse_ist(str(form.get("payout_opens_at", ""))),
            "brand_name": str(form.get("brand_name", "")).strip()[:100] or None,
            "level_1_reward_paise": _rupees(str(form.get("level_1_reward_rupees", "")), "Level 1 reward"),
            "min_withdrawal_paise": _rupees(str(form.get("min_withdrawal_rupees", "")), "Minimum withdrawal"),
            "capacity": _int(str(form.get("capacity", "")), "Capacity"),
            "signups_open": form.get("signups_open") == "on",
            "paused": form.get("paused") == "on",
            "show_promo_allocation": form.get("show_promo_allocation") == "on",
        }
        if values["starts_at"] >= values["ends_at"]:
            raise errors.ValidationFailed("The campaign must start before it ends.")
        if values["level_1_reward_paise"] <= 0 or values["min_withdrawal_paise"] <= 0 or values["capacity"] <= 0:
            raise errors.ValidationFailed("Amounts and capacity must be above zero.")
    except errors.ValidationFailed as exc:
        async with db.begin():
            c = await campaign.current_campaign(db)
            date_fields = ("starts_at", "ends_at", "brand_reveal_at", "launch_at", "payout_opens_at")
            return page(
                request,
                "campaign.html",
                ctx,
                c=c,
                dates={k: str(form.get(k, "")) for k in date_fields},
                funded=await campaign.funded_total(db),
                pool=await campaign.pool_balance(db),
                nonce=secrets.token_urlsafe(12),
                error=exc.message,
            )
    async with db.begin():
        c = await campaign.current_campaign(db)
        before = {k: getattr(c, k) for k in values}
        for key, value in values.items():
            setattr(c, key, value)
        c.updated_at = timeutil.now()
        changed = {k: [str(before[k]), str(v)] for k, v in values.items() if before[k] != v}
        await audit.record(db, ctx.actor, "campaign.updated", f"campaign:{c.id}", {"changed": changed}, ip=client_ip(request))
    return back("/campaign", "saved")


@router.post("/campaign/fund")
async def campaign_fund(
    request: Request,
    amount_rupees: str = Form(max_length=20),
    memo: str = Form(default="", max_length=200),
    nonce: str = Form(max_length=40),
    ctx: AdminContext = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    amount = _rupees(amount_rupees, "Amount")
    if amount <= 0:
        raise errors.ValidationFailed("Amount must be above zero.")
    async with db.begin():
        # The form nonce makes a double-submitted form record the money once.
        txn = await ledger.transfer(
            db,
            kind="FUNDING",
            idempotency_key=f"funding:{nonce}",
            source=await ledger.system_account(db, "COMPANY_FUNDING"),
            destination=await ledger.system_account(db, "PROMO_POOL"),
            amount_paise=amount,
            created_by=ctx.actor,
            memo=memo.strip() or None,
        )
        if txn is not None:
            await audit.record(
                db,
                ctx.actor,
                "pool.funded",
                f"txn:{txn.public_id}",
                {"amount_paise": amount, "memo": memo[:200]},
                ip=client_ip(request),
            )
    return back("/campaign", "funded")


# --- Settings ----------------------------------------------------------------------

SETTING_TEXT_FIELDS = (
    "company_name",
    "company_legal_name",
    "company_address",
    "support_email",
    "support_url",
    "terms_url",
    "privacy_url",
    "min_app_version",
    "apk_download_url",
    "maintenance_message",
    "announcement_text",
)
SETTING_BOOL_FIELDS = (
    "maintenance_active",
    "ads_banner_enabled",
    "ads_interstitial_enabled",
    "ads_rewarded_enabled",
    "accept_pending_join_requests",
)


@router.get("/settings")
async def settings_form(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        s = await campaign.app_settings(db)
        return page(request, "settings.html", ctx, s=s, maintenance_until=_ist_input(s.maintenance_until), error=None)


@router.post("/settings")
async def settings_save(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    form = await request.form()
    async with db.begin():
        s = (await db.execute(select(AppSettings).where(AppSettings.id == 1).with_for_update())).scalar_one()
        try:
            changed: dict[str, list[str]] = {}
            new: dict[str, object] = {}
            for key in SETTING_TEXT_FIELDS:
                value = str(form.get(key, "")).strip()
                new[key] = value or (None if key not in ("company_name", "min_app_version") else getattr(s, key))
            for key in SETTING_BOOL_FIELDS:
                new[key] = form.get(key) == "on"
            tone = str(form.get("announcement_tone", "info"))
            new["announcement_tone"] = tone if tone in ("info", "success", "warning") else "info"
            until = str(form.get("maintenance_until", "")).strip()
            new["maintenance_until"] = _parse_ist(until) if until else None
            new["ads_min_interstitial_interval_seconds"] = max(
                60, _int(str(form.get("ads_min_interstitial_interval_seconds", "300")), "Interstitial interval")
            )
            new["verification_session_minutes"] = min(
                1440, max(5, _int(str(form.get("verification_session_minutes", "30")), "Session minutes"))
            )
            new["max_contact_mismatches"] = min(10, max(1, _int(str(form.get("max_contact_mismatches", "3")), "Mismatch limit")))
            if new["min_app_version"] and not all(p.isdigit() for p in str(new["min_app_version"]).split(".")):
                raise errors.ValidationFailed("Minimum app version looks like 1.0.0.")
        except errors.ValidationFailed as exc:
            return page(request, "settings.html", ctx, s=s, maintenance_until=_ist_input(s.maintenance_until), error=exc.message)
        for key, value in new.items():
            if getattr(s, key) != value:
                changed[key] = [str(getattr(s, key)), str(value)]
                setattr(s, key, value)
        s.updated_at = timeutil.now()
        await audit.record(db, ctx.actor, "settings.updated", "settings", {"changed": changed}, ip=client_ip(request))
    reset_gate_cache()
    return back("/settings", "saved")


# --- Bots and channels --------------------------------------------------------------


@router.get("/bots")
async def bots_page(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        rows = (await db.execute(select(TelegramBot).order_by(TelegramBot.role, TelegramBot.id))).scalars().all()
        return page(request, "bots.html", ctx, bots=rows, error=None, public_base_url=get_settings().public_base_url)


@router.post("/bots")
async def bots_add(
    request: Request,
    token: str = Form(max_length=100),
    role: str = Form(max_length=10),
    weight: str = Form(default="1", max_length=3),
    ctx: AdminContext = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if role not in ("VERIFIER", "WATCHER"):
        raise errors.ValidationFailed("Choose a role.")
    try:
        async with db.begin():
            bot = await bots.register(db, token.strip(), role, max(1, min(100, _int(weight, "Weight"))))
            await audit.record(db, ctx.actor, "bot.registered", f"bot:{bot.username}", {"role": role}, ip=client_ip(request))
    except TelegramError as exc:
        async with db.begin():
            rows = (await db.execute(select(TelegramBot).order_by(TelegramBot.role, TelegramBot.id))).scalars().all()
            return page(
                request,
                "bots.html",
                ctx,
                bots=rows,
                public_base_url=get_settings().public_base_url,
                error=f"Telegram rejected this bot: {exc}",
            )
    return back("/bots", "bot_added")


@router.post("/bots/{bot_id}/toggle")
async def bots_toggle(
    bot_id: int, request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    async with db.begin():
        bot = await db.get(TelegramBot, bot_id, with_for_update=True)
        if bot is None:
            raise errors.NotFound()
        bot.enabled = not bot.enabled
        if bot.enabled:
            bots.mark_ok(bot)
        await audit.record(db, ctx.actor, "bot.toggled", f"bot:{bot.username}", {"enabled": bot.enabled}, ip=client_ip(request))
    return back("/bots", "bot_updated")


@router.get("/channels")
async def channels_page(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        rows = (
            (await db.execute(select(RequiredChannel).order_by(RequiredChannel.sort_order, RequiredChannel.id))).scalars().all()
        )
        s = await campaign.app_settings(db)
        return page(request, "channels.html", ctx, channels=rows, accept_pending=s.accept_pending_join_requests, error=None)


@router.post("/channels")
async def channels_add(
    request: Request,
    title: str = Form(max_length=100),
    chat_id: str = Form(max_length=20),
    invite_link: str = Form(default="", max_length=200),
    sort_order: str = Form(default="0", max_length=4),
    ctx: AdminContext = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        numeric_id = int(chat_id.strip())
    except ValueError as exc:
        raise errors.ValidationFailed("Chat id is a number like -1001234567890.") from exc
    async with db.begin():
        link = invite_link.strip()
        if not link:
            watcher = await bots.watcher(db)
            if watcher is None:
                raise errors.ValidationFailed("Add a watcher bot first, or paste a join-request invite link.")
            try:
                created = await bots.call(
                    watcher,
                    "createChatInviteLink",
                    chat_id=numeric_id,
                    name="Future Fashion verification",
                    creates_join_request=True,
                )
            except TelegramError as exc:
                raise errors.ValidationFailed(f"Telegram couldn't create the link: {exc}") from exc
            link = created["invite_link"]
        if not link.startswith("https://t.me/"):
            raise errors.ValidationFailed("Invite links start with https://t.me/.")
        db.add(
            RequiredChannel(
                title=title.strip(), chat_id=numeric_id, invite_link=link, sort_order=_int(sort_order or "0", "Order")
            )
        )
        await audit.record(
            db, ctx.actor, "channel.added", f"channel:{numeric_id}", {"title": title.strip()}, ip=client_ip(request)
        )
    return back("/channels", "channel_added")


@router.post("/channels/{channel_id}/toggle")
async def channels_toggle(
    channel_id: int, request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    async with db.begin():
        channel = await db.get(RequiredChannel, channel_id, with_for_update=True)
        if channel is None:
            raise errors.NotFound()
        channel.active = not channel.active
        await audit.record(
            db, ctx.actor, "channel.toggled", f"channel:{channel.chat_id}", {"active": channel.active}, ip=client_ip(request)
        )
    return back("/channels", "channel_updated")


# --- Users ------------------------------------------------------------------------------


@router.get("/users")
async def users_page(
    request: Request, q: str = "", ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    q = q.strip()[:20]
    if q:
        async with db.begin():
            phone = normalize_indian_mobile(q)
            code = ids.normalize_code(q)
            user = None
            if phone:
                user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
            elif code:
                user = (await db.execute(select(User).where(User.public_id == code))).scalar_one_or_none()
        if user is not None:
            return RedirectResponse(f"/admin/users/{user.public_id}", status_code=303)
        return page(request, "users.html", ctx, q=q, not_found=True)
    return page(request, "users.html", ctx, q="", not_found=False)


@router.get("/users/{public_id}")
async def user_detail(
    public_id: str, request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        user = (await db.execute(select(User).where(User.public_id == public_id[:8]))).scalar_one_or_none()
        if user is None:
            raise errors.NotFound()
        referrer = await db.get(User, user.referrer_id) if user.referrer_id else None
        snapshot = await db.get(ReferralSnapshot, user.id)
        bank = await db.get(BankAccount, user.id)
        w = list(
            (
                await db.execute(
                    select(WithdrawalRequest)
                    .where(WithdrawalRequest.user_id == user.id)
                    .order_by(WithdrawalRequest.id.desc())
                    .limit(20)
                )
            ).scalars()
        )
        flags = list(
            (await db.execute(select(RiskFlag).where(RiskFlag.user_id == user.id).order_by(RiskFlag.id.desc()))).scalars()
        )
        await audit.record(db, ctx.actor, "user.viewed", f"user:{user.public_id}", ip=client_ip(request))
        return page(
            request,
            "user.html",
            ctx,
            user=user,
            referrer=referrer,
            snapshot=snapshot,
            direct_verified=await referrals.direct_count(db, user.id),
            direct_pending=await referrals.level_one_pending_count(db, user.id),
            pending_balance=await ledger.balance(db, "USER_PENDING", user.id),
            available_balance=await ledger.balance(db, "USER_AVAILABLE", user.id),
            bank=bank,
            bank_masked=bank_service.masked(bank.account_number_last4) if bank else None,
            withdrawals=w,
            flags=flags,
        )


@router.post("/users/{public_id}/suspend")
async def user_suspend(
    public_id: str, request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    async with db.begin():
        user = (await db.execute(select(User).where(User.public_id == public_id[:8]).with_for_update())).scalar_one_or_none()
        if user is None:
            raise errors.NotFound()
        user.status, user.suspended_at, user.updated_at = "SUSPENDED", timeutil.now(), timeutil.now()
        await sessions.revoke_all_for_user(db, user.id)
        await audit.record(db, ctx.actor, "user.suspended", f"user:{user.public_id}", ip=client_ip(request))
    return back(f"/users/{public_id}", "suspended")


@router.post("/users/{public_id}/unsuspend")
async def user_unsuspend(
    public_id: str, request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    async with db.begin():
        user = (await db.execute(select(User).where(User.public_id == public_id[:8]).with_for_update())).scalar_one_or_none()
        if user is None:
            raise errors.NotFound()
        if user.status == "SUSPENDED":
            user.status = "ACTIVE" if user.verified_at else "PENDING_VERIFICATION"
            user.suspended_at, user.updated_at = None, timeutil.now()
            await audit.record(db, ctx.actor, "user.unsuspended", f"user:{user.public_id}", ip=client_ip(request))
    return back(f"/users/{public_id}", "unsuspended")


# --- Withdrawals ------------------------------------------------------------------------


@router.get("/withdrawals")
async def withdrawals_page(
    request: Request,
    status: str = "REQUESTED",
    ctx: AdminContext = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    status = status if status in ("REQUESTED", "PROCESSING", "PAID", "FAILED") else "REQUESTED"
    async with db.begin():
        rows = (
            await db.execute(
                select(WithdrawalRequest, User.public_id)
                .join(User, User.id == WithdrawalRequest.user_id)
                .where(WithdrawalRequest.status == status)
                .order_by(WithdrawalRequest.requested_at)
                .limit(500)
            )
        ).all()
        flagged = set(
            (
                await db.execute(
                    select(RiskFlag.user_id).where(
                        RiskFlag.resolved_at.is_(None), RiskFlag.user_id.in_([w.user_id for w, _ in rows] or [0])
                    )
                )
            ).scalars()
        )
        batches = (await db.execute(select(PayoutBatch).order_by(PayoutBatch.id.desc()).limit(20))).scalars().all()
        return page(request, "withdrawals.html", ctx, rows=rows, status=status, flagged=flagged, batches=batches)


@router.post("/withdrawals/batch")
async def withdrawals_batch(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    async with db.begin():
        batch = await withdrawals.create_batch(db, ctx.actor)
    if batch is None:
        return back("/withdrawals", "no_requests")
    return back("/withdrawals?status=PROCESSING", "batch")


@router.get("/batches/{batch_id}.csv")
async def batch_export(
    batch_id: int, request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    """The bank upload file. It contains full account numbers, so every
    download is audit-logged."""
    async with db.begin():
        rows = (
            (
                await db.execute(
                    select(WithdrawalRequest).where(WithdrawalRequest.batch_id == batch_id).order_by(WithdrawalRequest.id)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            raise errors.NotFound()
        await audit.record(db, ctx.actor, "payout.exported", f"batch:{batch_id}", {"count": len(rows)}, ip=client_ip(request))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["withdrawal_id", "account_holder_name", "account_number", "ifsc", "amount_inr", "requested_at_ist"])
    for w in rows:
        rupees, paise = divmod(w.amount_paise, 100)
        writer.writerow(
            [
                f"WD-{w.public_id}",
                w.account_holder_name,
                crypto.decrypt(w.account_number_ciphertext, bank_service.purpose(w.user_id)),
                w.ifsc,
                f"{rupees}.{paise:02d}",
                w.requested_at.astimezone(timeutil.IST).strftime("%Y-%m-%d %H:%M"),
            ]
        )
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="payout-batch-{batch_id}.csv"', "Cache-Control": "no-store"},
    )


@router.post("/withdrawals/{public_id}/paid")
async def withdrawal_paid(
    public_id: str,
    request: Request,
    bank_reference: str = Form(max_length=64),
    ctx: AdminContext = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    async with db.begin():
        await withdrawals.mark_paid(db, ctx.actor, public_id.removeprefix("WD-")[:10], bank_reference)
    return back("/withdrawals?status=PROCESSING", "paid")


@router.post("/withdrawals/{public_id}/failed")
async def withdrawal_failed(
    public_id: str,
    request: Request,
    reason: str = Form(default="", max_length=200),
    ctx: AdminContext = Depends(current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    async with db.begin():
        await withdrawals.mark_failed(db, ctx.actor, public_id.removeprefix("WD-")[:10], reason)
    return back("/withdrawals?status=PROCESSING", "failed")


# --- Flags, audit, ledger ---------------------------------------------------------------


@router.get("/flags")
async def flags_page(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        rows = (
            await db.execute(
                select(RiskFlag, User.public_id)
                .join(User, User.id == RiskFlag.user_id)
                .where(RiskFlag.resolved_at.is_(None))
                .order_by(RiskFlag.id.desc())
                .limit(200)
            )
        ).all()
        return page(request, "flags.html", ctx, rows=rows)


@router.post("/flags/{flag_id}/resolve")
async def flags_resolve(
    flag_id: int, request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> Response:
    async with db.begin():
        flag = await db.get(RiskFlag, flag_id, with_for_update=True)
        if flag is None:
            raise errors.NotFound()
        flag.resolved_at, flag.resolved_by = timeutil.now(), ctx.actor
        await audit.record(db, ctx.actor, "flag.resolved", f"flag:{flag.id}", {"kind": flag.kind}, ip=client_ip(request))
    return back("/flags", "resolved")


@router.get("/audit")
async def audit_page(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    async with db.begin():
        rows = (await db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(200))).scalars().all()
        return page(request, "audit.html", ctx, rows=rows)


@router.get("/ledger")
async def ledger_page(
    request: Request, ctx: AdminContext = Depends(current_admin), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    """Reconciliation: balances must sum to zero and match their entries."""
    async with db.begin():
        total = (await db.execute(select(func.coalesce(func.sum(LedgerAccount.balance_paise), 0)))).scalar_one()
        mismatched = (
            await db.execute(
                text(
                    """
                    SELECT a.id, a.kind, a.balance_paise, COALESCE(SUM(e.amount_paise), 0)::bigint AS entries
                    FROM ledger_accounts a LEFT JOIN ledger_entries e ON e.account_id = a.id
                    GROUP BY a.id HAVING a.balance_paise <> COALESCE(SUM(e.amount_paise), 0)
                    LIMIT 50
                    """
                )
            )
        ).all()
        system = (
            (await db.execute(select(LedgerAccount).where(LedgerAccount.user_id.is_(None)).order_by(LedgerAccount.id)))
            .scalars()
            .all()
        )
        await audit.record(db, ctx.actor, "ledger.checked", details={"ok": total == 0 and not mismatched})
        return page(request, "ledger.html", ctx, total=int(total), mismatched=mismatched, system=system)


def install(app: FastAPI) -> None:
    app.include_router(router)

    @app.exception_handler(AdminLoginRequired)
    async def _login_required(request: Request, exc: AdminLoginRequired) -> Response:
        return RedirectResponse("/admin/login", status_code=303)

    @app.exception_handler(CsrfFailed)
    async def _csrf(request: Request, exc: CsrfFailed) -> Response:
        return Response("This form expired. Go back, reload the page and try again.", status_code=403, media_type="text/plain")
