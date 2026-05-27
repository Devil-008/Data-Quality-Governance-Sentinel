"""Quality Check Scheduler - periodically run AI quality checks on new/unchecked datasets.

This scheduler runs every 10 minutes and:
1. Finds datasets without quality scores (quality_score IS NULL)
2. Runs AI-driven quality checks on them
3. Updates the quality_score and pii_categories
4. Creates alerts if quality < 70 or PII detected
"""

import datetime
import threading
import json
# pyrefly: ignore [missing-import]
from apscheduler.schedulers.background import BackgroundScheduler

from database.db_connection import fetch_all, execute, fetch_one
from utils.common import logger
from controllers.monitoring_controller import run_quality_for_dataset
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

                # Run AI quality checks via controller
                run_quality_for_dataset(dataset_id)
                
                # Fetch updated dataset for alert evaluation
                updated = fetch_one("SELECT * FROM datasets WHERE id=%s", (dataset_id,))
                if not updated:
                    continue
                
                quality_score = updated.get("quality_score") or 100.0
                
                # Parse analysis JSON to get failed rules and PII info
                ai_json = updated.get("ai_analysis_json")
                ai_res = {}
                if ai_json:
                    try:
                        ai_res = json.loads(ai_json)
                    except:
                        pass
                
                py_result = ai_res.get("python", {})
                llm_res = ai_res.get("llm", {})
                
                summary = llm_res.get("executive_summary", "Check completed")
                failed_rules = py_result.get("failed_rules", [])
                severity = py_result.get("severity", "medium")
                pii_categories = py_result.get("pii_columns", [])

                logger.info(
                    "Quality check completed for dataset %d: score=%.1f",
                    dataset_id,
                    quality_score,
                )

                # Create alerts if needed
                if quality_score < 85:
                    # Quality alert
                    severity = ai_res.get("severity", "medium")
                    alert_title = f"Quality issues on {dataset['dataset_name']} (score {quality_score})"
                    failed_rules = ai_res.get("failed_rules", [])
                    alert_msg = f"Score: {quality_score}\nSummary: {summary}\n"
                    if failed_rules:
                        alert_msg += "Failed Rules: " + "; ".join([f"{r.get('rule_type')}: {r.get('reason')}" for r in failed_rules[:3]])

                    try:
                        alert_id = execute(
                            "INSERT INTO alerts (connector_id, dataset_id, category, severity, title, message, status) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (
                                dataset["connector_id"],
                                dataset_id,
                                "quality",
                                severity,
                                alert_title,
                                alert_msg,
                                "open",
                            ),
                        )
                        logger.info("Created quality alert for dataset %d (ID: %s)", dataset_id, alert_id)
                        
                        try:
                            from utils.graph_helper import graph_db
                            graph_db.insert_alert(alert_id, alert_title, alert_msg, dataset_id)
                            for r in failed_rules:
                                rule_name = r.get("rule_type") or r.get("rule")
                                if rule_name:
                                    graph_db.insert_rule(rule_name, 0, f"Rule: {rule_name}")
                                    graph_db.create_edge("VIOLATES", f"Alert/{alert_id}", f"Rule/{rule_name}")
                        except Exception as ge:
                            logger.error("Graph DB alert insert failed: %s", ge)

                        try:
                            from utils.escalation_engine import start_incident_escalation
                            start_incident_escalation(
                                alert_id=alert_id,
                                category="quality",
                                severity=severity,
                                dataset_id=dataset_id,
                                connector_id=dataset["connector_id"]
                            )
                        except Exception as ne:
                            logger.error("Escalation trigger failed for quality alert %s: %s", alert_id, ne)
                    except Exception as e:
                        logger.warning("Failed to create quality alert: %s", e)

                # Create PII alert if PII detected
                if pii_categories:
                    alert_title = f"PII detected in {dataset['dataset_name']}"
                    alert_msg = f"Detected PII categories: {', '.join(pii_categories)}"

                    try:
                        alert_id = execute(
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
                        logger.info("Created PII alert for dataset %d (ID: %s)", dataset_id, alert_id)
                        
                        try:
                            from utils.graph_helper import graph_db
                            graph_db.insert_alert(alert_id, alert_title, alert_msg, dataset_id)
                            for pii_cat in pii_categories:
                                graph_db.insert_rule(pii_cat, 0, f"PII Category: {pii_cat}")
                                graph_db.create_edge("VIOLATES", f"Alert/{alert_id}", f"Rule/{pii_cat}")
                        except Exception as ge:
                            logger.error("Graph DB PII alert insert failed: %s", ge)

                        try:
                            from utils.escalation_engine import start_incident_escalation
                            start_incident_escalation(
                                alert_id=alert_id,
                                category="pii",
                                severity="high",
                                dataset_id=dataset_id,
                                connector_id=dataset["connector_id"]
                            )
                        except Exception as ne:
                            logger.error("Escalation trigger failed for PII alert %s: %s", alert_id, ne)
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
