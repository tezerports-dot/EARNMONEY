"""Admin authentication: one shared token, one signed cookie.

The cookie carries an expiry and an HMAC over it, so a stolen cookie cannot be
extended and a changed ``SESSION_SECRET`` invalidates every session at once.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

from app.config import settings

COOKIE_NAME = "admin_session"
SESSION_TTL = 12 * 60 * 60  # 12 hours


def _sign(payload: str) -> str:
    digest = hmac.new(
        settings.session_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_cookie() -> str:
    expires = int(time.time()) + SESSION_TTL
    payload = f"admin.{expires}"
    return f"{payload}.{_sign(payload)}"


def valid_cookie(value: str | None) -> bool:
    if not value:
        return False
    parts = value.split(".")
    if len(parts) != 3:
        return False
    subject, expires, signature = parts
    payload = f"{subject}.{expires}"
    if not hmac.compare_digest(signature, _sign(payload)):
        return False
    try:
        return int(expires) > int(time.time())
    except ValueError:
        return False


def check_password(candidate: str) -> bool:
    """Constant-time comparison against ADMIN_TOKEN."""
    expected = settings.admin_token
    if not expected:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def is_authenticated(request: Request) -> bool:
    return valid_cookie(request.cookies.get(COOKIE_NAME))


def set_session(response: Response) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_cookie(),
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=settings.public_base_url.startswith("https://"),
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    return RedirectResponse(url=f"/admin/login?next={target}", status_code=303)
