"""Deployment settings, read from environment variables prefixed ``FF_``.

These are things that differ between dev, staging and production (URLs, keys,
token lifetimes). Campaign and product settings that an admin changes at run
time live in the database instead (``campaigns`` and ``app_settings``).
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keys that ship in the repository for local development and tests only.
# The app refuses to start with them outside dev/test.
_DEV_ENCRYPTION_KEY = base64.b64encode(b"dev-only-encryption-key-32-bytes").decode()
_DEV_HMAC_KEY = base64.b64encode(b"dev-only-hmac-key-not-for-prod!!").decode()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FF_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "staging", "production"] = "dev"

    database_url: str = "postgresql+asyncpg://postgres@127.0.0.1:5432/ff_dev"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    # The app connects as this DML-only role in production (see docs/SECURITY.md).
    # Left blank in dev/tests, where the connection in database_url is used as is.
    app_db_user: str = "futurefashion_app"
    app_db_password: str = ""
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Public origin of this server, used for referral links (/r/{code}),
    # Telegram webhooks and the APK download redirect.
    public_base_url: str = "http://localhost:8000"

    # base64-encoded 32-byte keys. AES-256-GCM for bank numbers, bot tokens
    # and TOTP secrets; HMAC-SHA256 for fingerprints and derived tokens.
    data_encryption_key: str = _DEV_ENCRYPTION_KEY
    hmac_key: str = _DEV_HMAC_KEY

    access_token_minutes: int = 15
    refresh_token_days: int = 30
    pending_account_hours: int = 24
    admin_session_hours: int = 8

    # Argon2id cost. Tests lower these to stay fast.
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    argon2_parallelism: int = 2

    # Behind a reverse proxy (nginx), the client IP is the last address the
    # proxy appended to X-Forwarded-For. Leave off when exposed directly.
    trust_proxy_headers: bool = False

    telegram_api_base: str = "https://api.telegram.org"

    android_package_name: str = "com.futurefashion.app"
    # SHA-256 fingerprints of the APK signing certificate, for App Links.
    android_cert_sha256: list[str] = Field(default_factory=list)

    log_level: str = "INFO"

    @field_validator("public_base_url")
    @classmethod
    def _strip_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def _require_real_keys_outside_dev(self) -> Settings:
        for name in ("data_encryption_key", "hmac_key"):
            raw = getattr(self, name)
            try:
                decoded = base64.b64decode(raw, validate=True)
            except ValueError as exc:
                raise ValueError(f"FF_{name.upper()} must be base64") from exc
            if len(decoded) != 32:
                raise ValueError(f"FF_{name.upper()} must decode to 32 bytes")
        if self.env in ("staging", "production"):
            if self.data_encryption_key == _DEV_ENCRYPTION_KEY or self.hmac_key == _DEV_HMAC_KEY:
                raise ValueError("Set FF_DATA_ENCRYPTION_KEY and FF_HMAC_KEY; the dev keys are not allowed here")
            if self.data_encryption_key == self.hmac_key:
                raise ValueError("FF_DATA_ENCRYPTION_KEY and FF_HMAC_KEY must differ")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("FF_PUBLIC_BASE_URL must use https outside dev")
        return self

    @property
    def encryption_key_bytes(self) -> bytes:
        return base64.b64decode(self.data_encryption_key)

    @property
    def hmac_key_bytes(self) -> bytes:
        return base64.b64decode(self.hmac_key)

    @property
    def is_production_like(self) -> bool:
        return self.env in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
