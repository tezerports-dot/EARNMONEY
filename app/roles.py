"""Bot roles.

Every bot token registered in the system carries exactly one role. The role
decides which routers are attached to that bot's dispatcher, so several bots
can share the same database while doing very different jobs.
"""

from __future__ import annotations

MAIN = "main"
MODERATION = "moderation"
COLLECTOR = "collector"
BROADCAST = "broadcast"

ROLES: dict[str, str] = {
    MAIN: "Onboarding, referrals, contact sharing, bank details, earnings",
    MODERATION: "Behaviour rules, warnings, mutes and bans across managed chats",
    COLLECTOR: "Daily bank-details reminder in every managed chat and DM",
    BROADCAST: "Relays whatever an owner sends it to every managed chat",
}
