"""Shared shapes for user data returned by the API."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timeutil
from app.models import User
from app.phone import mask_phone


async def me_json(db: AsyncSession, user: User) -> dict:
    referred_by = None
    if user.referrer_id is not None:
        referred_by = (await db.execute(select(User.public_id).where(User.id == user.referrer_id))).scalar_one()
    active = user.status == "ACTIVE"
    return {
        "public_id": user.public_id,
        "phone_masked": mask_phone(user.phone),
        "status": user.status,
        "referral_code": user.public_id if active else None,
        "referred_by": referred_by,
        "created_at": timeutil.iso(user.created_at),
        "verified_at": timeutil.iso(user.verified_at),
    }
