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

# Login throttling. nginx rate-limits /admin/login too, but the app must not
# depend on the proxy being configured: a single shared token is the only
# thing between the internet and every payout, so guessing has to be slow
# even if someone reaches uvicorn directly.
MAX_ATTEMPTS = 8
LOCKOUT_SECONDS = 300
_attempts: dict[str, list[float]] = {}


def client_key(request: Request) -> str:
    """Best-effort caller identity for throttling.

    X-Forwarded-For is only trusted for the last hop, which is our own nginx;
    a forged header can at worst lock out the forger.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def _recent_failures(key: str) -> list[float]:
    now = time.time()
    tries = [stamp for stamp in _attempts.get(key, []) if now - stamp < LOCKOUT_SECONDS]
    if tries:
        _attempts[key] = tries
    else:
        _attempts.pop(key, None)
    return tries


def is_locked_out(request: Request) -> int:
    """Seconds remaining before this caller may try again (0 = allowed)."""
    tries = _recent_failures(client_key(request))
    if len(tries) < MAX_ATTEMPTS:
        return 0
    return int(LOCKOUT_SECONDS - (time.time() - tries[0])) + 1


def record_failure(request: Request) -> None:
    key = client_key(request)
    _attempts.setdefault(key, []).append(time.time())


def clear_failures(request: Request) -> None:
    _attempts.pop(client_key(request), None)


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
