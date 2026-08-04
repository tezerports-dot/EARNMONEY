"""Update-level middleware that marks users active for the current month.

The Bot API cannot tell us that someone *opened* a group or *read* a channel —
no such update exists. So "activity" is built only from signals Telegram
actually delivers:

* ``callback_query``  — a tap on one of the bot's buttons
* commands            — ``/start``, ``/earnings``, ...
* group messages      — a message in a chat this fleet manages
* ``poll_answer``     — a vote, and *only* for polls the bot itself created
* private messages    — anything sent directly to a bot

All of them mean the same thing and are recorded the same way: a single month
marker on the user's row. There is no per-interaction log, so a member who
taps a hundred buttons costs one write in the first tap of the month and none
after it — which is what makes thirty million users affordable.
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
        elif update.callback_query is not None:
            self._mark(update.callback_query)
        elif update.poll_answer is not None:
            # Telegram delivers poll_answer only for polls created by this
            # bot; a poll a human posted in the group produces nothing at all.
            self._mark(update.poll_answer)

    def _from_message(self, message: Message) -> None:
        if message.chat.type != ChatType.PRIVATE and not db.chat_rows(message.chat.id):
            return  # chatter in a chat this fleet does not manage
        self._mark(message)

    def _mark(self, event: Message | CallbackQuery | PollAnswer) -> None:
        tg_user = getattr(event, "from_user", None) or getattr(event, "user", None)
        if tg_user is None or tg_user.is_bot:
            return
        user = ensure_user(tg_user)
        db.record_activity(int(user["id"]))
