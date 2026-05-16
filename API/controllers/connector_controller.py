"""
Connector Controller —  CRUD + test + dataset scan + AUTO quality check on create.

FLOW (ADF / Databricks):
  1. POST /test-connection  -> validates Tier-1 creds AND returns a preview
                               of every dataset + pipeline found.
                               Each dataset carries source_system_type and
                               required_fields so the UI knows what to ask.
  2. POST /test-dataset-credentials -> validates one set of Tier-2 creds
                                       (host/user/password etc.) without saving.
  3. POST /create -> body now optionally carries dataset_credentials[].
                     We test Tier-1, test every Tier-2, then save the connector
                     AND all dataset rows (with encrypted creds, status=Connected)
                     in one shot. Background scan fills in pipelines + any
                     datasets the user didn't supply creds for (as Pending).

FLOW (MySQL / MSSQL / GitHub):
  Same /test-connection still returns a preview, but datasets/pipelines have
  source_system_type=None and required_fields=[] because the connector-level
  credential is already sufficient to read them.
"""
import socket
import pymysql
import requests
import json
from datetime import datetime, timedelta, timezone

from typing import Dict, Any, List, Optional

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
class ConnectorTestIn(BaseModel):
    type: str
    config: Dict[str, Any]


class DatasetCredentialPayload(BaseModel):
    """One dataset's Tier-2 credentials, submitted as part of /create
    or to /test-dataset-credentials."""
    dataset_name: str
    schema_name: Optional[str] = None
    dataset_type: str = "dataset"              # "dataset" | "table" | "view"
    source_system_type: str                    # e.g. "AzureSqlDatabase"
    linked_service_name: Optional[str] = None  # ADF only
    connection_hint: Dict[str, Any] = {}       # echoed from preview
    credentials: Dict[str, Any]                # user-supplied secrets


class ConnectorIn(BaseModel):
    name: str
    type: str
    config: Dict[str, Any]
    dataset_credentials: List[DatasetCredentialPayload] = []


class DatasetCredsTestIn(BaseModel):
    source_system_type: str
    connection_hint: Dict[str, Any] = {}
    credentials: Dict[str, Any]


class DatasetCredentialsIn(BaseModel):
    credentials: Dict[str, Any]


# ============================================================
# TIER-1 TEST-CONNECTION HELPERS  (connector level)
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
# TIER-2 DATASET-LEVEL TESTER (per-dataset credentials)
# ============================================================
_CREDENTIAL_FIELDS = {
    # SQL family
    "AzureSqlDatabase":       ["host", "port", "database", "username", "password"],
    "AzureSqlMI":             ["host", "port", "database", "username", "password"],
    "AzureSqlDW":             ["host", "port", "database", "username", "password"],
    "SqlServer":              ["host", "port", "database", "username", "password"],
    "AzureMySql":             ["host", "port", "database", "username", "password"],
    "MySql":                  ["host", "port", "database", "username", "password"],
    "AzurePostgreSql":        ["host", "port", "database", "username", "password"],
    "PostgreSql":             ["host", "port", "database", "username", "password"],
    "Oracle":                 ["host", "port", "database", "username", "password"],
    "Snowflake":              ["account", "warehouse", "database", "username", "password"],
    # Storage
    "AzureBlobStorage":       ["account_name", "account_key"],
    "AzureDataLakeStoreGen2": ["account_name", "account_key"],
    # Databricks SQL warehouse for UC tables
    "DatabricksSqlWarehouse": ["server_hostname", "http_path", "token"],
}


def _test_dataset_source(source_type: str, hint: dict, creds: dict) -> Dict[str, Any]:
    """Test connectivity to the underlying source backing an ADF dataset or
    a Databricks UC table. Falls back to `hint` (discovered during preview)
    for any field the user didn't supply."""
    hint = hint or {}
    creds = creds or {}

    host     = creds.get("host")     or hint.get("host")
    database = creds.get("database") or hint.get("database")
    port     = creds.get("port")
    user     = creds.get("username")
    pwd      = creds.get("password")

    if source_type in ("AzureSqlDatabase", "AzureSqlMI", "AzureSqlDW", "SqlServer"):
        return _test_mssql({
            "server": host, "port": port or 1433,
            "database": database, "username": user, "password": pwd,
        })

    if source_type in ("AzureMySql", "MySql"):
        return _test_mysql({
            "host": host, "port": port or 3306,
            "database": database, "username": user, "password": pwd,
        })

    if source_type in ("AzurePostgreSql", "PostgreSql"):
        try:
            import psycopg2  # type: ignore
        except ImportError:
            raise RuntimeError("psycopg2 not installed")
        cn = psycopg2.connect(
            host=host, port=int(port or 5432), dbname=database,
            user=user, password=pwd, connect_timeout=8,
        )
        cn.close()
        return {"ok": True, "version": "Postgres reachable"}

    if source_type == "Oracle":
        try:
            import oracledb  # type: ignore
        except ImportError:
            raise RuntimeError("oracledb not installed")
        dsn = oracledb.makedsn(host, int(port or 1521), service_name=database)
        cn = oracledb.connect(user=user, password=pwd, dsn=dsn)
        cn.close()
        return {"ok": True, "version": "Oracle reachable"}

    if source_type == "Snowflake":
        try:
            import snowflake.connector  # type: ignore
        except ImportError:
            raise RuntimeError("snowflake-connector-python not installed")
        cn = snowflake.connector.connect(
            account=creds.get("account") or hint.get("account"),
            user=user, password=pwd,
            warehouse=creds.get("warehouse"),
            database=database,
        )
        cn.close()
        return {"ok": True, "version": "Snowflake reachable"}

    if source_type in ("AzureBlobStorage", "AzureDataLakeStoreGen2"):
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore
        except ImportError:
            raise RuntimeError("azure-storage-blob not installed")
        account = creds.get("account_name") or hint.get("account_name")
        key     = creds.get("account_key")
        if not account or not key:
            raise RuntimeError("account_name and account_key required")
        bsc = BlobServiceClient(
            account_url=f"https://{account}.blob.core.windows.net",
            credential=key,
        )
        list(bsc.list_containers(results_per_page=1))
        return {"ok": True, "version": f"Blob account {account} reachable"}

    if source_type == "DatabricksSqlWarehouse":
        try:
            from databricks import sql as dbsql  # type: ignore
        except ImportError:
            raise RuntimeError("databricks-sql-connector not installed")
        cn = dbsql.connect(
            server_hostname=creds.get("server_hostname") or hint.get("server_hostname"),
            http_path=creds["http_path"],
            access_token=creds["token"],
        )
        cn.close()
        return {"ok": True, "version": "Databricks SQL reachable"}

    raise RuntimeError(f"No Tier-2 tester available for source type: {source_type}")


