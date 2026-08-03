"""Builds a dispatcher for a bot, wiring only the routers its role needs."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bots.handlers import (
    account,
    bankflow,
    broadcast,
    collector,
    membership,
    moderation,
    onboarding,
)
from app.bots.middlewares import ActivityMiddleware
from app.roles import BROADCAST, COLLECTOR, MAIN, MODERATION

# Router order is significant: command routers are registered before the FSM
# router so that /start or /help typed midway through the bank form is still
# treated as a command rather than swallowed as an answer.
ROLE_SPECS = {
    MAIN: (onboarding.router, account.router, bankflow.router),
    MODERATION: (moderation.router,),
    COLLECTOR: (collector.router,),
    BROADCAST: (broadcast.router,),
}


def build_dispatcher(role: str) -> Dispatcher:
    """A fresh dispatcher, with fresh routers, for exactly one bot.

    Routers are built per call rather than shared: aiogram refuses to attach
    one ``Router`` instance to a second ``Dispatcher``, and every bot here
    gets its own dispatcher so it can be started and stopped on its own.
    """
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(ActivityMiddleware())

    # Every bot keeps membership state accurate for the chats it administers.
    dp.include_router(membership.router.build())
    for spec in ROLE_SPECS.get(role, ROLE_SPECS[MAIN]):
        dp.include_router(spec.build())
    return dp
