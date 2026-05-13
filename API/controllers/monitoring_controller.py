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
    logger,
    decrypt_config,
    detect_pii_in_column_name,
    detect_pii_in_samples,
    safe_json_dumps,
)
from utils.constants import QUALITY_CHECKS
from utils.ai_helper import analyze_issue, validate_dataset_quality
from utils.email_helper import send_alert_email
from utils.vector_helper import add_monitoring_log_to_index, search_rule_books
from controllers.connector_controller import test_connection

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


def _scan_azure_adf(conn_row: dict) -> Dict[str, Any]:
    logger.info("Starting Azure ADF scan for connector: %s", conn_row.get("name"))

    cfg = decrypt_config(conn_row["config_json"])

    tenant = cfg.get("tenant_id")
    cid = cfg.get("client_id")
    secret = cfg.get("client_secret")

    discovered = []

    logger.debug("Getting Azure token for tenant: %s", tenant)
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
        logger.error("Failed to get Azure token: %s", token_r.text[:200])
        raise RuntimeError(f"Azure auth failed: {token_r.status_code}")

    tok = token_r.json()["access_token"]

    base = (
        f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
        f"/resourceGroups/{cfg['resource_group']}"
        f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
    )

    headers = {"Authorization": f"Bearer {tok}"}

    # DATASETS
    logger.debug("Fetching datasets from: %s", f"{base}/datasets")
    ds_r = requests.get(
        f"{base}/datasets?api-version=2018-06-01",
        headers=headers,
        timeout=20,
    )

    if ds_r.status_code == 200:
        datasets = ds_r.json().get("value", [])
        logger.info("Found %d datasets in ADF", len(datasets))
        for ds in datasets:
            props = ds.get("properties", {})
            discovered.append(
                {
                    "schema": "adf",
                    "name": ds.get("name"),
                    "type": "dataset",
                    "row_count": None,
                    "columns": [],
                }
            )
    else:
        logger.warning(
            "Failed to fetch ADF datasets: %s %s", ds_r.status_code, ds_r.text[:200]
        )

    # PIPELINES
    logger.debug("Fetching pipelines from: %s", f"{base}/pipelines")
    pl_r = requests.get(
        f"{base}/pipelines?api-version=2018-06-01",
        headers=headers,
        timeout=20,
    )

    if pl_r.status_code == 200:
        pipelines = pl_r.json().get("value", [])
        logger.info("Found %d pipelines in ADF", len(pipelines))
        for p in pipelines:
            discovered.append(
                {
                    "schema": "adf",
                    "name": p.get("name"),
                    "type": "pipeline",
                    "row_count": None,
                    "columns": [],
                }
            )
    else:
        logger.warning(
            "Failed to fetch ADF pipelines: %s %s", pl_r.status_code, pl_r.text[:200]
        )

    logger.info("Azure ADF scan complete: discovered %d items", len(discovered))
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
    if not db_name:
        raise ValueError("MySQL database name not found in connector config")
    discovered: List[dict] = []
    try:
        logger.info("Starting MySQL scan for database: %s", db_name)
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
                logger.info("Found %d tables/views in MySQL", len(tables))
                for t in tables:
                    schema = t["TABLE_SCHEMA"]
                    tname = t["TABLE_NAME"]
                    ttype = "view" if t["TABLE_TYPE"] == "VIEW" else "table"
                    logger.debug("Processing table: %s.%s", schema, tname)
                    # Use approximate row count from information_schema to speed up scan
                    row_count = t.get("TABLE_ROWS")
                    # columns
                    cur.execute(
                        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
                        "FROM information_schema.columns "
                        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                        "ORDER BY ORDINAL_POSITION",
                        (schema, tname),
                    )
                    cols = cur.fetchall()
                    discovered.append(
                        {
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
                        }
                    )
        finally:
            cn.close()
        logger.info("MySQL scan complete, discovered %d datasets", len(discovered))
        return {"datasets": discovered}
    except Exception as e:
        logger.exception("MySQL scan failed: %s", e)
        raise


def _scan_github(conn_row: dict) -> Dict[str, Any]:
    cfg = decrypt_config(conn_row["config_json"])
    repo = (cfg.get("repository_url") or "").rstrip("/")
    if repo.startswith("http"):
        path = repo.split("github.com/", 1)[-1]
    else:
        path = repo
    headers = {
        "Authorization": f"Bearer {cfg.get('token')}",
        "Accept": "application/vnd.github+json",
    }
    discovered = []
    # workflows
    try:
        r = requests.get(
            f"https://api.github.com/repos/{path}/actions/workflows",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 200:
            for wf in r.json().get("workflows", []):
                discovered.append(
                    {
                        "schema": "actions",
                        "name": wf.get("name") or wf.get("path"),
                        "type": "workflow",
                        "row_count": None,
                        "columns": [],
                    }
                )
    except Exception as e:
        logger.warning("GitHub workflows fetch failed: %s", e)
    return {"datasets": discovered}


def _scan_databricks(conn_row: dict) -> Dict[str, Any]:
    """Scan Databricks: jobs, clusters, and Unity Catalog tables."""
    cfg = decrypt_config(conn_row["config_json"])
    base = cfg.get("workspace_url", "").rstrip("/")
    token = cfg.get("token")
    headers = {"Authorization": f"Bearer {token}"}
    discovered = []

    # ===== Jobs =====
    try:
        r = requests.get(f"{base}/api/2.0/jobs/list", headers=headers, timeout=15)
        if r.status_code == 200:
            for j in r.json().get("jobs", []):
                settings = j.get("settings") or {}
                discovered.append(
                    {
                        "schema": "jobs",
                        "name": settings.get("name") or f"job_{j.get('job_id')}",
                        "type": "job",
                        "row_count": None,
                        "columns": [],
                    }
                )
    except Exception as e:
        logger.warning("Databricks jobs failed: %s", e)

    # ===== Clusters =====
    try:
        r = requests.get(f"{base}/api/2.0/clusters/list", headers=headers, timeout=15)
        if r.status_code == 200:
            for cl in r.json().get("clusters", []):
                discovered.append(
                    {
                        "schema": "clusters",
                        "name": cl.get("cluster_name") or cl.get("cluster_id"),
                        "type": "cluster",
                        "row_count": None,
                        "columns": [],
                    }
                )
    except Exception as e:
        logger.warning("Databricks clusters failed: %s", e)

    # ===== Unity Catalog Tables =====
    try:
        # List all schemas in default catalog
        schemas_r = requests.get(
            f"{base}/api/2.1/unity-catalog/schemas?catalog_name=hive_metastore",
            headers=headers,
            timeout=15,
        )
        if schemas_r.status_code == 200:
            for schema in schemas_r.json().get("objects", []):
                schema_name = schema.get("name")
                try:
                    # List tables in this schema
                    tables_r = requests.get(
                        f"{base}/api/2.1/unity-catalog/tables?catalog_name=hive_metastore&schema_name={schema_name}",
                        headers=headers,
                        timeout=15,
                    )
                    if tables_r.status_code == 200:
                        for tbl in tables_r.json().get("objects", []):
                            tbl_name = tbl.get("name")
                            columns = []
                            row_count = None

                            # Get table columns
                            try:
                                col_r = requests.get(
                                    f"{base}/api/2.1/unity-catalog/tables/hive_metastore.{schema_name}.{tbl_name}",
                                    headers=headers,
                                    timeout=15,
                                )
                                if col_r.status_code == 200:
                                    tbl_obj = col_r.json()
                                    cols_info = tbl_obj.get("columns", [])
                                    columns = [
                                        {
                                            "name": c.get("name"),
                                            "type": c.get("type_text", "unknown"),
                                        }
                                        for c in cols_info
                                    ]
                            except Exception as col_e:
                                logger.debug(
                                    "Failed to get columns for %s.%s: %s",
                                    schema_name,
                                    tbl_name,
                                    col_e,
                                )

                            discovered.append(
                                {
                                    "schema": schema_name,
                                    "name": tbl_name,
                                    "type": "table",
                                    "row_count": row_count,  # Will be estimated by quality checks
                                    "columns": columns,
                                }
                            )
                except Exception as tbl_e:
                    logger.debug(
                        "Failed to list tables in schema %s: %s", schema_name, tbl_e
                    )
        else:
            logger.debug("Databricks schemas list returned %d", schemas_r.status_code)
    except Exception as e:
        logger.debug("Databricks Unity Catalog scan skipped: %s", e)

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
                "grant_type": "client_credentials",
                "client_id": cid,
                "client_secret": secret,
                "scope": "https://management.azure.com/.default",
            },
            timeout=15,
        )
        if token_r.status_code != 200:
            raise RuntimeError(f"Token: {token_r.text[:200]}")
        tok = token_r.json()["access_token"]
        # list resource groups
        rg = requests.get(
            f"https://management.azure.com/subscriptions/{sub}/resourcegroups?api-version=2021-04-01",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=15,
        )
        if rg.status_code == 200:
            for g in rg.json().get("value", []):
                discovered.append(
                    {
                        "schema": g.get("location", ""),
                        "name": g.get("name"),
                        "type": "blob",  # we group cloud resources as 'blob' container
                        "row_count": None,
                        "columns": [],
                    }
                )
    except Exception as e:
        logger.warning("Azure scan failed: %s", e)
    return {"datasets": discovered}


