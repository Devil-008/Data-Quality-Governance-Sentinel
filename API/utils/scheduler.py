
"""
Background scheduler for periodic connector rescans.
Detects new pipelines / datasets / files added in ADF, MySQL, Databricks etc.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from database.db_connection import fetch_all
from utils.common import logger

_scheduler: BackgroundScheduler | None = None


def _rescan_all_connectors():
    """Re-run discovery + auto-quality for every connector."""
    from controllers.connector_controller import run_scan

    try:
        rows = fetch_all(
            "SELECT id, name, type FROM connectors WHERE status='Connected'"
        )
        logger.info("Scheduler: rescanning %d connectors", len(rows))
        for r in rows:
            try:
                logger.info(
                    "Scheduler: rescanning connector %s (%s)",
                    r["id"], r["type"],
                )
                run_scan(r["id"])
            except Exception as e:
                logger.exception(
                    "Scheduler: rescan failed for connector %s: %s",
                    r["id"], e,
                )
        logger.info("Scheduler: rescan cycle complete")
    except Exception:
        logger.exception("Scheduler: rescan cycle failed")


def start_scheduler():
    """Start the background scheduler. Call this from main.py once on startup."""
    global _scheduler
    if _scheduler is not None:
        logger.warning("Scheduler already started")
        return

    _scheduler = BackgroundScheduler(
        timezone="UTC",
        job_defaults={
            "coalesce":      True,    # if missed runs pile up, run only the latest
            "max_instances": 1,       # never overlap with itself
            "misfire_grace_time": 300,
        },
    )

    # Rescan every 6 hours
    _scheduler.add_job(
        _rescan_all_connectors,
        trigger=IntervalTrigger(hours=6),
        id="rescan_all_connectors",
        name="Rescan all connectors (discover new pipelines / datasets)",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Background scheduler started — rescan every 6 hours")


def shutdown_scheduler():
    """Stop the scheduler cleanly. Call on app shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Background scheduler stopped")


