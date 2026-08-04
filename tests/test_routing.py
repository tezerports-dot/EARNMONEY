"""Router wiring: fresh routers per bot, and handler order that matters."""

from __future__ import annotations

from aiogram import Dispatcher

from app.bots.dispatcher import build_dispatcher
from app.bots.handlers import broadcast, moderation
from app.roles import ROLES


def test_every_role_builds_and_can_be_built_twice():
    """Two bots may share a role, and each needs its own router objects."""
    for role in ROLES:
        first = build_dispatcher(role)
        second = build_dispatcher(role)
        assert isinstance(first, Dispatcher)
        assert isinstance(second, Dispatcher)


def test_moderation_commands_are_registered_before_the_group_catch_all():
    """The catch-all matches every group message, so it must come last."""
    handlers = [handler.__name__ for handler, _, _ in moderation.router.message.handlers]
    assert handlers[-1] == "watch_group"
    for command in ("cmd_ban", "cmd_unban", "cmd_mute", "cmd_warn", "cmd_whois"):
        assert handlers.index(command) < handlers.index("watch_group")


def test_broadcast_relay_is_registered_after_its_commands():
    handlers = [handler.__name__ for handler, _, _ in broadcast.router.message.handlers]
    assert handlers[-1] == "relay_anything"
    for command in ("cmd_start", "cmd_targets", "cmd_poll", "cmd_say"):
        assert handlers.index(command) < handlers.index("relay_anything")


def test_main_role_orders_commands_before_the_bank_form_states():
    """/start must escape a half-finished form rather than be eaten by it."""
    from app.bots.handlers import bankflow, onboarding

    assert "cmd_start" in [h.__name__ for h, _, _ in onboarding.router.message.handlers]
    assert "step_name" in [h.__name__ for h, _, _ in bankflow.router.message.handlers]

    from app.bots.dispatcher import ROLE_SPECS
    from app.roles import MAIN

    specs = ROLE_SPECS[MAIN]
    assert specs.index(onboarding.router) < specs.index(bankflow.router)


def test_membership_router_carries_no_message_handlers():
    """It runs on every bot; it must never intercept another role's messages."""
    from app.bots.handlers import membership

    assert membership.router.message.handlers == []
    assert len(membership.router.chat_member.handlers) == 1
    assert len(membership.router.chat_join_request.handlers) == 1
    assert len(membership.router.my_chat_member.handlers) == 1
