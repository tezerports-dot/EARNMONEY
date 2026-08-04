"""The one background clock in the process.

Two jobs, both cheap:

* the daily bank-details sweep at ``DAILY_PROMPT_HOUR`` IST,
* a month-rollover snapshot so the owners get last month's totals on the 1st.

Activity and earnings themselves are never precomputed — they are derived on
read, so a member who leaves at 14:59 is already inactive at 15:00 without any
job having run.
"""

from __future__ import annotations

import asyncio
import logging

from app import db
from app.bots.services import daily_bank_prompt
from app.bots.telegram_utils import notify_admins
from app.config import settings
from app.earnings import month_totals
from app.timeutil import current_month, seconds_until_ist_hour, shift_month

log = logging.getLogger("scheduler")


async def _run_daily_jobs() -> None:
    today_month = current_month()

    # The audit log and the warning counters are the only tables that would
    # otherwise grow without bound; everything else is one row per user.
    try:
        pruned = db.prune_events() + db.prune_warnings()
        if pruned:
            log.info("pruned %d stale rows", pruned)
    except Exception:  # noqa: BLE001
        log.exception("pruning failed")

    # Refresh the cached dashboard aggregates. Below LIVE_AGGREGATE_LIMIT the
    # panel computes them live anyway and this is just a cheap no-op.
    try:
        db.refresh_snapshots()
    except Exception:  # noqa: BLE001
        log.exception("snapshot refresh failed")

    try:
        result = await daily_bank_prompt()
        log.info("daily prompt: %s", result)
    except Exception:  # noqa: BLE001
        log.exception("daily bank prompt failed")

    # First run of a new IST month: report what the closed month came to.
    last_reported = db.get_setting("last_month_report", "")
    if last_reported != today_month:
        db.set_setting("last_month_report", today_month)
        if last_reported:
            previous = shift_month(today_month, -1)
            try:
                totals = month_totals(previous)
                db.log_event("month_snapshot", None, str(totals))
                await notify_admins(
                    f"📅 <b>{previous} closed</b>\n"
                    f"Referrers with active referrals: {totals['earning_referrers']}\n"
                    f"Active referred users: {totals['active_referred']}\n"
                    f"Total payable: ₹{totals['total_inr']:g}\n\n"
                    "Export the bank file from the admin panel when you are "
                    "ready to transfer."
                )
            except Exception:  # noqa: BLE001
                log.exception("month snapshot failed")


async def daily_loop() -> None:
    """Sleep until the configured IST hour, run the jobs, repeat."""
    hour = settings.daily_prompt_hour
    while True:
        delay = seconds_until_ist_hour(hour)
        log.info("next daily sweep in %.0f minutes", delay / 60)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        await _run_daily_jobs()
