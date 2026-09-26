"""Minimal Telegram Bot API client.

Only the calls verification needs. Tests replace ``client_factory`` with a
fake, so no test ever reaches Telegram.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.config import get_settings


class TelegramError(Exception):
    def __init__(self, description: str, *, code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(description)
        self.code = code
        self.retry_after = retry_after


class BotApi(Protocol):
    async def call(self, method: str, **params: Any) -> Any: ...


class HttpBotApi:
    def __init__(self, token: str, http: httpx.AsyncClient) -> None:
        self._url = f"{get_settings().telegram_api_base}/bot{token}/"
        self._http = http

    async def call(self, method: str, **params: Any) -> Any:
        payload = {k: v for k, v in params.items() if v is not None}
        try:
            response = await self._http.post(self._url + method, json=payload, timeout=10)
            data = response.json()
        except (httpx.HTTPError, ValueError):
            # "from None" drops the original exception, whose message
            # includes the URL and therefore the bot token.
            raise TelegramError(f"network error calling {method}") from None
        if not data.get("ok"):
            params_ = data.get("parameters") or {}
            raise TelegramError(
                str(data.get("description", "error"))[:200],
                code=data.get("error_code"),
                retry_after=params_.get("retry_after"),
            )
        return data.get("result")


_http: httpx.AsyncClient | None = None


def http_client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient()
    return _http


def default_factory(token: str) -> BotApi:
    return HttpBotApi(token, http_client())


# Replaced in tests.
client_factory = default_factory


def api_for(token: str) -> BotApi:
    return client_factory(token)
