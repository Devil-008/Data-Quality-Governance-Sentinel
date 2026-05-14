"""Connector controller — CRUD, test-connection, and scan trigger.

Supports: mysql, mssql, azure, databricks, github.
Real connection libraries:
  - PyMySQL for MySQL
  - pyodbc for MSSQL (optional — falls back to a TCP probe if unavailable)
  - requests for Azure / Databricks / GitHub REST APIs
"""

import json
import socket
import datetime
import pymysql
import requests
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from database.db_connection import fetch_all, fetch_one, execute, db_cursor
from middleware.auth_middleware import get_current_user, require_roles
from utils.common import (
    logger,
    encrypt_config,
    decrypt_config,
    mask_secret,
    safe_json_loads,
)
from utils.constants import CONNECTOR_TYPES

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


# ---------- schemas -------------------------------------------------------
class ConnectorIn(BaseModel):
    name: str
    type: str
    config: Dict[str, Any]


class ConnectorTestIn(BaseModel):
    type: str
    config: Dict[str, Any]


# ---------- test connection ----------------------------------------------
def _test_mysql(c: Dict[str, Any]) -> Dict[str, Any]:
    conn = pymysql.connect(
        host=c.get("host"),
        port=int(c.get("port") or 3306),
        user=c.get("username"),
        password=c.get("password") or "",
        database=c.get("database"),
        connect_timeout=8,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()
        return {"ok": True, "version": (ver[0] if ver else "")}
    finally:
        conn.close()


def _test_mssql(c: Dict[str, Any]) -> Dict[str, Any]:
    """Try pyodbc; if missing, fall back to TCP probe."""
    server = c.get("server")
    port = int(c.get("port") or 1433)
    user = c.get("username")
    pwd = c.get("password") or ""
    database = c.get("database")
    try:
        import pyodbc  # type: ignore

        drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
        if not drivers:
            raise RuntimeError("No SQL Server ODBC driver installed")
        cs = (
            f"DRIVER={{{drivers[0]}}};SERVER={server},{port};"
            f"DATABASE={database};UID={user};PWD={pwd};Encrypt=no;TrustServerCertificate=yes;"
        )
        cn = pyodbc.connect(cs, timeout=8)
        cur = cn.cursor()
        cur.execute("SELECT @@VERSION")
        v = cur.fetchone()
        cn.close()
        return {"ok": True, "version": (v[0] if v else "")[:120]}
    except ImportError:
        # Fallback: just probe TCP socket
        with socket.create_connection((server, port), timeout=5):
            return {"ok": True, "version": "TCP probe (pyodbc not installed)"}


def _test_azure(c: Dict[str, Any]) -> Dict[str, Any]:
    """Acquire a token using client credentials flow."""
    tenant = c.get("tenant_id")
    cid = c.get("client_id")
    secret = c.get("client_secret")
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    r = requests.post(
        url,
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
            "scope": "https://management.azure.com/.default",
        },
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Azure auth failed: {r.status_code} {r.text[:200]}")
    return {
        "ok": True,
        "token": r.json().get("access_token"),
        "version": "Azure token acquired",
    }


def _test_azure_adf(c: Dict[str, Any]) -> Dict[str, Any]:
    auth = _test_azure(c)
    sub = c.get("subscription_id")
    rg = c.get("resource_group")
    adf = c.get("factory_name")
    url = f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.DataFactory/factories/{adf}?api-version=2018-06-01"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {auth['token']}"},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ADF not found: {r.status_code} {r.text[:200]}")
    return {"ok": True, "version": f"ADF {adf} reachable"}


def _test_databricks(c: Dict[str, Any]) -> Dict[str, Any]:
    url = c.get("workspace_url", "").rstrip("/") + "/api/2.0/clusters/list"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {c.get('token')}"},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Databricks failed: {r.status_code} {r.text[:200]}")
    return {"ok": True, "version": "Databricks workspace reachable"}


def _test_github(c: Dict[str, Any]) -> Dict[str, Any]:
    repo = (c.get("repository_url") or "").rstrip("/")
    # normalize: support both https://github.com/owner/repo and owner/repo
    if repo.startswith("http"):
        path = repo.split("github.com/", 1)[-1]
    else:
        path = repo
    url = f"https://api.github.com/repos/{path}"
    r = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {c.get('token')}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"GitHub failed: {r.status_code} {r.text[:200]}")
    return {"ok": True, "version": f"GitHub repo {path} reachable"}


