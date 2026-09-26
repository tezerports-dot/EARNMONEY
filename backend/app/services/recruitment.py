"""Job openings the admin posts and the app lists. Plain content only."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RecruitmentPost


def post_json(post: RecruitmentPost) -> dict:
    return {
        "title": post.title,
        "location": post.location,
        "employment_type": post.employment_type,
        "description": post.description,
        "apply_url": post.apply_url,
        "apply_email": post.apply_email,
    }


async def list_open(db: AsyncSession) -> dict:
    rows = (
        (
            await db.execute(
                select(RecruitmentPost).where(RecruitmentPost.is_open).order_by(RecruitmentPost.sort_order, RecruitmentPost.id)
            )
        )
        .scalars()
        .all()
    )
    return {"posts": [post_json(p) for p in rows]}


async def list_all(db: AsyncSession) -> list[RecruitmentPost]:
    return list((await db.execute(select(RecruitmentPost).order_by(RecruitmentPost.sort_order, RecruitmentPost.id))).scalars())
