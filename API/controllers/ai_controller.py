"""AI controller — on-demand insights over real platform metrics."""
from fastapi import APIRouter, Depends, HTTPException

from database.db_connection import fetch_all, fetch_one
from middleware.auth_middleware import get_current_user
from utils.ai_helper import analyze_issue, summarize_monitoring_snapshot

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/health-summary")
def health_summary(user: dict = Depends(get_current_user)):
    cards = fetch_one(
        """
        SELECT
          (SELECT COUNT(*) FROM connectors) AS connectors,
          (SELECT COUNT(*) FROM connectors WHERE status='healthy') AS healthy,
          (SELECT COUNT(*) FROM datasets) AS datasets,
          (SELECT COUNT(*) FROM datasets WHERE contains_pii=1) AS pii,
          (SELECT COUNT(*) FROM alerts WHERE status='open') AS open_alerts,
          (SELECT COUNT(*) FROM alerts WHERE severity IN ('critical','high') AND status='open') AS high_open
        """
    ) or {}
    severity = fetch_all(
        "SELECT severity, COUNT(*) AS c FROM alerts GROUP BY severity"
    )
    text = summarize_monitoring_snapshot({"cards": cards, "severity": severity})
    return {"summary": text or "AI summary unavailable. Configure MISTRAL_API_KEY to enable."}


@router.get("/alert/{alert_id}")
def alert_analysis(alert_id: int, user: dict = Depends(get_current_user)):
    a = fetch_one(
        "SELECT a.*, c.name AS connector_name, d.dataset_name "
        "FROM alerts a LEFT JOIN connectors c ON c.id=a.connector_id "
        "LEFT JOIN datasets d ON d.id=a.dataset_id WHERE a.id=%s",
        (alert_id,),
    )
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    if a.get("ai_summary") or a.get("ai_recommendation"):
        return {
            "summary": a.get("ai_summary"),
            "root_cause": a.get("ai_root_cause"),
            "impact": a.get("ai_impact"),
            "recommendation": a.get("ai_recommendation"),
        }
    return analyze_issue({
        "category": a["category"],
        "severity": a["severity"],
        "title": a["title"],
        "message": a["message"],
        "connector": a.get("connector_name"),
        "dataset": a.get("dataset_name"),
    })