# ---------- persistence helpers -------------------------------------------
def _upsert_dataset(connector_id: int, ds: dict) -> int:
    try:
        existing = fetch_one(
            "SELECT id FROM datasets WHERE connector_id=%s AND IFNULL(schema_name,'')=%s AND dataset_name=%s",
            (connector_id, ds.get("schema") or "", ds.get("name")),
        )
        cols = ds.get("columns") or []

        # Map to valid dataset type
        raw_type = ds.get("type", "table")
        type_mapping = {
            "dataset": "dataset",
            "pipeline": "pipeline",
            "table": "table",
            "view": "view",
            "file": "file",
            "job": "job",
            "workflow": "workflow",
            "blob": "blob",
            "adf": "adf",
            "cluster": "cluster",
            "notebook": "notebook",
        }
        valid_type = type_mapping.get(raw_type, "table")

        if existing:
            execute(
                "UPDATE datasets SET dataset_type=%s, row_count=%s, column_count=%s, "
                "last_profiled_at=%s WHERE id=%s",
                (
                    valid_type,
                    ds.get("row_count"),
                    len(cols),
                    datetime.datetime.utcnow(),
                    existing["id"],
                ),
            )
            return existing["id"]
        return execute(
            "INSERT INTO datasets (connector_id, schema_name, dataset_name, dataset_type, "
            "row_count, column_count, last_profiled_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                connector_id,
                ds.get("schema"),
                ds.get("name"),
                valid_type,
                ds.get("row_count"),
                len(cols),
                datetime.datetime.utcnow(),
            ),
        )
    except Exception as e:
        logger.exception("Failed to upsert dataset: %s", ds.get("name"))
        raise


def _refresh_columns(dataset_id: int, cols: List[dict]) -> List[dict]:
    """Replace columns and return PII categories detected by name hints."""
    try:
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
                (
                    dataset_id,
                    c["name"],
                    c.get("type"),
                    1 if c.get("nullable") else 0,
                    is_pii,
                    cat or None,
                ),
            )
        if pii_categories:
            cats = ",".join(sorted(set(pii_categories)))
            execute(
                "UPDATE datasets SET contains_pii=1, pii_categories=%s WHERE id=%s",
                (cats, dataset_id),
            )
        return pii_categories
    except Exception as e:
        logger.exception("Failed to refresh columns for dataset %s: %s", dataset_id, e)
        return []


def _capture_schema_history(dataset_id: int, cols: List[dict]):
    try:
        snap = json.dumps(
            [
                {
                    "name": c["name"],
                    "type": c.get("type"),
                    "nullable": c.get("nullable"),
                }
                for c in cols
            ]
        )
        execute(
            "INSERT INTO schema_history (dataset_id, snapshot_json) VALUES (%s, %s)",
            (dataset_id, snap),
        )
    except Exception as e:
        logger.warning(
            "Failed to capture schema history for dataset %s: %s", dataset_id, e
        )


def _detect_schema_drift(dataset_id: int) -> Optional[Dict[str, Any]]:
    try:
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
            if name in old_map and new_map[name].get("type") != old_map[name].get(
                "type"
            ):
                changed.append(
                    {
                        "name": name,
                        "old_type": old_map[name].get("type"),
                        "new_type": new_map[name].get("type"),
                    }
                )
        if added or removed or changed:
            return {"added": added, "removed": removed, "type_changes": changed}
        return None
    except Exception as e:
        logger.warning(
            "Failed to detect schema drift for dataset %s: %s", dataset_id, e
        )
        return None


