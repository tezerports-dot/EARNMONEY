"""Update-level middleware that turns Telegram events into activity rows.

The Bot API cannot tell us that someone *opened* a group or *read* a channel —
no such update exists. So "activity" is built only from signals Telegram
actually delivers:

* ``callback_query``  — a tap on one of the bot's buttons
* commands            — ``/start``, ``/earnings``, ...
* group messages      — a message in a chat this fleet manages
* ``poll_answer``     — a vote, and *only* for polls the bot itself created
* private messages    — anything sent directly to a bot

Group chatter is collapsed to one row per user per day; eligibility only ever
needs one row per month, so this keeps the table small without changing who
gets paid.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, PollAnswer, Update

from app import db
from app.bots.common import ensure_user

log = logging.getLogger("bots.activity")


class ActivityMiddleware(BaseMiddleware):
    """Records interactions before handlers run, for every bot in the fleet."""

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        try:
            self._record(event)
        except Exception:  # noqa: BLE001 - telemetry must never break a handler
            log.exception("failed to record activity")
        return await handler(event, data)

    def _record(self, update: Update) -> None:
        if update.message is not None:
            self._from_message(update.message)
        elif update.edited_message is not None:
            self._from_message(update.edited_message, edited=True)
        elif update.callback_query is not None:
            self._from_callback(update.callback_query)
        elif update.poll_answer is not None:
            self._from_poll_answer(update.poll_answer)

    def _from_message(self, message: Message, edited: bool = False) -> None:
        if message.from_user is None or message.from_user.is_bot:
            return
        user = ensure_user(message.from_user)
        user_id = int(user["id"])
        text = (message.text or message.caption or "")[:200]
        is_command = bool(text.startswith("/"))

        if message.chat.type == ChatType.PRIVATE:
            if is_command:
                db.record_activity(user_id, "command", text)
            elif not edited:
                db.record_activity(user_id, "dm", text)
            return

        # Group or supergroup: only chats this fleet manages produce signal.
        if not db.chat_rows(message.chat.id):
            return
        db.bump_message_count(user_id)
        if is_command:
            db.record_activity(user_id, "command", f"{message.chat.id} {text}")
        else:
            db.record_activity(
                user_id, "group_message", str(message.chat.id), once_per_day=True
            )

    def _from_callback(self, callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.from_user.is_bot:
            return
        user = ensure_user(callback.from_user)
        db.record_activity(int(user["id"]), "callback", (callback.data or "")[:200])

    def _from_poll_answer(self, answer: PollAnswer) -> None:
        # Telegram delivers poll_answer only for polls created by this bot;
        # a poll a human posted in the group produces nothing at all.
        if answer.user is None or answer.user.is_bot:
            return
        user = ensure_user(answer.user)
        db.record_activity(
            int(user["id"]), "poll_answer", f"{answer.poll_id}:{answer.option_ids}"
        )
