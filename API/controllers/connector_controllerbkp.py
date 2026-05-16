"""
Connector Controller — CRUD + test + dataset scan + AUTO quality check on create.

Scans discover datasets/pipelines by NAME + TYPE + SCHEMA only.
The monitoring controller does the full Python + LLM analysis afterwards.
"""
import socket
import pymysql
import requests
import json
from datetime import datetime, timedelta, timezone

from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user, require_roles
from utils.common import encrypt_config, decrypt_config, mask_secret, logger
from utils.constants import CONNECTOR_TYPES


router = APIRouter(prefix="/api/connectors", tags=["connectors"])


# ============================================================
# SCHEMAS
# ============================================================
class ConnectorIn(BaseModel):
    name: str
    type: str
    config: Dict[str, Any]


class ConnectorTestIn(BaseModel):
    type: str
    config: Dict[str, Any]


# ============================================================
# TEST-CONNECTION HELPERS
# ============================================================
def _test_mysql(c: Dict[str, Any]) -> Dict[str, Any]:
    db = (c.get("database") or "").strip() or None
    cn = pymysql.connect(
        host=c["host"],
        port=int(c.get("port") or 3306),
        user=c["username"],
        password=c.get("password") or "",
        database=db,
        connect_timeout=8,
    )
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()
        return {"ok": True, "version": (ver[0] if ver else "")}
    finally:
        cn.close()


