"""Shared Jinja2 environment for both routers."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import settings
from app.earnings import rates
from app.timeutil import current_month, human_ist

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals.update(
    # A callable, not a value: the rates are editable in the admin panel and
    # must not be frozen at import time.
    rates=rates,
    site_name="Referral Platform",
    public_base_url=settings.public_base_url,
    current_month=current_month,
)
templates.env.filters["ist"] = human_ist


def render(request, name: str, status_code: int = 200, **context):
    context.setdefault("request", request)
    return templates.TemplateResponse(request, name, context, status_code=status_code)
