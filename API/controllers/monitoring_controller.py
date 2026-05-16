"""Monitoring controller — quality scans only.

Triggered by either:
  • connector create (auto, no rulebook needed) — triggered_by_rulebook_id=0
  • rulebook upload                              — triggered_by_rulebook_id=<rb_id>

For each dataset of the connector type:
   → run the right Python deterministic check
   → write confidence_score, pii_percentage, outlier_count, quality_score
   → LLM wraps the Python result into the dashboard JSON

CHECKER DISPATCH:
   native mysql/mssql table or view   → _check_mysql_table
                                          (uses connector-level cfg directly)

   azure_adf pipeline | databricks pipeline
                                      → _check_pipeline  (no Tier-2 needed)

   azure_adf dataset                  → _check_adf_dataset
                                          → uses Tier-2 creds saved on the
                                            dataset row + connection_hint
                                            (host/database/schema/table)
                                            to connect DIRECTLY to the
                                            underlying Postgres / MSSQL /
                                            MySQL / Oracle / Snowflake / Blob.
                                          NO linked-service connection-string
                                          parsing anymore.

   databricks table (UC)              → _check_databricks_uc_table
                                          → uses Tier-2 server_hostname +
                                            http_path + token to query the
                                            Databricks SQL Warehouse.

A dataset with credential_status='Pending' is SKIPPED at run_quality time —
quality runs only against datasets the user has provided Tier-2 creds for.
"""

import json
import datetime
from typing import Dict, Any, List, Optional, Callable, Tuple

import pymysql
import requests

from fastapi import APIRouter, Depends, HTTPException
from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user
from utils.common import (
    logger, decrypt_config,
    detect_pii_in_column_name, detect_pii_in_samples, safe_json_dumps,
)
from utils.ai_helper import format_quality_report
from utils.vector_helper import search_rule_books
from utils import quality_engine as qe

from controllers.rule_book_controller import get_latest_rulebook, collection_name

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


