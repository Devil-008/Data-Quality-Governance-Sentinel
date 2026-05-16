"""Dashboard controller — all values computed dynamically from real metadata."""
import datetime
from fastapi import APIRouter, Depends

from database.db_connection import fetch_all, fetch_one
from middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(user: dict = Depends(get_current_user)):
    cards = fetch_one(
        """
        SELECT
          (SELECT COUNT(*) FROM connectors) AS total_connectors,
          (SELECT COUNT(*) FROM connectors WHERE status='Connected') AS healthy_connectors,
          (SELECT COUNT(*) FROM datasets) AS dataset_count,
          (SELECT COUNT(*) FROM datasets WHERE pii_percentage > 0) AS pii_datasets,
          (SELECT COUNT(*) FROM alerts WHERE severity IN ('critical','high') AND status='open') AS critical_alerts,
          (SELECT COUNT(*) FROM monitoring_jobs WHERE enabled=1) AS monitoring_jobs
        """
    ) or {}

    alerts = fetch_all(
        "SELECT a.*, c.name AS connector_name, d.dataset_name "
        "FROM alerts a LEFT JOIN connectors c ON c.id=a.connector_id "
        "LEFT JOIN datasets d ON d.id=a.dataset_id "
        "ORDER BY a.created_at DESC LIMIT 10"
    )

    activity = fetch_all(
        "SELECT r.*, c.name AS connector_name, d.dataset_name "
        "FROM monitoring_runs r "
        "LEFT JOIN connectors c ON c.id=r.connector_id "
        "LEFT JOIN datasets d ON d.id=r.dataset_id "
        "ORDER BY r.started_at DESC LIMIT 10"
    )

    health = fetch_all(
        "SELECT id, name, type, status, last_scanned_at FROM connectors ORDER BY id DESC"
    )

    # severity distribution (last 30 days)
    severity_dist = fetch_all(
        "SELECT severity, COUNT(*) AS c FROM alerts "
        "WHERE created_at >= %s GROUP BY severity",
        (datetime.datetime.utcnow() - datetime.timedelta(days=30),),
    )

    # alerts trend (last 7 days)
    trend = fetch_all(
        "SELECT DATE(created_at) AS day, COUNT(*) AS c FROM alerts "
        "WHERE created_at >= %s GROUP BY DATE(created_at) ORDER BY day",
        (datetime.datetime.utcnow() - datetime.timedelta(days=7),),
    )

    # category distribution
    category_dist = fetch_all(
        "SELECT category, COUNT(*) AS c FROM alerts "
        "WHERE created_at >= %s GROUP BY category",
        (datetime.datetime.utcnow() - datetime.timedelta(days=30),),
    )

    return {
        "cards": {
            "total_connectors": int(cards.get("total_connectors") or 0),
            "healthy_connectors": int(cards.get("healthy_connectors") or 0),
            "dataset_count": int(cards.get("dataset_count") or 0),
            "pii_datasets": int(cards.get("pii_datasets") or 0),
            "critical_alerts": int(cards.get("critical_alerts") or 0),
            "monitoring_jobs": int(cards.get("monitoring_jobs") or 0),
        },
        "recent_alerts": alerts,
        "recent_activity": activity,
        "connector_health": health,
        "charts": {
            "severity": severity_dist,
            "trend": trend,
            "category": category_dist,
        },
    }
