"""Public web pages: referral landing, APK download, App Links, health checks."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import ids
from app.config import get_settings
from app.db import get_db
from app.redis_client import redis
from app.services import campaign

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/r/{code}")
async def referral_landing(code: str, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Shows the code for people who don't have the app yet. Stores nothing:
    the referral is only bound when the new user signs up with the code."""
    normalized = ids.normalize_code(code[:20])
    async with db.begin():
        settings = await campaign.app_settings(db)
    package = get_settings().android_package_name
    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "company": settings.company_name,
            "code": normalized,
            "download_url": "/download",
            "app_link": f"intent://r/{normalized}#Intent;scheme=futurefashion;package={package};end" if normalized else None,
        },
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/download")
async def download(db: AsyncSession = Depends(get_db)) -> Response:
    async with db.begin():
        settings = await campaign.app_settings(db)
    if not settings.apk_download_url:
        return Response("The app download isn't available yet.", status_code=404, media_type="text/plain")
    return RedirectResponse(settings.apk_download_url, status_code=302)


@router.get("/.well-known/assetlinks.json")
async def assetlinks() -> JSONResponse:
    s = get_settings()
    statements = []
    if s.android_cert_sha256:
        statements.append(
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": s.android_package_name,
                    "sha256_cert_fingerprints": s.android_cert_sha256,
                },
            }
        )
    return JSONResponse(statements, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)) -> Response:
    try:
        async with db.begin():
            await db.execute(text("SELECT 1"))
        await redis().ping()
    except Exception:
        return JSONResponse({"ok": False}, status_code=503)
    return JSONResponse({"ok": True})
