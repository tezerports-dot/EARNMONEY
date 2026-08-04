"""The admin panel.

Everything an operator needs at runtime lives here: adding and removing bot
tokens (which starts and stops polling immediately), registering chats and
pairing them, inspecting users and activity, approving withdrawals, and
exporting the bank file.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

from app import db, export
from app.bots.manager import manager
from app.bots.services import daily_bank_prompt
from app.bots.telegram_utils import ban_everywhere, call_api, notify_admins, unban_everywhere
from app.config import settings
from app.earnings import month_totals, report_for, status_for
from app.ids import normalise_uid
from app.roles import ROLES
from app.timeutil import current_month
from app.web import auth
from app.web.templating import render

router = APIRouter(prefix="/admin")

FLASH_COOKIE = "admin_flash"


def _redirect(path: str, message: str = "") -> RedirectResponse:
    response = RedirectResponse(url=path, status_code=303)
    if message:
        # Cookie values must be latin-1 encodable, and these messages carry
        # em dashes and ₹ signs, so percent-encode on the way out.
        response.set_cookie(
            FLASH_COOKIE, quote(message[:400], safe=""), max_age=20, path="/"
        )
    return response


def _flash_of(request: Request) -> str:
    raw = request.cookies.get(FLASH_COOKIE, "")
    return unquote(raw) if raw else ""


def _safe_next(target: str) -> str:
    """Only ever redirect back inside the admin panel.

    ``next`` comes from the query string, so without this a crafted login link
    could bounce an authenticated admin to an attacker's page.
    """
    candidate = (target or "").strip()
    if not candidate.startswith("/admin") or candidate.startswith("//"):
        return "/admin"
    return candidate


def _page(request: Request, name: str, **context):
    context.setdefault("flash", _flash_of(request))
    context.setdefault("roles", ROLES)
    # Drives the nav highlight. Set from Python rather than a template-level
    # {% set %}, which does not reliably reach blocks defined in the parent.
    context.setdefault("page", Path(name).stem)
    response = render(request, name, **context)
    if request.cookies.get(FLASH_COOKIE):
        response.delete_cookie(FLASH_COOKIE, path="/")
    return response


# --------------------------------------------------------------------------- #
# login
# --------------------------------------------------------------------------- #

@router.get("/login")
async def login_form(request: Request, next: str = "/admin"):
    if auth.is_authenticated(request):
        return RedirectResponse(url=_safe_next(next), status_code=303)
    return render(request, "admin/login.html", error="", next=_safe_next(next))


@router.post("/login")
async def login_submit(
    request: Request, token: str = Form(...), next: str = Form("/admin")
):
    wait = auth.is_locked_out(request)
    if wait:
        return render(
            request,
            "admin/login.html",
            error=f"Too many failed attempts. Try again in {wait} seconds.",
            next=_safe_next(next),
        )
    if not auth.check_password(token):
        auth.record_failure(request)
        db.log_event("admin_login_failed", None, auth.client_key(request))
        return render(
            request, "admin/login.html", error="Wrong token.", next=_safe_next(next)
        )

    auth.clear_failures(request)
    db.log_event("admin_login", None, auth.client_key(request))
    response = RedirectResponse(url=_safe_next(next), status_code=303)
    auth.set_session(response)
    return response


@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/admin/login", status_code=303)
    auth.clear_session(response)
    return response


# --------------------------------------------------------------------------- #
# dashboard
# --------------------------------------------------------------------------- #

@router.get("")
@router.get("/")
async def dashboard(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    month = current_month()
    return _page(
        request,
        "admin/dashboard.html",
        stats=db.stats(),
        totals=month_totals(month),
        month=month,
        bots=manager.describe(),
        events=db.recent_events(15),
        pending=db.list_withdrawals(status="pending"),
    )


# --------------------------------------------------------------------------- #
# bots
# --------------------------------------------------------------------------- #

@router.get("/bots")
async def bots_page(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    return _page(request, "admin/bots.html", bots=manager.describe())


@router.post("/bots/add")
async def bots_add(
    request: Request,
    token: str = Form(...),
    name: str = Form(""),
    role: str = Form("main"),
    start_now: str = Form(""),
):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    token = token.strip()
    if ":" not in token:
        return _redirect("/admin/bots", "That does not look like a bot token.")
    if role not in ROLES:
        role = "main"
    if db.get_bot_by_token(token) is not None:
        return _redirect("/admin/bots", "That token is already registered.")

    bot_id = db.add_bot(
        token=token,
        name=name.strip() or f"{role} bot",
        role=role,
        status="stopped",
    )
    db.log_event("bot_added", None, f"bot={bot_id} role={role}")
    if start_now:
        result = await manager.start_bot(bot_id)
        return _redirect("/admin/bots", f"Bot added — {result}.")
    return _redirect("/admin/bots", "Bot added (stopped).")


@router.post("/bots/{bot_id}/start")
async def bots_start(request: Request, bot_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    return _redirect("/admin/bots", await manager.start_bot(bot_id))


@router.post("/bots/{bot_id}/stop")
async def bots_stop(request: Request, bot_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    await manager.stop_bot(bot_id)
    return _redirect("/admin/bots", "Bot stopped.")


@router.post("/bots/{bot_id}/edit")
async def bots_edit(
    request: Request, bot_id: int, name: str = Form(""), role: str = Form("main")
):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    if role not in ROLES:
        role = "main"
    db.update_bot(bot_id, name=name.strip() or "bot", role=role)
    message = "Bot updated."
    if manager.is_running(bot_id):
        message = f"Bot updated — {await manager.restart_bot(bot_id)}."
    return _redirect("/admin/bots", message)


@router.post("/bots/{bot_id}/delete")
async def bots_delete(request: Request, bot_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    await manager.stop_bot(bot_id, mark_stopped=False)
    db.delete_bot(bot_id)
    db.log_event("bot_removed", None, f"bot={bot_id}")
    return _redirect("/admin/bots", "Bot removed and its polling stopped.")


# --------------------------------------------------------------------------- #
# chats & pairs
# --------------------------------------------------------------------------- #

@router.get("/chats")
async def chats_page(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    return _page(
        request,
        "admin/chats.html",
        chats=db.list_chats(),
        pairs=db.list_pairs(),
        bots=db.list_bots(),
        loads={p['pair_id']: p['member_count'] for p in db.list_pairs()},
    )


@router.post("/chats/add")
async def chats_add(
    request: Request,
    chat_ref: str = Form(...),
    bot_id: int = Form(...),
    chat_type: str = Form("group"),
):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)

    bot = manager.get_bot(bot_id)
    if bot is None:
        return _redirect("/admin/chats", "Start that bot first — it must be running to join a chat.")

    ref: str | int = chat_ref.strip()
    if isinstance(ref, str) and (ref.lstrip("-").isdigit()):
        ref = int(ref)
    elif isinstance(ref, str) and not ref.startswith("@"):
        ref = "@" + ref

    chat = await call_api(bot.get_chat, chat_id=ref)
    if chat is None:
        return _redirect(
            "/admin/chats",
            "Could not read that chat. Add the bot to it as an administrator first, "
            "then try again (for private chats use the numeric id).",
        )

    kind = "channel" if chat.type == "channel" else "group"
    if kind != chat_type:
        chat_type = kind
    db.add_chat(chat_id=chat.id, bot_id=bot_id, chat_type=chat_type, title=chat.title)
    db.log_event("chat_added", None, f"bot={bot_id} chat={chat.id} type={chat_type}")
    return _redirect("/admin/chats", f"Registered {chat.title or chat.id} as a {chat_type}.")


@router.post("/chats/{chat_id}/delete")
async def chats_delete(request: Request, chat_id: int, bot_id: int = Form(...)):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    db.delete_chat(chat_id, bot_id)
    return _redirect("/admin/chats", "Chat unregistered.")


@router.post("/pairs/add")
async def pairs_add(
    request: Request,
    title: str = Form(""),
    group_chat_id: str = Form(""),
    channel_chat_id: str = Form(""),
    capacity: int = Form(0),
):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    group_id = int(group_chat_id) if group_chat_id.strip() else None
    channel_id = int(channel_chat_id) if channel_chat_id.strip() else None
    if group_id is None or channel_id is None:
        return _redirect("/admin/chats", "A pair needs exactly one group and one channel.")
    pair_id = db.create_pair(title.strip() or "Pair", group_id, channel_id, capacity)
    if len(db.list_pairs()) == 1:
        db.set_default_pair(pair_id)
        db.set_primary_pair(pair_id)
    return _redirect("/admin/chats", "Pair created.")


@router.post("/pairs/{pair_id}/edit")
async def pairs_edit(
    request: Request,
    pair_id: int,
    title: str = Form(""),
    group_chat_id: str = Form(""),
    channel_chat_id: str = Form(""),
    capacity: int = Form(0),
    closed: str = Form(""),
):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    db.update_pair(
        pair_id,
        title=title.strip() or None,
        group_chat_id=int(group_chat_id) if group_chat_id.strip() else None,
        channel_chat_id=int(channel_chat_id) if channel_chat_id.strip() else None,
        capacity=capacity,
        closed=1 if closed else 0,
    )
    return _redirect("/admin/chats", "Pair updated.")


@router.post("/pairs/{pair_id}/default")
async def pairs_default(request: Request, pair_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    db.set_default_pair(pair_id)
    return _redirect("/admin/chats", "Default pair set.")


@router.post("/pairs/{pair_id}/primary")
async def pairs_primary(request: Request, pair_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    db.set_primary_pair(pair_id)
    return _redirect("/admin/chats", "Primary pair set.")


@router.post("/pairs/{pair_id}/delete")
async def pairs_delete(request: Request, pair_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    db.delete_pair(pair_id)
    return _redirect("/admin/chats", "Pair deleted; its users are now unplaced.")


# --------------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------------- #

@router.get("/users")
async def users_page(request: Request, q: str = "", page: int = 1, month: str = ""):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    month = month or current_month()
    page = max(1, page)
    per_page = 50
    rows = db.list_users(search=q, limit=per_page, offset=(page - 1) * per_page)
    enriched = [(row, status_for(row, month)) for row in rows]
    return _page(
        request,
        "admin/users.html",
        rows=enriched,
        q=q,
        page=page,
        per_page=per_page,
        month=month,
        months=db.activity_horizon(),
        total=db.count_users(),
    )


@router.get("/users/{uid}")
async def user_detail(request: Request, uid: str, month: str = ""):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    canonical = normalise_uid(uid)
    user = db.get_user_by_uid(canonical) if canonical else None
    if user is None:
        return _redirect("/admin/users", "No such user.")
    month = month or current_month()
    return _page(
        request,
        "admin/user_detail.html",
        user=user,
        report=report_for(user, month),
        bank=db.get_bank_details(int(user["id"])),
        events=db.recent_events(30, user_id=int(user["id"])),
        pair=db.get_pair(int(user["pair_id"])) if user["pair_id"] else None,
        month=month,
        months=db.activity_horizon(),
    )


@router.post("/users/{user_id}/ban")
async def user_ban(request: Request, user_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    chats = await ban_everywhere(user_id, reason="banned from admin panel")
    user = db.get_user(user_id)
    target = f"/admin/users/{user['uid']}" if user else "/admin/users"
    return _redirect(target, f"Banned in {len(chats)} chat(s).")


@router.post("/users/{user_id}/unban")
async def user_unban(request: Request, user_id: int):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    chats = await unban_everywhere(user_id)
    db.reset_warnings(user_id)
    user = db.get_user(user_id)
    target = f"/admin/users/{user['uid']}" if user else "/admin/users"
    return _redirect(target, f"Unbanned in {len(chats)} chat(s).")


@router.post("/users/{user_id}/duplicate")
async def user_duplicate(request: Request, user_id: int, value: int = Form(1)):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    db.set_flags(user_id, duplicate=bool(value))
    db.log_event("duplicate_flag", user_id, f"value={value}")
    if value:
        await ban_everywhere(user_id, reason="marked duplicate in admin panel")
    user = db.get_user(user_id)
    target = f"/admin/users/{user['uid']}" if user else "/admin/users"
    return _redirect(target, "Duplicate flag updated.")


# --------------------------------------------------------------------------- #
# activity
# --------------------------------------------------------------------------- #

@router.get("/activity")
async def activity_page(request: Request, uid: str = "", month: str = ""):
    """Activity is a per-user-per-month fact, so this looks one up.

    There is no scrollable interaction log to browse: individual taps are
    never stored, which is exactly what keeps the database small.
    """
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    month = month or current_month()

    looked_up = None
    status = None
    canonical = normalise_uid(uid) if uid else None
    if canonical:
        looked_up = db.get_user_by_uid(canonical)
        if looked_up is not None:
            status = status_for(looked_up, month)

    return _page(
        request,
        "admin/activity.html",
        uid=uid,
        canonical=canonical,
        user=looked_up,
        status=status,
        month=month,
        months=db.activity_horizon(),
        active_now=db.active_user_count(month),
        verified=db.count_users("(flags & ?) = ?", (db.F_VERIFIED, db.F_VERIFIED)),
    )


@router.get("/events")
async def events_page(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    return _page(request, "admin/events.html", events=db.recent_events(300))


# --------------------------------------------------------------------------- #
# bank details & withdrawals
# --------------------------------------------------------------------------- #

@router.get("/bank")
async def bank_page(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    return _page(
        request,
        "admin/bank.html",
        rows=db.list_bank_details(),
        missing=db.users_without_bank_details(),
    )


@router.post("/bank/prompt")
async def bank_prompt(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    result = await daily_bank_prompt()
    return _redirect(
        "/admin/bank",
        f"Posted in {result['chats']} chat(s), DMed {result['dms']} user(s).",
    )


@router.get("/withdrawals")
async def withdrawals_page(request: Request, month: str = "", status: str = "all"):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    month = month or current_month()
    return _page(
        request,
        "admin/withdrawals.html",
        rows=db.list_withdrawals(month=month, status=status),
        month=month,
        months=db.withdrawal_months(),
        status=status,
        totals=month_totals(month),
    )


@router.post("/withdrawals/{withdrawal_id}/{action}")
async def withdrawal_action(
    request: Request,
    withdrawal_id: int,
    action: str,
    month: str = Form(""),
    note: str = Form(""),
):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    mapping = {"approve": "approved", "reject": "rejected", "paid": "paid"}
    if action not in mapping:
        return _redirect("/admin/withdrawals", "Unknown action.")

    row = db.query_one("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
    if row is None:
        return _redirect("/admin/withdrawals", "No such request.")

    db.set_withdrawal_status(withdrawal_id, mapping[action], note)
    db.log_event("withdrawal_" + mapping[action], int(row["user_id"]), f"id={withdrawal_id}")

    user = db.get_user(int(row["user_id"]))
    if user is not None:
        text = {
            "approved": f"✅ Your payout of ₹{row['amount']:g} for {row['month']} was approved.",
            "rejected": f"❌ Your payout request for {row['month']} was rejected."
            + (f"\nReason: {note}" if note else ""),
            "paid": f"💸 ₹{row['amount']:g} for {row['month']} has been transferred to your bank account.",
        }[mapping[action]]
        bot = manager.any_bot("main")
        if bot is not None:
            await call_api(bot.send_message, chat_id=int(user["id"]), text=text)

    suffix = f"?month={month}" if month else ""
    return _redirect(f"/admin/withdrawals{suffix}", f"Marked {mapping[action]}.")


@router.get("/export")
async def export_page(request: Request, month: str = "", status: str = "all"):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    month = month or current_month()
    rows, skipped = export.collect_rows(month, status)
    return _page(
        request,
        "admin/export.html",
        month=month,
        months=db.withdrawal_months(),
        status=status,
        rows=rows,
        skipped=skipped,
        columns=export.COLUMNS,
        total=sum(float(row[4]) for row in rows),
    )


@router.get("/export/download")
async def export_download(
    request: Request, month: str = "", status: str = "all", fmt: str = "csv"
):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    month = month or current_month()
    if fmt == "xlsx":
        payload, _ = export.to_xlsx(month, status)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        name = export.filename(month, status, "xlsx")
    else:
        payload, _ = export.to_csv(month, status)
        media = "text/csv; charset=utf-8"
        name = export.filename(month, status, "csv")
    db.log_event("export", None, f"{month} {status} {fmt}")
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #

EDITABLE_SETTINGS = [
    ("payout_level1", "Level 1 rate — INR per active direct referral", "number"),
    ("payout_level2", "Level 2 rate — INR per active indirect referral", "number"),
    ("welcome_text", "Welcome message shown before the contact button", "textarea"),
    ("daily_prompt_text", "Daily bank-details reminder", "textarea"),
    ("daily_prompt_dm", "Also DM users who owe bank details (1/0)", "text"),
    ("broadcast_confirm", "Ask before broadcasting (1/0)", "text"),
    ("moderation_enabled", "Moderation bot active (1/0)", "text"),
    ("flood_limit", "Messages allowed inside the flood window", "text"),
    ("flood_window_seconds", "Flood window, seconds", "text"),
    ("warn_mute_at", "Warnings before a mute", "text"),
    ("warn_ban_at", "Warnings before a ban", "text"),
    ("mute_minutes", "Mute length, minutes", "text"),
    ("block_links_from_unverified", "Delete links from unverified users (1/0)", "text"),
    ("banned_words", "Forbidden words, comma separated", "textarea"),
]


@router.get("/settings")
async def settings_page(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    return _page(
        request,
        "admin/settings.html",
        values=db.all_settings(),
        fields=EDITABLE_SETTINGS,
        env={
            "DB_PATH": str(settings.db_path),
            "ADMIN_IDS": ", ".join(str(i) for i in sorted(settings.admin_ids)) or "(none)",
            "PAYOUT_LEVEL1 / PAYOUT_LEVEL2": (
                "seed values only — the live rates are the two fields above"
            ),
            "DAILY_PROMPT_HOUR": f"{settings.daily_prompt_hour:02d}:00 IST",
            "PUBLIC_BASE_URL": settings.public_base_url or "(not set)",
        },
        rights={bot["bot_id"]: bot["rights_problems"] for bot in manager.describe()},
    )


@router.post("/settings")
async def settings_save(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    form = await request.form()
    kinds = {key: kind for key, _, kind in EDITABLE_SETTINGS}

    saved: list[str] = []
    rejected: list[str] = []
    for key, value in form.items():
        if key not in kinds:
            continue
        text = str(value).strip()
        if kinds[key] == "number":
            # A payout rate that silently became 0 — or a string — would quietly
            # zero out everyone's earnings, so refuse rather than coerce.
            try:
                number = float(text)
            except ValueError:
                rejected.append(key)
                continue
            if number < 0:
                rejected.append(key)
                continue
            text = f"{number:g}"
        db.set_setting(key, text)
        saved.append(key)

    db.log_event("settings_updated", None, ",".join(sorted(saved)))
    message = "Settings saved."
    if rejected:
        message += (
            f" Ignored {', '.join(sorted(rejected))} — must be a number of 0 or more."
        )
    return _redirect("/admin/settings", message)


@router.post("/notify-test")
async def notify_test(request: Request):
    if not auth.is_authenticated(request):
        return auth.login_redirect(request)
    await notify_admins("🔔 Test notification from the admin panel.")
    return _redirect("/admin/settings", "Test notification sent to ADMIN_IDS.")