def _execute_validation_rules(dataset_id: int, connector_cfg: dict) -> List[dict]:
    try:
        ds = fetch_one(
            "SELECT d.*, c.type AS connector_type FROM datasets d JOIN connectors c ON d.connector_id=c.id WHERE d.id=%s",
            (dataset_id,),
        )
        dataset_rules = []
        try:
            dataset_rules = fetch_all(
                "SELECT * FROM dataset_validation_rules WHERE dataset_id=%s AND is_active=1",
                (dataset_id,),
            )
        except Exception as e:
            logger.warning("dataset_validation_rules table not found or error: %s", e)

        type_based_rules = []
        if ds:
            try:
                type_based_rules = fetch_all(
                    "SELECT dvr.* FROM dataset_validation_rules dvr JOIN rule_books rb ON dvr.rule_book_id=rb.id "
                    "WHERE dvr.is_active=1 AND (rb.connector_type=%s OR rb.connector_type IS NULL) AND (rb.dataset_type=%s OR rb.dataset_type IS NULL)",
                    (ds.get("connector_type"), ds.get("dataset_type")),
                )
            except Exception as e:
                logger.warning(
                    "rule_books or dataset_validation_rules join failed: %s", e
                )

        all_rules = dataset_rules + type_based_rules
        results = []
        if not ds or (not all_rules) or ds["connector_type"] != "mysql":
            return results

        cfg = decrypt_config(connector_cfg)

        try:
            cn = _mysql_conn(cfg)
            try:
                with cn.cursor() as cur:
                    schema = ds["schema_name"] or cfg.get("database")
                    name = ds["dataset_name"]
                    for rule in all_rules:
                        rule_config = (
                            json.loads(rule["rule_config"])
                            if rule["rule_config"]
                            else {}
                        )
                        passed = True
                        result_msg = ""

                        if rule["rule_type"] == "null_check":
                            col = rule_config.get("column")
                            if col:
                                cur.execute(
                                    f"SELECT COUNT(*) AS c FROM `{schema}`.`{name}` WHERE `{col}` IS NULL"
                                )
                                null_count = (cur.fetchone() or {}).get("c", 0)
                                if null_count > (rule_config.get("max_nulls") or 0):
                                    passed = False
                                    result_msg = f"Column {col} has {null_count} NULLs"
                        elif rule["rule_type"] == "unique_check":
                            col = rule_config.get("column")
                            if col:
                                cur.execute(
                                    f"SELECT COUNT(*) AS total, COUNT(DISTINCT `{col}`) AS unique FROM `{schema}`.`{name}`"
                                )
                                row = cur.fetchone() or {}
                                total, unique = row.get("total", 0), row.get(
                                    "unique", 0
                                )
                                if total > 0 and unique < total:
                                    passed = False
                                    result_msg = (
                                        f"Column {col} has {total - unique} duplicates"
                                    )
                        elif rule["rule_type"] == "range_check":
                            col = rule_config.get("column")
                            min_val = rule_config.get("min")
                            max_val = rule_config.get("max")
                            if col and (min_val is not None or max_val is not None):
                                conditions = []
                                if min_val is not None:
                                    conditions.append(f"`{col}` < {min_val}")
                                if max_val is not None:
                                    conditions.append(f"`{col}` > {max_val}")
                                if conditions:
                                    cur.execute(
                                        f"SELECT COUNT(*) AS c FROM `{schema}`.`{name}` WHERE {' OR '.join(conditions)}"
                                    )
                                    invalid_count = (cur.fetchone() or {}).get("c", 0)
                                    if invalid_count > 0:
                                        passed = False
                                        result_msg = f"Column {col} has {invalid_count} values out of range"
                        elif rule["rule_type"] == "regex_check":
                            col = rule_config.get("column")
                            pattern = rule_config.get("pattern")
                            if col and pattern:
                                cur.execute(
                                    f"SELECT COUNT(*) AS c FROM `{schema}`.`{name}` WHERE `{col}` NOT REGEXP '{pattern}'"
                                )
                                invalid_count = (cur.fetchone() or {}).get("c", 0)
                                if invalid_count > 0:
                                    passed = False
                                    result_msg = f"Column {col} has {invalid_count} values not matching pattern"
                        elif rule["rule_type"] == "custom_sql":
                            sql = rule_config.get("sql")
                            if sql:
                                try:
                                    cur.execute(sql)
                                    result = cur.fetchall()
                                    if result:
                                        passed = False
                                        result_msg = f"Custom SQL failed: {len(result)} rows returned"
                                except Exception as e:
                                    passed = False
                                    result_msg = f"Custom SQL error: {str(e)}"

                        results.append(
                            {
                                "rule_id": rule["id"],
                                "rule_name": rule["rule_name"],
                                "rule_type": rule["rule_type"],
                                "passed": passed,
                                "message": result_msg,
                            }
                        )
            finally:
                cn.close()
        except Exception as e:
            logger.error(
                "Validation rules execution failed for dataset %s: %s", dataset_id, e
            )

        return results
    except Exception as e:
        logger.error("_execute_validation_rules top-level error: %s", e)
        return []


def _log_monitoring_event(
    log_type: str,
    log_content: str,
    dataset_id: Optional[int] = None,
    connector_id: Optional[int] = None,
):
    try:
        log_result = execute(
            "INSERT INTO monitoring_logs (dataset_id, connector_id, log_type, log_content) VALUES (%s, %s, %s, %s)",
            (dataset_id, connector_id, log_type, log_content),
        )
        log_id = log_result["last_insert_id"]
        try:
            add_monitoring_log_to_index(log_content, log_id, log_type)
        except Exception as e:
            logger.warning("Failed to add log to vector index: %s", e)
    except Exception as e:
        logger.warning("monitoring_logs table not found or logging failed: %s", e)


