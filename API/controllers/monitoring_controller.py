"""Monitoring controller — scan source systems, run quality / drift / PII checks.

This is where the real engine lives. Everything is driven by actual connector
queries; no hardcoded datasets. Results are persisted into datasets,
dataset_columns, schema_history, monitoring_runs and alerts.
"""
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple
import pymysql
import requests

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from database.db_connection import fetch_all, fetch_one, execute, db_cursor
from middleware.auth_middleware import get_current_user, require_roles
from utils.common import (
    logger, decrypt_config, detect_pii_in_column_name,
    detect_pii_in_samples, safe_json_dumps,
)
from utils.ai_helper import analyze_issue
from utils.email_helper import send_alert_email
from controllers.connector_controller import test_connection

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

def _scan_azure_adf(conn_row: dict) -> Dict[str, Any]:

    cfg = decrypt_config(conn_row["config_json"])

    tenant = cfg.get("tenant_id")
    cid = cfg.get("client_id")
    secret = cfg.get("client_secret")

    discovered = []

    token_r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
            "scope": "https://management.azure.com/.default",
        },
        timeout=15,
    )

    if token_r.status_code != 200:
        raise RuntimeError(token_r.text)

    tok = token_r.json()["access_token"]

    base = (
        f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
        f"/resourceGroups/{cfg['resource_group']}"
        f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
    )

    headers = {
        "Authorization": f"Bearer {tok}"
    }

    # DATASETS
    ds_r = requests.get(
        f"{base}/datasets?api-version=2018-06-01",
        headers=headers,
        timeout=20,
    )

    if ds_r.status_code == 200:
        for ds in ds_r.json().get("value", []):

            props = ds.get("properties", {})

            discovered.append({
                "schema": "adf",
                "name": ds.get("name"),
                "type": "dataset",
                "row_count": None,
                "columns": [],
            })

    # PIPELINES
    pl_r = requests.get(
        f"{base}/pipelines?api-version=2018-06-01",
        headers=headers,
        timeout=20,
    )

    if pl_r.status_code == 200:
        for p in pl_r.json().get("value", []):

            discovered.append({
                "schema": "adf",
                "name": p.get("name"),
                "type": "pipeline",
                "row_count": None,
                "columns": [],
            })

    return {"datasets": discovered}
# ---------- low-level source readers --------------------------------------
def _mysql_conn(cfg: Dict[str, Any]):
    return pymysql.connect(
        host=cfg.get("host"),
        port=int(cfg.get("port") or 3306),
        user=cfg.get("username"),
        password=cfg.get("password") or "",
        database=cfg.get("database"),
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _scan_mysql(conn_row: dict) -> Dict[str, Any]:
    cfg = decrypt_config(conn_row["config_json"])
    db_name = cfg.get("database")
    discovered: List[dict] = []
    cn = _mysql_conn(cfg)
    try:
        with cn.cursor() as cur:
            # Tables and views
            cur.execute(
                "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, TABLE_ROWS "
                "FROM information_schema.tables "
                "WHERE TABLE_SCHEMA = %s",
                (db_name,),
            )
            tables = cur.fetchall()
            for t in tables:
                schema = t["TABLE_SCHEMA"]
                tname = t["TABLE_NAME"]
                ttype = "view" if t["TABLE_TYPE"] == "VIEW" else "table"
                # accurate row count for tables (TABLE_ROWS is approximate)
                row_count = None
                try:
                    cur.execute(f"SELECT COUNT(*) AS c FROM `{schema}`.`{tname}`")
                    row_count = (cur.fetchone() or {}).get("c")
                except Exception as e:
                    logger.debug("Row count failed for %s.%s: %s", schema, tname, e)
                # columns
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
                    "FROM information_schema.columns "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "ORDER BY ORDINAL_POSITION",
                    (schema, tname),
                )
                cols = cur.fetchall()
                discovered.append({
                    "schema": schema,
                    "name": tname,
                    "type": ttype,
                    "row_count": row_count,
                    "columns": [
                        {
                            "name": c["COLUMN_NAME"],
                            "type": c["DATA_TYPE"],
                            "nullable": c["IS_NULLABLE"] == "YES",
                        }
                        for c in cols
                    ],
                })
    finally:
        cn.close()
    return {"datasets": discovered}


