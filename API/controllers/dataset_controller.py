# """Dataset controller — list, profile."""
# from typing import Optional
# from fastapi import APIRouter, Depends, HTTPException

# from database.db_connection import fetch_all, fetch_one
# from middleware.auth_middleware import get_current_user

# router = APIRouter(prefix="/api/datasets", tags=["datasets"])


# @router.get("/list")
# def list_datasets(
#     connector_id: Optional[int] = None,
#     q: Optional[str] = None,
#     user: dict = Depends(get_current_user),
# ):
#     sql = """
#         SELECT d.id, d.dataset_name, d.dataset_type, d.schema_name,
#                d.confidence_score, d.pii_percentage, d.outlier_count,
#                d.connector_id,
#                c.name AS connector_name, c.type AS connector_type
#         FROM datasets d
#         JOIN connectors c ON c.id = d.connector_id
#         WHERE 1=1
#     """
#     params = []
#     if connector_id:
#         sql += " AND d.connector_id = %s"
#         params.append(connector_id)
#     if q:
#         sql += " AND (d.dataset_name LIKE %s OR d.schema_name LIKE %s)"
#         params.extend([f"%{q}%", f"%{q}%"])
#     sql += " ORDER BY d.id DESC LIMIT 500"
#     return fetch_all(sql, tuple(params))


# @router.get("/profile/{dataset_id}")
# def get_profile(dataset_id: int, user: dict = Depends(get_current_user)):
#     ds = fetch_one(
#         """
#         SELECT d.*, c.name AS connector_name, c.type AS connector_type
#         FROM datasets d
#         JOIN connectors c ON c.id = d.connector_id
#         WHERE d.id = %s
#         """,
#         (dataset_id,),
#     )
#     if not ds:
#         raise HTTPException(status_code=404, detail="Dataset not found")
#     # Columns / history / runs return [] until the rule-book engine populates them
#     try:
#         columns = fetch_all(
#             "SELECT * FROM dataset_columns WHERE dataset_id=%s ORDER BY id",
#             (dataset_id,),
#         )
#     except Exception:
#         columns = []
#     try:
#         history = fetch_all(
#             "SELECT id, snapshot_json, captured_at FROM schema_history "
#             "WHERE dataset_id=%s ORDER BY captured_at DESC LIMIT 10",
#             (dataset_id,),
#         )
#     except Exception:
#         history = []
#     try:
#         runs = fetch_all(
#             "SELECT * FROM monitoring_runs WHERE dataset_id=%s "
#             "ORDER BY started_at DESC LIMIT 20",
#             (dataset_id,),
#         )
#     except Exception:
#         runs = []
#     return {
#         "dataset":        ds,
#         "columns":        columns,
#         "schema_history": history,
#         "runs":           runs,
#     }

"""Dataset controller — list datasets + return profile with full LLM report."""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from database.db_connection import fetch_all, fetch_one
from middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _extract_dashboard_fields(ai_json: Optional[str]) -> dict:
    """Pull RGB-bar + band fields out of ai_analysis_json for list view."""
    out = {
        "missing_data_pct":  None, "missing_data_band":  None,
        "junk_data_pct":     None, "junk_data_band":     None,
        "outlier_pct":       None, "outlier_band":       None,
        "asset_kind":        None,
    }
    if not ai_json:
        return out
    try:
        data = json.loads(ai_json)
        llm = data.get("llm") or {}
        out["missing_data_pct"]  = llm.get("missing_data_pct")
        out["missing_data_band"] = llm.get("missing_data_band")
        out["junk_data_pct"]     = llm.get("junk_data_pct")
        out["junk_data_band"]    = llm.get("junk_data_band")
        out["outlier_pct"]       = llm.get("outlier_pct")
        out["outlier_band"]      = llm.get("outlier_band")
        out["asset_kind"]        = llm.get("asset_kind")
    except Exception:
        pass
    return out


@router.get("/list")
def list_datasets(
    connector_id: Optional[int] = None,
    q: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    sql = """
        SELECT d.id, d.dataset_name, d.dataset_type, d.schema_name,
               d.confidence_score, d.pii_percentage, d.outlier_count,
               d.quality_score, d.last_profiled_at, d.ai_analysis_json,
               d.connector_id,
               c.name AS connector_name, c.type AS connector_type
        FROM datasets d
        JOIN connectors c ON c.id = d.connector_id
        WHERE 1=1
    """
    params = []
    if connector_id:
        sql += " AND d.connector_id = %s"
        params.append(connector_id)
    if q:
        sql += " AND (d.dataset_name LIKE %s OR d.schema_name LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY d.id DESC LIMIT 500"

    rows = fetch_all(sql, tuple(params))

    result = []
    for r in rows:
        dash = _extract_dashboard_fields(r.get("ai_analysis_json"))
        # Drop the heavy json from the list payload
        r_out = {k: v for k, v in r.items() if k != "ai_analysis_json"}
        r_out.update(dash)
        result.append(r_out)
    return result


@router.get("/profile/{dataset_id}")
def get_profile(dataset_id: int, user: dict = Depends(get_current_user)):
    ds = fetch_one(
        """
        SELECT d.*, c.name AS connector_name, c.type AS connector_type
        FROM datasets d
        JOIN connectors c ON c.id = d.connector_id
        WHERE d.id = %s
        """,
        (dataset_id,),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Parse the stored AI analysis JSON
    python_result = None
    llm_report = None
    if ds.get("ai_analysis_json"):
        try:
            data = json.loads(ds["ai_analysis_json"])
            python_result = data.get("python")
            llm_report    = data.get("llm")
        except Exception:
            pass

    try:
        columns = fetch_all(
            "SELECT * FROM dataset_columns WHERE dataset_id=%s ORDER BY id",
            (dataset_id,),
        )
    except Exception:
        columns = []
    try:
        history = fetch_all(
            "SELECT id, snapshot_json, captured_at FROM schema_history "
            "WHERE dataset_id=%s ORDER BY captured_at DESC LIMIT 10",
            (dataset_id,),
        )
    except Exception:
        history = []
    try:
        runs = fetch_all(
            "SELECT * FROM monitoring_runs WHERE dataset_id=%s "
            "ORDER BY started_at DESC LIMIT 20",
            (dataset_id,),
        )
    except Exception:
        runs = []

    return {
        "dataset":        ds,
        "python_result":  python_result,
        "llm_report":     llm_report,
        "columns":        columns,
        "schema_history": history,
        "runs":           runs,
    }