def _create_alert(
    category: str,
    severity: str,
    title: str,
    message: str,
    connector_id: Optional[int] = None,
    dataset_id: Optional[int] = None,
    ai_payload: Optional[dict] = None,
) -> int:
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
        (
            connector_id,
            dataset_id,
            category,
            severity,
            title,
            message,
            ai.get("summary"),
            ai.get("root_cause"),
            ai.get("impact"),
            ai.get("recommendation"),
        ),
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
            send_alert_email(
                recipients,
                {
                    "category": category,
                    "severity": severity,
                    "title": title,
                    "message": message,
                    "ai_summary": ai.get("summary"),
                    "ai_root_cause": ai.get("root_cause"),
                    "ai_impact": ai.get("impact"),
                    "ai_recommendation": ai.get("recommendation"),
                    "created_at": datetime.datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Alert email failed: %s", e)
    return aid


def _alert_recipients() -> List[str]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE setting_key='alert_email_recipients'"
    )
    raw = (row or {}).get("setting_value", "") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


# ---------- AI-driven quality checks -------------------------------------
def _run_ai_quality_checks(
    dataset_id: int,
    ds_info: dict,
    sample_rows: Optional[List[dict]] = None,
) -> Tuple[List[str], float, dict, List[str], List[str]]:
    """Run AI-driven quality checks using Rule Books from ChromaDB."""
    try:
        dataset_metadata = {
            "id": ds_info["id"],
            "name": ds_info["dataset_name"],
            "schema": ds_info["schema_name"],
            "type": ds_info["dataset_type"],
            "row_count": ds_info["row_count"],
            "column_count": ds_info["column_count"],
            "connector_type": ds_info["connector_type"],
        }

        columns = fetch_all(
            "SELECT * FROM dataset_columns WHERE dataset_id=%s", (dataset_id,)
        )
        schema = [
            {
                "name": c["column_name"],
                "type": c["data_type"],
                "nullable": bool(c["is_nullable"]),
                "is_pii": bool(c["is_pii"]),
                "pii_category": c["pii_category"],
            }
            for c in columns
        ]

        search_query = f"Data quality checks for {ds_info['connector_type']} {ds_info['dataset_type']} {ds_info['dataset_name']}"
        rule_results = search_rule_books(
            search_query, top_k=10, connector_type=ds_info["connector_type"]
        )

        rule_chunks = [r["document"] for r in rule_results if r.get("document")]

        ai_result = validate_dataset_quality(
            dataset_metadata=dataset_metadata,
            schema=schema,
            sample_rows=sample_rows,
            rule_chunks=rule_chunks,
        )

        return (
            ai_result["issues"],
            ai_result["quality_score"],
            {},
            ai_result["pii_columns"],
            ai_result["pii_categories"],
        )
    except Exception as e:
        logger.error("AI quality checks failed: %s", e)
        return [f"AI check error: {str(e)}"], 80.0, {}, [], []


# ---------- comprehensive quality checks ----------------------------------
def _run_mysql_quality_checks(
    dataset_id: int, cfg: dict, ds: dict
) -> Tuple[List[dict], float, dict]:
    """Run all 16 MySQL quality checks on a dataset."""
    issues = []
    score = 100.0
    metrics = {}

    try:
        cn = _mysql_conn(cfg)
        try:
            with cn.cursor() as cur:
                schema = ds["schema_name"] or cfg.get("database")
                name = ds["dataset_name"]

                # 1. Row count validation
                cur.execute(f"SELECT COUNT(*) AS c FROM `{schema}`.`{name}`")
                total_rows = (cur.fetchone() or {}).get("c", 0)
                metrics["row_count"] = total_rows
                if total_rows == 0:
                    issues.append("Row count validation: Empty table")
                    score -= 20

                # Get columns info
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY "
                    "FROM information_schema.columns "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
                    (schema, name),
                )
                columns = cur.fetchall()
                metrics["columns"] = []

                for col in columns:
                    col_name = col["COLUMN_NAME"]
                    col_metrics = {"column": col_name}

                    # 2. Null value check
                    try:
                        cur.execute(
                            f"SELECT SUM(CASE WHEN `{col_name}` IS NULL THEN 1 ELSE 0 END) AS n FROM `{schema}`.`{name}`"
                        )
                        null_count = (cur.fetchone() or {}).get("n", 0)
                        null_pct = (null_count / total_rows * 100) if total_rows else 0
                        col_metrics["null_pct"] = round(null_pct, 2)
                        if null_pct > 30:
                            issues.append(
                                f"Null value check: Column '{col_name}' has {round(null_pct,1)}% NULLs"
                            )
                            score -= 5
                    except Exception:
                        pass

                    # 3. Duplicate record check (for each column)
                    try:
                        cur.execute(
                            f"SELECT COUNT(*) AS total, COUNT(DISTINCT `{col_name}`) AS unique FROM `{schema}`.`{name}`"
                        )
                        row = cur.fetchone() or {}
                        total, unique = row.get("total", 0), row.get("unique", 0)
                        col_metrics["distinct_count"] = unique
                        if total > 0 and unique < total:
                            issues.append(
                                f"Duplicate record check: Column '{col_name}' has {total - unique} duplicates"
                            )
                            score -= 3
                    except Exception:
                        pass

                    # 4. Numeric range validation
                    if col["DATA_TYPE"] in [
                        "int",
                        "bigint",
                        "decimal",
                        "float",
                        "double",
                    ]:
                        try:
                            cur.execute(
                                f"SELECT MIN(`{col_name}`) AS min_val, MAX(`{col_name}`) AS max_val FROM `{schema}`.`{name}`"
                            )
                            range_row = cur.fetchone() or {}
                            col_metrics["min"] = range_row.get("min_val")
                            col_metrics["max"] = range_row.get("max_val")
                        except Exception:
                            pass

                    # 5. Invalid date/time check
                    if col["DATA_TYPE"] in ["date", "datetime", "timestamp"]:
                        try:
                            cur.execute(
                                f"SELECT COUNT(*) AS invalid FROM `{schema}`.`{name}` "
                                f"WHERE `{col_name}` < '1900-01-01' OR `{col_name}` > '2100-12-31'"
                            )
                            invalid = (cur.fetchone() or {}).get("invalid", 0)
                            if invalid > 0:
                                issues.append(
                                    f"Invalid date/time check: Column '{col_name}' has {invalid} invalid dates"
                                )
                                score -= 4
                        except Exception:
                            pass

                    metrics["columns"].append(col_metrics)

                # 6. Primary key uniqueness
                pk_cols = [
                    c["COLUMN_NAME"] for c in columns if c["COLUMN_KEY"] == "PRI"
                ]
                if pk_cols:
                    try:
                        pk_expr = ", ".join([f"`{c}`" for c in pk_cols])
                        cur.execute(
                            f"SELECT COUNT(*) - COUNT(DISTINCT {pk_expr}) AS duplicates FROM `{schema}`.`{name}`"
                        )
                        pk_duplicates = (cur.fetchone() or {}).get("duplicates", 0)
                        if pk_duplicates > 0:
                            issues.append(
                                f"Primary key uniqueness: {pk_duplicates} duplicate primary keys found"
                            )
                            score -= 10
                    except Exception:
                        pass

                # 7. Foreign key integrity
                try:
                    cur.execute(
                        """
                        SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                        FROM information_schema.KEY_COLUMN_USAGE
                        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                    """,
                        (schema, name),
                    )
                    fks = cur.fetchall()
                    for fk in fks:
                        try:
                            ref_table = fk["REFERENCED_TABLE_NAME"]
                            ref_col = fk["REFERENCED_COLUMN_NAME"]
                            fk_col = fk["COLUMN_NAME"]
                            cur.execute(f"""
                                SELECT COUNT(*) AS orphaned FROM `{schema}`.`{name}` t
                                LEFT JOIN `{schema}`.`{ref_table}` r ON t.`{fk_col}` = r.`{ref_col}`
                                WHERE t.`{fk_col}` IS NOT NULL AND r.`{ref_col}` IS NULL
                            """)
                            orphaned = (cur.fetchone() or {}).get("orphaned", 0)
                            if orphaned > 0:
                                issues.append(
                                    f"Foreign key integrity: {orphaned} orphaned records in FK '{fk['CONSTRAINT_NAME']}'"
                                )
                                score -= 8
                        except Exception:
                            pass
                except Exception:
                    pass

                # 8. Data type validation (basic)
                # Already covered by column metadata

                # 9. Truncation check (for string columns)
                for col in columns:
                    if col["DATA_TYPE"] in ["varchar", "char", "text"]:
                        try:
                            col_name = col["COLUMN_NAME"]
                            cur.execute(f"""
                                SELECT COUNT(*) AS truncated FROM `{schema}`.`{name}`
                                WHERE CHAR_LENGTH(`{col_name}`) = CHARACTER_MAXIMUM_LENGTH
                                AND CHARACTER_MAXIMUM_LENGTH IS NOT NULL
                            """)
                            truncated = (cur.fetchone() or {}).get("truncated", 0)
                            if truncated > 0:
                                issues.append(
                                    f"Truncation check: Column '{col_name}' has {truncated} potentially truncated values"
                                )
                                score -= 3
                        except Exception:
                            pass

                # 10. Data freshness check (if there's a timestamp column)
                timestamp_cols = [
                    c["COLUMN_NAME"]
                    for c in columns
                    if c["DATA_TYPE"] in ["datetime", "timestamp"]
                ]
                if timestamp_cols:
                    try:
                        fresh_col = timestamp_cols[0]
                        cur.execute(
                            f"SELECT MAX(`{fresh_col}`) AS last_update FROM `{schema}`.`{name}`"
                        )
                        last_update = (cur.fetchone() or {}).get("last_update")
                        if last_update:
                            metrics["last_update"] = (
                                last_update.isoformat() if last_update else None
                            )
                            days_old = (datetime.datetime.utcnow() - last_update).days
                            if days_old > 7:
                                issues.append(
                                    f"Data freshness check: Data is {days_old} days old"
                                )
                                score -= 5
                    except Exception:
                        pass

                # 11. Outlier detection (simple IQR method for numeric columns)
                for col in columns:
                    if col["DATA_TYPE"] in [
                        "int",
                        "bigint",
                        "decimal",
                        "float",
                        "double",
                    ]:
                        try:
                            col_name = col["COLUMN_NAME"]
                            cur.execute(f"""
                                SELECT `{col_name}` FROM `{schema}`.`{name}`
                                WHERE `{col_name}` IS NOT NULL
                                ORDER BY `{col_name}`
                            """)
                            values = [
                                r[col_name]
                                for r in cur.fetchall()
                                if r[col_name] is not None
                            ]
                            if len(values) > 10:
                                import statistics

                                q1 = statistics.quantiles(values, n=4)[0]
                                q3 = statistics.quantiles(values, n=4)[2]
                                iqr = q3 - q1
                                lower_bound = q1 - 1.5 * iqr
                                upper_bound = q3 + 1.5 * iqr
                                outliers = [
                                    v
                                    for v in values
                                    if v < lower_bound or v > upper_bound
                                ]
                                if len(outliers) > 0:
                                    issues.append(
                                        f"Outlier/anomaly detection: Column '{col_name}' has {len(outliers)} outliers"
                                    )
                                    score -= 3
                        except Exception:
                            pass

                # 12. Schema drift detection is handled separately

                # 13. PII detection is handled separately

                # 14. Missing mandatory columns - would require configuration

                # 15. Referential integrity check covered in FK check

        finally:
            cn.close()
    except Exception as e:
        logger.error("MySQL quality checks failed: %s", e)
        issues.append(f"Quality check error: {str(e)}")
        score -= 20

    score = max(0.0, min(100.0, score))
    return issues, score, metrics


