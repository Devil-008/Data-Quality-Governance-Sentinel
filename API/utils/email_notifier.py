"""
Email Notification Engine — DQ Sentinel
========================================
Handles:
  - Alert-triggered immediate emails (critical / high)
  - Hourly digest for medium alerts
  - Daily summary for low / info alerts
  - Category → recipient routing from app_settings
  - Deduplication (won't spam the same alert twice)
"""

import os
import json
import datetime
from typing import List, Optional

from database.db_connection import fetch_all, fetch_one, execute
from utils.email_helper import send_email, render_template
from utils.common import logger

# ──────────────────────────────────────────────────────────────────────────────
# Severity routing rules
# ──────────────────────────────────────────────────────────────────────────────
SEND_IMMEDIATELY = {"critical", "high"}
SEND_DIGEST_HOURLY = {"medium"}
SEND_DIGEST_DAILY = {"low", "info"}

# Category → app_settings key that holds the recipient list
CATEGORY_SETTING_MAP = {
    "quality":      "email_recipients_quality",
    "schema_drift": "email_recipients_schema_drift",
    "pii":          "email_recipients_pii",
    "governance":   "email_recipients_governance",
    "pipeline":     "email_recipients_pipeline",
    "cloud":        "email_recipients_cloud",
    "databricks":   "email_recipients_databricks",
}
DEFAULT_RECIPIENTS_KEY = "alert_email_recipients"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_setting(key: str) -> Optional[str]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE setting_key=%s", (key,)
    )
    return row["setting_value"] if row else None


def _get_recipients(category: str) -> List[str]:
    """Return list of recipient emails for a given alert category."""
    # Try category-specific list first
    category_key = CATEGORY_SETTING_MAP.get(category, "")
    raw = _get_setting(category_key) if category_key else None

    # Fall back to global default
    if not raw:
        raw = _get_setting(DEFAULT_RECIPIENTS_KEY)

    if not raw:
        return []

    return [e.strip() for e in raw.split(",") if e.strip()]


def _already_notified(alert_id: int) -> bool:
    """Check if we have already sent an email for this alert."""
    row = fetch_one(
        "SELECT id FROM email_notification_log WHERE alert_id=%s AND sent=1 LIMIT 1",
        (alert_id,),
    )
    return row is not None