def _scan_github(conn_row: dict) -> Dict[str, Any]:
    cfg = decrypt_config(conn_row["config_json"])
    repo = (cfg.get("repository_url") or "").rstrip("/")
    if repo.startswith("http"):
        path = repo.split("github.com/", 1)[-1]
    else:
        path = repo
    headers = {"Authorization": f"Bearer {cfg.get('token')}", "Accept": "application/vnd.github+json"}
    discovered = []
    # workflows
    try:
        r = requests.get(f"https://api.github.com/repos/{path}/actions/workflows", headers=headers, timeout=15)
        if r.status_code == 200:
            for wf in r.json().get("workflows", []):
                discovered.append({
                    "schema": "actions",
                    "name": wf.get("name") or wf.get("path"),
                    "type": "workflow",
                    "row_count": None,
                    "columns": [],
                })
    except Exception as e:
        logger.warning("GitHub workflows fetch failed: %s", e)
    return {"datasets": discovered}


def _scan_databricks(conn_row: dict) -> Dict[str, Any]:
    cfg = decrypt_config(conn_row["config_json"])
    base = cfg.get("workspace_url", "").rstrip("/")
    headers = {"Authorization": f"Bearer {cfg.get('token')}"}
    discovered = []
    try:
        r = requests.get(f"{base}/api/2.0/jobs/list", headers=headers, timeout=15)
        if r.status_code == 200:
            for j in r.json().get("jobs", []):
                settings = j.get("settings") or {}
                discovered.append({
                    "schema": "jobs",
                    "name": settings.get("name") or f"job_{j.get('job_id')}",
                    "type": "job",
                    "row_count": None,
                    "columns": [],
                })
    except Exception as e:
        logger.warning("Databricks jobs failed: %s", e)
    try:
        r = requests.get(f"{base}/api/2.0/clusters/list", headers=headers, timeout=15)
        if r.status_code == 200:
            for cl in r.json().get("clusters", []):
                discovered.append({
                    "schema": "clusters",
                    "name": cl.get("cluster_name") or cl.get("cluster_id"),
                    "type": "cluster",
                    "row_count": None,
                    "columns": [],
                })
    except Exception as e:
        logger.warning("Databricks clusters failed: %s", e)
    return {"datasets": discovered}


def _scan_azure(conn_row: dict) -> Dict[str, Any]:
    cfg = decrypt_config(conn_row["config_json"])
    tenant = cfg.get("tenant_id")
    cid = cfg.get("client_id")
    secret = cfg.get("client_secret")
    sub = cfg.get("subscription_id")
    discovered = []
    try:
        token_r = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials", "client_id": cid,
                "client_secret": secret, "scope": "https://management.azure.com/.default",
            }, timeout=15,
        )
        if token_r.status_code != 200:
            raise RuntimeError(f"Token: {token_r.text[:200]}")
        tok = token_r.json()["access_token"]
        # list resource groups
        rg = requests.get(
            f"https://management.azure.com/subscriptions/{sub}/resourcegroups?api-version=2021-04-01",
            headers={"Authorization": f"Bearer {tok}"}, timeout=15,
        )
        if rg.status_code == 200:
            for g in rg.json().get("value", []):
                discovered.append({
                    "schema": g.get("location", ""),
                    "name": g.get("name"),
                    "type": "blob",  # we group cloud resources as 'blob' container
                    "row_count": None,
                    "columns": [],
                })
    except Exception as e:
        logger.warning("Azure scan failed: %s", e)
    return {"datasets": discovered}


# ---------- persistence helpers -------------------------------------------
def _upsert_dataset(connector_id: int, ds: dict) -> int:
    existing = fetch_one(
        "SELECT id FROM datasets WHERE connector_id=%s AND IFNULL(schema_name,'')=%s AND dataset_name=%s",
        (connector_id, ds.get("schema") or "", ds.get("name")),
    )
    cols = ds.get("columns") or []
    if existing:
        execute(
            "UPDATE datasets SET dataset_type=%s, row_count=%s, column_count=%s, "
            "last_profiled_at=%s WHERE id=%s",
            (ds.get("type", "table"), ds.get("row_count"), len(cols),
             datetime.datetime.utcnow(), existing["id"]),
        )
        return existing["id"]
    return execute(
        "INSERT INTO datasets (connector_id, schema_name, dataset_name, dataset_type, "
        "row_count, column_count, last_profiled_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (connector_id, ds.get("schema"), ds.get("name"), ds.get("type", "table"),
         ds.get("row_count"), len(cols), datetime.datetime.utcnow()),
    )


