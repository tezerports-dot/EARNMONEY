"""Process configuration, read once from the environment at import time."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _id_set(raw: str) -> set[int]:
    out: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.add(int(chunk))
        except ValueError:
            continue
    return out


def _seed_bots(raw: str) -> list[tuple[str, str]]:
    """Parse BOT_TOKENS into ``[(role, token), ...]``.

    Accepts ``role:token`` pairs; a bare token is treated as the main bot.
    Tokens themselves contain a colon, so only the first colon is a separator
    and only when the part before it is a known role.
    """
    from app.roles import ROLES

    out: list[tuple[str, str]] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        role = "main"
        token = chunk
        head, sep, tail = chunk.partition(":")
        if sep and head.strip().lower() in ROLES and tail.strip():
            role = head.strip().lower()
            token = tail.strip()
        out.append((role, token))
    return out


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("DB_PATH", str(Path.cwd() / "data" / "referral.db"))
        )
    )
    admin_token: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN", ""))
    session_secret: str = field(
        default_factory=lambda: os.getenv("SESSION_SECRET", "")
        or os.getenv("ADMIN_TOKEN", "insecure-dev-secret")
    )
    admin_ids: set[int] = field(
        default_factory=lambda: _id_set(os.getenv("ADMIN_IDS", ""))
    )
    seed_bots: list[tuple[str, str]] = field(
        default_factory=lambda: _seed_bots(os.getenv("BOT_TOKENS", ""))
    )
    public_base_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    )
    # Seed values only. Once the database exists the admin panel owns these,
    # so changing the env afterwards has no effect (same deal as BOT_TOKENS).
    payout_level1: float = field(
        default_factory=lambda: _float_env("PAYOUT_LEVEL1", 5.0)
    )
    payout_level2: float = field(
        default_factory=lambda: _float_env("PAYOUT_LEVEL2", 5.0)
    )
    daily_prompt_hour: int = field(
        default_factory=lambda: _int_env("DAILY_PROMPT_HOUR", 10)
    )
    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _int_env("PORT", 8000))


settings = Settings()
