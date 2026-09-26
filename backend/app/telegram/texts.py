"""Everything the verification bots say. No internal details, ever: no phone
numbers, bot names, channel ids or reasons beyond what the user can act on."""

from __future__ import annotations


def start_invalid(company: str) -> str:
    return (
        f"This verification link isn't valid anymore.\n\nOpen the {company} app and tap “Verify with Telegram” to get a new one."
    )


def welcome(company: str, titles: list[str]) -> str:
    lines = "\n".join(f"JOIN {i} — {title}" for i, title in enumerate(titles, 1))
    return (
        f"Welcome to {company} verification.\n\n"
        "Step 1 of 2: tap each JOIN button and send a join request.\n\n"
        f"{lines}\n\n"
        "When you've sent them all, tap “I've sent the requests”."
    )


def channels_missing(titles: list[str]) -> str:
    return (
        "Almost there. We couldn't find a join request for:\n"
        + "\n".join(f"• {t}" for t in titles)
        + "\n\nTap its JOIN button, send the request, then tap “I've sent the requests” again."
    )


def contact_ask() -> str:
    return "Step 2 of 2: tap “Share my phone number” below.\n\nWe only check that it matches the number you signed up with."


def contact_not_own() -> str:
    return "Please use the “Share my phone number” button, so Telegram sends your own number."


def mismatch(company: str, attempts_left: int) -> str:
    return (
        "This Telegram account's number doesn't match the number you signed up with.\n\n"
        "Use the Telegram account that has that number, or sign up again in the "
        f"{company} app with this number. Attempts left: {attempts_left}."
    )


def mismatch_limit(company: str) -> str:
    return f"Too many numbers didn't match. Open the {company} app to start verification again."


def linked_elsewhere(company: str) -> str:
    return (
        f"This Telegram account is already linked to another {company} account.\n\n"
        "Use a different Telegram account, or log in to that account in the app."
    )


def verified(company: str) -> str:
    return f"✅ You're verified. Go back to the {company} app to continue."


def already_verified(company: str) -> str:
    return f"You're already verified. Open the {company} app to continue."


def no_session(company: str) -> str:
    return f"To verify, open the {company} app and tap “Verify with Telegram”."


def try_later() -> str:
    return "We can't check right now. Please try again in a few minutes."


CHECK_BUTTON = "✓ I've sent the requests"
CONTACT_BUTTON = "📱 Share my phone number"
CHECK_CALLBACK = "vs:check"
