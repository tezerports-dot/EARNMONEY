"""Runs every registered bot as an asyncio task inside the FastAPI process.

There is no external worker, queue or scheduler. Adding a bot in the admin
panel calls :meth:`BotManager.start_bot`, removing one cancels its task —
polling starts and stops without restarting the service.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app import db
from app.config import settings
from app.roles import MAIN, ROLES

log = logging.getLogger("bots.manager")

ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "channel_post",
    "callback_query",
    "chat_member",
    "my_chat_member",
    "chat_join_request",
    "poll_answer",
]


class BotManager:
    """Owns the live ``Bot`` objects and their polling tasks."""

    def __init__(self) -> None:
        self._bots: dict[int, Bot] = {}
        self._dispatchers: dict[int, Dispatcher] = {}
        self._tasks: dict[int, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self.rights_report: dict[int, list[str]] = {}

    # ------------------------------------------------------------------ #
    # lookups
    # ------------------------------------------------------------------ #

    def get_bot(self, bot_id: int) -> Bot | None:
        return self._bots.get(int(bot_id))

    def running_ids(self) -> set[int]:
        return {bot_id for bot_id, task in self._tasks.items() if not task.done()}

    def is_running(self, bot_id: int) -> bool:
        task = self._tasks.get(int(bot_id))
        return task is not None and not task.done()

    def any_bot(self, role: str | None = None) -> Bot | None:
        """Any running bot, preferring the given role."""
        if role:
            for row in db.bots_with_role(role):
                bot = self.get_bot(int(row["bot_id"]))
                if bot is not None:
                    return bot
        for bot_id in sorted(self._bots):
            if self.is_running(bot_id):
                return self._bots[bot_id]
        return None

    def bot_id_of(self, bot: Bot) -> int | None:
        for bot_id, instance in self._bots.items():
            if instance is bot:
                return bot_id
        return None

    async def main_bot_username(self) -> str | None:
        """Username of a running main bot, for building referral links."""
        for row in db.bots_with_role(MAIN):
            if row["username"]:
                return str(row["username"])
            bot = self.get_bot(int(row["bot_id"]))
            if bot is not None:
                try:
                    me = await bot.me()
                except Exception:  # noqa: BLE001
                    continue
                db.update_bot(int(row["bot_id"]), username=me.username)
                return me.username
        return None

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    async def start_all(self) -> None:
        self._seed_from_env()
        for row in db.list_bots():
            if row["status"] == "running":
                await self.start_bot(int(row["bot_id"]))

    async def stop_all(self) -> None:
        for bot_id in list(self._tasks):
            await self.stop_bot(bot_id, mark_stopped=False)

    def _seed_from_env(self) -> None:
        """Insert BOT_TOKENS on first boot; afterwards the DB is the source."""
        for role, token in settings.seed_bots:
            if not token or ":" not in token:
                continue
            if db.get_bot_by_token(token) is None:
                name = f"{role} bot"
                db.add_bot(token=token, name=name, role=role, status="running")
                log.info("seeded %s bot from BOT_TOKENS", role)

    async def start_bot(self, bot_id: int) -> str:
        """Start polling for one bot. Returns a human-readable status string."""
        async with self._lock:
            bot_id = int(bot_id)
            row = db.get_bot(bot_id)
            if row is None:
                return "bot not found"
            if self.is_running(bot_id):
                return "already running"

            role = str(row["role"] or MAIN)
            if role not in ROLES:
                role = MAIN

            bot = Bot(
                token=str(row["token"]),
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            try:
                me = await bot.get_me()
            except Exception as exc:  # noqa: BLE001 - bad token, no network, ...
                await bot.session.close()
                db.update_bot(bot_id, status="stopped", last_error=str(exc)[:300])
                log.error("bot %s failed getMe: %s", bot_id, exc)
                return f"could not start: {exc}"

            from app.bots.dispatcher import build_dispatcher

            dp = build_dispatcher(role)
            dp["bot_id"] = bot_id
            dp["bot_role"] = role

            self._bots[bot_id] = bot
            self._dispatchers[bot_id] = dp
            db.update_bot(
                bot_id,
                status="running",
                username=me.username,
                telegram_id=me.id,
                last_error=None,
            )

            task = asyncio.create_task(
                self._run(bot_id, dp, bot), name=f"bot-poller-{bot_id}"
            )
            self._tasks[bot_id] = task
            log.info("started bot %s (@%s) as %s", bot_id, me.username, role)
            asyncio.create_task(self._audit_rights(bot_id, bot))
            return f"started @{me.username}"

    async def _run(self, bot_id: int, dp: Dispatcher, bot: Bot) -> None:
        try:
            await dp.start_polling(
                bot,
                allowed_updates=ALLOWED_UPDATES,
                handle_signals=False,
                close_bot_session=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("bot %s polling crashed", bot_id)
            db.update_bot(bot_id, status="stopped", last_error=str(exc)[:300])

    async def _audit_rights(self, bot_id: int, bot: Bot) -> None:
        from app.bots.telegram_utils import check_admin_rights

        try:
            problems = await check_admin_rights(bot, bot_id)
        except Exception as exc:  # noqa: BLE001
            problems = [f"rights check failed: {exc}"]
        self.rights_report[bot_id] = problems
        if problems:
            log.warning("bot %s rights issues: %s", bot_id, problems)
            db.log_event("rights_check", None, f"bot={bot_id} {problems}")

    async def stop_bot(self, bot_id: int, mark_stopped: bool = True) -> str:
        bot_id = int(bot_id)
        task = self._tasks.pop(bot_id, None)
        dp = self._dispatchers.pop(bot_id, None)
        bot = self._bots.pop(bot_id, None)

        if dp is not None:
            try:
                await dp.stop_polling()
            except Exception:  # noqa: BLE001 - not polling yet
                pass
        if task is not None:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=10)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:  # noqa: BLE001
                pass
        if bot is not None:
            try:
                await bot.session.close()
            except Exception:  # noqa: BLE001
                pass
        if mark_stopped:
            db.update_bot(bot_id, status="stopped")
        self.rights_report.pop(bot_id, None)
        log.info("stopped bot %s", bot_id)
        return "stopped"

    async def restart_bot(self, bot_id: int) -> str:
        await self.stop_bot(bot_id, mark_stopped=False)
        return await self.start_bot(bot_id)

    def describe(self) -> list[dict[str, object]]:
        """Bot rows decorated with live task state, for the admin panel."""
        out: list[dict[str, object]] = []
        for row in db.list_bots():
            bot_id = int(row["bot_id"])
            token = str(row["token"])
            out.append(
                {
                    "bot_id": bot_id,
                    "name": row["name"],
                    "role": row["role"],
                    "role_help": ROLES.get(str(row["role"]), ""),
                    "status": row["status"],
                    "running": self.is_running(bot_id),
                    "username": row["username"],
                    "telegram_id": row["telegram_id"],
                    "last_error": row["last_error"],
                    "added_at": row["added_at"],
                    "masked_token": mask_token(token),
                    "chats": len(db.list_chats(bot_id)),
                    "rights_problems": self.rights_report.get(bot_id, []),
                }
            )
        return out


def mask_token(token: str) -> str:
    """``123456:AAF...xyz`` — never show a full token in the browser."""
    text = str(token or "")
    head, sep, tail = text.partition(":")
    if not sep:
        return "*" * len(text)
    return f"{head}:{tail[:3]}...{tail[-3:]}" if len(tail) > 8 else f"{head}:***"


manager = BotManager()
