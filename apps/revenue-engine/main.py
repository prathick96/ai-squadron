"""
apps/revenue-engine/main.py
Revenue Engine — Day 2: sync revenue, scorecards, confidence report, SCALE/KILL.

Run once:  python -m apps.revenue_engine.main --mode once
Schedule:  python -m apps.revenue_engine.main --mode schedule
Sync only: python -m apps.revenue_engine.main --mode sync
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("squadron.revenue-engine")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


async def run_revenue_cycle() -> dict:
    from packages.revenue.cycle import run_day2_cycle

    return await run_day2_cycle()


async def run_sync_only() -> None:
    from packages.revenue.adsense_sync import sync_adsense
    from packages.revenue.stripe_sync import sync_stripe

    log.info("Revenue sync only")
    log.info("Stripe: %s", sync_stripe())
    log.info("AdSense: %s", sync_adsense())


def start_scheduler() -> object | None:
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            run_revenue_cycle,
            "cron",
            hour=0,
            minute=0,
            id="revenue_cycle",
            replace_existing=True,
        )
        scheduler.add_job(
            run_revenue_cycle,
            "cron",
            day_of_week="mon",
            hour=8,
            minute=0,
            id="confidence_weekly",
            replace_existing=True,
        )
        scheduler.start()
        log.info("Revenue Engine scheduler started (daily 00:00 UTC + Monday 08:00 UTC)")
        return scheduler
    except ImportError:
        log.warning("APScheduler not installed — run manually with --mode once")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Squadron Revenue Engine (Day 2)")
    parser.add_argument(
        "--mode",
        choices=["once", "schedule", "sync"],
        default="once",
    )
    args = parser.parse_args()

    if args.mode == "sync":
        asyncio.run(run_sync_only())
    elif args.mode == "once":
        result = asyncio.run(run_revenue_cycle())
        log.info("Cycle complete | storage=%s", result.get("storage_mode"))
    else:
        scheduler = start_scheduler()
        if scheduler:
            try:
                asyncio.get_event_loop().run_forever()
            except KeyboardInterrupt:
                scheduler.shutdown()
                log.info("Revenue Engine stopped")