def _refresh_columns(dataset_id: int, cols: List[dict]) -> List[dict]:
    """Replace columns and return PII categories detected by name hints."""
    execute("DELETE FROM dataset_columns WHERE dataset_id=%s", (dataset_id,))
    pii_categories = []
    for c in cols:
        cat = detect_pii_in_column_name(c["name"])
        is_pii = 1 if cat else 0
        if cat:
            pii_categories.append(cat)
        execute(
            "INSERT INTO dataset_columns (dataset_id, column_name, data_type, is_nullable, "
            "is_pii, pii_category) VALUES (%s, %s, %s, %s, %s, %s)",
            (dataset_id, c["name"], c.get("type"), 1 if c.get("nullable") else 0,
             is_pii, cat or None),
        )
    if pii_categories:
        cats = ",".join(sorted(set(pii_categories)))
        execute(
            "UPDATE datasets SET contains_pii=1, pii_categories=%s WHERE id=%s",
            (cats, dataset_id),
        )
    return pii_categories


def _capture_schema_history(dataset_id: int, cols: List[dict]):
    snap = json.dumps([
        {"name": c["name"], "type": c.get("type"), "nullable": c.get("nullable")}
        for c in cols
    ])
    execute(
        "INSERT INTO schema_history (dataset_id, snapshot_json) VALUES (%s, %s)",
        (dataset_id, snap),
    )


def _detect_schema_drift(dataset_id: int) -> Optional[Dict[str, Any]]:
    rows = fetch_all(
        "SELECT snapshot_json, captured_at FROM schema_history WHERE dataset_id=%s "
        "ORDER BY captured_at DESC LIMIT 2",
        (dataset_id,),
    )
    if len(rows) < 2:
        return None
    new = json.loads(rows[0]["snapshot_json"])
    old = json.loads(rows[1]["snapshot_json"])
    new_map = {c["name"]: c for c in new}
    old_map = {c["name"]: c for c in old}
    added = [n for n in new_map if n not in old_map]
    removed = [n for n in old_map if n not in new_map]
    changed = []
    for name in new_map:
        if name in old_map and new_map[name].get("type") != old_map[name].get("type"):
            changed.append({
                "name": name,
                "old_type": old_map[name].get("type"),
                "new_type": new_map[name].get("type"),
            })
    if added or removed or changed:
        return {"added": added, "removed": removed, "type_changes": changed}
    return None


