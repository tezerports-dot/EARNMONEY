"""Admin sign-in: password + TOTP code, cookie session, CSRF token per session."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

import pyotp
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.config import get_settings
from app.db import get_db
from app.models import AdminSession, AdminUser
from app.security import crypto, passwords
from app.security.tokens import new_token, same, token_hash

COOKIE = "ff_admin"


class AdminLoginRequired(Exception):
    pass


class CsrfFailed(Exception):
    pass


@dataclass
class AdminContext:
    admin: AdminUser
    session: AdminSession

    @property
    def actor(self) -> str:
        return f"admin:{self.admin.username}"


def totp_for(admin: AdminUser) -> pyotp.TOTP:
    return pyotp.TOTP(crypto.decrypt(admin.totp_secret_ciphertext, f"totp:{admin.username}"))


async def create_admin(db: AsyncSession, username: str, password: str) -> tuple[AdminUser, str]:
    """Returns the admin and the TOTP provisioning URI to scan once."""
    secret = pyotp.random_base32()
    admin = AdminUser(
        username=username,
        password_hash=await passwords.hash_password(password),
        totp_secret_ciphertext=crypto.encrypt(secret, f"totp:{username}"),
    )
    db.add(admin)
    await db.flush()
    uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Future Fashion Admin")
    return admin, uri


async def sign_in(db: AsyncSession, username: str, password: str, code: str) -> tuple[AdminSession, str] | None:
    admin = (
        await db.execute(select(AdminUser).where(AdminUser.username == username[:64]))
    ).scalar_one_or_none()
    ok = await passwords.verify_password(admin.password_hash if admin else None, password)
    if not ok or admin is None or not admin.active:
        return None
    if not totp_for(admin).verify(code.strip(), valid_window=1):
        return None
    token = new_token("ffadm")
    session = AdminSession(
        admin_id=admin.id,
        token_hash=token_hash(token),
        csrf_token=secrets.token_urlsafe(24),
        expires_at=timeutil.now() + timedelta(hours=get_settings().admin_session_hours),
    )
    admin.last_login_at = timeutil.now()
    db.add(session)
    await db.flush()
    return session, token


async def current_admin(request: Request, db: AsyncSession = Depends(get_db)) -> AdminContext:
    token = request.cookies.get(COOKIE)
    if not token:
        raise AdminLoginRequired()
    async with db.begin():
        row = (
            await db.execute(
                select(AdminSession, AdminUser)
                .join(AdminUser, AdminUser.id == AdminSession.admin_id)
                .where(AdminSession.token_hash == token_hash(token))
            )
        ).first()
    if row is None:
        raise AdminLoginRequired()
    session, admin = row
    if session.revoked_at is not None or session.expires_at <= timeutil.now() or not admin.active:
        raise AdminLoginRequired()
    if request.method == "POST":
        form = await request.form()
        if not same(str(form.get("csrf", "")).encode(), session.csrf_token.encode()):
            raise CsrfFailed()
    return AdminContext(admin, session)
