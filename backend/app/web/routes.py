"""Public web pages: referral landing, APK download, App Links, health checks."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import ids
from app.api.deps import client_ip
from app.config import get_settings
from app.db import get_db
from app.redis_client import redis
from app.security import ratelimit
from app.services import campaign, launch_gate

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


@router.get("/miniapp")
async def miniapp(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """The Telegram Mini App: shows an Adsgram ad, then records the launch pass.
    Runs inside Telegram, which passes the signed initData the page sends back."""
    async with db.begin():
        settings = await campaign.app_settings(db)
    return templates.TemplateResponse(
        request,
        "miniapp.html",
        {
            "company": settings.company_name,
            "adsgram_block_id": settings.adsgram_block_id or "",
            # An https link on our domain opens the app (App Links); the custom
            # scheme is the fallback. The app also re-checks on its own when it
            # comes back to the foreground.
            "return_url": "futurefashion://gate",
        },
        headers={
            "Cache-Control": "no-store",
            # The Mini App loads Telegram's SDK and Adsgram; allow just those.
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://telegram.org https://sad.adsgram.ai; "
                "connect-src 'self' https://sad.adsgram.ai; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; frame-src https://sad.adsgram.ai"
            ),
        },
    )


class MiniAppComplete(BaseModel):
    init_data: str = Field(max_length=4096)
    nonce: str | None = Field(default=None, max_length=64)


@router.post("/miniapp/complete")
async def miniapp_complete(body: MiniAppComplete, request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    await ratelimit.hit(ratelimit.MINIAPP_COMPLETE, client_ip(request))
    async with db.begin():
        result = await launch_gate.complete(db, body.init_data, body.nonce)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


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
