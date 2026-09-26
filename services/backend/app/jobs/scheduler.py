"""Scheduler: daily 18:01 PKT Jazz sync + catch-up + retention + report finalization."""

from __future__ import annotations

import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.config.logging import get_logger, setup_logging
from app.config.settings import get_settings

log = get_logger("scheduler")
PKT = ZoneInfo("Asia/Karachi")


def _today_pkt() -> date:
    return datetime.now(PKT).date()


def daily_sync_job() -> None:
    from app.ingestion.runner import scheduled_sync_window

    try:
        scheduled_sync_window()
    except Exception:
        log.exception("sync failed")


def catchup_job() -> None:
    daily_sync_job()


def retention_job() -> None:
    from app.retention.worker import cleanup_debug_artifacts, cleanup_expired_audio

    try:
        cleanup_expired_audio()
    except Exception:
        pass
    try:
        cleanup_debug_artifacts()
    except Exception:
        pass


def main() -> None:
    setup_logging("scheduler")
    s = get_settings()
    # Startup retries missed closed batches. Today's batch is released at 18:01.
    try:
        catchup_job()
    except Exception:
        pass
    sched = BackgroundScheduler(timezone=str(PKT))
    # daily 18:01 PKT main sync
    sched.add_job(daily_sync_job, "cron", hour=18, minute=1, id="jazz_daily_sync")
    sched.add_job(catchup_job, "interval", minutes=60, id="catchup")
    sched.add_job(retention_job, "cron", hour=2, minute=30, id="retention")
    sched.start()
    try:
        while True:
            time.sleep(s.SCHEDULER_CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        sched.shutdown()


if __name__ == "__main__":
    main()
