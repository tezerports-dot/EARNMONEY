"""Membership tracking — the backbone of the activity rule.

Every bot in the fleet runs this router, so a chat covered by any one of them
keeps an accurate ``memberships`` table. Telegram sends ``chat_member`` only
to bots that are administrators in the chat.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatJoinRequest, ChatMemberUpdated

from app import db
from app.bots.routerspec import RouterSpec
from app.bots.common import ensure_user
from app.bots.telegram_utils import call_api, esc

log = logging.getLogger("bots.membership")

router = RouterSpec("membership")

MEMBER_STATES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
}


def _chat_kind(chat_type: str) -> str:
    return "channel" if chat_type == ChatType.CHANNEL else "group"


def _status_of(update: ChatMemberUpdated) -> str:
    new = update.new_chat_member
    status = new.status
    if status in MEMBER_STATES:
        return "member"
    if status == ChatMemberStatus.RESTRICTED:
        # A restricted user may or may not still be in the chat.
        return "member" if getattr(new, "is_member", False) else "restricted"
    if status == ChatMemberStatus.KICKED:
        return "banned"
    return "left"


@router.chat_member()
async def on_chat_member(update: ChatMemberUpdated, bot: Bot) -> None:
    """A user joined, left, was promoted, restricted or banned."""
    tg_user = update.new_chat_member.user
    if tg_user.is_bot:
        return

    if not db.chat_rows(update.chat.id):
        # A chat nobody registered: remember it so the admin panel can adopt it.
        log.debug("membership update from unmanaged chat %s", update.chat.id)
        return

    user = ensure_user(tg_user)
    user_id = int(user["id"])
    status = _status_of(update)
    kind = _chat_kind(update.chat.type)
    db.set_membership(user_id, update.chat.id, kind, status)
    db.log_event(
        "membership",
        user_id,
        f"chat={update.chat.id} type={kind} status={status}",
    )

    if status != "member":
        return

    # Someone banned elsewhere in the fleet must not slip back in.
    if user["banned"] or user["duplicate"]:
        await call_api(bot.ban_chat_member, chat_id=update.chat.id, user_id=user_id)
        db.set_membership(user_id, update.chat.id, kind, "banned")
        return

    await _credit_inviter(update, user_id)


async def _credit_inviter(update: ChatMemberUpdated, user_id: int) -> None:
    """If they joined through someone's named link, record that referral."""
    link = update.invite_link
    if link is None:
        return
    owner = db.owner_of_invite_link(link.invite_link, link.name)
    if owner is None or int(owner["id"]) == user_id:
        return

    joined = db.get_user(user_id)
    if joined is not None and joined["referred_by_uid"] is None:
        db.set_user_fields(user_id, referred_by_uid=str(owner["uid"]))
        db.log_event(
            "referral_via_invite_link",
            user_id,
            f"inviter={owner['uid']} chat={update.chat.id}",
        )


@router.chat_join_request()
async def on_join_request(request: ChatJoinRequest, bot: Bot) -> None:
    """Auto-approve the join requests our own personal invite links create.

    No bot can add a user to a chat, so onboarding hands out a personal
    join-request link instead: the user taps it once and this handler lets
    them straight in.
    """
    tg_user = request.from_user
    user = ensure_user(tg_user)
    user_id = int(user["id"])

    if user["banned"] or user["duplicate"]:
        await call_api(
            bot.decline_chat_join_request, chat_id=request.chat.id, user_id=user_id
        )
        db.log_event("join_declined", user_id, f"chat={request.chat.id} banned/duplicate")
        return

    approved = await call_api(
        bot.approve_chat_join_request, chat_id=request.chat.id, user_id=user_id
    )
    if approved is None:
        log.warning("could not approve %s into %s", user_id, request.chat.id)
        return

    kind = _chat_kind(request.chat.type)
    db.set_membership(user_id, request.chat.id, kind, "member")
    db.log_event("join_approved", user_id, f"chat={request.chat.id}")

    link = request.invite_link
    if link is not None:
        owner = db.owner_of_invite_link(link.invite_link, link.name)
        if owner is not None and int(owner["id"]) != user_id:
            joined = db.get_user(user_id)
            if joined is not None and joined["referred_by_uid"] is None:
                db.set_user_fields(user_id, referred_by_uid=str(owner["uid"]))


@router.my_chat_member()
async def on_my_chat_member(update: ChatMemberUpdated, bot: Bot) -> None:
    """The bot itself was added to, promoted in, or removed from a chat."""
    from app.bots.manager import manager

    bot_id = manager.bot_id_of(bot)
    if bot_id is None:
        return
    if update.chat.type == ChatType.PRIVATE:
        return

    status = update.new_chat_member.status
    kind = _chat_kind(update.chat.type)

    if status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER}:
        db.add_chat(
            chat_id=update.chat.id,
            bot_id=bot_id,
            chat_type=kind,
            title=update.chat.title,
        )
        db.log_event(
            "chat_registered", None, f"bot={bot_id} chat={update.chat.id} status={status}"
        )
        if status != ChatMemberStatus.ADMINISTRATOR:
            await call_api(
                bot.send_message,
                chat_id=update.chat.id,
                text=(
                    "⚠️ Please make me an <b>administrator</b> with the "
                    "<b>invite users</b> right, otherwise I cannot track "
                    f"members or issue invite links for {esc(update.chat.title or 'this chat')}."
                ),
            )
    elif status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        db.delete_chat(update.chat.id, bot_id)
        db.log_event("chat_removed", None, f"bot={bot_id} chat={update.chat.id}")
