"""Quality Check Scheduler - periodically run AI quality checks on new/unchecked datasets.

This scheduler runs every 10 minutes and:
1. Finds datasets without quality scores (quality_score IS NULL)
2. Runs AI-driven quality checks on them
3. Updates the quality_score and pii_categories
4. Creates alerts if quality < 70 or PII detected
"""

import datetime
import threading
from apscheduler.schedulers.background import BackgroundScheduler

from database.db_connection import fetch_all, execute, fetch_one
from utils.common import logger
from controllers.monitoring_controller import _run_ai_quality_checks
from utils.email_helper import send_alert_email

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _process_unchecked_datasets():
    """Find datasets without quality scores and run AI quality checks on them."""
    try:
        # Find datasets that haven't been checked yet (quality_score IS NULL)
        unchecked = fetch_all(
            "SELECT d.* FROM datasets d "
            "WHERE d.quality_score IS NULL "
            "LIMIT 10"  # Process up to 10 per tick to avoid overload
        )

        if not unchecked:
            logger.debug("No unchecked datasets found")
            return

        logger.info("Processing %d unchecked datasets", len(unchecked))

        for dataset in unchecked:
            try:
                dataset_id = dataset["id"]

                # Skip quality checks for datasets without columns (jobs/pipelines/clusters)
                if dataset.get("column_count", 0) == 0:
                    logger.info(
                        "Skipping quality check for schema-less dataset: id=%d, name=%s (type=%s)",
                        dataset_id,
                        dataset["dataset_name"],
                        dataset.get("dataset_type"),
                    )
                    # Set default score for schema-less items
                    execute(
                        "UPDATE datasets SET quality_score=%s WHERE id=%s",
                        (75.0, dataset_id),  # Neutral score for schema-less items
                    )
                    continue

                logger.info(
                    "Running quality checks on dataset: id=%d, name=%s",
                    dataset_id,
                    dataset["dataset_name"],
                )

                # Add connector_type from connector table
                connector = fetch_one(
                    "SELECT type FROM connectors WHERE id=%s",
                    (dataset["connector_id"],),
                )
                dataset["connector_type"] = (
                    connector.get("type") if connector else "unknown"
                )

                # Run AI quality checks
                issues, quality_score, _, pii_columns, pii_categories = (
                    _run_ai_quality_checks(dataset_id, dataset, sample_rows=None)
                )

                logger.info(
                    "AI checks returned: dataset=%d, score=%.1f, issues=%d, pii_cats=%s",
                    dataset_id,
                    quality_score,
                    len(issues),
                    pii_categories,
                )

                # Format PII categories
                pii_cats_str = ",".join(pii_categories) if pii_categories else None
                contains_pii = 1 if pii_categories else 0

                # Update dataset with quality score and PII info
                now = datetime.datetime.utcnow()
                execute(
                    "UPDATE datasets SET quality_score=%s, pii_categories=%s, contains_pii=%s, last_profiled_at=%s WHERE id=%s",
                    (quality_score, pii_cats_str, contains_pii, now, dataset_id),
                )

                logger.info(
                    "Quality check completed for dataset %d: score=%.1f, pii=%s",
                    dataset_id,
                    quality_score,
                    pii_cats_str or "none",
                )

                # Create alerts if needed
                if quality_score < 70:
                    # Quality alert
                    alert_title = f"Quality issues on {dataset['dataset_name']} (score {quality_score})"
                    alert_msg = f"Score: {quality_score}\n" + "\n".join(
                        issues[:3]
                    )  # First 3 issues

                    try:
                        execute(
                            "INSERT INTO alerts (connector_id, dataset_id, category, severity, title, message, status) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (
                                dataset["connector_id"],
                                dataset_id,
                                "quality",
                                "medium" if quality_score >= 60 else "high",
                                alert_title,
                                alert_msg,
                                "open",
                            ),
                        )
                        logger.info("Created quality alert for dataset %d", dataset_id)
                    except Exception as e:
                        logger.warning("Failed to create quality alert: %s", e)

                # Create PII alert if PII detected
                if pii_categories:
                    alert_title = f"PII detected in {dataset['dataset_name']}"
                    alert_msg = f"Detected PII categories: {', '.join(pii_categories)}\nColumns: {', '.join(pii_columns[:5])}"

                    try:
                        execute(
                            "INSERT INTO alerts (connector_id, dataset_id, category, severity, title, message, status) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (
                                dataset["connector_id"],
                                dataset_id,
                                "pii",
                                "high",
                                alert_title,
                                alert_msg,
                                "open",
                            ),
                        )
                        logger.info("Created PII alert for dataset %d", dataset_id)
                    except Exception as e:
                        logger.warning("Failed to create PII alert: %s", e)

            except Exception as e:
                logger.error("Error processing dataset %d: %s", dataset.get("id"), e)
                continue

    except Exception as e:
        logger.error("Quality check scheduler tick failed: %s", e)


def start():
    """Start the quality check scheduler."""
    global _scheduler
    with _lock:
        if _scheduler is not None:
            return

        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(
            _process_unchecked_datasets,
            "interval",
            minutes=1,  # Run every 1 minute
            id="quality_check_scheduler",
        )
        _scheduler.start()
        logger.info("Quality check scheduler started (1 min interval)")


def stop():
    """Stop the quality check scheduler."""
    global _scheduler
    with _lock:
        if _scheduler:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            logger.info("Quality check scheduler stopped")
