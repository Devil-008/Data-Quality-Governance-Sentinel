"""
Escalation & SLA Tracking Engine — DQ Sentinel
==============================================
Manages SLA-based escalations through the persona master hierarchy.
Executes background checks for active escalations and escalates when
acknowledgment/resolution deadlines are breached.
"""

import json
import datetime
from typing import List, Optional

from database.db_connection import fetch_all, fetch_one, execute
from utils.email_helper import send_email, render_template
from utils.common import logger

# ──────────────────────────────────────────────────────────────────────────────
# Public Interface
# ──────────────────────────────────────────────────────────────────────────────

def start_incident_escalation(alert_id: int, category: str, severity: str, dataset_id: Optional[int] = None, connector_id: Optional[int] = None) -> bool:
    """
    Register a newly created alert inside the SLA Escalation Tracking system.
    Immediately alerts the Level 1 persona users.
    """
    try:
        incident_type = category.upper() # QUALITY, PII, GOVERNANCE, etc.

        # Fetch Level 1 persona configuration
        p1 = fetch_one(
            "SELECT id FROM persona_master WHERE hierarchy_level = 1 AND is_active = 1 LIMIT 1"
        )
        p1_id = p1["id"] if p1 else 1  # default to persona 1

        # Insert tracking row
        tracking_id = execute(
            """INSERT INTO incident_escalation_tracking
               (incident_id, incident_type, severity, dataset_id, connector_id, current_level, current_persona_id, escalation_status, is_sla_breached, started_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                alert_id,
                incident_type,
                severity,
                dataset_id,
                connector_id,
                1,              # Level 1
                p1_id,          # Persona L1
                "active",
                0,              # Not breached initially
                datetime.datetime.utcnow(),
                datetime.datetime.utcnow()
            )
        )
        logger.info("Escalation tracking started for alert %s (Tracking ID: %s)", alert_id, tracking_id)

        # Immediate Level 1 notification
        _send_escalation_notification(tracking_id, level=1, persona_id=p1_id, is_initial=True)
        return True
    except Exception as exc:
        logger.error("start_incident_escalation failed: %s", exc)
        return False


def run_escalations() -> int:
    """
    Chron job execution (every 1 minute).
    Checks all active incident_escalation_tracking rows, stops them if alert status is resolved/acknowledged,
    or escalates if SLA timeframe is breached.
    """
    try:
        active_escalations = fetch_all(
            "SELECT * FROM incident_escalation_tracking WHERE escalation_status = 'active'"
        )
        if not active_escalations:
            return 0

        logger.info("Escalation Engine: Evaluating %s active incidents...", len(active_escalations))
        escalated_count = 0

        for esc in active_escalations:
            tracking_id = esc["id"]
            alert_id = esc["incident_id"]
            incident_type = esc["incident_type"]
            current_level = esc["current_level"]
            current_persona_id = esc["current_persona_id"]

            # 1. Check current alert status in database
            alert = fetch_one("SELECT status, title, message FROM alerts WHERE id = %s", (alert_id,))
            if not alert:
                # Alert deleted, stop tracking
                execute(
                    "UPDATE incident_escalation_tracking SET escalation_status = 'stopped', stopped_reason = 'Alert no longer exists', stopped_at = %s WHERE id = %s",
                    (datetime.datetime.utcnow(), tracking_id)
                )
                continue

            if alert["status"] in ("acknowledged", "resolved"):
                # Stop tracking since action has been taken
                execute(
                    "UPDATE incident_escalation_tracking SET escalation_status = 'stopped', stopped_reason = %s, stopped_at = %s WHERE id = %s",
                    (f"Alert marked as {alert['status']} in UI", datetime.datetime.utcnow(), tracking_id)
                )
                logger.info("Escalation stopped for tracking %s (Alert status: %s)", tracking_id, alert["status"])
                continue

            # 2. Retrieve SLA configuration
            sla_row = fetch_one(
                "SELECT sla_minutes FROM mail_escalation_config WHERE incident_type = %s AND persona_id = %s AND is_enabled = 1 LIMIT 1",
                (incident_type, current_persona_id)
            )
            # Default fallback of 60 minutes if no matching SLA config
            sla_minutes = sla_row["sla_minutes"] if sla_row else 60

            # Calculate minutes elapsed since last escalation/update
            last_update = esc["updated_at"]
            elapsed = datetime.datetime.utcnow() - last_update
            elapsed_minutes = elapsed.total_seconds() / 60.0

            if elapsed_minutes >= sla_minutes:
                # 3. SLA Breached - Perform Escalation
                logger.warning("SLA BREACHED on incident %s (Elapsed: %.1f mins, Allowed: %d mins)", tracking_id, elapsed_minutes, sla_minutes)

                # Fetch next hierarchical level config
                next_level = current_level + 1
                next_config = fetch_one(
                    """SELECT persona_id FROM mail_escalation_config
                       WHERE incident_type = %s AND hierarchy_level = %s AND is_enabled = 1 LIMIT 1""",
                    (incident_type, next_level)
                )

                if next_config:
                    next_persona_id = next_config["persona_id"]

                    # Log escalation step inside history
                    execute(
                        """INSERT INTO escalation_history
                           (escalation_tracking_id, from_level, to_level, from_persona_id, to_persona_id, escalation_reason, escalated_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (
                            tracking_id,
                            current_level,
                            next_level,
                            current_persona_id,
                            next_persona_id,
                            f"SLA Deadline of {sla_minutes} minutes exceeded",
                            datetime.datetime.utcnow()
                        )
                    )

                    # Update incident tracking status
                    execute(
                        """UPDATE incident_escalation_tracking
                           SET current_level = %s, current_persona_id = %s, is_sla_breached = 1, updated_at = %s
                           WHERE id = %s""",
                        (next_level, next_persona_id, datetime.datetime.utcnow(), tracking_id)
                    )

                    # Send Email to all users holding the next level persona
                    _send_escalation_notification(tracking_id, level=next_level, persona_id=next_persona_id, is_initial=False, prev_sla=sla_minutes)
                    escalated_count += 1
                else:
                    # Final level reached, complete escalation tracking
                    execute(
                        """UPDATE incident_escalation_tracking
                           SET escalation_status = 'completed', stopped_reason = 'Final escalation level reached', stopped_at = %s, updated_at = %s
                           WHERE id = %s""",
                        (datetime.datetime.utcnow(), datetime.datetime.utcnow(), tracking_id)
                    )
                    logger.info("Escalation sequence complete (final level) for tracking %s", tracking_id)

        return escalated_count
    except Exception as exc:
        logger.error("run_escalations failed: %s", exc)
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# Helper Notification Mechanics
# ──────────────────────────────────────────────────────────────────────────────

def _send_escalation_notification(tracking_id: int, level: int, persona_id: int, is_initial: bool = False, prev_sla: int = 0) -> bool:
    """Finds emails mapped to the target persona and fires a highly formatted email alert."""
    try:
        # Fetch alert details via tracking
        incident = fetch_one(
            """SELECT esc.*, a.title, a.message, a.ai_summary, a.ai_root_cause, a.ai_recommendation, d.dataset_name, c.name AS connector_name
               FROM incident_escalation_tracking esc
               JOIN alerts a ON a.id = esc.incident_id
               LEFT JOIN datasets d ON d.id = esc.dataset_id
               LEFT JOIN connectors c ON c.id = esc.connector_id
               WHERE esc.id = %s""",
            (tracking_id,)
        )
        if not incident:
            return False

        # Fetch persona name
        persona_row = fetch_one("SELECT persona_name FROM persona_master WHERE id = %s", (persona_id,))
        persona_name = persona_row["persona_name"] if persona_row else "Team Member"

        # Query all active emails mapped to this persona
        users = fetch_all(
            """SELECT u.email, u.username FROM users u
               JOIN persona_user_mapping pum ON pum.user_id = u.id
               WHERE pum.persona_id = %s AND pum.is_active = 1 AND u.email IS NOT NULL AND u.email != ''""",
            (persona_id,)
        )

        # Fallback to default alert recipient if no mapped users
        recipients = [u["email"].strip() for u in users if u["email"].strip()]
        if not recipients:
            default_row = fetch_one("SELECT setting_value FROM app_settings WHERE setting_key = 'alert_email_recipients'")
            if default_row and default_row["setting_value"]:
                recipients = [e.strip() for e in default_row["setting_value"].split(",") if e.strip()]

        if not recipients:
            logger.warning("No recipients mapped for escalation level %s (Persona: %s); skipping email.", level, persona_name)
            return False

        # Compose escalation context details
        subj_prefix = "[DQ Sentinel Alert]" if is_initial else "[DQ Sentinel Escalation]"
        subject = f"{subj_prefix} {incident['severity'].upper()} Incident: {incident['title']}"

        # HTML payload context
        html = render_template(
            "escalation_alert.html",
            incident=incident,
            level=level,
            persona_name=persona_name,
            is_initial=is_initial,
            prev_sla=prev_sla,
            header_style='style="background:#1e293b;color:#fff;padding:24px;"' if is_initial else 'style="background:#dc2626;color:#fff;padding:24px;"',
            now=datetime.datetime.utcnow()
        )

        return send_email(recipients, subject, html)
    except Exception as exc:
        logger.error("Failed to send escalation notification for tracking %s: %s", tracking_id, exc)
        return False