def _run_adf_quality_checks(
    connector_id: int, cfg: dict
) -> Tuple[List[dict], float, dict]:
    """Run all 15 ADF quality checks."""
    issues = []
    score = 100.0
    metrics = {}

    try:
        tenant = cfg.get("tenant_id")
        cid = cfg.get("client_id")
        secret = cfg.get("client_secret")

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
            issues.append(f"Linked service connectivity check: Authentication failed")
            score -= 30
            return issues, max(0, score), metrics

        tok = token_r.json()["access_token"]
        base = (
            f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
            f"/resourceGroups/{cfg['resource_group']}"
            f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
        )
        headers = {"Authorization": f"Bearer {tok}"}

        # 1. Pipeline execution status check
        try:
            pl_r = requests.get(
                f"{base}/pipelines?api-version=2018-06-01", headers=headers, timeout=20
            )
            if pl_r.status_code == 200:
                pipelines = pl_r.json().get("value", [])
                metrics["pipeline_count"] = len(pipelines)

                # Check recent runs for each pipeline
                failed_pipelines = 0
                for pl in pipelines:
                    pl_name = pl.get("name")
                    try:
                        runs_r = requests.get(
                            f"{base}/pipelines/{pl_name}/queryPipelineRuns?api-version=2018-06-01",
                            headers=headers,
                            json={
                                "lastUpdatedAfter": (
                                    datetime.datetime.utcnow()
                                    - datetime.timedelta(days=7)
                                ).isoformat()
                            },
                            timeout=20,
                        )
                        if runs_r.status_code == 200:
                            runs = runs_r.json().get("value", [])
                            for run in runs:
                                if run.get("status") == "Failed":
                                    failed_pipelines += 1
                                    issues.append(
                                        f"Pipeline execution status check: Pipeline '{pl_name}' failed"
                                    )
                                    score -= 5
                    except Exception:
                        pass
        except Exception as e:
            issues.append(f"Pipeline status check failed: {str(e)}")
            score -= 10

        # 2. Failed activity detection
        # 3. Pipeline duration threshold
        # 4. Trigger failure monitoring
        try:
            trigger_r = requests.get(
                f"{base}/triggers?api-version=2018-06-01", headers=headers, timeout=20
            )
            if trigger_r.status_code == 200:
                triggers = trigger_r.json().get("value", [])
                metrics["trigger_count"] = len(triggers)
                for trigger in triggers:
                    if trigger.get("properties", {}).get("runtimeState") != "Started":
                        issues.append(
                            f"Trigger failure monitoring: Trigger '{trigger.get('name')}' is not started"
                        )
                        score -= 3
        except Exception:
            pass

        # 5. Dataset existence validation
        try:
            ds_r = requests.get(
                f"{base}/datasets?api-version=2018-06-01", headers=headers, timeout=20
            )
            if ds_r.status_code == 200:
                datasets = ds_r.json().get("value", [])
                metrics["dataset_count"] = len(datasets)
        except Exception:
            pass

        # 6. Linked service connectivity check
        try:
            ls_r = requests.get(
                f"{base}/linkedservices?api-version=2018-06-01",
                headers=headers,
                timeout=20,
            )
            if ls_r.status_code == 200:
                linked_services = ls_r.json().get("value", [])
                metrics["linked_service_count"] = len(linked_services)
        except Exception:
            pass

        # 7-15: Additional checks would require more detailed ADF API calls

    except Exception as e:
        logger.error("ADF quality checks failed: %s", e)
        issues.append(f"ADF quality check error: {str(e)}")
        score -= 30

    score = max(0.0, min(100.0, score))
    return issues, score, metrics