def test_connection(conn_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if conn_type == "mysql":
        return _test_mysql(config)
    if conn_type == "mssql":
        return _test_mssql(config)
    if conn_type == "azure_adf":
        return _test_azure_adf(config)
    if conn_type == "databricks":
        return _test_databricks(config)
    if conn_type == "github":
        return _test_github(config)
    raise RuntimeError(f"Unsupported connector type: {conn_type}")


# ---------- helpers -------------------------------------------------------
def _mask_config_for_response(cfg: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(cfg)
    for f in ("password", "client_secret", "token", "secret"):
        if f in safe and safe[f]:
            safe[f] = mask_secret(str(safe[f]))
    return safe


def _serialize(row: dict) -> dict:
    cfg = decrypt_config(row.get("config_json") or "{}")
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "status": row["status"],
        "last_tested_at": row.get("last_tested_at"),
        "last_scanned_at": row.get("last_scanned_at"),
        "created_at": row.get("created_at"),
        "config": _mask_config_for_response(cfg),
    }


# ---------- routes --------------------------------------------------------
@router.get("/list")
def list_connectors(user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT id, name, type, status, last_tested_at, last_scanned_at, "
        "config_json, created_at FROM connectors ORDER BY id DESC"
    )
    return [_serialize(r) for r in rows]


@router.get("/{cid}")
def get_connector(cid: int, user: dict = Depends(get_current_user)):
    row = fetch_one(
        "SELECT id, name, type, status, last_tested_at, last_scanned_at, "
        "config_json, created_at FROM connectors WHERE id=%s",
        (cid,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Connector not found")
    return _serialize(row)


@router.post("/create")
def create_connector(
    body: ConnectorIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles("admin", "steward")),
):
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid connector type")
    # try real test first
    status = "unknown"
    try:
        test_connection(body.type, body.config)
        status = "Connected"
    except Exception as e:
        logger.warning("Create connector test failed: %s", e)
        status = "Connection Failed"
    enc = encrypt_config(body.config)
    try:
        new_id = execute(
            "INSERT INTO connectors (name, type, config_json, status, last_tested_at, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                body.name,
                body.type,
                enc,
                status,
                datetime.datetime.utcnow(),
                user["user_id"],
            ),
        )
    except pymysql.err.IntegrityError:
        raise HTTPException(status_code=409, detail="Connector name already exists")
    row = fetch_one("SELECT * FROM connectors WHERE id=%s", (new_id,))

    if status == "Connected":
        from controllers.monitoring_controller import _run_scan

        # Run scan in background
        background_tasks.add_task(_run_scan, new_id)
        logger.info("Scheduled auto-scan for connector %d in background", new_id)

    return _serialize(row)


@router.post("/test-connection")
def test_endpoint(body: ConnectorTestIn, user: dict = Depends(get_current_user)):
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid connector type")
    try:
        res = test_connection(body.type, body.config)
        return {"ok": True, "details": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/{cid}/test")
def test_existing(
    cid: int, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)
):
    row = fetch_one("SELECT type, config_json FROM connectors WHERE id=%s", (cid,))
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    cfg = decrypt_config(row["config_json"])
    try:
        res = test_connection(row["type"], cfg)
        execute(
            "UPDATE connectors SET status='Connected', last_tested_at=%s WHERE id=%s",
            (datetime.datetime.utcnow(), cid),
        )
        from controllers.monitoring_controller import _run_scan

        # Run scan in background
        background_tasks.add_task(_run_scan, cid)
        logger.info("Scheduled auto-scan for connector %d in background (test)", cid)
        return {"ok": True, "details": res}
    except Exception as e:
        execute(
            "UPDATE connectors SET status='Connection Failed', last_tested_at=%s WHERE id=%s",
            (datetime.datetime.utcnow(), cid),
        )
        return {"ok": False, "error": str(e)}


@router.put("/{cid}")
def update_connector(
    cid: int,
    body: ConnectorIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles("admin", "steward")),
):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (cid,)):
        raise HTTPException(status_code=404, detail="Connector not found")
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid connector type")
    status = "unknown"
    try:
        test_connection(body.type, body.config)
        status = "Connected"
    except Exception as e:
        logger.warning("Update connector test failed: %s", e)
        status = "Connection Failed"
    enc = encrypt_config(body.config)
    try:
        execute(
            "UPDATE connectors SET name=%s, type=%s, config_json=%s, status=%s, last_tested_at=%s WHERE id=%s",
            (body.name, body.type, enc, status, datetime.datetime.utcnow(), cid),
        )
    except pymysql.err.IntegrityError:
        raise HTTPException(status_code=409, detail="Connector name already exists")
    row = fetch_one("SELECT * FROM connectors WHERE id=%s", (cid,))

    if status == "Connected":
        from controllers.monitoring_controller import _run_scan

        # Run scan in background
        background_tasks.add_task(_run_scan, cid)
        logger.info("Scheduled auto-scan for connector %d in background (update)", cid)

    return _serialize(row)


@router.delete("/{cid}")
def delete_connector(cid: int, user: dict = Depends(require_roles("admin"))):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (cid,)):
        raise HTTPException(status_code=404, detail="Not found")
    execute("DELETE FROM connectors WHERE id=%s", (cid,))
    return {"deleted": True}