def _log_notification(alert_id: int, recipients: List[str], sent: bool, error: str = ""):
    """Record the notification attempt in email_notification_log."""
    try:
        execute(
            """INSERT INTO email_notification_log
               (alert_id, recipients_json, sent, error_message, sent_at)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
               sent=%s, error_message=%s, sent_at=%s""",
            (
                alert_id,
                json.dumps(recipients),
                1 if sent else 0,
                error,
                datetime.datetime.utcnow(),
                1 if sent else 0,
                error,
                datetime.datetime.utcnow(),
            ),
        )
    except Exception as exc:
        logger.error("_log_notification DB error: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Template selection
# ──────────────────────────────────────────────────────────────────────────────

def _pick_template_and_subject(alert: dict):
    cat = (alert.get("category") or "").lower()
    sev = (alert.get("severity") or "info").upper()
    title = alert.get("title", "Alert")

    if cat == "schema_drift":
        return "schema_alert.html", f"[Schema Drift] {title}"
    elif cat in ("pii", "governance"):
        return "governance_alert.html", f"[{sev}] Governance: {title}"
    elif cat in ("pipeline", "cloud", "databricks"):
        return "pipeline_alert.html", f"[{sev}] Pipeline Issue: {title}"
    else:
        return "alert_email.html", f"[{sev}] {title}"


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def notify_alert(alert_id: int) -> bool:
    """
    Trigger email for a single alert (called right after alert is inserted).
    Only sends immediately for critical / high severity.
    Medium/low/info are queued for digest jobs.
    Returns True if email was sent.
    """
    alert = fetch_one(
        """SELECT a.*, c.name AS connector_name, d.dataset_name
           FROM alerts a
           LEFT JOIN connectors c ON c.id = a.connector_id
           LEFT JOIN datasets d ON d.id = a.dataset_id
           WHERE a.id = %s""",
        (alert_id,),
    )
    if not alert:
        logger.warning("notify_alert: alert %s not found", alert_id)
        return False

    severity = (alert.get("severity") or "info").lower()

    if severity not in SEND_IMMEDIATELY:
        logger.info(
            "notify_alert: alert %s severity=%s — will be handled by digest job",
            alert_id, severity,
        )
        return False  # digest jobs will handle it

    if _already_notified(alert_id):
        logger.info("notify_alert: alert %s already notified — skip", alert_id)
        return False

    recipients = _get_recipients(alert.get("category", ""))
    if not recipients:
        logger.warning("notify_alert: no recipients configured for alert %s", alert_id)
        return False

    tpl, subject = _pick_template_and_subject(alert)
    try:
        html = render_template(tpl, alert=alert)
    except Exception:
        html = render_template("alert_email.html", alert=alert)

    sent = send_email(recipients, subject, html)
    _log_notification(alert_id, recipients, sent, "" if sent else "send_email returned False")
    return sent


def send_medium_digest() -> int:
    """
    Hourly digest — collects all open/unnotified medium-severity alerts
    and sends one consolidated email.
    Returns number of alerts included.
    """
    alerts = fetch_all(
        """SELECT a.*, c.name AS connector_name, d.dataset_name
           FROM alerts a
           LEFT JOIN connectors c ON c.id = a.connector_id
           LEFT JOIN datasets d ON d.id = a.dataset_id
           LEFT JOIN email_notification_log enl ON enl.alert_id = a.id AND enl.sent = 1
           WHERE a.severity = 'medium'
             AND a.status = 'open'
             AND enl.id IS NULL
           ORDER BY a.created_at DESC
           LIMIT 50"""
    )

    if not alerts:
        return 0

    # Group by category for routing (send to union of all relevant recipients)
    all_recipients: set = set()
    for al in alerts:
        all_recipients.update(_get_recipients(al.get("category", "")))

    if not all_recipients:
        return 0

    subject = f"[DQ Sentinel] Medium Alert Digest — {len(alerts)} issue(s) found"
    html = render_template("digest_email.html", alerts=alerts, severity_label="Medium", now=datetime.datetime.utcnow())
    sent = send_email(list(all_recipients), subject, html)

    for al in alerts:
        _log_notification(al["id"], list(all_recipients), sent)

    logger.info("Medium digest: %d alerts sent=%s", len(alerts), sent)
    return len(alerts)


def send_daily_summary() -> int:
    """
    Daily digest — low + info severity alerts from the past 24 hours.
    Returns number of alerts included.
    """
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    alerts = fetch_all(
        """SELECT a.*, c.name AS connector_name, d.dataset_name
           FROM alerts a
           LEFT JOIN connectors c ON c.id = a.connector_id
           LEFT JOIN datasets d ON d.id = a.dataset_id
           LEFT JOIN email_notification_log enl ON enl.alert_id = a.id AND enl.sent = 1
           WHERE a.severity IN ('low', 'info')
             AND a.created_at >= %s
             AND enl.id IS NULL
           ORDER BY a.created_at DESC
           LIMIT 100""",
        (since,),
    )

    if not alerts:
        return 0

    recipients: set = set()
    for al in alerts:
        recipients.update(_get_recipients(al.get("category", "")))

    if not recipients:
        return 0

    subject = f"[DQ Sentinel] Daily Summary — {len(alerts)} low-priority items"
    html = render_template("digest_email.html", alerts=alerts, severity_label="Low / Info", now=datetime.datetime.utcnow())
    sent = send_email(list(recipients), subject, html)

    for al in alerts:
        _log_notification(al["id"], list(recipients), sent)

    logger.info("Daily summary: %d alerts sent=%s", len(alerts), sent)
    return len(alerts)