# ============================================================
# ADF METADATA HELPERS (shared by preview and full scan)
# ============================================================
_ADF_FILE_TYPES = {
    "DelimitedText", "Parquet", "Json", "Avro", "Orc",
    "Binary", "Excel", "Xml",
}
_ADF_TABLE_TYPES = {
    "AzureSqlTable", "AzureSqlDWTable", "AzurePostgreSqlTable",
    "AzureMySqlTable", "AzureMariaDBTable", "AzureSqlMITable",
    "SqlServerTable", "OracleTable", "MySqlTable", "PostgreSqlTable",
    "SnowflakeTable", "AmazonRedshiftTable", "GoogleBigQueryObject",
    "DynamicsEntity", "SalesforceObject", "MongoDbCollection",
    "CosmosDbSqlApiCollection", "CosmosDbMongoDbApiCollection",
    "AzureTableStorage", "RestResource",
}

_ADF_LINKED_SERVICE_TO_SOURCE = {
    "AzureSqlDatabase":           "AzureSqlDatabase",
    "AzureSqlMI":                 "AzureSqlMI",
    "AzureSqlDW":                 "AzureSqlDW",
    "SqlServer":                  "SqlServer",
    "AzureMySql":                 "AzureMySql",
    "MySql":                      "MySql",
    "AzurePostgreSql":            "AzurePostgreSql",
    "PostgreSql":                 "PostgreSql",
    "Oracle":                     "Oracle",
    "Snowflake":                  "Snowflake",
    "AzureBlobStorage":           "AzureBlobStorage",
    "AzureBlobFS":                "AzureDataLakeStoreGen2",
    "AzureDataLakeStoreGen2":     "AzureDataLakeStoreGen2",
}


def _adf_base_url(cfg: Dict[str, Any]) -> str:
    return (
        f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
        f"/resourceGroups/{cfg['resource_group']}"
        f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
    )


def _fetch_adf_linked_services(base: str, headers: dict) -> Dict[str, dict]:
    """Returns {linked_service_name: {ls_type, source_system_type, connection_hint}}.
    Secrets in linked services are SecureStrings/Key Vault refs, so we only
    extract non-secret discovery info."""
    out: Dict[str, dict] = {}
    try:
        r = requests.get(
            f"{base}/linkedservices?api-version=2018-06-01",
            headers=headers, timeout=20,
        )
        if r.status_code != 200:
            logger.warning("ADF linkedservices %d: %s",
                           r.status_code, r.text[:200])
            return out

        for ls in r.json().get("value", []) or []:
            name  = ls.get("name")
            props = ls.get("properties") or {}
            ls_type = props.get("type")
            tprops  = props.get("typeProperties") or {}
            if not name or not ls_type:
                continue

            hint: Dict[str, Any] = {}
            cs = tprops.get("connectionString")
            if isinstance(cs, str):
                for part in cs.split(";"):
                    if "=" not in part:
                        continue
                    k, v = part.split("=", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if k in ("server", "data source"):
                        hint["host"] = v
                    elif k in ("initial catalog", "database"):
                        hint["database"] = v
                    elif k == "user id":
                        hint["username"] = v

            for key_in, key_out in (
                ("server",       "host"),
                ("database",     "database"),
                ("databaseName", "database"),
                ("userName",     "username"),
                ("username",     "username"),
                ("password",     "password"),
                ("pwd",          "password"),
                ("url",          "url"),
                ("accountName",  "account_name"),
                ("port",         "port"),
            ):
                if key_in in tprops and isinstance(tprops[key_in], (str, int)):
                    hint.setdefault(key_out, tprops[key_in])

            if ls_type in ("AzureBlobStorage", "AzureBlobFS"):
                ep = tprops.get("serviceEndpoint") or tprops.get("url")
                if isinstance(ep, str):
                    hint.setdefault("endpoint", ep)
                    try:
                        host_part = ep.split("//", 1)[-1].split("/", 1)[0]
                        acct = host_part.split(".", 1)[0]
                        if acct:
                            hint.setdefault("account_name", acct)
                    except Exception:
                        pass
            logger.info(
            "ADF LINKED SERVICE HINT => %s",
            json.dumps(hint, indent=2)
            )
            out[name] = {
                "ls_type":            ls_type,
                "source_system_type": _ADF_LINKED_SERVICE_TO_SOURCE.get(ls_type),
                "connection_hint":    hint,
            }
    except Exception as e:
        logger.warning("ADF linkedservices fetch failed: %s", e)
    return out


def _get_db_meta(dialect, host, port, database, username, password, schema, table):
    """Fetch row count, columns, PKs, and FKs for a table."""
    try:
        if dialect == "postgres":
            import psycopg2
            cn = psycopg2.connect(
                host=host, port=int(port or 5432), dbname=database,
                user=username, password=password, connect_timeout=8,
            )
            cur = cn.cursor()
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            row_count = cur.fetchone()[0]
            cur.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s "
                "ORDER BY ordinal_position", (schema, table),
            )
            cols = [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "is_pk": False}
                    for r in cur.fetchall()]
            cur.execute(
                "SELECT kc.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kc "
                "  ON kc.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type='PRIMARY KEY' "
                "  AND tc.table_schema=%s AND tc.table_name=%s", (schema, table),
            )
            pks = [r[0] for r in cur.fetchall()]
            for c in cols:
                if c["name"] in pks: c["is_pk"] = True
            
            # FKs
            cur.execute(
                "SELECT kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=%s AND tc.table_name=%s",
                (schema, table),
            )
            fks = [{"column": r[0], "ref_table": r[1], "ref_column": r[2]} for r in cur.fetchall()]
            
            cur.close()
            cn.close()
            return {"row_count": row_count, "columns": cols, "pks": pks, "fks": fks}

        if dialect == "mysql":
            cn = pymysql.connect(
                host=host, port=int(port or 3306), user=username, password=password,
                database=database, connect_timeout=8,
            )
            with cn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                row_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY "
                    "FROM information_schema.columns "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (database, table),
                )
                cols = [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "is_pk": r[3] == "PRI"}
                        for r in cur.fetchall()]
                # FKs
                cur.execute(
                    "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                    "FROM information_schema.KEY_COLUMN_USAGE "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND REFERENCED_TABLE_NAME IS NOT NULL",
                    (database, table),
                )
                fks = [{"column": r[0], "ref_table": r[1], "ref_column": r[2]} for r in cur.fetchall()]
            cn.close()
            return {"row_count": row_count, "columns": cols, "pks": [c["name"] for c in cols if c["is_pk"]], "fks": fks}

        if dialect == "mssql":
            import pyodbc
            drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
            cs = (f"DRIVER={{{drivers[0]}}};SERVER={host},{int(port or 1433)};"
                  f"DATABASE={database};UID={username};PWD={password};"
                  "Encrypt=no;TrustServerCertificate=yes;")
            cn = pyodbc.connect(cs, timeout=8)
            cur = cn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM [{schema}].[{table}]")
            row_count = cur.fetchone()[0]
            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=? AND TABLE_NAME=?", (schema, table),
            )
            cols = [{"name": r[0], "type": r[1], "nullable": r[2] == "YES", "is_pk": False}
                    for r in cur.fetchall()]
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
                "WHERE OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + QUOTENAME(CONSTRAINT_NAME)), 'IsPrimaryKey')=1 "
                "AND TABLE_SCHEMA=? AND TABLE_NAME=?", (schema, table),
            )
            pks = [r[0] for r in cur.fetchall()]
            for c in cols:
                if c["name"] in pks: c["is_pk"] = True
            
            # FKs
            cur.execute(
                "SELECT c1.name, OBJECT_NAME(fkc.referenced_object_id), c2.name "
                "FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id "
                "JOIN sys.columns c1 ON fkc.parent_object_id = c1.object_id AND fkc.parent_column_id = c1.column_id "
                "JOIN sys.columns c2 ON fkc.referenced_object_id = c2.object_id AND fkc.referenced_column_id = c2.column_id "
                "WHERE OBJECT_NAME(fk.parent_object_id)=?", (table,),
            )
            fks = [{"column": r[0], "ref_table": r[1], "ref_column": r[2]} for r in cur.fetchall()]
            
            cn.close()
            return {"row_count": row_count, "columns": cols, "pks": pks, "fks": fks}

    except Exception as e:
        logger.warning("%s meta fetch failed: %s", dialect, e)
    return None


