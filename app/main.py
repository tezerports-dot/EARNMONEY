"""Process entry point: one FastAPI app, N bot pollers, one daily job.

    uvicorn app.main:app --host 127.0.0.1 --port 8000

Nothing else runs. No docker, no celery, no redis — the bots are asyncio tasks
inside this same event loop, which is what keeps the whole thing inside a few
hundred megabytes on an Ampere A1.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.bots.manager import manager
from app.config import settings
from app.scheduler import daily_loop
from app.web import admin, public
from app.web.templating import render

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("app")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db.init_db()
    except db.SchemaMismatch as exc:
        log.error("=" * 70)
        log.error("Cannot start: %s", exc)
        log.error("=" * 70)
        raise
    log.info("database ready at %s", settings.db_path)

    if not settings.admin_token:
        log.warning("ADMIN_TOKEN is empty — the admin panel will refuse every login")
    elif len(settings.admin_token) < 16:
        log.warning(
            "ADMIN_TOKEN is only %d characters — it is the single password "
            "guarding every payout; use at least 24 random characters",
            len(settings.admin_token),
        )
    if settings.session_secret == settings.admin_token:
        log.warning(
            "SESSION_SECRET is unset and falling back to ADMIN_TOKEN — set it "
            "so rotating one does not invalidate the other"
        )
    if not settings.admin_ids:
        log.warning(
            "ADMIN_IDS is empty — nobody can drive the broadcast bot or the "
            "in-chat moderation commands"
        )

    await manager.start_all()
    scheduler_task = asyncio.create_task(daily_loop(), name="daily-scheduler")
    log.info("started %d bot(s)", len(manager.running_ids()))

    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await manager.stop_all()
        log.info("shut down cleanly")


app = FastAPI(
    title="Referral Platform",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(admin.router)
app.include_router(public.router)


@app.exception_handler(404)
async def not_found(request: Request, exc):  # noqa: ANN001
    if request.url.path.startswith("/admin"):
        return RedirectResponse(url="/admin", status_code=303)
    return render(request, "public/404.html", status_code=404)
