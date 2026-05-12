"""Dataset controller — list datasets, profile, get columns."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from database.db_connection import fetch_all, fetch_one
from middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("/list")
def list_datasets(connector_id: Optional[int] = None,
                  contains_pii: Optional[bool] = None,
                  q: Optional[str] = None,
                  user: dict = Depends(get_current_user)):
    sql = (
        "SELECT d.*, c.name AS connector_name, c.type AS connector_type "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE 1=1"
    )
    params = []
    if connector_id:
        sql += " AND d.connector_id=%s"; params.append(connector_id)
    if contains_pii is not None:
        sql += " AND d.contains_pii=%s"; params.append(1 if contains_pii else 0)
    if q:
        sql += " AND (d.dataset_name LIKE %s OR d.schema_name LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY d.id DESC LIMIT 500"
    return fetch_all(sql, tuple(params))


@router.get("/profile/{dataset_id}")
def get_profile(dataset_id: int, user: dict = Depends(get_current_user)):
    ds = fetch_one(
        "SELECT d.*, c.name AS connector_name, c.type AS connector_type "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
        (dataset_id,),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    columns = fetch_all(
        "SELECT * FROM dataset_columns WHERE dataset_id=%s ORDER BY id", (dataset_id,)
    )
    history = fetch_all(
        "SELECT id, snapshot_json, captured_at FROM schema_history "
        "WHERE dataset_id=%s ORDER BY captured_at DESC LIMIT 10",
        (dataset_id,),
    )
    runs = fetch_all(
        "SELECT * FROM monitoring_runs WHERE dataset_id=%s ORDER BY started_at DESC LIMIT 20",
        (dataset_id,),
    )
    return {"dataset": ds, "columns": columns, "schema_history": history, "runs": runs}