def _extract_adf_dataset_meta(
    dataset_name: str,
    props: dict,
    linked_services: Dict[str, dict],
) -> dict:
    if not isinstance(props, dict):
        props = {}

    ds_type = props.get("type") or "Unknown"
    type_props = props.get("typeProperties")
    if not isinstance(type_props, dict):
        type_props = {}

    ls_ref = None
    ls_block = props.get("linkedServiceName")
    if isinstance(ls_block, dict):
        ls_ref = ls_block.get("referenceName")
    ls_info = linked_services.get(ls_ref) if ls_ref else None
    source_system_type = (ls_info or {}).get("source_system_type")
    connection_hint    = dict((ls_info or {}).get("connection_hint") or {})

    raw_schema = props.get("schema")
    columns = []
    if isinstance(raw_schema, list):
        for c in raw_schema:
            if isinstance(c, dict):
                columns.append({"name": c.get("name"), "type": c.get("type")})

    if ds_type in _ADF_FILE_TYPES:
        location = type_props.get("location")
        if not isinstance(location, dict):
            location = {}

        location_info = {
            "kind":         location.get("type"),
            "container":    location.get("container") or location.get("fileSystem"),
            "folder_path":  location.get("folderPath"),
            "file_name":    location.get("fileName"),
        }
        if location_info["container"]:
            connection_hint.setdefault("container", location_info["container"])
        if location_info["folder_path"]:
            connection_hint.setdefault("folder_path", location_info["folder_path"])
        if location_info["file_name"]:
            connection_hint.setdefault("file_name", location_info["file_name"])

        delimiter = first_row_header = encoding = compression = None
        if ds_type == "DelimitedText":
            delimiter        = type_props.get("columnDelimiter")
            first_row_header = type_props.get("firstRowAsHeader")
            encoding         = type_props.get("encodingName")
        elif ds_type == "Parquet":
            compression      = type_props.get("compressionCodec")
        elif ds_type == "Json":
            encoding         = type_props.get("encodingName")

        return {
            "dataset_name":         dataset_name,
            "dataset_type":         ds_type,
            "source_kind":          "file",
            "location":             location_info,
            "delimiter":            delimiter,
            "first_row_as_header":  first_row_header,
            "encoding":             encoding,
            "compression":          compression,
            "schema_name":          None,
            "table_name":           None,
            "columns":              columns,
            "linked_service_name":  ls_ref,
            "source_system_type":   source_system_type,
            "connection_hint":      connection_hint,
        }

    if ds_type in _ADF_TABLE_TYPES:
        schema_name = type_props.get("schema") if isinstance(type_props.get("schema"), str) else None
        table_name = (
            type_props.get("table")
            or type_props.get("tableName")
            or type_props.get("collection")
            or type_props.get("collectionName")
        )
        if not isinstance(table_name, str):
            table_name = None
        if schema_name:
            connection_hint.setdefault("schema", schema_name)
        if table_name:
            connection_hint.setdefault("table", table_name)

        return {
            "dataset_name":         dataset_name,
            "dataset_type":         ds_type,
            "source_kind":          "table",
            "location":             None,
            "delimiter":            None,
            "first_row_as_header":  None,
            "encoding":             None,
            "compression":          None,
            "schema_name":          schema_name,
            "table_name":           table_name,
            "columns":              columns,
            "linked_service_name":  ls_ref,
            "source_system_type":   source_system_type,
            "connection_hint":      connection_hint,
        }

    return {
        "dataset_name":         dataset_name,
        "dataset_type":         ds_type,
        "source_kind":          "unknown",
        "location":             None,
        "delimiter":            None,
        "first_row_as_header":  None,
        "encoding":             None,
        "compression":          None,
        "schema_name":          None,
        "table_name":           None,
        "columns":              columns,
        "linked_service_name":  ls_ref,
        "source_system_type":   source_system_type,
        "connection_hint":      connection_hint,
    }


# ============================================================
# FULL SCANNERS (background, post-save) — heavy: pipeline runs, activity logs
# These need to be defined BEFORE the preview functions reference _scan_mysql etc.
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


def _scan_databricks_uc_tables(base: str, headers: dict) -> List[dict]:
    out: List[dict] = []
    server_hostname = base.replace("https://", "").replace("http://", "").rstrip("/")
    try:
        rc = requests.get(
            f"{base}/api/2.1/unity-catalog/catalogs",
            headers=headers, timeout=20,
        )
        if rc.status_code != 200:
            logger.debug("UC catalogs %d: %s", rc.status_code, rc.text[:200])
            return out

        for cat in rc.json().get("catalogs", []) or []:
            cname = cat.get("name")
            if not cname:
                continue
            rs = requests.get(
                f"{base}/api/2.1/unity-catalog/schemas?catalog_name={cname}",
                headers=headers, timeout=20,
            )
            if rs.status_code != 200:
                continue
            for sch in rs.json().get("schemas", []) or []:
                sname = sch.get("name")
                if not sname or sname == "information_schema":
                    continue
                rt = requests.get(
                    f"{base}/api/2.1/unity-catalog/tables"
                    f"?catalog_name={cname}&schema_name={sname}",
                    headers=headers, timeout=20,
                )
                if rt.status_code != 200:
                    continue
                for t in rt.json().get("tables", []) or []:
                    tname = t.get("name")
                    if not tname:
                        continue
                    hint = {
                        "server_hostname":  server_hostname,
                        "catalog":          cname,
                        "schema":           sname,
                        "table":            tname,
                        "table_type":       t.get("table_type"),
                        "storage_location": t.get("storage_location"),
                    }
                    out.append({
                        "name":                 tname,
                        "type":                 "table",
                        "schema":               f"{cname}.{sname}",
                        "source_system_type":   "DatabricksSqlWarehouse",
                        "connection_hint_json": json.dumps(hint),
                    })
    except Exception as e:
        logger.warning("Databricks UC scan failed: %s", e)
    return out