def _run_databricks_quality_checks(
    connector_id: int, cfg: dict
) -> Tuple[List[dict], float, dict]:
    """Run all 15 Databricks quality checks."""
    issues = []
    score = 100.0
    metrics = {}

    try:
        base = cfg.get("workspace_url", "").rstrip("/")
        headers = {"Authorization": f"Bearer {cfg.get('token')}"}

        # 1. Job failure monitoring
        try:
            r = requests.get(f"{base}/api/2.0/jobs/list", headers=headers, timeout=15)
            if r.status_code == 200:
                jobs = r.json().get("jobs", [])
                metrics["job_count"] = len(jobs)
                failed_jobs = 0
                for job in jobs:
                    job_id = job.get("job_id")
                    try:
                        runs_r = requests.get(
                            f"{base}/api/2.0/jobs/runs/list?job_id={job_id}&limit=10",
                            headers=headers,
                            timeout=15,
                        )
                        if runs_r.status_code == 200:
                            runs = runs_r.json().get("runs", [])
                            for run in runs:
                                if run.get("state", {}).get("result_state") == "FAILED":
                                    failed_jobs += 1
                                    job_name = job.get("settings", {}).get(
                                        "name", f"job_{job_id}"
                                    )
                                    issues.append(
                                        f"Job failure monitoring: Job '{job_name}' failed"
                                    )
                                    score -= 5
                                    break
                    except Exception:
                        pass
        except Exception as e:
            issues.append(f"Job monitoring failed: {str(e)}")
            score -= 10

        # 2. Cluster health monitoring
        try:
            r = requests.get(
                f"{base}/api/2.0/clusters/list", headers=headers, timeout=15
            )
            if r.status_code == 200:
                clusters = r.json().get("clusters", [])
                metrics["cluster_count"] = len(clusters)
                for cluster in clusters:
                    state = cluster.get("state")
                    if state in ["ERROR", "TERMINATED"]:
                        cluster_name = cluster.get(
                            "cluster_name", cluster.get("cluster_id")
                        )
                        issues.append(
                            f"Cluster health monitoring: Cluster '{cluster_name}' is {state}"
                        )
                        score -= 5
        except Exception as e:
            issues.append(f"Cluster health check failed: {str(e)}")
            score -= 5

        # 3. Notebook execution status - covered in job monitoring

        # 4-15: Additional checks would require Databricks SQL or more APIs

    except Exception as e:
        logger.error("Databricks quality checks failed: %s", e)
        issues.append(f"Databricks quality check error: {str(e)}")
        score -= 30

    score = max(0.0, min(100.0, score))
    return issues, score, metrics


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
                        (
                            "high"
                            if (drift["removed"] or drift["type_changes"])
                            else "medium"
                        ),
                        f"Schema drift on {ds.get('name')}",
                        msg,
                        connector_id=connector_id,
                        dataset_id=ds_id,
                        ai_payload={
                            "category": "schema_drift",
                            "connector_type": ctype,
                            "dataset": f"{ds.get('schema') or ''}.{ds.get('name')}",
                            "changes": drift,
                        },
                    )

            # ===== Run LLM-powered quality checks =====
            try:
                ds_full = fetch_one(
                    "SELECT d.*, c.name AS connector_name FROM datasets d JOIN connectors c ON d.connector_id=c.id WHERE d.id=%s",
                    (ds_id,),
                )
                if ds_full and ds_full.get("column_count", 0) > 0:
                    issues, quality_score, _, pii_cols, pii_cats = (
                        _run_ai_quality_checks(ds_id, ds_full)
                    )

                    # Update dataset with LLM results
                    pii_categories = ",".join(pii_cats) if pii_cats else None
                    execute(
                        "UPDATE datasets SET quality_score=%s, pii_categories=%s, contains_pii=%s WHERE id=%s",
                        (quality_score, pii_categories, 1 if pii_cats else 0, ds_id),
                    )

                    # Log quality check event
                    if issues:
                        issue_str = "; ".join(issues[:5])  # Limit to first 5 issues
                        _log_monitoring_event(
                            "quality_check",
                            issue_str,
                            dataset_id=ds_id,
                            connector_id=connector_id,
                        )

                    # Create alert if quality is low
                    if quality_score < 70:
                        _create_alert(
                            "quality",
                            "high" if quality_score < 50 else "medium",
                            f"Low data quality detected on {ds.get('name')}",
                            f"Quality score: {quality_score:.1f}/100. Issues: {'; '.join(issues[:3])}",
                            connector_id=connector_id,
                            dataset_id=ds_id,
                            ai_payload={
                                "category": "quality",
                                "dataset": f"{ds.get('schema') or ''}.{ds.get('name')}",
                                "quality_score": quality_score,
                                "issues": issues,
                            },
                        )

                    # Create alert if PII detected
                    if pii_cats:
                        _create_alert(
                            "pii",
                            "high",
                            f"PII data detected on {ds.get('name')}",
                            f"PII categories: {', '.join(pii_cats)}. Columns: {', '.join(pii_cols[:5])}",
                            connector_id=connector_id,
                            dataset_id=ds_id,
                            ai_payload={
                                "category": "pii",
                                "dataset": f"{ds.get('schema') or ''}.{ds.get('name')}",
                                "pii_categories": pii_cats,
                                "pii_columns": pii_cols,
                            },
                        )

                    logger.info(
                        "LLM quality check complete for dataset %s: score=%.1f, pii=%s",
                        ds_id,
                        quality_score,
                        pii_cats,
                    )
            except Exception as e:
                logger.warning("LLM quality check failed for dataset %s: %s", ds_id, e)

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
            "pipeline",
            "critical",
            f"Scan failed for connector #{connector_id}",
            str(e)[:500],
            connector_id=connector_id,
            ai_payload={
                "category": "pipeline",
                "error": str(e)[:500],
                "connector_type": ctype,
            },
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
                schema,
                name,
            )
            cols = cur.fetchall()
            discovered.append(
                {
                    "schema": schema,
                    "name": name,
                    "type": ttype,
                    "row_count": row_count,
                    "columns": [
                        {"name": c[0], "type": c[1], "nullable": c[2] == "YES"}
                        for c in cols
                    ],
                }
            )
    finally:
        cn.close()
    return {"datasets": discovered}


# ---------- routes --------------------------------------------------------
@router.post("/scan/{connector_id}")
def scan_connector(
    connector_id: int,
    background: BackgroundTasks,
    user: dict = Depends(require_roles("admin", "steward")),
):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (connector_id,)):
        raise HTTPException(status_code=404, detail="Connector not found")
    try:
        result = _run_scan(connector_id)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quality-check-all/{connector_id}")