def _test_mssql(c: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import pyodbc  # type: ignore
        drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
        if not drivers:
            raise RuntimeError("No SQL Server ODBC driver installed")
        cs = (
            f"DRIVER={{{drivers[0]}}};SERVER={c['server']},{int(c.get('port') or 1433)};"
            f"DATABASE={c.get('database','')};UID={c['username']};PWD={c.get('password','')};"
            "Encrypt=no;TrustServerCertificate=yes;"
        )
        cn = pyodbc.connect(cs, timeout=8)
        cn.cursor().execute("SELECT 1")
        cn.close()
        return {"ok": True, "version": "MSSQL reachable"}
    except ImportError:
        with socket.create_connection(
            (c["server"], int(c.get("port") or 1433)), timeout=5
        ):
            return {"ok": True, "version": "TCP probe (pyodbc not installed)"}


def _azure_token(c: Dict[str, Any]) -> str:
    r = requests.post(
        f"https://login.microsoftonline.com/{c['tenant_id']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": c["client_id"],
            "client_secret": c["client_secret"],
            "scope": "https://management.azure.com/.default",
        },
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Azure auth failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def _test_azure_adf(c: Dict[str, Any]) -> Dict[str, Any]:
    tok = _azure_token(c)
    url = (
        f"https://management.azure.com/subscriptions/{c['subscription_id']}"
        f"/resourceGroups/{c['resource_group']}"
        f"/providers/Microsoft.DataFactory/factories/{c['factory_name']}"
        "?api-version=2018-06-01"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"ADF not reachable: {r.status_code} {r.text[:200]}")
    return {"ok": True, "version": f"ADF {c['factory_name']} reachable"}


def _test_databricks(c: Dict[str, Any]) -> Dict[str, Any]:
    base = c["workspace_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {c['token']}"}
    r = requests.get(f"{base}/api/2.1/jobs/list?limit=1", headers=headers, timeout=10)
    if r.status_code != 200:
        r = requests.get(f"{base}/api/2.0/jobs/list", headers=headers, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"Databricks failed: {r.status_code} {r.text[:200]}")
    return {"ok": True, "version": "Databricks workspace reachable"}


def _test_github(c: Dict[str, Any]) -> Dict[str, Any]:
    repo = (c.get("repository_url") or "").rstrip("/")
    path = repo.split("github.com/", 1)[-1] if repo.startswith("http") else repo
    r = requests.get(
        f"https://api.github.com/repos/{path}",
        headers={
            "Authorization": f"Bearer {c['token']}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"GitHub failed: {r.status_code} {r.text[:200]}")
    return {"ok": True, "version": f"GitHub repo {path} reachable"}


def test_connection(conn_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if conn_type == "mysql":      return _test_mysql(config)
    if conn_type == "mssql":      return _test_mssql(config)
    if conn_type == "azure_adf":  return _test_azure_adf(config)
    if conn_type == "databricks": return _test_databricks(config)
    if conn_type == "github":     return _test_github(config)
    raise RuntimeError(f"Unsupported connector type: {conn_type}")


# ============================================================
# DATASET SCANNERS — discovery only, returns list of {name, type, schema}
# ============================================================
def _scan_mysql(cfg: Dict[str, Any]) -> List[dict]:
    db = (cfg.get("database") or "").strip() or None
    cn = pymysql.connect(
        host=cfg["host"],
        port=int(cfg.get("port") or 3306),
        user=cfg["username"],
        password=cfg.get("password") or "",
        database=db,
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )
    out: List[dict] = []
    try:
        with cn.cursor() as cur:
            if db:
                target_dbs = [db]
            else:
                cur.execute(
                    "SELECT SCHEMA_NAME FROM information_schema.schemata "
                    "WHERE SCHEMA_NAME NOT IN "
                    "('mysql','information_schema','performance_schema','sys')"
                )
                target_dbs = [r["SCHEMA_NAME"] for r in cur.fetchall()]
            for d in target_dbs:
                cur.execute(
                    "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.tables "
                    "WHERE TABLE_SCHEMA=%s",
                    (d,),
                )
                for row in cur.fetchall():
                    out.append({
                        "name":   row["TABLE_NAME"],
                        "type":   "view" if row["TABLE_TYPE"] == "VIEW" else "table",
                        "schema": d,
                    })
    finally:
        cn.close()
    return out


def _scan_mssql(cfg: Dict[str, Any]) -> List[dict]:
    try:
        import pyodbc  # type: ignore
    except ImportError:
        logger.warning("pyodbc not installed — MSSQL scan returns empty")
        return []
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if not drivers:
        return []
    cs = (
        f"DRIVER={{{drivers[0]}}};SERVER={cfg['server']},{int(cfg.get('port') or 1433)};"
        f"DATABASE={cfg.get('database','')};UID={cfg['username']};PWD={cfg.get('password','')};"
        "Encrypt=no;TrustServerCertificate=yes;"
    )
    cn = pyodbc.connect(cs, timeout=10)
    out: List[dict] = []
    try:
        cur = cn.cursor()
        cur.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES"
        )
        for r in cur.fetchall():
            out.append({
                "name":   r[1],
                "type":   "view" if r[2] == "VIEW" else "table",
                "schema": r[0],
            })
    finally:
        cn.close()
    return out


def _scan_databricks(cfg: Dict[str, Any]) -> List[dict]:
    """Pipelines only — Jobs + DLT pipelines. Discovery only.
    Full monitoring metrics built later by monitoring_controller._check_pipeline.
    """
    base = cfg["workspace_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['token']}"}
    out: List[dict] = []

    # Classic Jobs
    try:
        r = requests.get(f"{base}/api/2.1/jobs/list?limit=100",
                         headers=headers, timeout=20)
        if r.status_code != 200:
            r = requests.get(f"{base}/api/2.0/jobs/list",
                             headers=headers, timeout=20)
        if r.status_code == 200:
            for j in r.json().get("jobs", []) or []:
                name = (j.get("settings") or {}).get("name") or f"job_{j.get('job_id')}"
                out.append({"name": name, "type": "pipeline", "schema": "databricks"})
    except Exception as e:
        logger.warning("Databricks jobs scan failed: %s", e)

    # DLT pipelines — separate try block, separate loop variable
    try:
        r = requests.get(f"{base}/api/2.0/pipelines?max_results=100",
                         headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            for p in (data.get("statuses") or data.get("pipelines") or []):
                pname = p.get("name") or p.get("pipeline_id")
                if not pname:
                    continue
                out.append({"name": pname, "type": "pipeline", "schema": "databricks"})
    except Exception as e:
        logger.debug("Databricks DLT scan failed: %s", e)

    logger.info("Databricks scan: %d pipelines discovered", len(out))
    return out

# Mapping of ADF dataset types → category for cleaner handling
_ADF_FILE_TYPES = {
    "DelimitedText", "Parquet", "Json", "Avro", "Orc",
    "Binary", "Excel", "Xml"
}
_ADF_TABLE_TYPES = {
    "AzureSqlTable", "AzureSqlDWTable", "AzurePostgreSqlTable",
    "AzureMySqlTable", "AzureMariaDBTable", "AzureSqlMITable",
    "SqlServerTable", "OracleTable", "MySqlTable", "PostgreSqlTable",
    "SnowflakeTable", "AmazonRedshiftTable", "GoogleBigQueryObject",
    "DynamicsEntity", "SalesforceObject", "MongoDbCollection",
    "CosmosDbSqlApiCollection", "CosmosDbMongoDbApiCollection",
    "AzureTableStorage", "RestResource"
}


def _extract_adf_dataset_meta(dataset_name: str, props: dict) -> dict:
    """Pull useful metadata from any ADF dataset shape — SQL, CSV, Parquet, etc.

    Returns a dict with: dataset_type, source_kind, location_info,
    table_info, columns (always a list, can be empty).
    """
    if not isinstance(props, dict):
        props = {}

    ds_type = props.get("type") or "Unknown"
    type_props = props.get("typeProperties")
    if not isinstance(type_props, dict):
        type_props = {}

    # ----- COLUMNS -----
    # properties.schema can be: list of dicts, string, None, or missing
    raw_schema = props.get("schema")
    columns = []
    if isinstance(raw_schema, list):
        for c in raw_schema:
            if isinstance(c, dict):
                columns.append({
                    "name": c.get("name"),
                    "type": c.get("type"),
                })
            # ignore non-dict entries silently

    # ----- BRANCH BY DATASET CATEGORY -----
    if ds_type in _ADF_FILE_TYPES:
        # File-based dataset (CSV, Parquet, JSON, Binary etc.)
        location = type_props.get("location")
        if not isinstance(location, dict):
            location = {}

        location_info = {
            "kind":         location.get("type"),  # AzureBlobStorageLocation etc
            "container":    location.get("container") or location.get("fileSystem"),
            "folder_path":  location.get("folderPath"),
            "file_name":    location.get("fileName"),
        }

        # CSV-specific extras
        delimiter = None
        first_row_header = None
        encoding = None
        compression = None
        if ds_type == "DelimitedText":
            delimiter         = type_props.get("columnDelimiter")
            first_row_header  = type_props.get("firstRowAsHeader")
            encoding          = type_props.get("encodingName")
        elif ds_type == "Parquet":
            compression       = type_props.get("compressionCodec")
        elif ds_type == "Json":
            encoding          = type_props.get("encodingName")

        return {
            "dataset_name":  dataset_name,
            "dataset_type":  ds_type,
            "source_kind":   "file",
            "location":      location_info,
            "delimiter":     delimiter,
            "first_row_as_header": first_row_header,
            "encoding":      encoding,
            "compression":   compression,
            "schema_name":   None,
            "table_name":    None,
            "columns":       columns,
        }

    if ds_type in _ADF_TABLE_TYPES:
        # Table-based dataset (SQL, NoSQL, REST etc.)
        schema_name = type_props.get("schema")
        if not isinstance(schema_name, str):
            schema_name = None
        table_name = (
            type_props.get("table")
            or type_props.get("tableName")
            or type_props.get("collection")
            or type_props.get("collectionName")
        )
        if not isinstance(table_name, str):
            table_name = None

        return {
            "dataset_name":  dataset_name,
            "dataset_type":  ds_type,
            "source_kind":   "table",
            "location":      None,
            "delimiter":     None,
            "first_row_as_header": None,
            "encoding":      None,
            "compression":   None,
            "schema_name":   schema_name,
            "table_name":    table_name,
            "columns":       columns,
        }

    # Unknown type — store what we can without making assumptions
    return {
        "dataset_name":  dataset_name,
        "dataset_type":  ds_type,
        "source_kind":   "unknown",
        "location":      None,
        "delimiter":     None,
        "first_row_as_header": None,
        "encoding":      None,
        "compression":   None,
        "schema_name":   None,
        "table_name":    None,
        "columns":       columns,
    }


def _scan_adf(cfg: Dict[str, Any]) -> List[dict]:
    """ADF scan — handles datasets of ALL types (SQL, CSV, Parquet, JSON, etc.)
    plus pipelines with run + activity logs.
    """
    try:
        tok = _azure_token(cfg)
    except Exception as e:
        logger.warning("ADF auth failed: %s", e)
        return []

    base = (
        f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
        f"/resourceGroups/{cfg['resource_group']}"
        f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
    )
    headers = {"Authorization": f"Bearer {tok}"}
    out: List[dict] = []

    # ========================================================
    # DATASETS — type-aware: SQL tables, CSV, Parquet, JSON, etc.
    # ========================================================
    try:
        r = requests.get(
            f"{base}/datasets?api-version=2018-06-01",
            headers=headers,
            timeout=20,
        )
        if r.status_code == 200:
            payload = r.json() if r.content else {}
            items = payload.get("value", []) if isinstance(payload, dict) else []
            logger.info("ADF: %d datasets returned by API", len(items))

            for x in items:
                try:
                    if not isinstance(x, dict):
                        logger.warning(
                            "ADF dataset item not a dict: %r", str(x)[:100]
                        )
                        continue

                    dataset_name = x.get("name")
                    if not dataset_name:
                        continue

                    props = x.get("properties") or {}
                    meta = _extract_adf_dataset_meta(dataset_name, props)

                    logger.info(
                        "ADF dataset '%s' → type=%s, source_kind=%s",
                        dataset_name, meta["dataset_type"], meta["source_kind"]
                    )

                    profiling_json = {
                        "profile": {
                            "source": {
                                "type": "ADF",
                                "asset_kind": "dataset",
                                "name": dataset_name,
                                "dataset_type": meta["dataset_type"],
                                "source_kind":  meta["source_kind"],
                            },
                            "summary": {
                                "technical_context": {
                                    "generated_by": "python",
                                    "dataset_type": meta["dataset_type"],
                                    "source_kind":  meta["source_kind"],
                                    "location":     meta["location"],
                                    "delimiter":    meta["delimiter"],
                                    "first_row_as_header": meta["first_row_as_header"],
                                    "encoding":     meta["encoding"],
                                    "compression":  meta["compression"],
                                    "tables": [
                                        {
                                            "table_name":   meta["table_name"],
                                            "schema":       meta["schema_name"],
                                            "column_count": len(meta["columns"]),
                                            "columns":      meta["columns"],
                                        }
                                    ]
                                }
                            }
                        }
                    }

                    out.append({
                        "name":            dataset_name,
                        "type":            "dataset",
                        "schema":          "adf",
                        "profiling_json":  json.dumps(profiling_json),
                        "monitoring_json": None,
                    })

                except Exception as e:
                    logger.warning(
                        "ADF dataset parse failed for %s: %s",
                        x.get("name") if isinstance(x, dict) else "<unknown>",
                        e
                    )
                    # Register the dataset by name only so it's not lost
                    try:
                        nm = x.get("name") if isinstance(x, dict) else None
                        if nm:
                            out.append({
                                "name":            nm,
                                "type":            "dataset",
                                "schema":          "adf",
                                "profiling_json":  None,
                                "monitoring_json": None,
                            })
                    except Exception:
                        pass
        else:
            logger.warning("ADF datasets API %d: %s",
                           r.status_code, r.text[:300])

    except Exception as e:
        logger.warning("ADF datasets fetch failed: %s", e)

    # ========================================================
    # PIPELINES — full run + activity logs (unchanged behavior)
    # ========================================================
    try:
        r = requests.get(
            f"{base}/pipelines?api-version=2018-06-01",
            headers=headers,
            timeout=20,
        )

        if r.status_code == 200:
            pipeline_items = r.json().get("value", []) or []
            logger.info("ADF: %d pipelines returned by API", len(pipeline_items))

            for x in pipeline_items:

                if not isinstance(x, dict):
                    continue

                pipeline_name = x.get("name")
                if not pipeline_name:
                    continue

                try:
                    end_time = datetime.now(timezone.utc)
                    start_time = end_time - timedelta(days=7)

                    pipeline_runs_url = (
                        f"{base}/queryPipelineRuns?api-version=2018-06-01"
                    )
                    payload = {
                        "lastUpdatedAfter":
                            start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "lastUpdatedBefore":
                            end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "filters": [
                            {
                                "operand": "PipelineName",
                                "operator": "Equals",
                                "values": [pipeline_name]
                            }
                        ]
                    }

                    run_resp = requests.post(
                        pipeline_runs_url,
                        headers={
                            **headers,
                            "Content-Type": "application/json"
                        },
                        json=payload,
                        timeout=30
                    )

                    total_runs = 0
                    failed_runs = 0
                    runtime_list = []
                    latest_error = None
                    monitoring_runs = []

                    if run_resp.status_code == 200:
                        runs = run_resp.json().get("value", []) or []
                        total_runs = len(runs)

                        for rr in runs:
                            status = rr.get("status")
                            run_id = rr.get("runId")
                            run_start = rr.get("runStart")
                            run_end = rr.get("runEnd")
                            duration = 0

                            if status != "Succeeded":
                                failed_runs += 1

                            if run_start and run_end:
                                try:
                                    st = datetime.fromisoformat(
                                        run_start.replace("Z", "+00:00")
                                    )
                                    et = datetime.fromisoformat(
                                        run_end.replace("Z", "+00:00")
                                    )
                                    duration = int((et - st).total_seconds())
                                    runtime_list.append(duration)
                                except Exception:
                                    pass

                            # -----------------------------------------
                            # ACTIVITY RUNS
                            # -----------------------------------------
                            activity_url = (
                                f"{base}/pipelineruns/{run_id}/queryActivityruns"
                                f"?api-version=2018-06-01"
                            )
                            activity_payload = {
                                "lastUpdatedAfter":
                                    start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "lastUpdatedBefore":
                                    end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                            }

                            activities = []
                            try:
                                act_resp = requests.post(
                                    activity_url,
                                    headers={
                                        **headers,
                                        "Content-Type": "application/json"
                                    },
                                    json=activity_payload,
                                    timeout=30
                                )

                                if act_resp.status_code == 200:
                                    for act in act_resp.json().get("value", []):
                                        error_message = (
                                            act.get("error", {}) or {}
                                        ).get("message")

                                        if error_message and not latest_error:
                                            latest_error = error_message[:1000]

                                        activities.append({
                                            "activity_name":  act.get("activityName"),
                                            "activity_type":  act.get("activityType"),
                                            "status":         act.get("status"),
                                            "duration_in_ms": act.get("durationInMs"),
                                            "error":          error_message,
                                        })
                            except Exception as e:
                                logger.warning(
                                    "ADF activity fetch failed for run %s: %s",
                                    run_id, e
                                )

                            monitoring_runs.append({
                                "run_id":           run_id,
                                "status":           status,
                                "duration_seconds": duration,
                                "activities":       activities,
                            })

                    # ---------------- PYTHON METRICS ----------------
                    success_rate = 0
                    avg_runtime = 0

                    if total_runs > 0:
                        success_rate = round(
                            ((total_runs - failed_runs) / total_runs) * 100,
                            2
                        )

                    if runtime_list:
                        avg_runtime = int(sum(runtime_list) / len(runtime_list))

                    monitoring_json = {
                        "profile": {
                            "source": {
                                "type":       "ADF",
                                "asset_kind": "pipeline",
                                "name":       pipeline_name,
                            },
                            "data_quality": {
                                "quality_score": {
                                    "value":        success_rate,
                                    "generated_by": "python",
                                },
                                "missing_data": {
                                    "percentage":   0,
                                    "band":         "Green",
                                    "generated_by": "python",
                                },
                                "junk_data": {
                                    "percentage":   0,
                                    "band":         "Green",
                                    "generated_by": "python",
                                },
                                "outlier": {
                                    "percentage": failed_runs,
                                    "band":
                                        "Red"   if failed_runs > 5
                                        else "Amber" if failed_runs > 0
                                        else "Green",
                                    "generated_by": "python",
                                },
                                "trend_analysis": {
                                    "text":
                                        f"Pipeline success rate is "
                                        f"{success_rate}% over the last 7 days.",
                                    "generated_by": "llm",
                                }
                            },
                            "summary": {
                                "technical_context": {
                                    "generated_by": "python",
                                    "tables": [
                                        {
                                            "pipeline_name":       pipeline_name,
                                            "total_runs":          total_runs,
                                            "failed_runs":         failed_runs,
                                            "avg_runtime_seconds": avg_runtime,
                                            "latest_error":        latest_error,
                                        }
                                    ]
                                }
                            }
                        },
                        "runs": monitoring_runs
                    }

                    out.append({
                        "name":            pipeline_name,
                        "type":            "pipeline",
                        "schema":          "adf",
                        "profiling_json":  None,
                        "monitoring_json": json.dumps(monitoring_json),
                    })

                except Exception as e:
                    logger.warning(
                        "ADF pipeline analysis failed for %s : %s",
                        pipeline_name, e
                    )
                    out.append({
                        "name":            pipeline_name,
                        "type":            "pipeline",
                        "schema":          "adf",
                        "profiling_json":  None,
                        "monitoring_json": None,
                    })
        else:
            logger.warning("ADF pipelines API %d: %s",
                           r.status_code, r.text[:300])

    except Exception as e:
        logger.warning("ADF pipelines fetch failed: %s", e)

    logger.info(
        "ADF scan complete: %d total items (datasets + pipelines)", len(out)
    )
    return out


def _scan_github(cfg: Dict[str, Any]) -> List[dict]:
    repo = (cfg.get("repository_url") or "").rstrip("/")
    path = repo.split("github.com/", 1)[-1] if repo.startswith("http") else repo
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Accept": "application/vnd.github+json",
    }
    out: List[dict] = []
    try:
        r = requests.get(
            f"https://api.github.com/repos/{path}/actions/workflows",
            headers=headers, timeout=15,
        )
        if r.status_code == 200:
            for wf in r.json().get("workflows", []):
                out.append({
                    "name":   wf.get("name") or wf.get("path"),
                    "type":   "workflow",
                    "schema": "actions",
                })
    except Exception as e:
        logger.warning("GitHub workflows fetch failed: %s", e)
    return out


SCAN_MAP = {
    "mysql":      _scan_mysql,
    "mssql":      _scan_mssql,
    "databricks": _scan_databricks,
    "azure_adf":  _scan_adf,
    "github":     _scan_github,
}


# ============================================================
# SCAN ENGINE — discovers datasets + AUTO-RUNS QUALITY CHECK
# ============================================================
def run_scan(connector_id: int):
    try:
        connector = fetch_one("SELECT * FROM connectors WHERE id=%s", (connector_id,))
        if not connector:
            logger.error("Scan: connector %s not found", connector_id)
            return
        cfg = decrypt_config(connector["config_json"])
        ctype = connector["type"]
        scanner = SCAN_MAP.get(ctype)
        if not scanner:
            logger.warning("No scanner for type %s", ctype)
            return

        datasets = scanner(cfg) or []
        logger.info("Connector %s (%s): %d datasets discovered",
                    connector_id, ctype, len(datasets))

        new_datasets_added = 0
        for d in datasets:
            # De-dupe by (connector, schema, name, dataset_type)
            existing = fetch_one(
                "SELECT id FROM datasets "
                "WHERE connector_id=%s "
                "  AND IFNULL(schema_name,'')=%s "
                "  AND dataset_name=%s "
                "  AND dataset_type=%s",
                (connector_id, d.get("schema") or "", d["name"], d["type"]),
            )
            if existing:
                continue
            # execute(
            #     "INSERT INTO datasets "
            #     "(connector_id, dataset_name, dataset_type, schema_name, "
            #     " confidence_score, pii_percentage, outlier_count) "
            #     "VALUES (%s, %s, %s, %s, 0, 0, 0)",
            #     (connector_id, d["name"], d["type"], d.get("schema")),
            # )
            execute(
                "INSERT INTO datasets "
                "("
                "connector_id, "
                "dataset_name, "
                "dataset_type, "
                "schema_name, "
                "profiling_json, "
                "monitoring_json, "
                "confidence_score, "
                "pii_percentage, "
                "outlier_count"
                ") "
                "VALUES (%s,%s,%s,%s,%s,%s,0,0,0)",
                (
                    connector_id,
                    d["name"],
                    d["type"],
                    d.get("schema"),
                    d.get("profiling_json"),
                    d.get("monitoring_json"),
                ),
            )
            new_datasets_added += 1

        execute(
            "UPDATE connectors SET last_scanned_at=%s, status='Connected' WHERE id=%s",
            (datetime.now(timezone.utc), connector_id),
        )
        logger.info("Connector %s: %d new datasets added",
                    connector_id, new_datasets_added)

        # ====================================================
        # AUTO-TRIGGER QUALITY CHECK — no rulebook required
        # ====================================================
        try:
            from controllers.monitoring_controller import run_quality_for_connector_type
            logger.info(
                "Auto-triggering quality check for connector %s (%s) — "
                "no rulebook required", connector_id, ctype,
            )
            summary = run_quality_for_connector_type(ctype, triggered_by_rulebook_id=0)
            logger.info("Auto quality check complete for connector %s: %s",
                        connector_id, summary)
        except Exception as e:
            logger.exception(
                "Auto quality check failed for connector %s: %s", connector_id, e,
            )

    except Exception as e:
        logger.exception("Scan failed for connector %s: %s", connector_id, e)
        execute(
            "UPDATE connectors SET status='Connection Failed' WHERE id=%s",
            (connector_id,),
        )


# ============================================================
# SERIALIZE / MASK
# ============================================================
def _mask(cfg: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(cfg)
    for f in ("password", "client_secret", "token", "secret"):
        if safe.get(f):
            safe[f] = mask_secret(str(safe[f]))
    return safe


def _serialize(row: dict) -> dict:
    cfg = decrypt_config(row.get("config_json") or "{}")
    return {
        "id":              row["id"],
        "name":            row["name"],
        "type":            row["type"],
        "status":          row["status"],
        "last_tested_at":  row.get("last_tested_at"),
        "last_scanned_at": row.get("last_scanned_at"),
        "created_at":      row.get("created_at"),
        "config":          _mask(cfg),
    }


# ============================================================
# ROUTES
# ============================================================
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


@router.post("/test-connection")
def test_endpoint(body: ConnectorTestIn, user: dict = Depends(get_current_user)):
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid connector type")
    try:
        return {"ok": True, "details": test_connection(body.type, body.config)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/create")
def create_connector(
    body: ConnectorIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles("admin", "steward")),
):
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid connector type")
    try:
        test_connection(body.type, body.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    enc = encrypt_config(body.config)
    try:
        new_id = execute(
            "INSERT INTO connectors (name, type, config_json, status, "
            "last_tested_at, created_at, created_by) "
            "VALUES (%s, %s, %s, 'Connected', %s, %s, %s)",
            (
                body.name, body.type, enc,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
                user.get("user_id"),
            ),
        )
    except pymysql.err.IntegrityError:
        raise HTTPException(status_code=409, detail="Connector name already exists")

    background_tasks.add_task(run_scan, new_id)
    row = fetch_one("SELECT * FROM connectors WHERE id=%s", (new_id,))
    return _serialize(row)


@router.post("/{cid}/test")
def test_existing(
    cid: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    row = fetch_one("SELECT type, config_json FROM connectors WHERE id=%s", (cid,))
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    cfg = decrypt_config(row["config_json"])
    try:
        res = test_connection(row["type"], cfg)
        execute(
            "UPDATE connectors SET status='Connected', last_tested_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), cid),
        )
        background_tasks.add_task(run_scan, cid)
        return {"ok": True, "details": res}
    except Exception as e:
        execute(
            "UPDATE connectors SET status='Connection Failed', last_tested_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), cid),
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
    try:
        test_connection(body.type, body.config)
        status = "Connected"
    except Exception as e:
        logger.warning("Update test failed: %s", e)
        status = "Connection Failed"
    enc = encrypt_config(body.config)
    try:
        execute(
            "UPDATE connectors SET name=%s, type=%s, config_json=%s, status=%s, "
            "last_tested_at=%s WHERE id=%s",
            (body.name, body.type, enc, status, datetime.now(timezone.utc), cid),
        )
    except pymysql.err.IntegrityError:
        raise HTTPException(status_code=409, detail="Connector name already exists")
    if status == "Connected":
        background_tasks.add_task(run_scan, cid)
    row = fetch_one("SELECT * FROM connectors WHERE id=%s", (cid,))
    return _serialize(row)


@router.delete("/{cid}")
def delete_connector(cid: int, user: dict = Depends(require_roles("admin"))):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (cid,)):
        raise HTTPException(status_code=404, detail="Not found")
    execute("DELETE FROM datasets WHERE connector_id=%s", (cid,))
    execute("DELETE FROM connectors WHERE id=%s", (cid,))
    return {"deleted": True}

