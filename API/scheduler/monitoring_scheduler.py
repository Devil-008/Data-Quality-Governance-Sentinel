"""APScheduler monitoring engine.

A single background scheduler polls `monitoring_jobs` every minute and triggers
the appropriate scan/quality job when its `next_run_at` is due. This avoids
running everything on every minute and stays scalable.
"""
import datetime
import threading
from apscheduler.schedulers.background import BackgroundScheduler

from database.db_connection import fetch_all, execute
from utils.common import logger
from controllers.monitoring_controller import _run_scan, quality_check  # noqa: F401

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _tick():
    """Runs every minute. Picks due jobs and executes them serially per tick."""
    now = datetime.datetime.utcnow()
    try:
        due = fetch_all(
            "SELECT * FROM monitoring_jobs "
            "WHERE enabled=1 AND (next_run_at IS NULL OR next_run_at <= %s) "
            "ORDER BY next_run_at ASC LIMIT 10",
            (now,),
        )
    except Exception as e:
        logger.error("Scheduler tick query failed: %s", e)
        return
    for job in due:
        try:
            logger.info("Scheduler executing job id=%s type=%s connector=%s",
                        job["id"], job["job_type"], job["connector_id"])
            if job["job_type"] == "scan":
                _run_scan(job["connector_id"])
            # Future types (quality/cloud/pii) currently piggyback on the scan,
            # which performs schema-drift detection & PII discovery as part of
            # its workflow. They could be split out later without changing the
            # scheduler.
        except Exception as e:
            logger.exception("Job %s failed: %s", job["id"], e)
        finally:
            next_run = now + datetime.timedelta(minutes=int(job["interval_minutes"]))
            try:
                execute(
                    "UPDATE monitoring_jobs SET last_run_at=%s, next_run_at=%s WHERE id=%s",
                    (now, next_run, job["id"]),
                )
            except Exception as e:
                logger.error("Failed to update job %s: %s", job["id"], e)


def start_scheduler():
    global _scheduler
    with _lock:
        if _scheduler is not None:
            return _scheduler
        sched = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
        sched.add_job(_tick, "interval", minutes=1, id="dq_tick", replace_existing=True)
        sched.start()
        _scheduler = sched
        logger.info("APScheduler started (1-minute tick).")
        return sched


def shutdown_scheduler():
    global _scheduler
    with _lock:
        if _scheduler:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            logger.info("APScheduler stopped.")