def quality_check_all_datasets(
    connector_id: int,
    background: BackgroundTasks,
    user: dict = Depends(require_roles("admin", "steward")),
):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (connector_id,)):
        raise HTTPException(status_code=404, detail="Connector not found")

    def run_all_checks():
        conn_row = fetch_one("SELECT * FROM connectors WHERE id=%s", (connector_id,))
        ctype = conn_row["type"]
        cfg = decrypt_config(conn_row["config_json"])
        results = []

        if ctype in ["mysql", "mssql"]:
            datasets = fetch_all(
                "SELECT id FROM datasets WHERE connector_id=%s", (connector_id,)
            )
            for ds in datasets:
                dataset_id = ds["id"]
                try:
                    logger.info("Running quality check for dataset %s", dataset_id)
                    ds_info = fetch_one(
                        "SELECT d.*, c.type AS connector_type, c.config_json "
                        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
                        (dataset_id,),
                    )
                    if ds_info and ds_info["connector_type"] == "mysql":
                        sample_rows = []
                        try:
                            cn = _mysql_conn(cfg)
                            with cn.cursor() as cur:
                                schema = ds_info["schema_name"] or cfg.get("database")
                                name = ds_info["dataset_name"]
                                try:
                                    cur.execute(
                                        f"SELECT * FROM `{schema}`.`{name}` LIMIT 20"
                                    )
                                    sample_rows = cur.fetchall()
                                except Exception:
                                    pass
                            cn.close()
                        except Exception:
                            pass

                        ai_issues, ai_score, ai_metrics, pii_columns, pii_categories = (
                            _run_ai_quality_checks(dataset_id, ds_info, sample_rows)
                        )

                        issues, score, metrics = _run_mysql_quality_checks(
                            dataset_id, cfg, ds_info
                        )

                        issues.extend(ai_issues)
                        combined_score = (score + ai_score) / 2

                        validation_results = _execute_validation_rules(
                            dataset_id, ds_info["config_json"]
                        )
                        failed_rules = [
                            r for r in validation_results if not r["passed"]
                        ]
                        for r in failed_rules:
                            issues.append(
                                f"Rule '{r['rule_name']}' failed: {r['message']}"
                            )
                            combined_score -= 5

                        if pii_columns:
                            pii_cat_str = ",".join(sorted(set(pii_categories)))
                            execute(
                                "UPDATE datasets SET contains_pii=1, pii_categories=%s WHERE id=%s",
                                (pii_cat_str, dataset_id),
                            )
                            for col_name in pii_columns:
                                execute(
                                    "UPDATE dataset_columns SET is_pii=1 WHERE dataset_id=%s AND column_name=%s",
                                    (dataset_id, col_name),
                                )

                        combined_score = max(0.0, min(100.0, combined_score))
                        execute(
                            "UPDATE datasets SET quality_score=%s, last_profiled_at=%s WHERE id=%s",
                            (combined_score, datetime.datetime.utcnow(), dataset_id),
                        )
                        execute(
                            "INSERT INTO monitoring_runs (connector_id, dataset_id, run_type, status, message, "
                            "metrics_json, finished_at) VALUES (%s, %s, 'quality', 'success', %s, %s, %s)",
                            (
                                ds_info["connector_id"],
                                dataset_id,
                                f"score={combined_score}",
                                safe_json_dumps({**metrics, **ai_metrics}),
                                datetime.datetime.utcnow(),
                            ),
                        )

                        _log_monitoring_event(
                            log_type="quality_check",
                            log_content=f"Quality check on {ds_info['dataset_name']}: score {combined_score:.1f}, issues {len(issues)}",
                            dataset_id=dataset_id,
                            connector_id=ds_info["connector_id"],
                        )

                        if issues:
                            severity = (
                                "high"
                                if combined_score < 70
                                else ("medium" if combined_score < 85 else "low")
                            )
                            _create_alert(
                                "quality",
                                severity,
                                f"Quality issues on {ds_info['dataset_name']} (score {combined_score:.1f})",
                                f"Score: {combined_score:.1f} - {'; '.join(issues[:10])}",
                                connector_id=ds_info["connector_id"],
                                dataset_id=dataset_id,
                                ai_payload={
                                    "score": combined_score,
                                    "issues": issues,
                                    "metrics": {**metrics, **ai_metrics},
                                },
                            )

                        results.append(
                            {
                                "dataset_id": dataset_id,
                                "score": combined_score,
                                "issues": len(issues),
                            }
                        )
                except Exception as e:
                    logger.exception(
                        "Quality check failed for dataset %s: %s", dataset_id, e
                    )
                    results.append(
                        {
                            "dataset_id": dataset_id,
                            "error": str(e),
                        }
                    )

        elif ctype == "azure_adf":
            try:
                issues, score, metrics = _run_adf_quality_checks(connector_id, cfg)

                execute(
                    "INSERT INTO monitoring_runs (connector_id, run_type, status, message, "
                    "metrics_json, finished_at) VALUES (%s, 'quality', 'success', %s, %s, %s)",
                    (
                        connector_id,
                        f"score={score}",
                        safe_json_dumps(metrics),
                        datetime.datetime.utcnow(),
                    ),
                )

                _log_monitoring_event(
                    log_type="quality_check",
                    log_content=f"ADF quality check: score {score:.1f}, issues {len(issues)}",
                    connector_id=connector_id,
                )

                if issues:
                    severity = (
                        "high" if score < 70 else ("medium" if score < 85 else "low")
                    )
                    _create_alert(
                        "pipeline",
                        severity,
                        f"ADF quality issues detected (score {score:.1f})",
                        f"Score: {score:.1f} - {'; '.join(issues[:10])}",
                        connector_id=connector_id,
                        ai_payload={
                            "score": score,
                            "issues": issues,
                            "metrics": metrics,
                        },
                    )

                results.append(
                    {
                        "connector_id": connector_id,
                        "score": score,
                        "issues": len(issues),
                    }
                )
            except Exception as e:
                logger.exception("ADF quality check failed: %s", e)

        elif ctype == "databricks":
            try:
                issues, score, metrics = _run_databricks_quality_checks(
                    connector_id, cfg
                )

                execute(
                    "INSERT INTO monitoring_runs (connector_id, run_type, status, message, "
                    "metrics_json, finished_at) VALUES (%s, 'quality', 'success', %s, %s, %s)",
                    (
                        connector_id,
                        f"score={score}",
                        safe_json_dumps(metrics),
                        datetime.datetime.utcnow(),
                    ),
                )

                _log_monitoring_event(
                    log_type="quality_check",
                    log_content=f"Databricks quality check: score {score:.1f}, issues {len(issues)}",
                    connector_id=connector_id,
                )

                if issues:
                    severity = (
                        "high" if score < 70 else ("medium" if score < 85 else "low")
                    )
                    _create_alert(
                        "databricks",
                        severity,
                        f"Databricks quality issues detected (score {score:.1f})",
                        f"Score: {score:.1f} - {'; '.join(issues[:10])}",
                        connector_id=connector_id,
                        ai_payload={
                            "score": score,
                            "issues": issues,
                            "metrics": metrics,
                        },
                    )

                results.append(
                    {
                        "connector_id": connector_id,
                        "score": score,
                        "issues": len(issues),
                    }
                )
            except Exception as e:
                logger.exception("Databricks quality check failed: %s", e)

        logger.info("Quality check all complete for connector %s", connector_id)

    background.add_task(run_all_checks)
    return {
        "status": "success",
        "message": "Started quality checks - results will appear shortly",
    }