def _scan_databricks(cfg: Dict[str, Any]) -> List[dict]:
    base = cfg["workspace_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['token']}"}
    out: List[dict] = []

    try:
        r = requests.get(f"{base}/api/2.1/jobs/list?limit=100",
                         headers=headers, timeout=20)
        if r.status_code != 200:
            r = requests.get(f"{base}/api/2.0/jobs/list",
                             headers=headers, timeout=20)
        if r.status_code == 200:
            for j in r.json().get("jobs", []) or []:
                name = (j.get("settings") or {}).get("name") or f"job_{j.get('job_id')}"
                out.append({
                    "name": name, "type": "pipeline", "schema": "databricks",
                    "source_system_type": None,
                })
    except Exception as e:
        logger.warning("Databricks jobs scan failed: %s", e)

    try:
        r = requests.get(f"{base}/api/2.0/pipelines?max_results=100",
                         headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            for p in (data.get("statuses") or data.get("pipelines") or []):
                pname = p.get("name") or p.get("pipeline_id")
                if not pname:
                    continue
                out.append({
                    "name": pname, "type": "pipeline", "schema": "databricks",
                    "source_system_type": None,
                })
    except Exception as e:
        logger.debug("Databricks DLT scan failed: %s", e)

    uc_tables = _scan_databricks_uc_tables(base, headers)
    out.extend(uc_tables)

    logger.info(
        "Databricks scan: %d pipelines/jobs + %d UC tables discovered",
        len(out) - len(uc_tables), len(uc_tables),
    )
    return out


# def _scan_adf(cfg: Dict[str, Any]) -> List[dict]:
def _scan_adf(connector_id: int, cfg: Dict[str, Any]) -> List[dict]:
    """Full ADF scan: datasets + pipelines with full run/activity history."""
    try:
        tok = _azure_token(cfg)
    except Exception as e:
        logger.warning("ADF auth failed: %s", e)
        return []

    base = _adf_base_url(cfg)
    headers = {"Authorization": f"Bearer {tok}"}
    out: List[dict] = []

    linked_services = _fetch_adf_linked_services(base, headers)
    logger.info("ADF: %d linked services discovered", len(linked_services))

    # ----- datasets -----
    try:
        r = requests.get(
            f"{base}/datasets?api-version=2018-06-01",
            headers=headers, timeout=20,
        )
        if r.status_code == 200:
            payload = r.json() if r.content else {}
            items = payload.get("value", []) if isinstance(payload, dict) else []
            logger.info("ADF: %d datasets returned by API", len(items))
            for x in items:
                try:
                    if not isinstance(x, dict):
                        continue
                    dataset_name = x.get("name")
                    if not dataset_name:
                        continue
                    props = x.get("properties") or {}
                    meta = _extract_adf_dataset_meta(dataset_name, props, linked_services)
                    db_meta = None
                    try:
                        source_type = meta["source_system_type"]
                        dialect = None
                        if source_type in ("AzurePostgreSql", "PostgreSql"): dialect = "postgres"
                        elif source_type in ("AzureMySql", "MySql"): dialect = "mysql"
                        elif source_type in ("AzureSqlDatabase", "AzureSqlMI", "SqlServer"): dialect = "mssql"

                        if dialect:
                            hint = meta["connection_hint"] or {}
                            dataset_row = fetch_one(
                                "SELECT credentials_json FROM datasets WHERE connector_id=%s AND dataset_name=%s",
                                (connector_id, dataset_name),
                            )
                            if dataset_row and dataset_row.get("credentials_json"):
                                dataset_creds = decrypt_config(dataset_row["credentials_json"])
                                db_meta = _get_db_meta(
                                    dialect=dialect,
                                    host=hint.get("host"),
                                    port=hint.get("port"),
                                    database=hint.get("database"),
                                    username=dataset_creds.get("username"),
                                    password=dataset_creds.get("password"),
                                    schema=meta["schema_name"] or hint.get("schema") or "dbo",
                                    table=meta["table_name"] or hint.get("table"),
                                )
                    except Exception as e:
                        logger.warning("Metadata fetch failed for %s: %s", dataset_name, e)

                    row_count = db_meta.get("row_count") if db_meta else None
                    cols = db_meta.get("columns") if db_meta else meta.get("columns")
                    col_count = len(cols) if cols else 0
                    
                    profiling_json = {
                        "source": {
                            "type":               "ADF",
                            "asset_kind":         "dataset",
                            "name":               dataset_name,
                            "dataset_type":       meta["dataset_type"],
                            "source_kind":        meta["source_kind"],
                            "linked_service_name": meta["linked_service_name"],
                            "source_system_type": meta["source_system_type"],
                        },
                        "summary": {
                            "row_count":    row_count,
                            "column_count": col_count,
                        }
                    }
                    if cols:
                        profiling_json["tables"] = [{
                            "table_name": meta["table_name"],
                            "schema":     meta["schema_name"],
                            "column_count": col_count,
                            "columns":      cols,
                            "row_count":    row_count,
                            "primary_keys": db_meta.get("pks", []) if db_meta else [],
                            "foreign_keys": db_meta.get("fks", []) if db_meta else [],
                        }]

                    out.append({
                        "name":                dataset_name,
                        "type":                "dataset",
                        "schema":              "adf",
                        "linked_service_name": meta["linked_service_name"],
                        "source_system_type":  meta["source_system_type"],
                        "row_count":           row_count,
                        "column_count":        col_count,
                        "connection_hint_json": json.dumps(meta["connection_hint"]),
                        "profiling_json":      json.dumps(profiling_json),
                    })
                except Exception as e:
                    logger.warning(
                        "ADF dataset parse failed for %s: %s",
                        x.get("name") if isinstance(x, dict) else "<unknown>", e,
                    )
        else:
            logger.warning("ADF datasets API %d: %s", r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("ADF datasets fetch failed: %s", e)

    # ----- pipelines with full run history -----
    try:
        r = requests.get(
            f"{base}/pipelines?api-version=2018-06-01",
            headers=headers, timeout=20,
        )
        if r.status_code == 200:
            pipeline_items = r.json().get("value", []) or []
            for x in pipeline_items:
                if not isinstance(x, dict):
                    continue
                pipeline_name = x.get("name")
                if not pipeline_name:
                    continue

                try:
                    end_time = datetime.now(timezone.utc)
                    start_time = end_time - timedelta(days=7)

                    payload = {
                        "lastUpdatedAfter":  start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "lastUpdatedBefore": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "filters": [{
                            "operand": "PipelineName", "operator": "Equals",
                            "values": [pipeline_name],
                        }],
                    }
                    run_resp = requests.post(
                        f"{base}/queryPipelineRuns?api-version=2018-06-01",
                        headers={**headers, "Content-Type": "application/json"},
                        json=payload, timeout=30,
                    )

                    total_runs = 0
                    failed_runs = 0
                    runtime_list: List[int] = []
                    latest_error = None
                    monitoring_runs: List[dict] = []

                    if run_resp.status_code == 200:
                        runs = run_resp.json().get("value", []) or []
                        total_runs = len(runs)
                        for rr in runs:
                            status    = rr.get("status")
                            run_id    = rr.get("runId")
                            run_start = rr.get("runStart")
                            run_end   = rr.get("runEnd")
                            duration  = 0
                            if status != "Succeeded":
                                failed_runs += 1
                            if run_start and run_end:
                                try:
                                    st = datetime.fromisoformat(run_start.replace("Z", "+00:00"))
                                    et = datetime.fromisoformat(run_end.replace("Z", "+00:00"))
                                    duration = int((et - st).total_seconds())
                                    runtime_list.append(duration)
                                except Exception:
                                    pass

                            activities: List[dict] = []
                            try:
                                act_resp = requests.post(
                                    f"{base}/pipelineruns/{run_id}/queryActivityruns"
                                    f"?api-version=2018-06-01",
                                    headers={**headers, "Content-Type": "application/json"},
                                    json={
                                        "lastUpdatedAfter":  start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        "lastUpdatedBefore": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    },
                                    timeout=30,
                                )
                                if act_resp.status_code == 200:
                                    for act in act_resp.json().get("value", []):
                                        error_message = (act.get("error", {}) or {}).get("message")
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
                                logger.warning("ADF activity fetch failed for run %s: %s", run_id, e)

                            monitoring_runs.append({
                                "run_id":           run_id,
                                "status":           status,
                                "duration_seconds": duration,
                                "activities":       activities,
                            })

                    success_rate = round(((total_runs - failed_runs) / total_runs) * 100, 2) if total_runs else 0
                    avg_runtime  = int(sum(runtime_list) / len(runtime_list)) if runtime_list else 0

                    monitoring_json = {
                        "profile": {
                            "source": {"type": "ADF", "asset_kind": "pipeline", "name": pipeline_name},
                            "data_quality": {
                                "quality_score": {"value": success_rate, "generated_by": "python"},
                                "missing_data":  {"percentage": 0, "band": "Green", "generated_by": "python"},
                                "junk_data":     {"percentage": 0, "band": "Green", "generated_by": "python"},
                                "outlier": {
                                    "percentage": failed_runs,
                                    "band": "Red" if failed_runs > 5 else ("Amber" if failed_runs > 0 else "Green"),
                                    "generated_by": "python",
                                },
                                "trend_analysis": {
                                    "text": f"Pipeline success rate is {success_rate}% over the last 7 days.",
                                    "generated_by": "llm",
                                },
                            },
                            "summary": {
                                "technical_context": {
                                    "generated_by": "python",
                                    "tables": [{
                                        "pipeline_name":       pipeline_name,
                                        "total_runs":          total_runs,
                                        "failed_runs":         failed_runs,
                                        "avg_runtime_seconds": avg_runtime,
                                        "latest_error":        latest_error,
                                    }],
                                },
                            },
                        },
                        "runs": monitoring_runs,
                    }

                    out.append({
                        "name":                 pipeline_name,
                        "type":                 "pipeline",
                        "schema":               "adf",
                        "linked_service_name":  None,
                        "source_system_type":   None,
                        "row_count":            total_runs,
                        "column_count":         0,
                        "connection_hint_json": None,
                        "profiling_json":       None,
                        "monitoring_json":      json.dumps(monitoring_json),
                    })
                except Exception as e:
                    logger.warning("ADF pipeline analysis failed for %s: %s", pipeline_name, e)
                    out.append({
                        "name":                 pipeline_name,
                        "type":                 "pipeline",
                        "schema":               "adf",
                        "linked_service_name":  None,
                        "source_system_type":   None,
                        "connection_hint_json": None,
                        "profiling_json":       None,
                        "monitoring_json":      None,
                    })
        else:
            logger.warning("ADF pipelines API %d: %s", r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("ADF pipelines fetch failed: %s", e)

    logger.info("ADF scan complete: %d total items", len(out))
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
# PREVIEW SCANNERS — fast, returned synchronously from /test-connection
# Light-weight: NO pipeline run history, NO activity logs.
# Returns {"datasets": [...], "pipelines": [...]} for the UI.
# ============================================================
def _preview_item_for_ui(
    name: str,
    schema: Optional[str],
    dataset_type: str,
    source_system_type: Optional[str],
    connection_hint: Optional[dict],
    linked_service_name: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    item = {
        "name":                name,
        "schema":              schema,
        "dataset_type":        dataset_type,
        "linked_service_name": linked_service_name,
        "source_system_type":  source_system_type,
        "connection_hint":     connection_hint or {},
        "required_fields":     _CREDENTIAL_FIELDS.get(source_system_type or "", []),
        "needs_credentials":   source_system_type is not None,
    }
    if extra:
        item.update(extra)
    return item


def _preview_mysql(cfg: Dict[str, Any]) -> Dict[str, List[dict]]:
    rows = _scan_mysql(cfg)
    return {
        "datasets": [
            _preview_item_for_ui(
                name=r["name"], schema=r["schema"], dataset_type=r["type"],
                source_system_type=None, connection_hint={},
            ) for r in rows
        ],
        "pipelines": [],
    }


def _preview_mssql(cfg: Dict[str, Any]) -> Dict[str, List[dict]]:
    rows = _scan_mssql(cfg)
    return {
        "datasets": [
            _preview_item_for_ui(
                name=r["name"], schema=r["schema"], dataset_type=r["type"],
                source_system_type=None, connection_hint={},
            ) for r in rows
        ],
        "pipelines": [],
    }


def _preview_adf(cfg: Dict[str, Any]) -> Dict[str, List[dict]]:
    tok = _azure_token(cfg)
    base = _adf_base_url(cfg)
    headers = {"Authorization": f"Bearer {tok}"}

    linked_services = _fetch_adf_linked_services(base, headers)
    datasets: List[dict] = []
    pipelines: List[dict] = []

    # ----- datasets -----
    try:
        r = requests.get(
            f"{base}/datasets?api-version=2018-06-01",
            headers=headers, timeout=20,
        )
        if r.status_code == 200:
            for x in r.json().get("value", []) or []:
                if not isinstance(x, dict):
                    continue
                name = x.get("name")
                if not name:
                    continue
                meta = _extract_adf_dataset_meta(
                    name, x.get("properties") or {}, linked_services,
                )
                datasets.append(_preview_item_for_ui(
                    name=name,
                    schema="adf",
                    dataset_type="dataset",
                    source_system_type=meta["source_system_type"],
                    connection_hint=meta["connection_hint"],
                    linked_service_name=meta["linked_service_name"],
                    extra={
                        "adf_dataset_type": meta["dataset_type"],
                        "source_kind":      meta["source_kind"],
                    },
                ))
        else:
            logger.warning("ADF preview datasets %d: %s",
                           r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("ADF preview datasets failed: %s", e)

    # ----- pipelines (names only — no run history) -----
    try:
        r = requests.get(
            f"{base}/pipelines?api-version=2018-06-01",
            headers=headers, timeout=20,
        )
        if r.status_code == 200:
            for x in r.json().get("value", []) or []:
                if not isinstance(x, dict):
                    continue
                name = x.get("name")
                if name:
                    pipelines.append(_preview_item_for_ui(
                        name=name, schema="adf", dataset_type="pipeline",
                        source_system_type=None, connection_hint={},
                    ))
        else:
            logger.warning("ADF preview pipelines %d: %s",
                           r.status_code, r.text[:300])
    except Exception as e:
        logger.warning("ADF preview pipelines failed: %s", e)

    return {"datasets": datasets, "pipelines": pipelines}


def _preview_databricks(cfg: Dict[str, Any]) -> Dict[str, List[dict]]:
    base = cfg["workspace_url"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['token']}"}
    datasets: List[dict] = []
    pipelines: List[dict] = []

    # ----- jobs -----
    try:
        r = requests.get(f"{base}/api/2.1/jobs/list?limit=100",
                         headers=headers, timeout=20)
        if r.status_code != 200:
            r = requests.get(f"{base}/api/2.0/jobs/list",
                             headers=headers, timeout=20)
        if r.status_code == 200:
            for j in r.json().get("jobs", []) or []:
                name = (j.get("settings") or {}).get("name") or f"job_{j.get('job_id')}"
                pipelines.append(_preview_item_for_ui(
                    name=name, schema="databricks", dataset_type="pipeline",
                    source_system_type=None, connection_hint={},
                ))
    except Exception as e:
        logger.warning("Databricks preview jobs failed: %s", e)

    # ----- DLT pipelines -----
    try:
        r = requests.get(f"{base}/api/2.0/pipelines?max_results=100",
                         headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            for p in (data.get("statuses") or data.get("pipelines") or []):
                pname = p.get("name") or p.get("pipeline_id")
                if not pname:
                    continue
                pipelines.append(_preview_item_for_ui(
                    name=pname, schema="databricks", dataset_type="pipeline",
                    source_system_type=None, connection_hint={},
                ))
    except Exception as e:
        logger.debug("Databricks preview DLT failed: %s", e)

    # ----- Unity Catalog tables (Tier-2 datasets) -----
    uc = _scan_databricks_uc_tables(base, headers)
    for t in uc:
        try:
            hint = json.loads(t.get("connection_hint_json") or "{}")
        except Exception:
            hint = {}
        datasets.append(_preview_item_for_ui(
            name=t["name"],
            schema=t["schema"],
            dataset_type=t["type"],
            source_system_type=t.get("source_system_type"),
            connection_hint=hint,
        ))

    return {"datasets": datasets, "pipelines": pipelines}


def _preview_github(cfg: Dict[str, Any]) -> Dict[str, List[dict]]:
    rows = _scan_github(cfg)
    return {
        "datasets": [],
        "pipelines": [
            _preview_item_for_ui(
                name=r["name"], schema=r["schema"], dataset_type=r["type"],
                source_system_type=None, connection_hint={},
            ) for r in rows
        ],
    }


PREVIEW_MAP = {
    "mysql":      _preview_mysql,
    "mssql":      _preview_mssql,
    "azure_adf":  _preview_adf,
    "databricks": _preview_databricks,
    "github":     _preview_github,
}


def preview_scan(conn_type: str, cfg: Dict[str, Any]) -> Dict[str, List[dict]]:
    fn = PREVIEW_MAP.get(conn_type)
    if not fn:
        return {"datasets": [], "pipelines": []}
    try:
        return fn(cfg) or {"datasets": [], "pipelines": []}
    except Exception as e:
        logger.warning("Preview scan failed for %s: %s", conn_type, e)
        return {"datasets": [], "pipelines": []}


# ============================================================
# SCAN ENGINE (background, post-save)
# ============================================================
_TIER2_REQUIRED_TYPES = {"dataset", "table", "view"}


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

        # datasets = scanner(cfg) or []
        # datasets = scanner(connector_id, cfg) or []
        if ctype == "azure_adf":
           datasets = scanner(connector_id, cfg) or []
        else:
            datasets = scanner(cfg) or []
        logger.info("Connector %s (%s): %d items discovered",
                    connector_id, ctype, len(datasets))

        new_datasets_added = 0
        for d in datasets:
            existing = fetch_one(
                "SELECT id FROM datasets "
                "WHERE connector_id=%s "
                "  AND IFNULL(schema_name,'')=%s "
                "  AND dataset_name=%s "
                "  AND dataset_type=%s",
                (connector_id, d.get("schema") or "", d["name"], d["type"]),
            )
            if existing:
                execute(
                    "UPDATE datasets SET "
                    " profiling_json = %s, "
                    " monitoring_json = %s, "
                    " linked_service_name = COALESCE(%s, linked_service_name), "
                    " source_system_type = COALESCE(%s, source_system_type), "
                    " connection_hint_json = COALESCE(%s, connection_hint_json), "
                    " updated_at = %s "
                    "WHERE id=%s",
                    (
                        d.get("profiling_json"),
                        d.get("monitoring_json"),
                        d.get("linked_service_name"),
                        d.get("source_system_type"),
                        d.get("connection_hint_json"),
                        datetime.now(timezone.utc),
                        existing["id"],
                    ),
                )

                logger.info(
                    "Dataset refreshed => %s",
                    d["name"],
                )

                continue
                # Refresh profiling/monitoring on re-scan, leave creds alone
                # execute(
                #     "UPDATE datasets SET "
                #     " profiling_json = COALESCE(%s, profiling_json), "
                #     " monitoring_json = COALESCE(%s, monitoring_json), "
                #     " linked_service_name = COALESCE(linked_service_name, %s), "
                #     " source_system_type  = COALESCE(source_system_type,  %s), "
                #     " connection_hint_json = COALESCE(connection_hint_json, %s) "
                #     "WHERE id=%s",
                #     (
                #         d.get("profiling_json"),
                #         d.get("monitoring_json"),
                #         d.get("linked_service_name"),
                #         d.get("source_system_type"),
                #         d.get("connection_hint_json"),
                #         existing["id"],
                #     ),
                # )
                # continue

            existing = fetch_one(
                "SELECT id FROM datasets WHERE connector_id=%s AND dataset_name=%s AND dataset_type=%s",
                (connector_id, d["name"], d["type"]),
            )

            if existing:
                execute(
                    "UPDATE datasets SET "
                    " schema_name=%s, linked_service_name=%s, source_system_type=%s, "
                    " connection_hint_json=%s, profiling_json=%s, monitoring_json=%s, "
                    " row_count=%s, column_count=%s "
                    " WHERE id=%s",
                    (
                        d.get("schema"), d.get("linked_service_name"), d.get("source_system_type"),
                        d.get("connection_hint_json"), d.get("profiling_json"), d.get("monitoring_json"),
                        d.get("row_count"), d.get("column_count"),
                        existing["id"],
                    ),
                )
                continue

            asset_type = d["type"]
            needs_tier2 = (
                asset_type in _TIER2_REQUIRED_TYPES
                and ctype in ("azure_adf", "databricks")
                and d.get("source_system_type") is not None
            )
            credential_status = "Pending" if needs_tier2 else "Connected"

            execute(
                "INSERT INTO datasets ("
                " connector_id, dataset_name, dataset_type, schema_name,"
                " linked_service_name, source_system_type, connection_hint_json,"
                " profiling_json, monitoring_json,"
                " confidence_score, pii_percentage, outlier_count,"
                " credential_status, row_count, column_count"
                ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,0,%s,%s,%s)",
                (
                    connector_id, d["name"], d["type"], d.get("schema"),
                    d.get("linked_service_name"), d.get("source_system_type"),
                    d.get("connection_hint_json"),
                    d.get("profiling_json"), d.get("monitoring_json"),
                    credential_status,
                    d.get("row_count"), d.get("column_count"),
                ),
            )
            new_datasets_added += 1

        execute(
            "UPDATE connectors SET last_scanned_at=%s, status='Connected' WHERE id=%s",
            (datetime.now(timezone.utc), connector_id),
        )
        logger.info("Connector %s: %d new datasets added",
                    connector_id, new_datasets_added)

        try:
            from controllers.monitoring_controller import run_quality_for_connector_type
            logger.info(
                "Auto-triggering quality check for connector %s (%s) — "
                "only Connected datasets will be processed", connector_id, ctype,
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


def _run_quality_for_single_dataset(dataset_id: int):
    try:
        from controllers.monitoring_controller import run_quality_for_dataset
        run_quality_for_dataset(dataset_id)
    except ImportError:
        try:
            from controllers.monitoring_controller import run_quality_for_connector_type
            row = fetch_one(
                "SELECT c.type FROM datasets d "
                "JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
                (dataset_id,),
            )
            if row:
                run_quality_for_connector_type(row["type"], triggered_by_rulebook_id=0)
        except Exception as e:
            logger.warning("Per-dataset quality fallback failed: %s", e)
    except Exception as e:
        logger.warning("Per-dataset quality run failed for %s: %s", dataset_id, e)


# ============================================================
# SERIALIZE / MASK
# ============================================================
def _mask(cfg: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(cfg)
    for f in ("password", "client_secret", "token", "secret", "account_key"):
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


def _serialize_dataset(row: dict) -> dict:
    hint = {}
    raw_hint = row.get("connection_hint_json")
    if raw_hint:
        try:
            hint = json.loads(raw_hint)
        except Exception:
            hint = {}
    source_type = row.get("source_system_type")
    return {
        "id":                   row["id"],
        "connector_id":         row.get("connector_id"),
        "dataset_name":         row["dataset_name"],
        "dataset_type":         row["dataset_type"],
        "schema_name":          row.get("schema_name"),
        "linked_service_name":  row.get("linked_service_name"),
        "source_system_type":   source_type,
        "connection_hint":      hint,
        "credential_status":    row.get("credential_status") or "Pending",
        "last_dataset_test_at": row.get("last_dataset_test_at"),
        "required_fields":      _CREDENTIAL_FIELDS.get(source_type or "", []),
        "confidence_score":     row.get("confidence_score"),
        "pii_percentage":       row.get("pii_percentage"),
        "outlier_count":        row.get("outlier_count"),
    }


# ============================================================
# ROUTES — CONNECTOR CRUD
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
    """Tier-1 test + LIGHTWEIGHT preview of datasets and pipelines.
    The frontend uses preview.datasets[*].source_system_type and
    preview.datasets[*].required_fields to render Tier-2 credential forms
    BEFORE the user clicks Save."""
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid connector type")
    try:
        details = test_connection(body.type, body.config)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    preview = preview_scan(body.type, body.config)
    return {
        "ok":       True,
        "details":  details,
        "preview":  preview,
    }


@router.post("/test-dataset-credentials")
def test_dataset_creds_endpoint(
    body: DatasetCredsTestIn,
    user: dict = Depends(get_current_user),
):
    """Validate one set of Tier-2 credentials WITHOUT saving.
    Frontend should call this for each dataset card before submitting /create."""
    if body.source_system_type not in _CREDENTIAL_FIELDS:
        return {
            "ok": False,
            "error": f"Unsupported source_system_type: {body.source_system_type}",
        }
    try:
        details = _test_dataset_source(
            body.source_system_type, body.connection_hint, body.credentials,
        )
        return {
            "ok":              True,
            "details":         details,
            "required_fields": _CREDENTIAL_FIELDS[body.source_system_type],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/create")
def create_connector(
    body: ConnectorIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles("admin", "steward")),
):
    """Atomic save:
      1. Validate Tier-1 connector creds.
      2. Validate every Tier-2 dataset credential in dataset_credentials[].
      3. Insert connector + each dataset row (with encrypted creds, Connected).
      4. Background full scan fills in pipelines + any datasets the user didn't
         supply creds for (those land as Pending).
    """
    if body.type not in CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="Invalid connector type")

    # 1) Tier-1
    try:
        test_connection(body.type, body.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connector test failed: {e}")

    # 2) Tier-2 — validate each up front so we don't half-save
    dataset_errors: List[dict] = []
    for dc in body.dataset_credentials:
        if dc.source_system_type not in _CREDENTIAL_FIELDS:
            dataset_errors.append({
                "dataset_name": dc.dataset_name,
                "error": f"Unsupported source_system_type: {dc.source_system_type}",
            })
            continue
        try:
            _test_dataset_source(dc.source_system_type, dc.connection_hint, dc.credentials)
        except Exception as e:
            dataset_errors.append({"dataset_name": dc.dataset_name, "error": str(e)})

    if dataset_errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "One or more dataset credentials failed",
                    "errors": dataset_errors},
        )

    # 3) Persist connector
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

    # 3b) Persist each pre-validated dataset row with its encrypted creds
    for dc in body.dataset_credentials:
        execute(
            "INSERT INTO datasets ("
            " connector_id, dataset_name, dataset_type, schema_name,"
            " linked_service_name, source_system_type, connection_hint_json,"
            " credentials_json, credential_status, last_dataset_test_at,"
            " confidence_score, pii_percentage, outlier_count"
            ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Connected',%s,0,0,0)",
            (
                new_id,
                dc.dataset_name,
                dc.dataset_type or "dataset",
                dc.schema_name,
                dc.linked_service_name,
                dc.source_system_type,
                json.dumps(dc.connection_hint or {}),
                encrypt_config(dc.credentials),
                datetime.now(timezone.utc),
            ),
        )

    # 4) Background full scan: profiling JSONs + pipeline run history,
    #    plus any datasets the user didn't pre-credential (they go in as Pending).
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
            "UPDATE connectors SET status='Connection Failed', last_tested_at=%s "
            "WHERE id=%s",
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
    # 1.5) Tier-2 — validate each up front
    dataset_errors: List[dict] = []
    for dc in body.dataset_credentials:
        if dc.source_system_type in _CREDENTIAL_FIELDS:
            try:
                _test_dataset_source(dc.source_system_type, dc.connection_hint, dc.credentials)
            except Exception as e:
                dataset_errors.append({"dataset_name": dc.dataset_name, "error": str(e)})

    if dataset_errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "One or more dataset credentials failed", "errors": dataset_errors},
        )

    # 1.4) Handle masked secrets
    old_row = fetch_one("SELECT config_json FROM connectors WHERE id=%s", (cid,))
    if old_row:
        old_cfg = decrypt_config(old_row["config_json"])
        for key, val in body.config.items():
            if isinstance(val, str) and ("***" in val or val == "********"):
                if key in old_cfg:
                    body.config[key] = old_cfg[key]

    enc = encrypt_config(body.config)
    try:
        execute(
            "UPDATE connectors SET name=%s, type=%s, config_json=%s, status=%s, "
            "last_tested_at=%s WHERE id=%s",
            (body.name, body.type, enc, status, datetime.now(timezone.utc), cid),
        )
    except pymysql.err.IntegrityError:
        raise HTTPException(status_code=409, detail="Connector name already exists")

    # 1.6) Update or Insert dataset rows with encrypted creds
    for dc in body.dataset_credentials:
        existing = fetch_one(
            "SELECT id FROM datasets WHERE connector_id=%s AND dataset_name=%s AND dataset_type=%s",
            (cid, dc.dataset_name, dc.dataset_type or "dataset")
        )
        if existing:
            execute(
                "UPDATE datasets SET "
                " schema_name=%s, linked_service_name=%s, source_system_type=%s, "
                " connection_hint_json=%s, credentials_json=%s, credential_status='Connected', "
                " last_dataset_test_at=%s "
                " WHERE id=%s",
                (
                    dc.schema_name, dc.linked_service_name, dc.source_system_type,
                    json.dumps(dc.connection_hint or {}),
                    encrypt_config(dc.credentials),
                    datetime.now(timezone.utc),
                    existing["id"]
                )
            )
        else:
            execute(
                "INSERT INTO datasets ("
                " connector_id, dataset_name, dataset_type, schema_name,"
                " linked_service_name, source_system_type, connection_hint_json,"
                " credentials_json, credential_status, last_dataset_test_at,"
                " confidence_score, pii_percentage, outlier_count"
                ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Connected',%s,0,0,0)",
                (
                    cid, dc.dataset_name, dc.dataset_type or "dataset",
                    dc.schema_name, dc.linked_service_name, dc.source_system_type,
                    json.dumps(dc.connection_hint or {}),
                    encrypt_config(dc.credentials),
                    datetime.now(timezone.utc),
                )
            )

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


# ============================================================
# ROUTES — TIER-2 DATASET CREDENTIALS (post-save management)
# ============================================================
@router.get("/{cid}/datasets")
def list_datasets_for_connector(
    cid: int,
    user: dict = Depends(get_current_user),
):
    if not fetch_one("SELECT id FROM connectors WHERE id=%s", (cid,)):
        raise HTTPException(status_code=404, detail="Connector not found")
    rows = fetch_all(
        "SELECT id, connector_id, dataset_name, dataset_type, schema_name, "
        "linked_service_name, source_system_type, connection_hint_json, "
        "credential_status, last_dataset_test_at, "
        "confidence_score, pii_percentage, outlier_count "
        "FROM datasets WHERE connector_id=%s ORDER BY id DESC",
        (cid,),
    )
    return [_serialize_dataset(r) for r in rows]


@router.post("/{cid}/datasets/{did}/credentials")
def set_dataset_credentials(
    cid: int,
    did: int,
    body: DatasetCredentialsIn,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_roles("admin", "steward")),
):
    """Submit Tier-2 creds for a dataset that was discovered later
    (i.e. wasn't included in the original /create payload)."""
    ds = fetch_one(
        "SELECT id, source_system_type, connection_hint_json "
        "FROM datasets WHERE id=%s AND connector_id=%s",
        (did, cid),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    source_type = ds.get("source_system_type")
    if not source_type:
        raise HTTPException(
            status_code=400,
            detail="Source system type unknown for this dataset",
        )
    if source_type not in _CREDENTIAL_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"No credential schema for source type: {source_type}",
        )

    hint = {}
    if ds.get("connection_hint_json"):
        try:
            hint = json.loads(ds["connection_hint_json"])
        except Exception:
            hint = {}

    try:
        details = _test_dataset_source(source_type, hint, body.credentials)
    except Exception as e:
        execute(
            "UPDATE datasets SET credential_status='Failed', "
            "last_dataset_test_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), did),
        )
        return {"ok": False, "error": str(e)}

    execute(
        "UPDATE datasets SET credentials_json=%s, credential_status='Connected', "
        "last_dataset_test_at=%s WHERE id=%s",
        (encrypt_config(body.credentials), datetime.now(timezone.utc), did),
    )
    background_tasks.add_task(_run_quality_for_single_dataset, did)
    return {"ok": True, "details": details}


@router.post("/{cid}/datasets/{did}/test")
def retest_dataset(
    cid: int,
    did: int,
    user: dict = Depends(get_current_user),
):
    ds = fetch_one(
        "SELECT source_system_type, connection_hint_json, credentials_json "
        "FROM datasets WHERE id=%s AND connector_id=%s",
        (did, cid),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if not ds.get("credentials_json"):
        raise HTTPException(
            status_code=400,
            detail="No credentials saved yet — POST to /credentials first.",
        )
    source_type = ds.get("source_system_type")
    if not source_type:
        raise HTTPException(status_code=400, detail="Source system type unknown")

    hint = {}
    if ds.get("connection_hint_json"):
        try:
            hint = json.loads(ds["connection_hint_json"])
        except Exception:
            hint = {}

    creds = decrypt_config(ds["credentials_json"])
    try:
        details = _test_dataset_source(source_type, hint, creds)
        execute(
            "UPDATE datasets SET credential_status='Connected', "
            "last_dataset_test_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), did),
        )
        return {"ok": True, "details": details}
    except Exception as e:
        execute(
            "UPDATE datasets SET credential_status='Failed', "
            "last_dataset_test_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), did),
        )
        return {"ok": False, "error": str(e)}


@router.delete("/{cid}/datasets/{did}/credentials")
def clear_dataset_credentials(
    cid: int,
    did: int,
    user: dict = Depends(require_roles("admin", "steward")),
):
    ds = fetch_one(
        "SELECT id FROM datasets WHERE id=%s AND connector_id=%s",
        (did, cid),
    )
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    execute(
        "UPDATE datasets SET credentials_json=NULL, credential_status='Pending', "
        "last_dataset_test_at=NULL WHERE id=%s",
        (did,),
    )
    return {"ok": True}