# ======================================================================
#  MySQL helper (used by native mysql/mssql connector type)
# ======================================================================
def _mysql_conn(cfg: Dict[str, Any], database: Optional[str] = None):
    db = database if database is not None else cfg.get("database")
    return pymysql.connect(
        host=cfg.get("host"),
        port=int(cfg.get("port") or 3306),
        user=cfg.get("username"),
        password=cfg.get("password") or "",
        database=db or None,
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _is_non_negative_column(col_name: str, declared_type: str) -> bool:
    name = (col_name or "").lower()
    keywords = ("price", "qty", "quantity", "amount", "count", "age", "salary",
                "balance", "total", "rate", "duration", "len", "length",
                "size", "weight", "score")
    return any(k in name for k in keywords)


# ======================================================================
#  RULEBOOK LOADER
# ======================================================================
def _load_rulebook_context(connector_type: str) -> Dict[str, Any]:
    rb = get_latest_rulebook(connector_type)
    if not rb:
        logger.info("No rulebook for %s — proceeding with built-in rules only",
                    connector_type)
        return {"rulebook": None, "chunks": []}
    chunks: List[Any] = []
    try:
        chunks = search_rule_books(
            rb["rulebook_content"][:2000], top_k=10,
            collection=collection_name(connector_type),
        )
    except TypeError:
        try:
            chunks = search_rule_books(rb["rulebook_content"][:2000], top_k=10)
        except Exception as e:
            logger.warning("Rulebook chunk fetch (fallback) failed: %s", e)
    except Exception as e:
        logger.warning("Rulebook chunk fetch failed: %s", e)
    return {"rulebook": rb, "chunks": chunks}


def _load_previous_py_result(dataset_id: int) -> Optional[dict]:
    row = fetch_one(
        "SELECT ai_analysis_json FROM datasets WHERE id=%s", (dataset_id,)
    )
    if not row or not row.get("ai_analysis_json"):
        return None
    try:
        return json.loads(row["ai_analysis_json"]).get("python")
    except Exception:
        return None


# ======================================================================
#  ROW-NORMALIZATION HELPER
#  Different drivers return rows differently:
#    • pymysql DictCursor       → dict
#    • psycopg2 RealDictCursor  → dict
#    • pymssql as_dict=True     → dict
#    • databricks-sql connector → Row (namedtuple-like)
#  This helper normalizes access by lowercase key.
# ======================================================================
def _row_get(row, key: str, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        # try both cases
        return row.get(key, row.get(key.upper(), row.get(key.lower(), default)))
    if hasattr(row, "_asdict"):
        d = row._asdict()
        return d.get(key, d.get(key.upper(), d.get(key.lower(), default)))
    if hasattr(row, "asDict"):
        d = row.asDict()
        return d.get(key, default)
    # tuple / Row with attribute access
    try:
        return getattr(row, key)
    except Exception:
        try:
            return row[0]
        except Exception:
            return default


# ======================================================================
#  GENERIC SQL TABLE PROFILER
#  Used by:
#    - _check_mysql_table              (native mysql/mssql connector)
#    - _profile_dataset_via_postgres   (ADF dataset → Postgres)
#    - _profile_dataset_via_mssql      (ADF dataset → SQL Server)
#    - _profile_dataset_via_mysql      (ADF dataset → MySQL)
#    - _check_databricks_uc_table      (Databricks UC table)
#
#  Runs the FULL per-column quality scan (nulls, blanks, garbage, outliers,
#  duplicates, PII, freshness, PK/FK), aggregates, and returns the standard
#  py_result dict consumed by the LLM formatter.
# ======================================================================
def _profile_sql_table(
    dialect: str,                  # 'mysql' | 'postgres' | 'mssql' | 'databricks'
    cn,                            # open DBAPI connection
    schema: str,
    table: str,
    dataset_name: str,
    *,
    catalog: Optional[str] = None,
    cursor_factory=None,           # for psycopg2 RealDictCursor
    sample_limit: int = 500,
) -> Dict[str, Any]:

    # --- dialect-specific identifier quoting + SQL fragments ---
    if dialect == "mysql":
        full_ref = f"`{schema}`.`{table}`"
        qcol = lambda c: f"`{c}`"
        info_cols_sql = (
            "SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type, "
            "       IS_NULLABLE AS is_nullable, COLUMN_KEY AS column_key "
            "FROM information_schema.columns "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
            "ORDER BY ORDINAL_POSITION"
        )
        info_cols_args = (schema, table)
        fk_sql = (
            "SELECT COLUMN_NAME AS column_name, "
            "       REFERENCED_TABLE_NAME AS ref_table, "
            "       REFERENCED_COLUMN_NAME AS ref_column, "
            "       CONSTRAINT_NAME AS constraint_name "
            "FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
            "AND REFERENCED_TABLE_NAME IS NOT NULL"
        )
        fk_args = (schema, table)
        pk_from_info_schema = False  # PKs come from COLUMN_KEY='PRI'
        sample_sql_tmpl = "SELECT {col} AS v FROM {ref} WHERE {col} IS NOT NULL LIMIT {n}"

    elif dialect == "postgres":
        full_ref = f'"{schema}"."{table}"'
        qcol = lambda c: f'"{c}"'
        info_cols_sql = (
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s "
            "ORDER BY ordinal_position"
        )
        info_cols_args = (schema, table)
        fk_sql = (
            "SELECT kcu.column_name AS column_name, "
            "       ccu.table_name AS ref_table, "
            "       ccu.column_name AS ref_column, "
            "       tc.constraint_name AS constraint_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name = tc.constraint_name "
            "WHERE tc.constraint_type='FOREIGN KEY' "
            "  AND tc.table_schema=%s AND tc.table_name=%s"
        )
        fk_args = (schema, table)
        pk_sql = (
            "SELECT kc.column_name AS column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kc "
            "  ON kc.constraint_name = tc.constraint_name "
            "WHERE tc.constraint_type='PRIMARY KEY' "
            "  AND tc.table_schema=%s AND tc.table_name=%s"
        )
        pk_args = (schema, table)
        pk_from_info_schema = True
        sample_sql_tmpl = "SELECT {col} AS v FROM {ref} WHERE {col} IS NOT NULL LIMIT {n}"

    elif dialect == "mssql":
        full_ref = f"[{schema}].[{table}]"
        qcol = lambda c: f"[{c}]"
        info_cols_sql = (
            "SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type, "
            "       IS_NULLABLE AS is_nullable "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
            "ORDER BY ORDINAL_POSITION"
        )
        info_cols_args = (schema, table)
        pk_sql = (
            "SELECT COLUMN_NAME AS column_name "
            "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
            "WHERE OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + "
            "      QUOTENAME(CONSTRAINT_NAME)), 'IsPrimaryKey')=1 "
            "  AND TABLE_SCHEMA=%s AND TABLE_NAME=%s"
        )
        pk_args = (schema, table)
        fk_sql = (
            "SELECT c1.name AS column_name, "
            "       OBJECT_NAME(fkc.referenced_object_id) AS ref_table, "
            "       c2.name AS ref_column, "
            "       fk.name AS constraint_name "
            "FROM sys.foreign_keys fk "
            "JOIN sys.foreign_key_columns fkc "
            "  ON fk.object_id = fkc.constraint_object_id "
            "JOIN sys.columns c1 "
            "  ON fkc.parent_object_id = c1.object_id "
            " AND fkc.parent_column_id = c1.column_id "
            "JOIN sys.columns c2 "
            "  ON fkc.referenced_object_id = c2.object_id "
            " AND fkc.referenced_column_id = c2.column_id "
            "WHERE OBJECT_NAME(fk.parent_object_id)=%s"
        )
        fk_args = (table,)
        pk_from_info_schema = True
        sample_sql_tmpl = "SELECT TOP {n} {col} AS v FROM {ref} WHERE {col} IS NOT NULL"

    elif dialect == "databricks":
        if catalog:
            full_ref = f"`{catalog}`.`{schema}`.`{table}`"
        else:
            full_ref = f"`{schema}`.`{table}`"
        qcol = lambda c: f"`{c}`"
        # Unity Catalog system.information_schema
        if catalog:
            info_cols_sql = (
                "SELECT column_name, data_type, is_nullable "
                "FROM system.information_schema.columns "
                "WHERE table_catalog=? AND table_schema=? AND table_name=? "
                "ORDER BY ordinal_position"
            )
            info_cols_args = (catalog, schema, table)
        else:
            info_cols_sql = (
                "SELECT column_name, data_type, is_nullable "
                "FROM system.information_schema.columns "
                "WHERE table_schema=? AND table_name=? "
                "ORDER BY ordinal_position"
            )
            info_cols_args = (schema, table)
        pk_sql = None
        pk_args = None
        fk_sql = None
        fk_args = None
        pk_from_info_schema = False
        sample_sql_tmpl = "SELECT {col} AS v FROM {ref} WHERE {col} IS NOT NULL LIMIT {n}"

    else:
        raise ValueError(f"Unsupported dialect: {dialect}")

    # --- get a cursor (driver-specific) ---
    if dialect == "postgres":
        import psycopg2.extras
        cur = cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    elif dialect == "mssql":
        cur = cn.cursor(as_dict=True)
    elif dialect == "mysql":
        cur = cn.cursor()  # already DictCursor
    else:  # databricks
        cur = cn.cursor()

    # --- profile ---
    rules: List[qe.RuleResult] = []
    pii_cols: List[str] = []
    total_outliers = 0
    outlier_reasons: List[Dict[str, Any]] = []
    columns_out: List[dict] = []
    primary_keys: List[str] = []
    foreign_keys: List[Dict[str, Any]] = []

    total_null_cells      = 0
    total_value_samples   = 0
    total_junk_values     = 0
    total_numeric_samples = 0

    try:
        # ---- row count
        cur.execute(f"SELECT COUNT(*) AS c FROM {full_ref}")
        total = int(_row_get(cur.fetchone(), "c") or 0)
        if total == 0:
            rules.append(qe.RuleResult(
                "row_count", "Row count", "completeness",
                False, 40.0, ["Table is empty"], {"row_count": 0}))
        else:
            rules.append(qe.RuleResult(
                "row_count", "Row count", "completeness",
                True, 100.0, [], {"row_count": total}))

        # ---- columns metadata
        cur.execute(info_cols_sql, info_cols_args)
        col_rows = cur.fetchall() or []
        total_columns_scanned = len(col_rows)
        timestamp_cols: List[str] = []

        for cr in col_rows:
            col_name = _row_get(cr, "column_name")
            dtype = (_row_get(cr, "data_type") or "").lower()
            is_nullable = (_row_get(cr, "is_nullable") or "").upper() == "YES"
            mysql_key = _row_get(cr, "column_key")
            is_pk_mysql = (mysql_key == "PRI")
            if is_pk_mysql:
                primary_keys.append(col_name)

            # null count
            try:
                cur.execute(
                    f"SELECT SUM(CASE WHEN {qcol(col_name)} IS NULL THEN 1 ELSE 0 END) "
                    f"AS n FROM {full_ref}"
                )
                n_null = int(_row_get(cur.fetchone(), "n") or 0)
            except Exception:
                n_null = 0
            total_null_cells += n_null

            # distinct count
            try:
                cur.execute(f"SELECT COUNT(DISTINCT {qcol(col_name)}) AS d FROM {full_ref}")
                distinct = int(_row_get(cur.fetchone(), "d") or 0)
            except Exception:
                distinct = 0

            # sample
            samples: List[Any] = []
            numeric_samples: List[float] = []
            try:
                cur.execute(sample_sql_tmpl.format(
                    col=qcol(col_name), ref=full_ref, n=sample_limit,
                ))
                for rr in cur.fetchall():
                    v = _row_get(rr, "v")
                    samples.append(v)
                    f = qe._to_float(v)
                    if f is not None:
                        numeric_samples.append(f)
            except Exception as e:
                logger.debug("Sample fetch failed for %s.%s: %s",
                             full_ref, col_name, e)

            total_value_samples   += len(samples)
            total_numeric_samples += len(numeric_samples)

            # ----- rules -----
            rules.append(qe.rule_null_completeness(col_name, n_null, total))

            blank_rule = qe.rule_blank_garbage(col_name, samples)
            rules.append(blank_rule)
            bm = blank_rule.metrics or {}
            total_junk_values += int(
                bm.get("garbage_count")
                or bm.get("blank_count")
                or bm.get("invalid_count")
                or (0 if blank_rule.passed else max(1, len(samples) // 20))
            )

            rules.append(qe.rule_duplicate_check(col_name, total, distinct))

            misp_rule = qe.rule_misplaced_data(col_name, samples, dtype)
            rules.append(misp_rule)
            mm = misp_rule.metrics or {}
            total_junk_values += int(
                mm.get("misplaced_count")
                or mm.get("invalid_count")
                or (0 if misp_rule.passed else max(1, len(samples) // 20))
            )

            if numeric_samples:
                outlier_rule = qe.rule_outlier_detection(col_name, numeric_samples)
                rules.append(outlier_rule)
                om = outlier_rule.metrics or {}
                n_iqr = om.get("iqr_outliers", 0)
                n_z   = om.get("z_outliers", 0)
                n_out = max(n_iqr, n_z)
                total_outliers += n_out
                if n_out > 0:
                    outlier_reasons.append({
                        "column":       col_name,
                        "iqr_outliers": n_iqr,
                        "z_outliers":   n_z,
                        "lower_bound":  om.get("lower_bound"),
                        "upper_bound":  om.get("upper_bound"),
                        "sample_size":  len(numeric_samples),
                        "reason": f"{n_out} value(s) outside expected range "
                                  f"[{om.get('lower_bound')}, {om.get('upper_bound')}] "
                                  f"based on {len(numeric_samples)} sampled values.",
                    })
                if _is_non_negative_column(col_name, dtype):
                    rules.append(qe.rule_invalid_sign(
                        col_name, numeric_samples, expect_positive=True))

            # PII
            pii_cat = detect_pii_in_column_name(col_name)
            if not pii_cat and samples:
                pii_cat = detect_pii_in_samples([str(s) for s in samples[:50]])
            if pii_cat:
                pii_cols.append(col_name)

            if dtype in ("datetime", "timestamp", "date",
                         "timestamp with time zone",
                         "timestamp without time zone",
                         "datetime2", "smalldatetime"):
                timestamp_cols.append(col_name)

            columns_out.append({
                "name":     col_name,
                "type":     dtype,
                "nullable": is_nullable,
                "is_pk":    is_pk_mysql,
            })

        # ---- PKs from INFORMATION_SCHEMA (non-mysql)
        if pk_from_info_schema and pk_sql:
            try:
                cur.execute(pk_sql, pk_args)
                for r in cur.fetchall() or []:
                    pkname = _row_get(r, "column_name")
                    if pkname and pkname not in primary_keys:
                        primary_keys.append(pkname)
            except Exception as e:
                logger.debug("PK fetch failed: %s", e)

        # mark PKs in columns_out
        pk_set = set(primary_keys)
        for c in columns_out:
            if c["name"] in pk_set:
                c["is_pk"] = True

        # ---- FKs
        if fk_sql:
            try:
                cur.execute(fk_sql, fk_args)
                for r in cur.fetchall() or []:
                    foreign_keys.append({
                        "column":     _row_get(r, "column_name"),
                        "ref_table":  _row_get(r, "ref_table"),
                        "ref_column": _row_get(r, "ref_column"),
                        "constraint": _row_get(r, "constraint_name"),
                    })
            except Exception as e:
                logger.debug("FK fetch failed: %s", e)

        # ---- PK uniqueness
        if primary_keys and total > 0:
            pk_expr = ", ".join([qcol(c) for c in primary_keys])
            try:
                cur.execute(
                    f"SELECT COUNT(*) - COUNT(DISTINCT {pk_expr}) AS d FROM {full_ref}"
                )
                pk_dup = int(_row_get(cur.fetchone(), "d") or 0)
                rules.append(qe.rule_pk_uniqueness(",".join(primary_keys), pk_dup))
            except Exception as e:
                logger.debug("PK uniqueness check failed: %s", e)

        # ---- Freshness
        if timestamp_cols:
            ts = timestamp_cols[0]
            try:
                cur.execute(f"SELECT MAX({qcol(ts)}) AS m FROM {full_ref}")
                last = _row_get(cur.fetchone(), "m")
                rules.append(qe.rule_freshness(ts, last, threshold_days=7))
            except Exception as e:
                logger.debug("Freshness check failed: %s", e)

        rules.append(qe.rule_pii_governance(pii_cols))

    finally:
        try:
            cur.close()
        except Exception:
            pass

    aggregated = qe.aggregate(rules)
    pii_pct = (len(pii_cols) / total_columns_scanned * 100) if total_columns_scanned else 0.0
    total_cells = total * total_columns_scanned
    missing_data_pct = (total_null_cells / total_cells * 100) if total_cells else 0.0
    junk_data_pct    = (total_junk_values / total_value_samples * 100) if total_value_samples else 0.0
    outlier_pct      = (total_outliers / total_numeric_samples * 100) if total_numeric_samples else 0.0

    tables_summary = [{
        "schema":       schema,
        "table_name":   table,
        "row_count":    total,
        "column_count": total_columns_scanned,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
    }]

    return {
        "score":           aggregated["final_score"],
        "confidence":      aggregated["confidence"],
        "severity":        aggregated["severity"],
        "pii_percentage":  round(pii_pct, 2),
        "outlier_count":   total_outliers,
        "pii_columns":     pii_cols,
        "total_rules":     aggregated["total_rules"],
        "passed":          aggregated["passed"],
        "failed":          aggregated["failed"],
        "by_category":     aggregated["by_category"],
        "failed_rules": [
            {"rule": r["rule_name"], "category": r["category"],
             "score": r["score"], "reason": "; ".join(r["findings"])}
            for r in aggregated["rules"] if not r["passed"]
        ],
        "findings":        aggregated["findings"],
        "row_count":       total,
        "columns_scanned": total_columns_scanned,
        "asset_kind":      "table",
        "table_info": {
            "table_name":   table,
            "schema":       schema,
            "catalog":      catalog,
            "row_count":    total,
            "column_count": total_columns_scanned,
            "columns":      columns_out,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "dialect":      dialect,
        },
        "outlier_reasons":  outlier_reasons,
        "missing_data_pct": round(missing_data_pct, 2),
        "junk_data_pct":    round(junk_data_pct, 2),
        "outlier_pct":      round(outlier_pct, 2),
        "tables_summary":   tables_summary,
    }


# ======================================================================
#  CHECK 1 — NATIVE MySQL TABLE
#  (called when ctype='mysql' and dstype in ('table','view'))
# ======================================================================
def _check_mysql_table(dataset_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
    schema_name = ds["schema_name"] or cfg.get("database")
    name = ds["dataset_name"]
    cn = _mysql_conn(cfg, database=schema_name)
    try:
        result = _profile_sql_table(
            dialect="mysql",
            cn=cn,
            schema=schema_name,
            table=name,
            dataset_name=name,
        )
        return result
    finally:
        cn.close()


# ======================================================================
#  CHECK 2 — ADF / DATABRICKS PIPELINE
#  (no Tier-2 creds required — connector token reaches the pipeline metadata)
# ======================================================================
def _suggest_pipeline_fix(error_message: str, activity_logs: List[dict]) -> str:
    msg = (error_message or "").lower()
    if "permission" in msg or "unauthorized" in msg or "403" in msg or "forbidden" in msg:
        return ("Verify the service principal has 'Data Factory Contributor' role "
                "and the linked service credentials are not expired.")
    if "timeout" in msg or "timed out" in msg:
        return ("Increase the activity timeout setting or check the source/sink "
                "for slow response. Investigate network latency.")
    if "not found" in msg or "404" in msg or "doesnotexist" in msg or "blobnotexist" in msg:
        return ("The referenced source path/blob/table no longer exists. "
                "Check upstream job dependency or re-run the producer.")
    if "credentials" in msg or "authentication" in msg or "401" in msg:
        return ("Linked service credentials are invalid or expired. "
                "Rotate the secret in Key Vault and update the linked service.")
    if "schema" in msg or "column" in msg or "type mismatch" in msg:
        return ("Source schema has drifted. Update the dataset definition or "
                "enable schema-drift handling in the copy activity.")
    if "throttl" in msg or "rate limit" in msg or "429" in msg:
        return ("Downstream system throttled the request. Add retry policy "
                "with exponential backoff and reduce parallelism.")
    if "out of memory" in msg or "outofmemory" in msg or "executor" in msg:
        return ("Increase the data integration runtime / cluster memory, or "
                "partition the source for smaller batches.")
    if activity_logs:
        a = activity_logs[0]
        return (f"Investigate failed activity '{a.get('activity')}' "
                f"({a.get('activity_type')}) — see error_message in logs.")
    return ("Review the run logs and the activity error details, then "
            "re-trigger after fixing the upstream issue.")


def _check_pipeline(connector_id: int, cfg: dict, ds: dict, ctype: str) -> Dict[str, Any]:
    rules: List[qe.RuleResult] = []
    name = ds["dataset_name"]
    total_runs = 0
    failed_runs = 0
    run_details: List[Dict[str, Any]] = []
    pipeline_meta: Dict[str, Any] = {
        "pipeline_id":   None,
        "pipeline_name": name,
        "created_time":  None,
        "last_modified": None,
        "activities":    [],
    }

    try:
        if ctype == "azure_adf":
            token_r = requests.post(
                f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "scope":         "https://management.azure.com/.default",
                }, timeout=30,
            )
            if token_r.status_code != 200:
                raise RuntimeError(f"ADF auth failed: {token_r.status_code}")
            tok = token_r.json()["access_token"]
            base_url = (
                f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
                f"/resourceGroups/{cfg['resource_group']}"
                f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
            )
            headers = {"Authorization": f"Bearer {tok}"}

            pl_r = requests.get(
                f"{base_url}/pipelines/{name}?api-version=2018-06-01",
                headers=headers, timeout=30)
            if pl_r.status_code == 200:
                pl = pl_r.json()
                pipeline_meta["pipeline_id"]   = pl.get("id")
                pipeline_meta["created_time"]  = (
                    (pl.get("properties") or {}).get("createdDate")
                    or pl.get("systemData", {}).get("createdAt")
                )
                pipeline_meta["last_modified"] = pl.get("systemData", {}).get("lastModifiedAt")
                pipeline_meta["activities"] = []
                for a in (pl.get("properties") or {}).get("activities", []):
                    tp = a.get("typeProperties") or {}
                    pipeline_meta["activities"].append({
                        "name":             a.get("name"),
                        "type":             a.get("type"),
                        "inputs":           a.get("inputs", []),
                        "outputs":          a.get("outputs", []),
                        "source":           tp.get("source", {}),
                        "sink":             tp.get("sink", {}),
                        "translator":       tp.get("translator", {}),
                        "sql_reader_query": tp.get("sqlReaderQuery"),
                        "raw_activity":     a,
                    })

            runs_r = requests.post(
                f"{base_url}/queryPipelineRuns?api-version=2018-06-01",
                headers=headers,
                json={
                    "lastUpdatedAfter":  (datetime.datetime.utcnow()
                                          - datetime.timedelta(days=7)).isoformat(),
                    "lastUpdatedBefore": datetime.datetime.utcnow().isoformat(),
                    "filters": [{"operand":  "PipelineName",
                                 "operator": "Equals",
                                 "values":   [name]}],
                }, timeout=20,
            )
            if runs_r.status_code == 200:
                runs = runs_r.json().get("value", []) or []
                total_runs = len(runs)
                for r in runs:
                    status  = r.get("status")
                    is_fail = status == "Failed"
                    if is_fail:
                        failed_runs += 1

                    activity_logs: List[Dict[str, Any]] = []
                    if is_fail and r.get("runId"):
                        try:
                            act_r = requests.post(
                                f"{base_url}/pipelineruns/{r['runId']}/queryActivityruns?api-version=2018-06-01",
                                headers=headers,
                                json={
                                    "lastUpdatedAfter":  (datetime.datetime.utcnow()
                                                          - datetime.timedelta(days=7)).isoformat(),
                                    "lastUpdatedBefore": datetime.datetime.utcnow().isoformat(),
                                }, timeout=30)
                            if act_r.status_code == 200:
                                for a in act_r.json().get("value", []):
                                    if a.get("status") == "Failed":
                                        err = (a.get("error") or {}).get("message", "")
                                        activity_logs.append({
                                            "activity":      a.get("activityName"),
                                            "activity_type": a.get("activityType"),
                                            "status":        a.get("status"),
                                            "error_message": err[:500],
                                        })
                        except Exception:
                            pass

                    run_details.append({
                        "pipeline_id":          r.get("pipelineName"),
                        "run_id":               r.get("runId"),
                        "status":               status,
                        "is_success":           status == "Succeeded",
                        "failure_reason":       (r.get("message") or "")[:500] if is_fail else "",
                        "recommended_solution": _suggest_pipeline_fix(r.get("message", ""), activity_logs) if is_fail else "",
                        "run_start":            r.get("runStart"),
                        "run_end":              r.get("runEnd"),
                        "duration_ms":          r.get("durationInMs"),
                        "duration_minutes":     round((r.get("durationInMs") or 0) / 60000, 2),
                        "activity_logs":        activity_logs,
                    })

        elif ctype == "databricks":
            base_url = cfg["workspace_url"].rstrip("/")
            headers = {"Authorization": f"Bearer {cfg['token']}"}
            jr = requests.get(f"{base_url}/api/2.1/jobs/list?limit=100",
                              headers=headers, timeout=20)
            if jr.status_code != 200:
                jr = requests.get(f"{base_url}/api/2.0/jobs/list",
                                  headers=headers, timeout=20)
            if jr.status_code == 200:
                jobs = jr.json().get("jobs", []) or []
                match = next((j for j in jobs
                              if (j.get("settings") or {}).get("name") == name), None)
                if match:
                    job_id = match.get("job_id")
                    pipeline_meta["pipeline_id"] = job_id
                    if match.get("created_time"):
                        pipeline_meta["created_time"] = datetime.datetime.utcfromtimestamp(
                            match["created_time"] / 1000).isoformat()
                    pipeline_meta["activities"] = [
                        {"name": t.get("task_key"), "type": "task"}
                        for t in (match.get("settings") or {}).get("tasks", [])
                    ]

                    runs_r = requests.get(
                        f"{base_url}/api/2.1/jobs/runs/list?job_id={job_id}&limit=20",
                        headers=headers, timeout=30)
                    if runs_r.status_code != 200:
                        runs_r = requests.get(
                            f"{base_url}/api/2.0/jobs/runs/list?job_id={job_id}&limit=20",
                            headers=headers, timeout=30)
                    if runs_r.status_code == 200:
                        runs = runs_r.json().get("runs", []) or []
                        total_runs = len(runs)
                        for run in runs:
                            state = run.get("state") or {}
                            result_state = state.get("result_state") or state.get("life_cycle_state")
                            is_fail = result_state == "FAILED"
                            if is_fail:
                                failed_runs += 1
                            start_ms = run.get("start_time") or 0
                            end_ms   = run.get("end_time") or 0
                            err_msg  = (state.get("state_message") or "")[:500]
                            run_details.append({
                                "pipeline_id":          job_id,
                                "run_id":               run.get("run_id"),
                                "status":               result_state,
                                "is_success":           result_state == "SUCCESS",
                                "failure_reason":       err_msg if is_fail else "",
                                "recommended_solution": _suggest_pipeline_fix(err_msg, []) if is_fail else "",
                                "run_start":            datetime.datetime.utcfromtimestamp(start_ms / 1000).isoformat() if start_ms else None,
                                "run_end":              datetime.datetime.utcfromtimestamp(end_ms / 1000).isoformat() if end_ms else None,
                                "duration_ms":          (end_ms - start_ms) if end_ms and start_ms else None,
                                "duration_minutes":     round(((end_ms - start_ms) / 60000), 2) if end_ms and start_ms else None,
                                "activity_logs":        [],
                            })

        if total_runs == 0:
            rules.append(qe.RuleResult(
                f"no_runs_{name}", "No recent runs", "integrity",
                True, 85.0, [f"No runs in the last 7 days for {name}"],
                {"total_runs": 0}))
        else:
            rules.append(qe.rule_pipeline_failure(name, total_runs, failed_runs))

    except Exception as e:
        rules.append(qe.RuleResult(
            f"pipeline_err_{name}", f"Pipeline check {name}", "integrity",
            False, 30.0, [f"Pipeline check error: {e}"], {}))

    aggregated = qe.aggregate(rules)
    return {
        "score":           aggregated["final_score"],
        "confidence":      aggregated["confidence"],
        "severity":        aggregated["severity"],
        "pii_percentage":  0.0,
        "outlier_count":   0,
        "pii_columns":     [],
        "total_rules":     aggregated["total_rules"],
        "passed":          aggregated["passed"],
        "failed":          aggregated["failed"],
        "by_category":     aggregated["by_category"],
        "failed_rules": [
            {"rule": r["rule_name"], "category": r["category"],
             "score": r["score"], "reason": "; ".join(r["findings"])}
            for r in aggregated["rules"] if not r["passed"]
        ],
        "findings":        aggregated["findings"],
        "row_count":       None,
        "columns_scanned": 0,
        "total_runs":      total_runs,
        "failed_runs":     failed_runs,
        "run_details":     run_details,
        "pipeline_meta":   pipeline_meta,
        "asset_kind":      "pipeline",
        "outlier_reasons": [],
        "missing_data_pct": None,
        "junk_data_pct":    None,
        "outlier_pct":      None,
        "tables_summary":   [],
    }


# ======================================================================
#  CHECK 3 — ADF DATASET  (uses Tier-2 creds saved on the dataset row)
# ======================================================================
def _check_adf_dataset(connector_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
    """Profile the underlying source backing an ADF dataset using the
    Tier-2 credentials (and connection_hint) saved on the dataset row.
    No more linked-service connection-string parsing — secrets in ADF
    linked services are SecureString/Key Vault refs that the management
    API doesn't return.
    """
    creds_blob = ds.get("credentials_json")
    if not creds_blob:
        return _empty_py_result(
            "dataset",
            "No Tier-2 credentials saved for this dataset — submit creds via "
            "POST /api/connectors/{cid}/datasets/{did}/credentials",
            severity="low",
        )

    try:
        creds = decrypt_config(creds_blob)
    except Exception as e:
        return _empty_py_result(
            "dataset", f"Tier-2 credential decryption failed: {e}",
            severity="medium", failed=1,
        )

    hint: Dict[str, Any] = {}
    if ds.get("connection_hint_json"):
        try:
            hint = json.loads(ds["connection_hint_json"])
        except Exception:
            hint = {}

    source_type = ds.get("source_system_type") or ""
    name = ds["dataset_name"]

    logger.info(
        "ADF dataset %s → source_system_type=%s, hint=%s",
        name, source_type, {k: v for k, v in hint.items() if k != "password"},
    )

    try:
        if source_type in ("AzureSqlDatabase", "AzureSqlMI",
                           "AzureSqlDW", "SqlServer"):
            return _profile_dataset_via_mssql(creds, hint, ds)

        if source_type in ("AzureMySql", "MySql"):
            return _profile_dataset_via_mysql(creds, hint, ds)

        if source_type in ("AzurePostgreSql", "PostgreSql"):
            return _profile_dataset_via_postgres(creds, hint, ds)

        if source_type in ("AzureBlobStorage", "AzureDataLakeStoreGen2"):
            return _profile_dataset_via_blob(creds, hint, ds)

        if source_type == "Oracle":
            return _profile_dataset_via_oracle(creds, hint, ds)

        if source_type == "Snowflake":
            return _profile_dataset_via_snowflake(creds, hint, ds)

        return _empty_py_result(
            "dataset",
            f"No profiler implemented for source_system_type={source_type}",
            severity="low",
        )
    except Exception as e:
        logger.exception("ADF dataset profile raised for %s", name)
        return _empty_py_result(
            "dataset", f"Profiling raised: {e}",
            severity="critical", failed=1,
        )


def _profile_dataset_via_postgres(creds: dict, hint: dict, ds: dict) -> Dict[str, Any]:
    host     = creds.get("host")     or hint.get("host")
    port     = int(creds.get("port") or hint.get("port") or 5432)
    database = creds.get("database") or hint.get("database")
    user     = creds.get("username")
    pwd      = creds.get("password")
    schema   = hint.get("schema") or "public"
    table    = hint.get("table")   or ds["dataset_name"]
    sslmode  = creds.get("sslmode") or hint.get("sslmode") or "require"

    if not (host and database and user):
        return _empty_py_result(
            "dataset",
            f"Postgres: missing host/database/username (host={host}, db={database})",
            severity="medium",
        )

    try:
        import psycopg2
    except ImportError:
        return _empty_py_result(
            "dataset", "psycopg2 not installed (pip install psycopg2-binary)",
            severity="low",
        )

    try:
        cn = psycopg2.connect(
            host=host, port=port, dbname=database,
            user=user, password=pwd,
            sslmode=sslmode, connect_timeout=10,
        )
    except Exception as e:
        return _empty_py_result(
            "dataset", f"Postgres connection failed: {e}",
            severity="critical", failed=1,
        )

    try:
        return _profile_sql_table(
            dialect="postgres", cn=cn,
            schema=schema, table=table,
            dataset_name=ds["dataset_name"],
        )
    finally:
        try:
            cn.close()
        except Exception:
            pass


def _profile_dataset_via_mysql(creds: dict, hint: dict, ds: dict) -> Dict[str, Any]:
    host     = creds.get("host")     or hint.get("host")
    port     = int(creds.get("port") or hint.get("port") or 3306)
    database = creds.get("database") or hint.get("database")
    user     = creds.get("username")
    pwd      = creds.get("password")
    # MySQL: schema_name == database
    table    = hint.get("table") or ds["dataset_name"]

    if not (host and database and user):
        return _empty_py_result(
            "dataset",
            f"MySQL: missing host/database/username (host={host}, db={database})",
            severity="medium",
        )

    try:
        cn = pymysql.connect(
            host=host, port=port, database=database,
            user=user, password=pwd or "",
            connect_timeout=10,
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as e:
        return _empty_py_result(
            "dataset", f"MySQL connection failed: {e}",
            severity="critical", failed=1,
        )

    try:
        return _profile_sql_table(
            dialect="mysql", cn=cn,
            schema=database, table=table,
            dataset_name=ds["dataset_name"],
        )
    finally:
        try:
            cn.close()
        except Exception:
            pass


def _profile_dataset_via_mssql(creds: dict, hint: dict, ds: dict) -> Dict[str, Any]:
    host     = creds.get("host")     or hint.get("host")
    port     = int(creds.get("port") or hint.get("port") or 1433)
    database = creds.get("database") or hint.get("database")
    user     = creds.get("username")
    pwd      = creds.get("password")
    schema   = hint.get("schema") or "dbo"
    table    = hint.get("table")  or ds["dataset_name"]

    if not (host and database and user):
        return _empty_py_result(
            "dataset",
            f"MSSQL: missing host/database/username (host={host}, db={database})",
            severity="medium",
        )

    try:
        import pymssql
    except ImportError:
        return _empty_py_result(
            "dataset", "pymssql not installed (pip install pymssql)",
            severity="low",
        )

    try:
        cn = pymssql.connect(
            server=host, port=port, user=user,
            password=pwd, database=database, login_timeout=10,
        )
    except Exception as e:
        return _empty_py_result(
            "dataset", f"MSSQL connection failed: {e}",
            severity="critical", failed=1,
        )

    try:
        return _profile_sql_table(
            dialect="mssql", cn=cn,
            schema=schema, table=table,
            dataset_name=ds["dataset_name"],
        )
    finally:
        try:
            cn.close()
        except Exception:
            pass


def _profile_dataset_via_oracle(creds: dict, hint: dict, ds: dict) -> Dict[str, Any]:
    host     = creds.get("host")     or hint.get("host")
    port     = int(creds.get("port") or hint.get("port") or 1521)
    database = creds.get("database") or hint.get("database")
    user     = creds.get("username")
    pwd      = creds.get("password")
    schema   = (hint.get("schema") or user or "").upper()
    table    = hint.get("table")  or ds["dataset_name"]

    if not (host and database and user):
        return _empty_py_result(
            "dataset", "Oracle: missing host/database/username",
            severity="medium",
        )

    try:
        import oracledb
    except ImportError:
        return _empty_py_result(
            "dataset", "oracledb not installed (pip install oracledb)",
            severity="low",
        )

    try:
        dsn = oracledb.makedsn(host, port, service_name=database)
        cn = oracledb.connect(user=user, password=pwd, dsn=dsn)
    except Exception as e:
        return _empty_py_result(
            "dataset", f"Oracle connection failed: {e}",
            severity="critical", failed=1,
        )

    # Oracle uses ALL_TABLES/ALL_TAB_COLUMNS, not INFORMATION_SCHEMA — so a
    # full quality profile via _profile_sql_table isn't directly compatible.
    # Do a light-weight check here.
    try:
        cur = cn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        total = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT column_name, data_type, nullable "
            "FROM all_tab_columns "
            "WHERE owner=:o AND table_name=:t",
            {"o": schema, "t": table},
        )
        cols = [{"name": r[0], "type": r[1], "nullable": r[2] == "Y", "is_pk": False}
                for r in cur.fetchall()]
        cur.close()
    except Exception as e:
        try:
            cn.close()
        except Exception:
            pass
        return _empty_py_result(
            "dataset", f"Oracle query failed: {e}",
            severity="critical", failed=1,
        )

    try:
        cn.close()
    except Exception:
        pass

    rules: List[qe.RuleResult] = []
    if total == 0:
        rules.append(qe.RuleResult(
            "row_count", "Row count", "completeness",
            False, 40.0, ["Table is empty"], {"row_count": 0}))
    else:
        rules.append(qe.RuleResult(
            "row_count", "Row count", "completeness",
            True, 100.0, [], {"row_count": total}))

    aggregated = qe.aggregate(rules)
    return {
        "score":           aggregated["final_score"],
        "confidence":      aggregated["confidence"],
        "severity":        aggregated["severity"],
        "pii_percentage":  0.0, "outlier_count": 0, "pii_columns": [],
        "total_rules":     aggregated["total_rules"],
        "passed":          aggregated["passed"],
        "failed":          aggregated["failed"],
        "by_category":     aggregated["by_category"],
        "failed_rules":    [],
        "findings":        aggregated["findings"],
        "row_count":       total,
        "columns_scanned": len(cols),
        "asset_kind":      "dataset",
        "table_info": {
            "table_name": table, "schema": schema,
            "row_count": total, "column_count": len(cols),
            "columns": cols, "primary_keys": [], "foreign_keys": [],
            "dialect": "oracle",
        },
        "outlier_reasons":  [],
        "missing_data_pct": None,
        "junk_data_pct":    None,
        "outlier_pct":      None,
        "tables_summary": [{
            "schema": schema, "table_name": table,
            "row_count": total, "column_count": len(cols),
            "primary_keys": [], "foreign_keys": [],
        }],
    }


def _profile_dataset_via_snowflake(creds: dict, hint: dict, ds: dict) -> Dict[str, Any]:
    account   = creds.get("account")   or hint.get("account")
    warehouse = creds.get("warehouse") or hint.get("warehouse")
    database  = creds.get("database")  or hint.get("database")
    user      = creds.get("username")
    pwd       = creds.get("password")
    schema    = hint.get("schema") or "PUBLIC"
    table     = hint.get("table")  or ds["dataset_name"]

    if not (account and database and user):
        return _empty_py_result(
            "dataset", "Snowflake: missing account/database/username",
            severity="medium",
        )

    try:
        import snowflake.connector
    except ImportError:
        return _empty_py_result(
            "dataset",
            "snowflake-connector-python not installed",
            severity="low",
        )

    try:
        cn = snowflake.connector.connect(
            account=account, user=user, password=pwd,
            warehouse=warehouse, database=database, schema=schema,
        )
    except Exception as e:
        return _empty_py_result(
            "dataset", f"Snowflake connection failed: {e}",
            severity="critical", failed=1,
        )

    # Snowflake supports ANSI INFORMATION_SCHEMA; reuse generic profiler
    # via the "postgres" dialect (same SQL grammar for our queries).
    try:
        # patch: snowflake uses %s as paramstyle by default
        return _profile_sql_table(
            dialect="postgres", cn=cn,
            schema=schema, table=table,
            dataset_name=ds["dataset_name"],
        )
    finally:
        try:
            cn.close()
        except Exception:
            pass


def _profile_dataset_via_blob(creds: dict, hint: dict, ds: dict) -> Dict[str, Any]:
    """For file datasets (CSV / Parquet / JSON) in Azure Blob or ADLS Gen2.
    We can't run full column-level checks without parsing every file, so we
    do lightweight checks: list files matching the folder_path, count them,
    measure total bytes, and check freshness of the newest file."""
    account = creds.get("account_name") or hint.get("account_name")
    key     = creds.get("account_key")
    container   = hint.get("container")
    folder      = hint.get("folder_path") or ""
    file_filter = hint.get("file_name")

    if not (account and key and container):
        return _empty_py_result(
            "dataset",
            f"Blob: missing account_name/account_key/container "
            f"(account={account}, container={container})",
            severity="medium",
        )

    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        return _empty_py_result(
            "dataset", "azure-storage-blob not installed",
            severity="low",
        )

    blobs = []
    total_bytes = 0
    latest_modified = None
    try:
        bsc = BlobServiceClient(
            account_url=f"https://{account}.blob.core.windows.net",
            credential=key,
        )
        cc = bsc.get_container_client(container)
        prefix = folder.rstrip("/")
        if file_filter:
            prefix = f"{prefix}/{file_filter}" if prefix else file_filter

        for b in cc.list_blobs(name_starts_with=prefix):
            blobs.append(b)
            total_bytes += b.size or 0
            if latest_modified is None or (
                b.last_modified and b.last_modified > latest_modified
            ):
                latest_modified = b.last_modified
            if len(blobs) >= 1000:
                break
    except Exception as e:
        return _empty_py_result(
            "dataset", f"Blob access failed: {e}",
            severity="critical", failed=1,
        )

    rules: List[qe.RuleResult] = []
    if not blobs:
        rules.append(qe.RuleResult(
            "blob_files_present", "Files present in path",
            "completeness", False, 40.0,
            [f"No files in {container}/{prefix or '(root)'}"],
            {"file_count": 0},
        ))
    else:
        rules.append(qe.RuleResult(
            "blob_files_present", "Files present in path",
            "completeness", True, 100.0, [],
            {"file_count": len(blobs)},
        ))

    if latest_modified:
        now = datetime.datetime.now(datetime.timezone.utc)
        if latest_modified.tzinfo is None:
            latest_modified = latest_modified.replace(tzinfo=datetime.timezone.utc)
        days_old = max(0, (now - latest_modified).days)
        passed = days_old <= 7
        rules.append(qe.RuleResult(
            "blob_freshness", "Latest file freshness", "freshness",
            passed,
            max(50.0, 100.0 - days_old * 5),
            [] if passed else [f"Latest file is {days_old} days old"],
            {"days_old": days_old, "latest_modified": str(latest_modified)},
        ))

    aggregated = qe.aggregate(rules)

    return {
        "score":           aggregated["final_score"],
        "confidence":      aggregated["confidence"],
        "severity":        aggregated["severity"],
        "pii_percentage":  0.0,
        "outlier_count":   0,
        "pii_columns":     [],
        "total_rules":     aggregated["total_rules"],
        "passed":          aggregated["passed"],
        "failed":          aggregated["failed"],
        "by_category":     aggregated["by_category"],
        "failed_rules": [
            {"rule": r["rule_name"], "category": r["category"],
             "score": r["score"], "reason": "; ".join(r["findings"])}
            for r in aggregated["rules"] if not r["passed"]
        ],
        "findings":        aggregated["findings"],
        "row_count":       None,
        "columns_scanned": 0,
        "asset_kind":      "dataset",
        "outlier_reasons": [],
        "missing_data_pct": None,
        "junk_data_pct":    None,
        "outlier_pct":      None,
        "tables_summary": [{
            "schema":       container,
            "table_name":   folder or "(root)",
            "row_count":    None,
            "column_count": None,
            "primary_keys": [],
            "foreign_keys": [],
        }],
        "file_summary": {
            "account":         account,
            "container":       container,
            "prefix":          prefix,
            "file_count":      len(blobs),
            "total_bytes":     total_bytes,
            "latest_modified": str(latest_modified) if latest_modified else None,
            "files": [
                {"name": b.name, "size": b.size,
                 "last_modified": str(b.last_modified) if b.last_modified else None}
                for b in blobs[:50]
            ],
        },
    }


# ======================================================================
#  CHECK 4 — DATABRICKS UC TABLE (uses Tier-2 SQL warehouse creds)
# ======================================================================
def _check_databricks_uc_table(ds: dict) -> Dict[str, Any]:
    creds_blob = ds.get("credentials_json")
    if not creds_blob:
        return _empty_py_result(
            "table",
            "No Tier-2 credentials saved for this Databricks table",
            severity="low",
        )
    try:
        creds = decrypt_config(creds_blob)
    except Exception as e:
        return _empty_py_result(
            "table", f"Tier-2 decryption failed: {e}",
            severity="medium", failed=1,
        )

    hint = {}
    if ds.get("connection_hint_json"):
        try:
            hint = json.loads(ds["connection_hint_json"])
        except Exception:
            hint = {}

    server_hostname = creds.get("server_hostname") or hint.get("server_hostname")
    http_path       = creds.get("http_path")
    token           = creds.get("token")
    catalog         = hint.get("catalog")
    schema          = hint.get("schema")
    table           = hint.get("table") or ds["dataset_name"]

    if not all([server_hostname, http_path, token, catalog, schema, table]):
        return _empty_py_result(
            "table",
            f"Databricks: missing fields "
            f"(server={server_hostname}, http_path={'set' if http_path else 'missing'}, "
            f"catalog={catalog}, schema={schema}, table={table})",
            severity="medium",
        )

    try:
        from databricks import sql as dbsql
    except ImportError:
        return _empty_py_result(
            "table", "databricks-sql-connector not installed",
            severity="low",
        )

    try:
        cn = dbsql.connect(
            server_hostname=server_hostname,
            http_path=http_path,
            access_token=token,
        )
    except Exception as e:
        return _empty_py_result(
            "table", f"Databricks SQL connect failed: {e}",
            severity="critical", failed=1,
        )

    try:
        result = _profile_sql_table(
            dialect="databricks", cn=cn,
            schema=schema, table=table,
            dataset_name=ds["dataset_name"],
            catalog=catalog,
        )
        result["asset_kind"] = "table"
        return result
    finally:
        try:
            cn.close()
        except Exception:
            pass


# ======================================================================
#  DISPATCHER + DRIVER
# ======================================================================
def _empty_py_result(asset_kind: str, finding: str, severity: str = "low",
                     failed: int = 0) -> Dict[str, Any]:
    return {
        "score": 0, "confidence": 0, "severity": severity,
        "pii_percentage": 0, "outlier_count": 0,
        "pii_columns": [], "total_rules": 0, "passed": 0, "failed": failed,
        "by_category": {}, "failed_rules": [],
        "findings": [finding],
        "row_count": None, "columns_scanned": 0,
        "asset_kind": asset_kind, "outlier_reasons": [],
        "missing_data_pct": None, "junk_data_pct": None,
        "outlier_pct": None, "tables_summary": [],
    }


def _run_quality_for_dataset(dataset_id: int, rb_ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ds = fetch_one(
        "SELECT d.*, c.type AS connector_type, c.config_json, c.name AS connector_name "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
        (dataset_id,))
    if not ds:
        raise RuntimeError(f"Dataset {dataset_id} not found")

    # Skip Pending datasets (no Tier-2 creds yet)
    cred_status = (ds.get("credential_status") or "Connected")
    if cred_status == "Pending":
        logger.info(
            "Skipping quality check for dataset %s — credential_status=Pending "
            "(user has not yet supplied Tier-2 credentials)", dataset_id,
        )
        return None

    cfg = decrypt_config(ds["config_json"])
    ctype  = ds["connector_type"]
    dstype = (ds.get("dataset_type") or "").lower()

    previous_py = _load_previous_py_result(dataset_id)

    try:
        if ctype in ("mysql", "mssql") and dstype in ("table", "view"):
            py_result = _check_mysql_table(dataset_id, cfg, ds)

        elif ctype == "azure_adf" and dstype == "pipeline":
            py_result = _check_pipeline(ds["connector_id"], cfg, ds, ctype)

        elif ctype == "azure_adf" and dstype == "dataset":
            py_result = _check_adf_dataset(ds["connector_id"], cfg, ds)

        elif ctype == "databricks" and dstype in ("pipeline", "job"):
            py_result = _check_pipeline(ds["connector_id"], cfg, ds, ctype)

        elif ctype == "databricks" and dstype in ("table", "view"):
            py_result = _check_databricks_uc_table(ds)

        else:
            py_result = _empty_py_result(
                dstype or "unknown",
                f"No checker available for {ctype}/{dstype}")
    except Exception as e:
        logger.exception("Quality check raised for dataset %s", dataset_id)
        py_result = _empty_py_result(
            dstype, str(e)[:200], severity="critical", failed=1)
        py_result["failed_rules"] = [{
            "rule": "exception", "category": "integrity",
            "score": 0, "reason": str(e)[:200]
        }]

    llm_report = format_quality_report(
        dataset_metadata={
            "id":             ds["id"],
            "name":           ds["dataset_name"],
            "schema":         ds["schema_name"],
            "type":           ds["dataset_type"],
            "connector_type": ctype,
            "connector_name": ds["connector_name"],
            "source_system_type":  ds.get("source_system_type"),
            "linked_service_name": ds.get("linked_service_name"),
        },
        py_result=py_result,
        rulebook=rb_ctx.get("rulebook"),
        rulebook_chunks=rb_ctx.get("chunks") or [],
        previous_report=previous_py,
    )

    # Extract deep metadata for discovery UI
    row_count = py_result.get("row_count")
    col_count = py_result.get("columns_scanned")
    table_info = py_result.get("table_info") or {}
    
    # If it's a pipeline, we might have activities/runs
    if dstype == "pipeline":
        # row_count for pipeline could be total runs? 
        # But usually we keep row_count for data assets.
        pass

    profiling_json = None
    if table_info:
        profiling_json = safe_json_dumps({
            "tables": [{
                "table_name":   table_info.get("table_name"),
                "schema":       table_info.get("schema"),
                "column_count": table_info.get("column_count"),
                "columns":      table_info.get("columns", []),
                "row_count":    table_info.get("row_count"),
                "primary_keys": table_info.get("primary_keys", []),
                "foreign_keys": table_info.get("foreign_keys", []),
            }]
        })

    execute(
        "UPDATE datasets SET "
        "confidence_score=%s, pii_percentage=%s, outlier_count=%s, "
        "quality_score=%s, last_profiled_at=%s, ai_analysis_json=%s, "
        "row_count=%s, column_count=%s, profiling_json=COALESCE(%s, profiling_json) "
        "WHERE id=%s",
        (
            float(llm_report.get("confidence_score") or py_result["confidence"] * 100),
            float(py_result["pii_percentage"]),
            int(py_result["outlier_count"]),
            float(py_result["score"]),
            datetime.datetime.utcnow(),
            safe_json_dumps({"python": py_result, "llm": llm_report}),
            row_count,
            col_count,
            profiling_json,
            dataset_id,
        ),
    )

    execute(
        "INSERT INTO monitoring_runs (connector_id, dataset_id, run_type, status, "
        "message, metrics_json, finished_at) "
        "VALUES (%s, %s, 'quality', 'success', %s, %s, %s)",
        (ds["connector_id"], dataset_id,
         f"score={py_result['score']:.1f}",
         safe_json_dumps({"python": py_result, "llm": llm_report}),
         datetime.datetime.utcnow()),
    )
    return llm_report


def run_quality_for_dataset(dataset_id: int) -> Optional[Dict[str, Any]]:
    """Run quality check for ONE specific dataset.
    Called by connector_controller after Tier-2 credentials are submitted.
    """
    row = fetch_one(
        "SELECT c.type FROM datasets d JOIN connectors c ON c.id=d.connector_id "
        "WHERE d.id=%s", (dataset_id,),
    )
    if not row:
        raise RuntimeError(f"Dataset {dataset_id} not found")
    rb_ctx = _load_rulebook_context(row["type"])
    return _run_quality_for_dataset(dataset_id, rb_ctx)


def run_quality_for_connector_type(db_connector_type: str,
                                    triggered_by_rulebook_id: int = 0) -> Dict[str, Any]:
    trigger_label = (f"rulebook {triggered_by_rulebook_id}"
                     if triggered_by_rulebook_id
                     else "auto (no rulebook)")
    logger.info("Quality scan triggered by %s for connector_type=%s",
                trigger_label, db_connector_type)

    rb_ctx = _load_rulebook_context(db_connector_type)
    # Only run on datasets the user has provided creds for (or that need none).
    # ADF datasets / Databricks UC tables stuck in Pending are skipped.
    datasets = fetch_all(
        "SELECT d.id "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id "
        "WHERE c.type=%s "
        "  AND COALESCE(d.credential_status, 'Connected') <> 'Pending'",
        (db_connector_type,))

    processed, failed, skipped = 0, 0, 0
    for d in datasets:
        try:
            result = _run_quality_for_dataset(d["id"], rb_ctx)
            if result is None:
                skipped += 1
            else:
                processed += 1
        except Exception:
            logger.exception("Quality check failed for dataset %s", d["id"])
            failed += 1

    summary = {
        "connector_type":   db_connector_type,
        "triggered_by":     trigger_label,
        "rulebook_id":      triggered_by_rulebook_id,
        "datasets_total":   len(datasets),
        "datasets_passed":  processed,
        "datasets_failed":  failed,
        "datasets_skipped": skipped,
        "completed_at":     datetime.datetime.utcnow().isoformat(),
    }
    logger.info("Quality scan complete: %s", summary)
    return summary


# ======================================================================
#  ROUTES — read-only history
# ======================================================================
@router.get("/runs")
def list_runs(limit: int = 50, offset: int = 0, user: dict = Depends(get_current_user)):
    runs = fetch_all(
        "SELECT r.*, c.name AS connector_name, d.dataset_name "
        "FROM monitoring_runs r "
        "LEFT JOIN connectors c ON c.id=r.connector_id "
        "LEFT JOIN datasets d ON d.id=r.dataset_id "
        "ORDER BY r.started_at DESC LIMIT %s OFFSET %s", (limit, offset))
    
    total = fetch_all("SELECT COUNT(*) as count FROM monitoring_runs")[0]['count']
    
    # Calculate global stats with safety
    stats = {
        "total": total,
        "success": 0,
        "failed": 0,
        "pii": 0,
        "low_quality": 0
    }
    try:
        stats["success"] = fetch_all("SELECT COUNT(*) as count FROM datasets WHERE quality_score >= 80")[0]['count']
        stats["failed"] = fetch_all("SELECT COUNT(*) as count FROM datasets WHERE quality_score < 50")[0]['count']
        stats["pii"] = fetch_all("SELECT COUNT(*) as count FROM datasets WHERE pii_percentage > 0")[0]['count']
        stats["low_quality"] = fetch_all("SELECT COUNT(*) as count FROM datasets WHERE quality_score IS NOT NULL AND quality_score < 50")[0]['count']
    except Exception as e:
        logger.warning("Failed to fetch global stats: %s", e)
    
    return {"runs": runs, "total": total, "stats": stats}


@router.get("/dataset-report/{dataset_id}")
def get_dataset_report(dataset_id: int, user: dict = Depends(get_current_user)):
    """Return the latest quality report for one dataset."""
    ds = fetch_one(
        "SELECT id, dataset_name, dataset_type, schema_name, "
        "linked_service_name, source_system_type, credential_status, "
        "confidence_score, pii_percentage, outlier_count, quality_score, "
        "ai_analysis_json, last_profiled_at FROM datasets WHERE id=%s",
        (dataset_id,))
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    report = {}
    if ds.get("ai_analysis_json"):
        try:
            report = json.loads(ds["ai_analysis_json"])
        except Exception:
            report = {}
    return {
        "dataset":       ds,
        "python_result": report.get("python"),
        "llm_report":    report.get("llm"),
    }