def _create_alert(category: str, severity: str, title: str, message: str,
                  connector_id: Optional[int] = None, dataset_id: Optional[int] = None,
                  ai_payload: Optional[dict] = None) -> int:
    ai = {}
    try:
        if ai_payload is not None:
            ai = analyze_issue(ai_payload) or {}
    except Exception as e:
        logger.warning("AI enrichment failed: %s", e)
    aid = execute(
        "INSERT INTO alerts (connector_id, dataset_id, category, severity, title, message, "
        "ai_summary, ai_root_cause, ai_impact, ai_recommendation) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (connector_id, dataset_id, category, severity, title, message,
         ai.get("summary"), ai.get("root_cause"), ai.get("impact"), ai.get("recommendation")),
    )
    # in-app notifications (broadcast to all active users)
    users = fetch_all("SELECT id FROM users WHERE is_active=1")
    for u in users:
        execute(
            "INSERT INTO notifications (user_id, alert_id, title, message) VALUES (%s, %s, %s, %s)",
            (u["id"], aid, title, message[:500]),
        )
    # email
    recipients = _alert_recipients()
    if recipients:
        try:
            send_alert_email(recipients, {
                "category": category, "severity": severity,
                "title": title, "message": message,
                "ai_summary": ai.get("summary"), "ai_root_cause": ai.get("root_cause"),
                "ai_impact": ai.get("impact"), "ai_recommendation": ai.get("recommendation"),
                "created_at": datetime.datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.warning("Alert email failed: %s", e)
    return aid


def _alert_recipients() -> List[str]:
    row = fetch_one("SELECT setting_value FROM app_settings WHERE setting_key='alert_email_recipients'")
    raw = (row or {}).get("setting_value", "") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


# ---------- public scan entry ---------------------------------------------
def _run_scan(connector_id: int) -> Dict[str, Any]:
    conn_row = fetch_one("SELECT * FROM connectors WHERE id=%s", (connector_id,))
    if not conn_row:
        raise RuntimeError("Connector not found")
    ctype = conn_row["type"]
    run_id = execute(
        "INSERT INTO monitoring_runs (connector_id, run_type, status, started_at) "
        "VALUES (%s, 'scan', 'running', %s)",
        (connector_id, datetime.datetime.utcnow()),
    )
    summary = {"datasets": 0, "drifts": 0, "pii_datasets": 0}
    try:
        if ctype == "mysql":
            scan = _scan_mysql(conn_row)
        elif ctype == "mssql":
            # Use generic ODBC for column discovery if available
            scan = {"datasets": []}
            try:
                scan = _scan_mssql(conn_row)
            except Exception as e:
                logger.warning("mssql scan limited: %s", e)
        elif ctype == "github":
            scan = _scan_github(conn_row)
        elif ctype == "databricks":
            scan = _scan_databricks(conn_row)
        elif ctype == "azure":
            scan = _scan_azure(conn_row)
        elif ctype == "azure_adf":
            scan = _scan_azure_adf(conn_row)

        else:
            scan = {"datasets": []}

        for ds in scan.get("datasets", []):
            ds_id = _upsert_dataset(connector_id, ds)
            cols = ds.get("columns") or []
            if cols:
                _refresh_columns(ds_id, cols)
                _capture_schema_history(ds_id, cols)
                drift = _detect_schema_drift(ds_id)
                if drift:
                    summary["drifts"] += 1
                    msg = (
                        f"Schema drift detected on {ds.get('schema') or ''}.{ds.get('name')}: "
                        f"added={drift['added']}, removed={drift['removed']}, type_changes={drift['type_changes']}"
                    )
                    _create_alert(
                        "schema_drift",
                        "high" if (drift["removed"] or drift["type_changes"]) else "medium",
                        f"Schema drift on {ds.get('name')}",
                        msg,
                        connector_id=connector_id, dataset_id=ds_id,
                        ai_payload={
                            "category": "schema_drift",
                            "connector_type": ctype,
                            "dataset": f"{ds.get('schema') or ''}.{ds.get('name')}",
                            "changes": drift,
                        },
                    )
            # mark PII
            row = fetch_one("SELECT contains_pii FROM datasets WHERE id=%s", (ds_id,))
            if row and row["contains_pii"]:
                summary["pii_datasets"] += 1
            summary["datasets"] += 1

        execute(
            "UPDATE connectors SET status='healthy', last_scanned_at=%s WHERE id=%s",
            (datetime.datetime.utcnow(), connector_id),
        )
        execute(
            "UPDATE monitoring_runs SET status='success', finished_at=%s, metrics_json=%s "
            "WHERE id=%s",
            (datetime.datetime.utcnow(), json.dumps(summary), run_id),
        )
        return summary
    except Exception as e:
        logger.exception("Scan failed: %s", e)
        execute(
            "UPDATE monitoring_runs SET status='failed', finished_at=%s, message=%s WHERE id=%s",
            (datetime.datetime.utcnow(), str(e)[:500], run_id),
        )
        execute("UPDATE connectors SET status='unhealthy' WHERE id=%s", (connector_id,))
        _create_alert(
            "pipeline", "critical",
            f"Scan failed for connector #{connector_id}",
            str(e)[:500],
            connector_id=connector_id,
            ai_payload={"category": "pipeline", "error": str(e)[:500], "connector_type": ctype},
        )
        raise


def _scan_mssql(conn_row: dict) -> Dict[str, Any]:
    """MSSQL scan via pyodbc if available."""
    import pyodbc  # type: ignore
    cfg = decrypt_config(conn_row["config_json"])
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if not drivers:
        return {"datasets": []}
    cs = (
        f"DRIVER={{{drivers[0]}}};SERVER={cfg.get('server')},{cfg.get('port',1433)};"
        f"DATABASE={cfg.get('database')};UID={cfg.get('username')};PWD={cfg.get('password','')};"
        f"Encrypt=no;TrustServerCertificate=yes;"
    )
    cn = pyodbc.connect(cs, timeout=10)
    discovered = []
    try:
        cur = cn.cursor()
        cur.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES"
        )
        tabs = cur.fetchall()
        for t in tabs:
            schema, name, typ = t[0], t[1], t[2]
            ttype = "view" if typ == "VIEW" else "table"
            row_count = None
            try:
                cur.execute(f"SELECT COUNT(*) FROM [{schema}].[{name}]")
                row_count = cur.fetchone()[0]
            except Exception:
                pass
            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION",
                schema, name,
            )
            cols = cur.fetchall()
            discovered.append({
                "schema": schema, "name": name, "type": ttype, "row_count": row_count,
                "columns": [
                    {"name": c[0], "type": c[1], "nullable": c[2] == "YES"} for c in cols
                ],
            })
    finally:
        cn.close()
    return {"datasets": discovered}