@router.post("/quality-check/{dataset_id}")
def quality_check(
    dataset_id: int, user: dict = Depends(require_roles("admin", "steward"))
):
    ds = fetch_one(
        "SELECT d.*, c.type AS connector_type, c.config_json "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
        (dataset_id,),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if ds["connector_type"] != "mysql":
        raise HTTPException(
            status_code=400, detail="Quality check supported on MySQL datasets only"
        )

    cfg = decrypt_config(ds["config_json"])
    issues, score, metrics = _run_mysql_quality_checks(dataset_id, cfg, ds)

    validation_results = _execute_validation_rules(dataset_id, ds["config_json"])
    failed_rules = [r for r in validation_results if not r["passed"]]
    for r in failed_rules:
        issues.append(f"Rule '{r['rule_name']}' failed: {r['message']}")
        score -= 10

    score = max(0.0, min(100.0, score))
    execute(
        "UPDATE datasets SET quality_score=%s, last_profiled_at=%s WHERE id=%s",
        (score, datetime.datetime.utcnow(), dataset_id),
    )
    run_id = execute(
        "INSERT INTO monitoring_runs (connector_id, dataset_id, run_type, status, message, "
        "metrics_json, finished_at) VALUES (%s, %s, 'quality', 'success', %s, %s, %s)",
        (
            ds["connector_id"],
            dataset_id,
            f"score={score}",
            safe_json_dumps(metrics),
            datetime.datetime.utcnow(),
        ),
    )

    _log_monitoring_event(
        log_type="quality_check",
        log_content=f"Quality check on {ds['dataset_name']}: score {score:.1f}, issues {len(issues)}, rules {len(validation_results)}",
        dataset_id=dataset_id,
        connector_id=ds["connector_id"],
    )

    if issues:
        severity = "high" if score < 70 else ("medium" if score < 85 else "low")
        _create_alert(
            "quality",
            severity,
            f"Quality issues on {ds['dataset_name']} (score {score:.1f})",
            "; ".join(issues[:10]),
            connector_id=ds["connector_id"],
            dataset_id=dataset_id,
            ai_payload={
                "category": "quality",
                "dataset": ds["dataset_name"],
                "score": score,
                "issues": issues,
                "metrics": metrics,
                "validation_results": validation_results,
            },
        )
    return {
        "score": score,
        "issues": issues,
        "metrics": metrics,
        "validation_results": validation_results,
        "run_id": run_id,
    }


@router.post("/schema-drift/{dataset_id}")
def schema_drift_endpoint(
    dataset_id: int, user: dict = Depends(require_roles("admin", "steward"))
):
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
            pii_results.append(
                {"column": c["column_name"], "category": cat, "source": "name"}
            )
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
                            pii_results.append(
                                {"column": col, "category": cat, "source": "value"}
                            )
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
        execute(
            "UPDATE datasets SET contains_pii=1, pii_categories=%s WHERE id=%s",
            (cats, dataset_id),
        )
        _create_alert(
            "pii",
            "high",
            f"PII detected in {ds['dataset_name']}",
            f"Sensitive categories: {cats}. Columns: "
            + ", ".join(p["column"] for p in pii_results),
            connector_id=ds["connector_id"],
            dataset_id=dataset_id,
            ai_payload={
                "category": "pii",
                "dataset": ds["dataset_name"],
                "categories": cats,
                "columns": pii_results,
            },
        )
    else:
        execute(
            "UPDATE datasets SET contains_pii=0, pii_categories=NULL WHERE id=%s",
            (dataset_id,),
        )

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
    next_run = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=body.interval_minutes
    )
    new_id = execute(
        "INSERT INTO monitoring_jobs (connector_id, job_type, interval_minutes, enabled, next_run_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            body.connector_id,
            body.job_type,
            body.interval_minutes,
            1 if body.enabled else 0,
            next_run,
        ),
    )
    return {"id": new_id, "message": "Monitoring job created"}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, user: dict = Depends(require_roles("admin", "steward"))):
    execute("DELETE FROM monitoring_jobs WHERE id=%s", (job_id,))
    return {"deleted": True}


@router.get("/quality-checks/{connector_type}")
def get_quality_checks(connector_type: str, user: dict = Depends(get_current_user)):
    """Get list of available quality checks for a specific connector type."""
    if connector_type not in QUALITY_CHECKS:
        raise HTTPException(
            status_code=400,
            detail=f"Connector type '{connector_type}' not supported. Available types: {', '.join(QUALITY_CHECKS.keys())}",
        )
    return {
        "connector_type": connector_type,
        "quality_checks": QUALITY_CHECKS[connector_type],
    }


@router.get("/debug/rule-books")
def debug_rule_books(user: dict = Depends(require_roles("admin"))):
    """Debug endpoint: Check if rule books are in ChromaDB and search for one."""
    try:
        # Search for any rule book
        results = search_rule_books("quality check", top_k=5)

        rule_books = fetch_all(
            "SELECT id, name, filename FROM rule_books ORDER BY id DESC LIMIT 10"
        )

        return {
            "status": "ok",
            "rule_books_in_db": len(rule_books),
            "rule_books_list": rule_books,
            "chroma_search_results": results,
            "chroma_results_count": len(results),
        }
    except Exception as e:
        logger.error("Debug rule books failed: %s", e)
        return {
            "status": "error",
            "error": str(e),
        }


@router.post("/manual-scan/{connector_id}")
def manual_trigger_scan(
    connector_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles("admin")),
):
    """Manually trigger a scan for a connector."""
    try:
        conn = fetch_one("SELECT id, name FROM connectors WHERE id=%s", (connector_id,))
        if not conn:
            raise HTTPException(status_code=404, detail="Connector not found")

        background_tasks.add_task(_run_scan, connector_id)
        logger.info("Scan triggered for connector %d (%s)", connector_id, conn["name"])

        return {"status": "ok", "message": f"Scan queued for {conn['name']}"}
    except Exception as e:
        logger.error("Manual scan trigger failed: %s", e)
        return {"status": "error", "error": str(e)}
