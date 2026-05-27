"""Alert controller — list, view, acknowledge, resolve alerts."""
import datetime
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user, require_roles

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/list")
def list_alerts(severity: Optional[str] = None,
                category: Optional[str] = None,
                status: Optional[str] = None,
                user: dict = Depends(get_current_user)):
    sql = (
        "SELECT a.*, c.name AS connector_name, d.dataset_name "
        "FROM alerts a LEFT JOIN connectors c ON c.id=a.connector_id "
        "LEFT JOIN datasets d ON d.id=a.dataset_id WHERE 1=1"
    )
    params = []
    if severity:
        sql += " AND a.severity=%s"; params.append(severity)
    if category:
        sql += " AND a.category=%s"; params.append(category)
    if status:
        sql += " AND a.status=%s"; params.append(status)
    sql += " ORDER BY a.created_at DESC LIMIT 500"
    return fetch_all(sql, tuple(params))


@router.get("/{alert_id}")
def get_alert(alert_id: int, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT a.*, c.name AS connector_name, d.dataset_name "
        "FROM alerts a LEFT JOIN connectors c ON c.id=a.connector_id "
        "LEFT JOIN datasets d ON d.id=a.dataset_id WHERE a.id=%s",
        (alert_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    # If AI summary is missing, generate it dynamically using the Knowledge Graph prompt!
    if not row.get("ai_summary"):
        from utils.ai_helper import analyze_issue
        ai_res = analyze_issue({
            "alert_id": row["id"],
            "category": row["category"],
            "severity": row["severity"],
            "title": row["title"],
            "message": row["message"],
            "connector": row.get("connector_name"),
            "dataset": row.get("dataset_name"),
        })
        row["ai_summary"] = ai_res.get("contextual_summary")
        row["ai_root_cause"] = ai_res.get("root_cause")
        row["ai_impact"] = ai_res.get("impact")
        row["ai_recommendation"] = ai_res.get("recommendation")
        row["confidence_score"] = ai_res.get("confidence_score")
        row["graph_nodes_to_update"] = ai_res.get("graph_nodes_to_update")
        
        # Save standard fields to DB so we don't query LLM every time
        try:
            execute("UPDATE alerts SET ai_summary=%s, ai_root_cause=%s, ai_impact=%s, ai_recommendation=%s WHERE id=%s",
                    (row["ai_summary"], row["ai_root_cause"], row["ai_impact"], row["ai_recommendation"], alert_id))
        except Exception as e:
            from utils.common import logger
            logger.error("Failed to update alert AI summary: %s", e)

    return row


class StatusIn(BaseModel):
    status: str


@router.patch("/{alert_id}/status")
def update_status(alert_id: int, body: StatusIn,
                  user: dict = Depends(require_roles("admin", "steward"))):
    if body.status not in ("open", "acknowledged", "resolved"):
        raise HTTPException(status_code=400, detail="Invalid status")
    if not fetch_one("SELECT id FROM alerts WHERE id=%s", (alert_id,)):
        raise HTTPException(status_code=404, detail="Alert not found")
    resolved_at = datetime.datetime.utcnow() if body.status == "resolved" else None
    execute(
        "UPDATE alerts SET status=%s, resolved_at=%s WHERE id=%s",
        (body.status, resolved_at, alert_id),
    )
    return {"updated": True}
