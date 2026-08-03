"""Cross-handler operations: placement, invite links, duplicate handling."""

from __future__ import annotations

import asyncio
import logging
import sqlite3

from app import db
from app.bots.telegram_utils import (
    ban_everywhere,
    bot_for_chat,
    call_api,
    ensure_personal_invite,
    esc,
    notify_admins,
)

log = logging.getLogger("bots.services")


async def assign_pair_and_links(
    user: sqlite3.Row,
) -> tuple[sqlite3.Row | None, str | None, str | None]:
    """Place a verified user in exactly one group+channel pair.

    Placement order is the referrer's pair, then the admin default, then the
    least-loaded open pair. A user already placed keeps their pair, so this is
    safe to call again (re-issuing links after a revoke, for instance).
    """
    user_id = int(user["id"])
    uid = str(user["uid"])

    pair = db.get_pair(int(user["pair_id"])) if user["pair_id"] else None
    if pair is None or pair["closed"]:
        referrer_pair_id = None
        if user["referred_by_uid"]:
            referrer = db.get_user_by_uid(str(user["referred_by_uid"]))
            if referrer is not None and referrer["pair_id"]:
                referrer_pair_id = int(referrer["pair_id"])
        pair = db.choose_pair(referrer_pair_id)
        if pair is None:
            log.warning("no usable pair configured; user %s left unplaced", uid)
            return None, None, None
        db.set_user_fields(user_id, pair_id=int(pair["pair_id"]))
        db.log_event("pair_assigned", user_id, f"pair={pair['pair_id']}")

    group_link = await _link_for(pair["group_chat_id"], uid, user_id)
    channel_link = await _link_for(pair["channel_chat_id"], uid, user_id)
    return pair, group_link, channel_link


async def _link_for(chat_id: int | None, uid: str, user_id: int) -> str | None:
    if not chat_id:
        return None
    bot = bot_for_chat(int(chat_id))
    if bot is None:
        log.warning("no running bot is admin in chat %s; cannot issue invite", chat_id)
        return None
    return await ensure_personal_invite(bot, int(chat_id), uid, user_id)


async def handle_duplicate(user: sqlite3.Row, original: sqlite3.Row) -> None:
    """One phone number, one account — the newer account loses.

    The duplicate is flagged, banned from every managed chat, and detached
    from its referrer so it stops appearing in anyone's referral list.
    """
    user_id = int(user["id"])
    db.set_user_fields(
        user_id, duplicate=1, banned=1, verified=0, referred_by_uid=None, pair_id=None
    )
    db.log_event(
        "duplicate_phone",
        user_id,
        f"same phone as {original['uid']} (telegram id {original['id']})",
    )
    await ban_everywhere(user_id, reason="duplicate phone number")
    await notify_admins(
        "🚫 <b>Duplicate phone blocked</b>\n"
        f"New account: <code>{user_id}</code> ({esc(user['uid'])})\n"
        f"Already registered as: {esc(original['uid'])} "
        f"(<code>{original['id']}</code>)"
    )


async def approve_pending_join(user_id: int, chat_id: int) -> bool:
    bot = bot_for_chat(int(chat_id))
    if bot is None:
        return False
    result = await call_api(
        bot.approve_chat_join_request, chat_id=int(chat_id), user_id=int(user_id)
    )
    return result is not None


async def daily_bank_prompt() -> dict[str, int]:
    """Post the bank-details reminder in every managed chat, then DM stragglers.

    The DM sweep goes one user at a time with a small delay: Telegram will
    throttle a burst, and the whole point of the daily nudge is to fill the
    bank_details table that the admin CSV export reads from.
    """
    from app.bots.common import main_bot_link
    from app.bots.telegram_utils import send_to_chats

    text = db.get_setting("daily_prompt_text")
    link = await main_bot_link()
    if link:
        text = f"{text}\n\n👉 {link}"

    chat_ids = [int(row["chat_id"]) for row in db.distinct_managed_chats()]
    delivered, failures = await send_to_chats(text, chat_ids)

    dm_sent = 0
    if db.get_setting_bool("daily_prompt_dm", True):
        for user in db.users_without_bank_details():
            bot = _dm_bot()
            if bot is None:
                break
            result = await call_api(
                bot.send_message,
                chat_id=int(user["id"]),
                text=(
                    "🏦 <b>Bank details needed for your payout</b>\n\n"
                    "Send /bank here and I will ask for your name, account "
                    "number, IFSC and UPI id one at a time. It takes a minute "
                    "and you only ever do it once."
                ),
            )
            if result is not None:
                dm_sent += 1
            await asyncio.sleep(0.4)

    db.log_event(
        "daily_prompt",
        None,
        f"chats={len(delivered)} failed={len(failures)} dms={dm_sent}",
    )
    return {"chats": len(delivered), "failed": len(failures), "dms": dm_sent}


def _dm_bot():
    from app.bots.manager import manager
    from app.roles import COLLECTOR, MAIN

    return manager.any_bot(COLLECTOR) or manager.any_bot(MAIN)
