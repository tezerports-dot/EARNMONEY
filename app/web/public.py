"""The public dashboard: look up a UID, see everything about that account."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app import db
from app.earnings import leaderboard, report_for
from app.ids import normalise_uid
from app.timeutil import current_month, recent_months
from app.web.templating import render

router = APIRouter()


@router.get("/")
async def home(request: Request, q: str = ""):
    uid = normalise_uid(q) if q else None
    if uid and db.get_user_by_uid(uid) is not None:
        return RedirectResponse(url=f"/u/{uid}", status_code=303)

    error = ""
    if q and not uid:
        error = f"“{q}” is not a valid ID. IDs look like UID-A1B2C3."
    elif q:
        error = f"No account found for {uid}."

    return render(
        request,
        "public/index.html",
        error=error,
        query=q,
        stats=db.stats(),
        board=leaderboard(current_month(), limit=10),
        month=current_month(),
    )


@router.get("/u/{uid}")
async def user_page(request: Request, uid: str, month: str = ""):
    canonical = normalise_uid(uid)
    if canonical is None:
        return render(
            request,
            "public/index.html",
            error=f"“{uid}” is not a valid ID.",
            query=uid,
            stats=db.stats(),
            board=leaderboard(current_month(), limit=10),
            month=current_month(),
        )

    user = db.get_user_by_uid(canonical)
    if user is None:
        return render(
            request,
            "public/index.html",
            error=f"No account found for {canonical}.",
            query=uid,
            stats=db.stats(),
            board=leaderboard(current_month(), limit=10),
            month=current_month(),
        )

    month = month or current_month()
    report = report_for(user, month)
    memberships = db.memberships_of(int(user["id"]))
    pair = db.get_pair(int(user["pair_id"])) if user["pair_id"] else None
    withdrawal = db.get_withdrawal(int(user["id"]), month)

    return render(
        request,
        "public/user.html",
        user=user,
        report=report,
        memberships=memberships,
        pair=pair,
        month=month,
        months=recent_months(6),
        withdrawal=withdrawal,
        has_bank=db.get_bank_details(int(user["id"])) is not None,
    )


@router.get("/leaderboard")
async def board(request: Request, month: str = ""):
    month = month or current_month()
    return render(
        request,
        "public/leaderboard.html",
        board=leaderboard(month, limit=50),
        month=month,
        months=recent_months(6),
    )


@router.get("/how-it-works")
async def how_it_works(request: Request):
    return render(request, "public/how.html")


@router.get("/healthz")
async def healthz():
    from app.bots.manager import manager

    return {
        "status": "ok",
        "bots_running": len(manager.running_ids()),
        "month": current_month(),
        **db.stats(),
    }