# ---------- routes --------------------------------------------------------
@router.post("/scan/{connector_id}")
def scan_connector(connector_id: int, background: BackgroundTasks,
                   user: dict = Depends(require_roles("admin", "steward"))):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (connector_id,)):
        raise HTTPException(status_code=404, detail="Connector not found")
    try:
        result = _run_scan(connector_id)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quality-check/{dataset_id}")
def quality_check(dataset_id: int, user: dict = Depends(require_roles("admin", "steward"))):
    ds = fetch_one(
        "SELECT d.*, c.type AS connector_type, c.config_json "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
        (dataset_id,),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if ds["connector_type"] != "mysql":
        raise HTTPException(status_code=400, detail="Quality check supported on MySQL datasets only")
    cfg = decrypt_config(ds["config_json"])
    cn = _mysql_conn(cfg)
    issues, score = [], 100.0
    metrics = {}
    try:
        with cn.cursor() as cur:
            schema = ds["schema_name"] or cfg.get("database")
            name = ds["dataset_name"]
            cur.execute(f"SELECT COUNT(*) AS c FROM `{schema}`.`{name}`")
            total = (cur.fetchone() or {}).get("c", 0)
            metrics["row_count"] = total
            # per-column null %, distinct
            cur.execute(
                "SELECT COLUMN_NAME FROM information_schema.columns "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                (schema, name),
            )
            cols = [r["COLUMN_NAME"] for r in cur.fetchall()]
            col_metrics = []
            for col in cols:
                try:
                    cur.execute(
                        f"SELECT SUM(CASE WHEN `{col}` IS NULL THEN 1 ELSE 0 END) AS n, "
                        f"COUNT(DISTINCT `{col}`) AS d FROM `{schema}`.`{name}`"
                    )
                    row = cur.fetchone() or {}
                    nulls = row.get("n") or 0
                    distincts = row.get("d") or 0
                    pct = (nulls / total * 100) if total else 0
                    col_metrics.append({
                        "column": col, "null_pct": round(pct, 2),
                        "distinct": distincts,
                    })
                    execute(
                        "UPDATE dataset_columns SET null_pct=%s, distinct_count=%s "
                        "WHERE dataset_id=%s AND column_name=%s",
                        (round(pct, 2), distincts, dataset_id, col),
                    )
                    if pct > 30:
                        issues.append(f"Column {col} has {round(pct,1)}% NULLs")
                        score -= 5
                    if total > 0 and distincts <= 1:
                        issues.append(f"Column {col} is constant (no variance)")
                        score -= 2
                except Exception as e:
                    logger.debug("column metric failed %s: %s", col, e)
            if total == 0:
                issues.append("Empty table")
                score -= 20
            metrics["columns"] = col_metrics
    finally:
        cn.close()

    score = max(0.0, min(100.0, score))
    execute(
        "UPDATE datasets SET quality_score=%s, last_profiled_at=%s WHERE id=%s",
        (score, datetime.datetime.utcnow(), dataset_id),
    )
    run_id = execute(
        "INSERT INTO monitoring_runs (connector_id, dataset_id, run_type, status, message, "
        "metrics_json, finished_at) VALUES (%s, %s, 'quality', 'success', %s, %s, %s)",
        (ds["connector_id"], dataset_id, f"score={score}",
         safe_json_dumps(metrics), datetime.datetime.utcnow()),
    )
    if issues:
        severity = "high" if score < 70 else ("medium" if score < 85 else "low")
        _create_alert(
            "quality", severity,
            f"Quality issues on {ds['dataset_name']} (score {score:.1f})",
            "; ".join(issues[:10]),
            connector_id=ds["connector_id"], dataset_id=dataset_id,
            ai_payload={
                "category": "quality", "dataset": ds["dataset_name"],
                "score": score, "issues": issues, "metrics": metrics,
            },
        )
    return {"score": score, "issues": issues, "metrics": metrics, "run_id": run_id}


@router.post("/schema-drift/{dataset_id}")
def schema_drift_endpoint(dataset_id: int, user: dict = Depends(require_roles("admin", "steward"))):
    if not fetch_one("SELECT id FROM datasets WHERE id=%s", (dataset_id,)):
        raise HTTPException(status_code=404, detail="Dataset not found")
    drift = _detect_schema_drift(dataset_id)
    return {"drift": drift or {"added": [], "removed": [], "type_changes": []}}


@router.post("/pii-scan/{dataset_id}")
def pii_scan(dataset_id: int, user: dict = Depends(require_roles("admin", "steward"))):
    ds = fetch_one(
        "SELECT d.*, c.type AS connector_type, c.config_json "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
        (dataset_id,),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    pii_results = []
    # name-based hints always
    cols = fetch_all("SELECT * FROM dataset_columns WHERE dataset_id=%s", (dataset_id,))
    for c in cols:
        cat = detect_pii_in_column_name(c["column_name"])
        if cat:
            pii_results.append({"column": c["column_name"], "category": cat, "source": "name"})
            execute(
                "UPDATE dataset_columns SET is_pii=1, pii_category=%s WHERE id=%s",
                (cat, c["id"]),
            )
    # value-based for MySQL
    if ds["connector_type"] == "mysql":
        cfg = decrypt_config(ds["config_json"])
        try:
            cn = _mysql_conn(cfg)
            with cn.cursor() as cur:
                for c in cols:
                    col = c["column_name"]
                    try:
                        cur.execute(
                            f"SELECT `{col}` AS v FROM `{ds['schema_name']}`.`{ds['dataset_name']}` "
                            f"WHERE `{col}` IS NOT NULL LIMIT 30"
                        )
                        samples = [str(r["v"]) for r in cur.fetchall()]
                        cat = detect_pii_in_samples(samples)
                        if cat and not any(p["column"] == col for p in pii_results):
                            pii_results.append({"column": col, "category": cat, "source": "value"})
                            execute(
                                "UPDATE dataset_columns SET is_pii=1, pii_category=%s WHERE id=%s",
                                (cat, c["id"]),
                            )
                    except Exception:
                        continue
            cn.close()
        except Exception as e:
            logger.warning("PII value scan failed: %s", e)

    if pii_results:
        cats = ",".join(sorted({p["category"] for p in pii_results}))
        execute("UPDATE datasets SET contains_pii=1, pii_categories=%s WHERE id=%s",
                (cats, dataset_id))
        _create_alert(
            "pii", "high",
            f"PII detected in {ds['dataset_name']}",
            f"Sensitive categories: {cats}. Columns: " + ", ".join(p["column"] for p in pii_results),
            connector_id=ds["connector_id"], dataset_id=dataset_id,
            ai_payload={
                "category": "pii", "dataset": ds["dataset_name"],
                "categories": cats, "columns": pii_results,
            },
        )
    else:
        execute("UPDATE datasets SET contains_pii=0, pii_categories=NULL WHERE id=%s", (dataset_id,))

    return {"pii": pii_results}


@router.get("/runs")
def list_runs(limit: int = 50, user: dict = Depends(get_current_user)):
    rows = fetch_all(
        "SELECT r.*, c.name AS connector_name, d.dataset_name "
        "FROM monitoring_runs r LEFT JOIN connectors c ON c.id=r.connector_id "
        "LEFT JOIN datasets d ON d.id=r.dataset_id "
        "ORDER BY r.started_at DESC LIMIT %s",
        (limit,),
    )
    return rows


@router.get("/jobs")
def list_jobs(user: dict = Depends(get_current_user)):
    return fetch_all(
        "SELECT j.*, c.name AS connector_name FROM monitoring_jobs j "
        "JOIN connectors c ON c.id=j.connector_id ORDER BY j.id DESC"
    )


class JobIn(BaseModel):
    connector_id: int
    job_type: str = "scan"
    interval_minutes: int = 60
    enabled: bool = True


@router.post("/jobs")
def create_job(body: JobIn, user: dict = Depends(require_roles("admin", "steward"))):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (body.connector_id,)):
        raise HTTPException(status_code=404, detail="Connector not found")
    next_run = datetime.datetime.utcnow() + datetime.timedelta(minutes=body.interval_minutes)
    new_id = execute(
        "INSERT INTO monitoring_jobs (connector_id, job_type, interval_minutes, enabled, next_run_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (body.connector_id, body.job_type, body.interval_minutes,
         1 if body.enabled else 0, next_run),
    )
    return {"id": new_id, "message": "Monitoring job created"}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, user: dict = Depends(require_roles("admin", "steward"))):
    execute("DELETE FROM monitoring_jobs WHERE id=%s", (job_id,))
    return {"deleted": True}
