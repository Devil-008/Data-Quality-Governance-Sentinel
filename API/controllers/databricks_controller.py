"""Databricks controller — uses connector credentials to query the Databricks
REST API.

Notes
-----
This platform monitors *pipelines* (Jobs + DLT pipelines) only — clusters are
not treated as datasets. The `/clusters/{connector_id}` route was removed.
"""

import requests
from fastapi import APIRouter, Depends, HTTPException

from database.db_connection import fetch_one
from middleware.auth_middleware import get_current_user
from utils.common import decrypt_config

router = APIRouter(prefix="/api/databricks", tags=["databricks"])


def _ctx(connector_id: int):
    row = fetch_one(
        "SELECT type, config_json FROM connectors WHERE id=%s", (connector_id,))
    if not row or row["type"] != "databricks":
        raise HTTPException(status_code=404, detail="Databricks connector not found")
    cfg = decrypt_config(row["config_json"])
    base = cfg.get("workspace_url", "").rstrip("/")
    headers = {"Authorization": f"Bearer {cfg.get('token')}"}
    return base, headers


@router.post("/jobs/{connector_id}")
def list_jobs(connector_id: int, user: dict = Depends(get_current_user)):
    """List Databricks jobs (treated as pipelines)."""
    base, headers = _ctx(connector_id)
    r = requests.get(f"{base}/api/2.1/jobs/list?limit=100",
                     headers=headers, timeout=20)
    if r.status_code != 200:
        r = requests.get(f"{base}/api/2.0/jobs/list", headers=headers, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    return r.json().get("jobs", [])


@router.post("/pipelines/{connector_id}")
def list_pipelines(connector_id: int, user: dict = Depends(get_current_user)):
    """List Delta Live Tables (DLT) pipelines."""
    base, headers = _ctx(connector_id)
    r = requests.get(f"{base}/api/2.0/pipelines?max_results=100",
                     headers=headers, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    body = r.json()
    return body.get("statuses") or body.get("pipelines") or []


@router.post("/runs/{connector_id}")
def list_runs(connector_id: int, user: dict = Depends(get_current_user)):
    """List recent job runs."""
    base, headers = _ctx(connector_id)
    r = requests.get(f"{base}/api/2.1/jobs/runs/list?limit=25",
                     headers=headers, timeout=20)
    if r.status_code != 200:
        r = requests.get(f"{base}/api/2.0/jobs/runs/list?limit=25",
                         headers=headers, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=r.text[:300])
    return r.json().get("runs", [])
