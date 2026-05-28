# """Monitoring controller — quality scans only.

# Triggered by either:
#   • connector create (auto, no rulebook needed) — triggered_by_rulebook_id=0
#   • rulebook upload                              — triggered_by_rulebook_id=<rb_id>

# For each dataset of the connector type:
#    → run the right Python deterministic check (table / pipeline / dataset)
#    → write confidence_score, pii_percentage, outlier_count, quality_score
#    → LLM wraps the Python result into the dashboard JSON
# """

# import json
# import datetime
# from typing import Dict, Any, List, Optional

# import pymysql
# import requests

# from fastapi import APIRouter, Depends, HTTPException
# from database.db_connection import fetch_all, fetch_one, execute
# from middleware.auth_middleware import get_current_user
# from utils.common import (
#     logger, decrypt_config,
#     detect_pii_in_column_name, detect_pii_in_samples, safe_json_dumps,
# )
# from utils.ai_helper import format_quality_report
# from utils.vector_helper import search_rule_books
# from utils import quality_engine as qe

# from controllers.rule_book_controller import get_latest_rulebook, collection_name

# router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


# # ======================================================================
# #  MySQL helper
# # ======================================================================
# def _mysql_conn(cfg: Dict[str, Any], database: Optional[str] = None):
#     db = database if database is not None else cfg.get("database")
#     return pymysql.connect(
#         host=cfg.get("host"),
#         port=int(cfg.get("port") or 3306),
#         user=cfg.get("username"),
#         password=cfg.get("password") or "",
#         database=db or None,
#         connect_timeout=10,
#         cursorclass=pymysql.cursors.DictCursor,
#     )


# def _is_non_negative_column(col_name: str, declared_type: str) -> bool:
#     name = (col_name or "").lower()
#     keywords = ("price", "qty", "quantity", "amount", "count", "age", "salary",
#                 "balance", "total", "rate", "duration", "len", "length",
#                 "size", "weight", "score")
#     return any(k in name for k in keywords)


# # ======================================================================
# #  RULEBOOK LOADER (returns empty when no rulebook exists)
# # ======================================================================
# def _load_rulebook_context(connector_type: str) -> Dict[str, Any]:
#     rb = get_latest_rulebook(connector_type)
#     if not rb:
#         logger.info("No rulebook for %s — proceeding with built-in rules only",
#                     connector_type)
#         return {"rulebook": None, "chunks": []}
#     chunks: List[Any] = []
#     try:
#         chunks = search_rule_books(
#             rb["rulebook_content"][:2000], top_k=10,
#             collection=collection_name(connector_type),
#         )
#     except TypeError:
#         try:
#             chunks = search_rule_books(rb["rulebook_content"][:2000], top_k=10)
#         except Exception as e:
#             logger.warning("Rulebook chunk fetch (fallback) failed: %s", e)
#     except Exception as e:
#         logger.warning("Rulebook chunk fetch failed: %s", e)
#     return {"rulebook": rb, "chunks": chunks}


# # ======================================================================
# #  PREVIOUS PYTHON RESULT (for differences computation)
# # ======================================================================
# def _load_previous_py_result(dataset_id: int) -> Optional[dict]:
#     row = fetch_one(
#         "SELECT ai_analysis_json FROM datasets WHERE id=%s", (dataset_id,)
#     )
#     if not row or not row.get("ai_analysis_json"):
#         return None
#     try:
#         return json.loads(row["ai_analysis_json"]).get("python")
#     except Exception:
#         return None


# # ======================================================================
# #  CHECK 1 — MySQL / MSSQL TABLE
# # ======================================================================
# def _check_mysql_table(dataset_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
#     """Deterministic checks for a MySQL table/view."""
#     rules: List[qe.RuleResult] = []
#     schema_name = ds["schema_name"] or cfg.get("database")
#     name = ds["dataset_name"]
#     full = f"`{schema_name}`.`{name}`"

#     total = 0
#     pii_cols: List[str] = []
#     total_outliers = 0
#     total_columns_scanned = 0
#     outlier_reasons: List[Dict[str, Any]] = []
#     columns: List[dict] = []
#     primary_keys: List[str] = []
#     foreign_keys: List[Dict[str, Any]] = []

#     total_null_cells      = 0
#     total_value_samples   = 0
#     total_junk_values     = 0
#     total_numeric_samples = 0

#     cn = _mysql_conn(cfg, database=schema_name)
#     try:
#         with cn.cursor() as cur:
#             cur.execute(f"SELECT COUNT(*) AS c FROM {full}")
#             total = (cur.fetchone() or {}).get("c", 0) or 0
#             if total == 0:
#                 rules.append(qe.RuleResult(
#                     "row_count", "Row count", "completeness",
#                     False, 40.0, ["Table is empty"], {"row_count": 0}))
#             else:
#                 rules.append(qe.RuleResult(
#                     "row_count", "Row count", "completeness",
#                     True, 100.0, [], {"row_count": total}))

#             cur.execute(
#                 "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY "
#                 "FROM information_schema.columns "
#                 "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                 "ORDER BY ORDINAL_POSITION",
#                 (schema_name, name))
#             columns = cur.fetchall() or []
#             total_columns_scanned = len(columns)
#             timestamp_cols: List[str] = []

#             for col in columns:
#                 col_name = col["COLUMN_NAME"]
#                 dtype = (col["DATA_TYPE"] or "").lower()

#                 try:
#                     cur.execute(
#                         f"SELECT SUM(CASE WHEN `{col_name}` IS NULL THEN 1 ELSE 0 END) "
#                         f"AS n FROM {full}")
#                     n_null = (cur.fetchone() or {}).get("n", 0) or 0
#                 except Exception:
#                     n_null = 0
#                 total_null_cells += int(n_null)

#                 try:
#                     cur.execute(f"SELECT COUNT(DISTINCT `{col_name}`) AS d FROM {full}")
#                     distinct = (cur.fetchone() or {}).get("d", 0) or 0
#                 except Exception:
#                     distinct = 0

#                 samples: List[Any] = []
#                 numeric_samples: List[float] = []
#                 try:
#                     cur.execute(
#                         f"SELECT `{col_name}` AS v FROM {full} "
#                         f"WHERE `{col_name}` IS NOT NULL LIMIT 500")
#                     for r in cur.fetchall():
#                         v = r["v"]
#                         samples.append(v)
#                         f = qe._to_float(v)
#                         if f is not None:
#                             numeric_samples.append(f)
#                 except Exception:
#                     pass

#                 total_value_samples   += len(samples)
#                 total_numeric_samples += len(numeric_samples)

#                 rules.append(qe.rule_null_completeness(col_name, n_null, total))

#                 blank_rule = qe.rule_blank_garbage(col_name, samples)
#                 rules.append(blank_rule)
#                 bm = blank_rule.metrics or {}
#                 total_junk_values += int(
#                     bm.get("garbage_count")
#                     or bm.get("blank_count")
#                     or bm.get("invalid_count")
#                     or (0 if blank_rule.passed else max(1, len(samples) // 20))
#                 )

#                 rules.append(qe.rule_duplicate_check(col_name, total, distinct))

#                 misp_rule = qe.rule_misplaced_data(col_name, samples, dtype)
#                 rules.append(misp_rule)
#                 mm = misp_rule.metrics or {}
#                 total_junk_values += int(
#                     mm.get("misplaced_count")
#                     or mm.get("invalid_count")
#                     or (0 if misp_rule.passed else max(1, len(samples) // 20))
#                 )

#                 if numeric_samples:
#                     outlier_rule = qe.rule_outlier_detection(col_name, numeric_samples)
#                     rules.append(outlier_rule)
#                     om = outlier_rule.metrics or {}
#                     n_iqr = om.get("iqr_outliers", 0)
#                     n_z   = om.get("z_outliers", 0)
#                     n_out = max(n_iqr, n_z)
#                     total_outliers += n_out
#                     if n_out > 0:
#                         outlier_reasons.append({
#                             "column":        col_name,
#                             "iqr_outliers":  n_iqr,
#                             "z_outliers":    n_z,
#                             "lower_bound":   om.get("lower_bound"),
#                             "upper_bound":   om.get("upper_bound"),
#                             "sample_size":   len(numeric_samples),
#                             "reason":        f"{n_out} value(s) outside expected range "
#                                              f"[{om.get('lower_bound')}, {om.get('upper_bound')}] "
#                                              f"based on {len(numeric_samples)} sampled values.",
#                         })
#                     if _is_non_negative_column(col_name, dtype):
#                         rules.append(qe.rule_invalid_sign(
#                             col_name, numeric_samples, expect_positive=True))

#                 pii_cat = detect_pii_in_column_name(col_name)
#                 if not pii_cat and samples:
#                     pii_cat = detect_pii_in_samples([str(s) for s in samples[:50]])
#                 if pii_cat:
#                     pii_cols.append(col_name)

#                 if dtype in ("datetime", "timestamp", "date"):
#                     timestamp_cols.append(col_name)

#             primary_keys = [c["COLUMN_NAME"] for c in columns if c["COLUMN_KEY"] == "PRI"]

#             try:
#                 cur.execute(
#                     "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, "
#                     "CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "AND REFERENCED_TABLE_NAME IS NOT NULL",
#                     (schema_name, name))
#                 for fk in cur.fetchall():
#                     foreign_keys.append({
#                         "column":     fk["COLUMN_NAME"],
#                         "ref_table":  fk["REFERENCED_TABLE_NAME"],
#                         "ref_column": fk["REFERENCED_COLUMN_NAME"],
#                         "constraint": fk["CONSTRAINT_NAME"],
#                     })
#             except Exception:
#                 pass

#             if primary_keys and total > 0:
#                 pk_expr = ", ".join([f"`{c}`" for c in primary_keys])
#                 try:
#                     cur.execute(
#                         f"SELECT COUNT(*) - COUNT(DISTINCT {pk_expr}) AS d FROM {full}")
#                     pk_dup = (cur.fetchone() or {}).get("d", 0) or 0
#                     rules.append(qe.rule_pk_uniqueness(",".join(primary_keys), pk_dup))
#                 except Exception:
#                     pass

#             if timestamp_cols:
#                 ts = timestamp_cols[0]
#                 try:
#                     cur.execute(f"SELECT MAX(`{ts}`) AS m FROM {full}")
#                     last = (cur.fetchone() or {}).get("m")
#                     rules.append(qe.rule_freshness(ts, last, threshold_days=7))
#                 except Exception:
#                     pass

#             rules.append(qe.rule_pii_governance(pii_cols))
#     finally:
#         cn.close()

#     aggregated = qe.aggregate(rules)
#     pii_pct = (len(pii_cols) / total_columns_scanned * 100) if total_columns_scanned else 0.0

#     total_cells = total * total_columns_scanned
#     missing_data_pct = (total_null_cells / total_cells * 100) if total_cells else 0.0
#     junk_data_pct    = (total_junk_values / total_value_samples * 100) if total_value_samples else 0.0
#     outlier_pct      = (total_outliers / total_numeric_samples * 100) if total_numeric_samples else 0.0

#     tables_summary = [{
#         "schema":       schema_name,
#         "table_name":   name,
#         "row_count":    total,
#         "column_count": total_columns_scanned,
#         "primary_keys": primary_keys,
#         "foreign_keys": foreign_keys,
#     }]

#     return {
#         "score":           aggregated["final_score"],
#         "confidence":      aggregated["confidence"],
#         "severity":        aggregated["severity"],
#         "pii_percentage":  round(pii_pct, 2),
#         "outlier_count":   total_outliers,
#         "pii_columns":     pii_cols,
#         "total_rules":     aggregated["total_rules"],
#         "passed":          aggregated["passed"],
#         "failed":          aggregated["failed"],
#         "by_category":     aggregated["by_category"],
#         "failed_rules": [
#             {"rule": r["rule_name"], "category": r["category"],
#              "score": r["score"], "reason": "; ".join(r["findings"])}
#             for r in aggregated["rules"] if not r["passed"]
#         ],
#         "findings":        aggregated["findings"],
#         "row_count":       total,
#         "columns_scanned": total_columns_scanned,
#         "asset_kind":      "table",
#         "table_info": {
#             "table_name":   name,
#             "schema":       schema_name,
#             "row_count":    total,
#             "column_count": total_columns_scanned,
#             "columns": [
#                 {
#                     "name":     c["COLUMN_NAME"],
#                     "type":     c["DATA_TYPE"],
#                     "nullable": c["IS_NULLABLE"] == "YES",
#                     "is_pk":    c["COLUMN_KEY"] == "PRI",
#                 }
#                 for c in columns
#             ],
#             "primary_keys": primary_keys,
#             "foreign_keys": foreign_keys,
#         },
#         "outlier_reasons":  outlier_reasons,
#         "missing_data_pct": round(missing_data_pct, 2),
#         "junk_data_pct":    round(junk_data_pct, 2),
#         "outlier_pct":      round(outlier_pct, 2),
#         "tables_summary":   tables_summary,
#     }


# # ======================================================================
# #  CHECK 2 — ADF / DATABRICKS PIPELINE
# # ======================================================================
# def _suggest_pipeline_fix(error_message: str, activity_logs: List[dict]) -> str:
#     msg = (error_message or "").lower()
#     if "permission" in msg or "unauthorized" in msg or "403" in msg or "forbidden" in msg:
#         return ("Verify the service principal has 'Data Factory Contributor' role "
#                 "and the linked service credentials are not expired.")
#     if "timeout" in msg or "timed out" in msg:
#         return ("Increase the activity timeout setting or check the source/sink "
#                 "for slow response. Investigate network latency.")
#     if "not found" in msg or "404" in msg or "doesnotexist" in msg or "blobnotexist" in msg:
#         return ("The referenced source path/blob/table no longer exists. "
#                 "Check upstream job dependency or re-run the producer.")
#     if "credentials" in msg or "authentication" in msg or "401" in msg:
#         return ("Linked service credentials are invalid or expired. "
#                 "Rotate the secret in Key Vault and update the linked service.")
#     if "schema" in msg or "column" in msg or "type mismatch" in msg:
#         return ("Source schema has drifted. Update the dataset definition or "
#                 "enable schema-drift handling in the copy activity.")
#     if "throttl" in msg or "rate limit" in msg or "429" in msg:
#         return ("Downstream system throttled the request. Add retry policy "
#                 "with exponential backoff and reduce parallelism.")
#     if "out of memory" in msg or "outofmemory" in msg or "executor" in msg:
#         return ("Increase the data integration runtime / cluster memory, or "
#                 "partition the source for smaller batches.")
#     if activity_logs:
#         a = activity_logs[0]
#         return (f"Investigate failed activity '{a.get('activity')}' "
#                 f"({a.get('activity_type')}) — see error_message in logs.")
#     return ("Review the run logs and the activity error details, then "
#             "re-trigger after fixing the upstream issue.")


# def _check_pipeline(connector_id: int, cfg: dict, ds: dict, ctype: str) -> Dict[str, Any]:
#     rules: List[qe.RuleResult] = []
#     name = ds["dataset_name"]
#     total_runs = 0
#     failed_runs = 0
#     run_details: List[Dict[str, Any]] = []
#     pipeline_meta: Dict[str, Any] = {
#         "pipeline_id":   None,
#         "pipeline_name": name,
#         "created_time":  None,
#         "last_modified": None,
#         "activities":    [],
#     }

#     try:
#         if ctype == "azure_adf":
#             token_r = requests.post(
#                 f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
#                 data={
#                     "grant_type":    "client_credentials",
#                     "client_id":     cfg["client_id"],
#                     "client_secret": cfg["client_secret"],
#                     "scope":         "https://management.azure.com/.default",
#                 }, timeout=30,
#             )
#             if token_r.status_code != 200:
#                 raise RuntimeError(f"ADF auth failed: {token_r.status_code}")
#             tok = token_r.json()["access_token"]
#             base_url = (
#                 f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
#                 f"/resourceGroups/{cfg['resource_group']}"
#                 f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
#             )
#             headers = {"Authorization": f"Bearer {tok}"}

#             pl_r = requests.get(
#                 f"{base_url}/pipelines/{name}?api-version=2018-06-01",
#                 headers=headers, timeout=30)
#             if pl_r.status_code == 200:
#                 pl = pl_r.json()
#                 pipeline_meta["pipeline_id"]   = pl.get("id")
#                 pipeline_meta["created_time"]  = (pl.get("properties") or {}).get("createdDate") \
#                                                   or pl.get("systemData", {}).get("createdAt")
#                 pipeline_meta["last_modified"] = pl.get("systemData", {}).get("lastModifiedAt")
#                 pipeline_meta["activities"] = [
#                     {"name": a.get("name"), "type": a.get("type")}
#                     for a in (pl.get("properties") or {}).get("activities", [])
#                 ]

#             runs_r = requests.post(
#                 f"{base_url}/queryPipelineRuns?api-version=2018-06-01",
#                 headers=headers,
#                 json={
#                     "lastUpdatedAfter":  (datetime.datetime.utcnow()
#                                           - datetime.timedelta(days=7)).isoformat(),
#                     "lastUpdatedBefore": datetime.datetime.utcnow().isoformat(),
#                     "filters": [{"operand":  "PipelineName",
#                                  "operator": "Equals",
#                                  "values":   [name]}],
#                 }, timeout=20,
#             )
#             if runs_r.status_code == 200:
#                 runs = runs_r.json().get("value", []) or []
#                 total_runs = len(runs)
#                 for r in runs:
#                     status  = r.get("status")
#                     is_fail = status == "Failed"
#                     if is_fail:
#                         failed_runs += 1

#                     activity_logs: List[Dict[str, Any]] = []
#                     if is_fail and r.get("runId"):
#                         try:
#                             act_r = requests.post(
#                                 f"{base_url}/pipelineruns/{r['runId']}/queryActivityruns?api-version=2018-06-01",
#                                 headers=headers,
#                                 json={
#                                     "lastUpdatedAfter":  (datetime.datetime.utcnow()
#                                                           - datetime.timedelta(days=7)).isoformat(),
#                                     "lastUpdatedBefore": datetime.datetime.utcnow().isoformat(),
#                                 }, timeout=30)
#                             if act_r.status_code == 200:
#                                 for a in act_r.json().get("value", []):
#                                     if a.get("status") == "Failed":
#                                         err = (a.get("error") or {}).get("message", "")
#                                         activity_logs.append({
#                                             "activity":      a.get("activityName"),
#                                             "activity_type": a.get("activityType"),
#                                             "status":        a.get("status"),
#                                             "error_message": err[:500],
#                                         })
#                         except Exception:
#                             pass

#                     run_details.append({
#                         "pipeline_id":          r.get("pipelineName"),
#                         "run_id":               r.get("runId"),
#                         "status":               status,
#                         "is_success":           status == "Succeeded",
#                         "failure_reason":       (r.get("message") or "")[:500] if is_fail else "",
#                         "recommended_solution": _suggest_pipeline_fix(r.get("message", ""), activity_logs) if is_fail else "",
#                         "run_start":            r.get("runStart"),
#                         "run_end":              r.get("runEnd"),
#                         "duration_ms":          r.get("durationInMs"),
#                         "duration_minutes":     round((r.get("durationInMs") or 0) / 60000, 2),
#                         "activity_logs":        activity_logs,
#                     })

#         elif ctype == "databricks":
#             base_url = cfg["workspace_url"].rstrip("/")
#             headers = {"Authorization": f"Bearer {cfg['token']}"}
#             jr = requests.get(f"{base_url}/api/2.1/jobs/list?limit=100",
#                               headers=headers, timeout=20)
#             if jr.status_code != 200:
#                 jr = requests.get(f"{base_url}/api/2.0/jobs/list",
#                                   headers=headers, timeout=20)
#             if jr.status_code == 200:
#                 jobs = jr.json().get("jobs", []) or []
#                 match = next((j for j in jobs
#                               if (j.get("settings") or {}).get("name") == name), None)
#                 if match:
#                     job_id = match.get("job_id")
#                     pipeline_meta["pipeline_id"] = job_id
#                     if match.get("created_time"):
#                         pipeline_meta["created_time"] = datetime.datetime.utcfromtimestamp(
#                             match["created_time"] / 1000).isoformat()
#                     pipeline_meta["activities"] = [
#                         {"name": t.get("task_key"), "type": "task"}
#                         for t in (match.get("settings") or {}).get("tasks", [])
#                     ]

#                     runs_r = requests.get(
#                         f"{base_url}/api/2.1/jobs/runs/list?job_id={job_id}&limit=20",
#                         headers=headers, timeout=30)
#                     if runs_r.status_code != 200:
#                         runs_r = requests.get(
#                             f"{base_url}/api/2.0/jobs/runs/list?job_id={job_id}&limit=20",
#                             headers=headers, timeout=30)
#                     if runs_r.status_code == 200:
#                         runs = runs_r.json().get("runs", []) or []
#                         total_runs = len(runs)
#                         for run in runs:
#                             state = run.get("state") or {}
#                             result_state = state.get("result_state") or state.get("life_cycle_state")
#                             is_fail = result_state == "FAILED"
#                             if is_fail:
#                                 failed_runs += 1
#                             start_ms = run.get("start_time") or 0
#                             end_ms   = run.get("end_time") or 0
#                             err_msg  = (state.get("state_message") or "")[:500]
#                             run_details.append({
#                                 "pipeline_id":          job_id,
#                                 "run_id":               run.get("run_id"),
#                                 "status":               result_state,
#                                 "is_success":           result_state == "SUCCESS",
#                                 "failure_reason":       err_msg if is_fail else "",
#                                 "recommended_solution": _suggest_pipeline_fix(err_msg, []) if is_fail else "",
#                                 "run_start":            datetime.datetime.utcfromtimestamp(start_ms / 1000).isoformat() if start_ms else None,
#                                 "run_end":              datetime.datetime.utcfromtimestamp(end_ms / 1000).isoformat() if end_ms else None,
#                                 "duration_ms":          (end_ms - start_ms) if end_ms and start_ms else None,
#                                 "duration_minutes":     round(((end_ms - start_ms) / 60000), 2) if end_ms and start_ms else None,
#                                 "activity_logs":        [],
#                             })

#         if total_runs == 0:
#             rules.append(qe.RuleResult(
#                 f"no_runs_{name}", "No recent runs", "integrity",
#                 True, 85.0, [f"No runs in the last 7 days for {name}"],
#                 {"total_runs": 0}))
#         else:
#             rules.append(qe.rule_pipeline_failure(name, total_runs, failed_runs))

#     except Exception as e:
#         rules.append(qe.RuleResult(
#             f"pipeline_err_{name}", f"Pipeline check {name}", "integrity",
#             False, 30.0, [f"Pipeline check error: {e}"], {}))

#     aggregated = qe.aggregate(rules)
#     return {
#         "score":           aggregated["final_score"],
#         "confidence":      aggregated["confidence"],
#         "severity":        aggregated["severity"],
#         "pii_percentage":  0.0,
#         "outlier_count":   0,
#         "pii_columns":     [],
#         "total_rules":     aggregated["total_rules"],
#         "passed":          aggregated["passed"],
#         "failed":          aggregated["failed"],
#         "by_category":     aggregated["by_category"],
#         "failed_rules": [
#             {"rule": r["rule_name"], "category": r["category"],
#              "score": r["score"], "reason": "; ".join(r["findings"])}
#             for r in aggregated["rules"] if not r["passed"]
#         ],
#         "findings":        aggregated["findings"],
#         "row_count":       None,
#         "columns_scanned": 0,
#         "total_runs":      total_runs,
#         "failed_runs":     failed_runs,
#         "run_details":     run_details,
#         "pipeline_meta":   pipeline_meta,
#         "asset_kind":      "pipeline",
#         "outlier_reasons": [],
#         "missing_data_pct": None,
#         "junk_data_pct":    None,
#         "outlier_pct":      None,
#         "tables_summary":   [],
#     }


# # ======================================================================
# #  CHECK 3 — ADF DATASET (linked service + underlying table)
# # ======================================================================
# def _check_adf_dataset(connector_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
#     rules: List[qe.RuleResult] = []
#     name = ds["dataset_name"]

#     dataset_info = {
#         "type":           None,
#         "linked_service": None,
#         "table_count":    0,
#         "tables":         [],
#     }

#     try:
#         token_r = requests.post(
#             f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
#             data={
#                 "grant_type":    "client_credentials",
#                 "client_id":     cfg["client_id"],
#                 "client_secret": cfg["client_secret"],
#                 "scope":         "https://management.azure.com/.default",
#             }, timeout=30,
#         )
#         if token_r.status_code != 200:
#             raise RuntimeError(f"Token fetch failed: {token_r.status_code}")

#         tok = token_r.json()["access_token"]
#         base_url = (
#             f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
#             f"/resourceGroups/{cfg['resource_group']}"
#             f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
#         )
#         headers = {"Authorization": f"Bearer {tok}"}

#         ds_r = requests.get(
#             f"{base_url}/datasets/{name}?api-version=2018-06-01",
#             headers=headers, timeout=30,
#         )
#         if ds_r.status_code == 200:
#             props = ds_r.json().get("properties", {}) or {}
#             dataset_info["type"] = props.get("type")
#             ls_ref = (props.get("linkedServiceName") or {}).get("referenceName")
#             dataset_info["linked_service"] = ls_ref
#             type_props = props.get("typeProperties") or {}

#             schema_name = type_props.get("schema") or "dbo"
#             table_name  = type_props.get("table") or type_props.get("tableName")

#             if ls_ref and table_name:
#                 ls_meta = _resolve_adf_linked_service(base_url, headers, ls_ref)
#                 tbl = _probe_table_via_linked_service(ls_meta, schema_name, table_name)
#                 if tbl:
#                     dataset_info["tables"].append(tbl)
#                     dataset_info["table_count"] = 1

#         if dataset_info["table_count"] > 0:
#             rules.append(qe.RuleResult(
#                 f"linked_service_reach_{name}", "Linked service reachable",
#                 "integrity", True, 100.0, [],
#                 {"linked_service": dataset_info["linked_service"]}))
#         else:
#             rules.append(qe.RuleResult(
#                 f"linked_service_reach_{name}", "Linked service reachable",
#                 "integrity", False, 50.0,
#                 ["Could not resolve underlying table via linked service"],
#                 {"linked_service": dataset_info["linked_service"]}))

#     except Exception as e:
#         rules.append(qe.RuleResult(
#             f"ds_err_{name}", f"Dataset check {name}", "integrity",
#             False, 30.0, [f"Dataset check error: {e}"], {}))

#     aggregated = qe.aggregate(rules)

#     tables_summary = [
#         {
#             "schema":       t.get("schema"),
#             "table_name":   t.get("table_name"),
#             "row_count":    t.get("row_count"),
#             "column_count": t.get("column_count"),
#             "primary_keys": t.get("primary_keys", []),
#             "foreign_keys": t.get("foreign_keys", []),
#         }
#         for t in dataset_info["tables"]
#     ]

#     return {
#         "score":           aggregated["final_score"],
#         "confidence":      aggregated["confidence"],
#         "severity":        aggregated["severity"],
#         "pii_percentage":  0.0,
#         "outlier_count":   0,
#         "pii_columns":     [],
#         "total_rules":     aggregated["total_rules"],
#         "passed":          aggregated["passed"],
#         "failed":          aggregated["failed"],
#         "by_category":     aggregated["by_category"],
#         "failed_rules": [
#             {"rule": r["rule_name"], "category": r["category"],
#              "score": r["score"], "reason": "; ".join(r["findings"])}
#             for r in aggregated["rules"] if not r["passed"]
#         ],
#         "findings":        aggregated["findings"],
#         "row_count":       sum(t.get("row_count") or 0 for t in dataset_info["tables"]) or None,
#         "columns_scanned": sum(len(t.get("columns") or []) for t in dataset_info["tables"]),
#         "asset_kind":      "dataset",
#         "outlier_reasons": [],
#         "dataset_info":    dataset_info,
#         "run_details":     [],
#         "missing_data_pct": None,
#         "junk_data_pct":    None,
#         "outlier_pct":      None,
#         "tables_summary":   tables_summary,
#     }


# # ======================================================================
# #  ADF LINKED SERVICE + DB PROBES
# # ======================================================================
# def _resolve_adf_linked_service(base_url: str, headers: dict, ls_name: str) -> dict:
#     r = requests.get(
#         f"{base_url}/linkedservices/{ls_name}?api-version=2018-06-01",
#         headers=headers, timeout=30,
#     )
#     if r.status_code != 200:
#         return {}
#     return (r.json().get("properties", {}) or {}).get("typeProperties", {}) or {}


# def _parse_conn_string(cs: str) -> dict:
#     out = {}
#     for part in (cs or "").split(";"):
#         if "=" in part:
#             k, v = part.split("=", 1)
#             out[k.strip().lower()] = v.strip()
#     return out


# def _probe_table_via_linked_service(ls_props: dict, schema: str, table: str) -> Optional[dict]:
#     conn_string = ls_props.get("connectionString")
#     if not conn_string:
#         return None

#     parsed = _parse_conn_string(conn_string)
#     server   = parsed.get("server") or parsed.get("host")
#     database = parsed.get("database") or parsed.get("initial catalog")
#     user     = parsed.get("user id") or parsed.get("user") or parsed.get("uid")
#     password = parsed.get("password") or parsed.get("pwd") or ""

#     if not (server and database):
#         return None

#     cs_lower = (conn_string or "").lower()
#     server_lower = (server or "").lower()
#     if "pgsql" in server_lower or "postgres" in cs_lower:
#         return _probe_postgres_table(server, database, user, password, schema, table)
#     if "mysql" in cs_lower:
#         return _probe_mysql_table(server, database, user, password, schema, table)
#     return _probe_mssql_table(server, database, user, password, schema, table)


# def _probe_mssql_table(server, database, user, password, schema, table) -> Optional[dict]:
#     try:
#         import pymssql
#         cn = pymssql.connect(server=server, user=user, password=password,
#                              database=database, login_timeout=10)
#         try:
#             with cn.cursor(as_dict=True) as cur:
#                 cur.execute(
#                     "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
#                     "       CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION "
#                     "FROM INFORMATION_SCHEMA.COLUMNS "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "ORDER BY ORDINAL_POSITION",
#                     (schema, table))
#                 cols = [
#                     {"name": c["COLUMN_NAME"], "type": c["DATA_TYPE"],
#                      "nullable": c["IS_NULLABLE"] == "YES",
#                      "max_length": c.get("CHARACTER_MAXIMUM_LENGTH")}
#                     for c in cur.fetchall()
#                 ]
#                 cur.execute(f"SELECT COUNT(*) AS c FROM [{schema}].[{table}]")
#                 row_count = cur.fetchone()["c"]
#                 cur.execute(
#                     "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
#                     "WHERE OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + "
#                     "QUOTENAME(CONSTRAINT_NAME)), 'IsPrimaryKey')=1 "
#                     "AND TABLE_SCHEMA=%s AND TABLE_NAME=%s",
#                     (schema, table))
#                 pks = [r["COLUMN_NAME"] for r in cur.fetchall()]
#                 cur.execute(
#                     "SELECT fk.name AS fk_name, c1.name AS column_name, "
#                     "       OBJECT_NAME(fkc.referenced_object_id) AS ref_table, "
#                     "       c2.name AS ref_column "
#                     "FROM sys.foreign_keys fk "
#                     "JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id "
#                     "JOIN sys.columns c1 ON fkc.parent_object_id = c1.object_id "
#                     "                    AND fkc.parent_column_id = c1.column_id "
#                     "JOIN sys.columns c2 ON fkc.referenced_object_id = c2.object_id "
#                     "                    AND fkc.referenced_column_id = c2.column_id "
#                     "WHERE OBJECT_NAME(fk.parent_object_id)=%s",
#                     (table,))
#                 fks = [{"column": r["column_name"], "ref_table": r["ref_table"],
#                         "ref_column": r["ref_column"]} for r in cur.fetchall()]
#         finally:
#             cn.close()
#         return {"schema": schema, "table_name": table, "row_count": row_count,
#                 "column_count": len(cols), "columns": cols,
#                 "primary_keys": pks, "foreign_keys": fks}
#     except Exception as e:
#         logger.warning("MSSQL probe failed: %s", e)
#         return None


# def _probe_postgres_table(server, database, user, password, schema, table) -> Optional[dict]:
#     try:
#         import psycopg2
#         import psycopg2.extras
#         cn = psycopg2.connect(host=server, user=user, password=password,
#                               dbname=database, connect_timeout=10)
#         try:
#             with cn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
#                 cur.execute(
#                     "SELECT column_name, data_type, is_nullable, character_maximum_length "
#                     "FROM information_schema.columns "
#                     "WHERE table_schema=%s AND table_name=%s "
#                     "ORDER BY ordinal_position",
#                     (schema, table))
#                 cols = [
#                     {"name": c["column_name"], "type": c["data_type"],
#                      "nullable": c["is_nullable"] == "YES",
#                      "max_length": c["character_maximum_length"]}
#                     for c in cur.fetchall()
#                 ]
#                 cur.execute(f'SELECT COUNT(*) AS c FROM "{schema}"."{table}"')
#                 row_count = cur.fetchone()["c"]
#                 cur.execute(
#                     "SELECT kc.column_name FROM information_schema.table_constraints tc "
#                     "JOIN information_schema.key_column_usage kc "
#                     "  ON kc.constraint_name = tc.constraint_name "
#                     "WHERE tc.constraint_type='PRIMARY KEY' "
#                     "  AND tc.table_schema=%s AND tc.table_name=%s",
#                     (schema, table))
#                 pks = [r["column_name"] for r in cur.fetchall()]
#                 cur.execute(
#                     "SELECT kcu.column_name, ccu.table_name AS ref_table, "
#                     "       ccu.column_name AS ref_column "
#                     "FROM information_schema.table_constraints tc "
#                     "JOIN information_schema.key_column_usage kcu "
#                     "  ON tc.constraint_name = kcu.constraint_name "
#                     "JOIN information_schema.constraint_column_usage ccu "
#                     "  ON ccu.constraint_name = tc.constraint_name "
#                     "WHERE tc.constraint_type='FOREIGN KEY' "
#                     "  AND tc.table_schema=%s AND tc.table_name=%s",
#                     (schema, table))
#                 fks = [{"column": r["column_name"], "ref_table": r["ref_table"],
#                         "ref_column": r["ref_column"]} for r in cur.fetchall()]
#         finally:
#             cn.close()
#         return {"schema": schema, "table_name": table, "row_count": row_count,
#                 "column_count": len(cols), "columns": cols,
#                 "primary_keys": pks, "foreign_keys": fks}
#     except Exception as e:
#         logger.warning("Postgres probe failed: %s", e)
#         return None


# def _probe_mysql_table(server, database, user, password, schema, table) -> Optional[dict]:
#     try:
#         cn = pymysql.connect(host=server, user=user, password=password,
#                              database=database, connect_timeout=10,
#                              cursorclass=pymysql.cursors.DictCursor)
#         try:
#             with cn.cursor() as cur:
#                 cur.execute(
#                     "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
#                     "       CHARACTER_MAXIMUM_LENGTH, COLUMN_KEY "
#                     "FROM information_schema.columns "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "ORDER BY ORDINAL_POSITION",
#                     (database, table))
#                 rows = cur.fetchall()
#                 cols = [
#                     {"name": c["COLUMN_NAME"], "type": c["DATA_TYPE"],
#                      "nullable": c["IS_NULLABLE"] == "YES",
#                      "max_length": c["CHARACTER_MAXIMUM_LENGTH"]}
#                     for c in rows
#                 ]
#                 pks = [c["COLUMN_NAME"] for c in rows if c.get("COLUMN_KEY") == "PRI"]
#                 cur.execute(f"SELECT COUNT(*) AS c FROM `{database}`.`{table}`")
#                 row_count = cur.fetchone()["c"]
#                 cur.execute(
#                     "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
#                     "FROM information_schema.KEY_COLUMN_USAGE "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "  AND REFERENCED_TABLE_NAME IS NOT NULL",
#                     (database, table))
#                 fks = [{"column": r["COLUMN_NAME"],
#                         "ref_table": r["REFERENCED_TABLE_NAME"],
#                         "ref_column": r["REFERENCED_COLUMN_NAME"]}
#                        for r in cur.fetchall()]
#         finally:
#             cn.close()
#         return {"schema": database, "table_name": table, "row_count": row_count,
#                 "column_count": len(cols), "columns": cols,
#                 "primary_keys": pks, "foreign_keys": fks}
#     except Exception as e:
#         logger.warning("MySQL probe failed: %s", e)
#         return None


# # ======================================================================
# #  DISPATCHER + DRIVER
# # ======================================================================
# def _empty_py_result(asset_kind: str, finding: str, severity: str = "low",
#                      failed: int = 0) -> Dict[str, Any]:
#     return {
#         "score": 0, "confidence": 0, "severity": severity,
#         "pii_percentage": 0, "outlier_count": 0,
#         "pii_columns": [], "total_rules": 0, "passed": 0, "failed": failed,
#         "by_category": {}, "failed_rules": [],
#         "findings": [finding],
#         "row_count": None, "columns_scanned": 0,
#         "asset_kind": asset_kind, "outlier_reasons": [],
#         "missing_data_pct": None, "junk_data_pct": None,
#         "outlier_pct": None, "tables_summary": [],
#     }


# def _run_quality_for_dataset(dataset_id: int, rb_ctx: Dict[str, Any]) -> Dict[str, Any]:
#     """Pick the right Python check, run it, format with LLM, persist."""
#     ds = fetch_one(
#         "SELECT d.*, c.type AS connector_type, c.config_json, c.name AS connector_name "
#         "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
#         (dataset_id,))
#     if not ds:
#         raise RuntimeError(f"Dataset {dataset_id} not found")

#     cfg = decrypt_config(ds["config_json"])
#     ctype  = ds["connector_type"]
#     dstype = (ds.get("dataset_type") or "").lower()

#     previous_py = _load_previous_py_result(dataset_id)

#     try:
#         if ctype in ("mysql", "mssql") and dstype in ("table", "view"):
#             py_result = _check_mysql_table(dataset_id, cfg, ds)
#         elif ctype == "azure_adf" and dstype == "pipeline":
#             py_result = _check_pipeline(ds["connector_id"], cfg, ds, ctype)
#         elif ctype == "azure_adf" and dstype == "dataset":
#             py_result = _check_adf_dataset(ds["connector_id"], cfg, ds)
#         elif ctype == "databricks" and dstype in ("pipeline", "job"):
#             py_result = _check_pipeline(ds["connector_id"], cfg, ds, ctype)
#         else:
#             py_result = _empty_py_result(
#                 dstype, f"No checker available for {ctype}/{dstype}")
#     except Exception as e:
#         logger.exception("Quality check raised for dataset %s", dataset_id)
#         py_result = _empty_py_result(
#             dstype, str(e)[:200], severity="critical", failed=1)
#         py_result["failed_rules"] = [{
#             "rule": "exception", "category": "integrity",
#             "score": 0, "reason": str(e)[:200]
#         }]

#     llm_report = format_quality_report(
#         dataset_metadata={
#             "id":             ds["id"],
#             "name":           ds["dataset_name"],
#             "schema":         ds["schema_name"],
#             "type":           ds["dataset_type"],
#             "connector_type": ctype,
#             "connector_name": ds["connector_name"],
#         },
#         py_result=py_result,
#         rulebook=rb_ctx.get("rulebook"),
#         rulebook_chunks=rb_ctx.get("chunks") or [],
#         previous_report=previous_py,
#     )

#     execute(
#         "UPDATE datasets SET "
#         "confidence_score=%s, pii_percentage=%s, outlier_count=%s, "
#         "quality_score=%s, last_profiled_at=%s, ai_analysis_json=%s "
#         "WHERE id=%s",
#         (
#             float(llm_report.get("confidence_score") or py_result["confidence"] * 100),
#             float(py_result["pii_percentage"]),
#             int(py_result["outlier_count"]),
#             float(py_result["score"]),
#             datetime.datetime.utcnow(),
#             safe_json_dumps({"python": py_result, "llm": llm_report}),
#             dataset_id,
#         ),
#     )

#     execute(
#         "INSERT INTO monitoring_runs (connector_id, dataset_id, run_type, status, "
#         "message, metrics_json, finished_at) "
#         "VALUES (%s, %s, 'quality', 'success', %s, %s, %s)",
#         (ds["connector_id"], dataset_id,
#          f"score={py_result['score']:.1f}",
#          safe_json_dumps({"python": py_result, "llm": llm_report}),
#          datetime.datetime.utcnow()),
#     )
#     return llm_report


# def run_quality_for_connector_type(db_connector_type: str,
#                                     triggered_by_rulebook_id: int = 0) -> Dict[str, Any]:
#     """Top-level entry. triggered_by_rulebook_id=0 → auto-trigger (no rulebook)."""
#     trigger_label = (f"rulebook {triggered_by_rulebook_id}"
#                      if triggered_by_rulebook_id
#                      else "auto (no rulebook)")
#     logger.info("Quality scan triggered by %s for connector_type=%s",
#                 trigger_label, db_connector_type)

#     rb_ctx = _load_rulebook_context(db_connector_type)
#     datasets = fetch_all(
#         "SELECT d.id FROM datasets d JOIN connectors c ON c.id=d.connector_id "
#         "WHERE c.type=%s", (db_connector_type,))

#     processed, failed = 0, 0
#     for d in datasets:
#         try:
#             _run_quality_for_dataset(d["id"], rb_ctx)
#             processed += 1
#         except Exception:
#             logger.exception("Quality check failed for dataset %s", d["id"])
#             failed += 1

#     summary = {
#         "connector_type":  db_connector_type,
#         "triggered_by":    trigger_label,
#         "rulebook_id":     triggered_by_rulebook_id,
#         "datasets_total":  len(datasets),
#         "datasets_passed": processed,
#         "datasets_failed": failed,
#         "completed_at":    datetime.datetime.utcnow().isoformat(),
#     }
#     logger.info("Quality scan complete: %s", summary)
#     return summary


# # ======================================================================
# #  ROUTES — read-only history
# # ======================================================================
# @router.get("/runs")
# def list_runs(limit: int = 50, user: dict = Depends(get_current_user)):
#     return fetch_all(
#         "SELECT r.*, c.name AS connector_name, d.dataset_name "
#         "FROM monitoring_runs r LEFT JOIN connectors c ON c.id=r.connector_id "
#         "LEFT JOIN datasets d ON d.id=r.dataset_id "
#         "ORDER BY r.started_at DESC LIMIT %s", (limit,))


# @router.get("/dataset-report/{dataset_id}")
# def get_dataset_report(dataset_id: int, user: dict = Depends(get_current_user)):
#     """Return the latest quality report for one dataset."""
#     ds = fetch_one(
#         "SELECT id, dataset_name, dataset_type, schema_name, "
#         "confidence_score, pii_percentage, outlier_count, quality_score, "
#         "ai_analysis_json, last_profiled_at FROM datasets WHERE id=%s",
#         (dataset_id,))
#     if not ds:
#         raise HTTPException(status_code=404, detail="Dataset not found")
#     report = {}
#     if ds.get("ai_analysis_json"):
#         try:
#             report = json.loads(ds["ai_analysis_json"])
#         except Exception:
#             report = {}
#     # return {
#     #     "dataset":       ds,
#     #     "python_result": report.get("python"),
#     #     "llm_report":    report.get("llm"),
#     # }
#     """Monitoring controller — quality scans only.

# Triggered by either:
#   • connector create (auto, no rulebook needed) — triggered_by_rulebook_id=0
#   • rulebook upload                              — triggered_by_rulebook_id=<rb_id>

# For each dataset of the connector type:
#    → run the right Python deterministic check (table / pipeline / dataset)
#    → write confidence_score, pii_percentage, outlier_count, quality_score
#    → LLM wraps the Python result into the dashboard JSON
# """

# import json
# import datetime
# from typing import Dict, Any, List, Optional

# import pymysql
# import requests

# from fastapi import APIRouter, Depends, HTTPException
# from database.db_connection import fetch_all, fetch_one, execute
# from middleware.auth_middleware import get_current_user
# from utils.common import (
#     logger, decrypt_config,
#     detect_pii_in_column_name, detect_pii_in_samples, safe_json_dumps,
# )
# from utils.ai_helper import format_quality_report
# from utils.vector_helper import search_rule_books
# from utils import quality_engine as qe

# from controllers.rule_book_controller import get_latest_rulebook, collection_name

# router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


# # ======================================================================
# #  MySQL helper
# # ======================================================================
# def _mysql_conn(cfg: Dict[str, Any], database: Optional[str] = None):
#     db = database if database is not None else cfg.get("database")
#     return pymysql.connect(
#         host=cfg.get("host"),
#         port=int(cfg.get("port") or 3306),
#         user=cfg.get("username"),
#         password=cfg.get("password") or "",
#         database=db or None,
#         connect_timeout=10,
#         cursorclass=pymysql.cursors.DictCursor,
#     )


# def _is_non_negative_column(col_name: str, declared_type: str) -> bool:
#     name = (col_name or "").lower()
#     keywords = ("price", "qty", "quantity", "amount", "count", "age", "salary",
#                 "balance", "total", "rate", "duration", "len", "length",
#                 "size", "weight", "score")
#     return any(k in name for k in keywords)


# # ======================================================================
# #  RULEBOOK LOADER (returns empty when no rulebook exists)
# # ======================================================================
# def _load_rulebook_context(connector_type: str) -> Dict[str, Any]:
#     rb = get_latest_rulebook(connector_type)
#     if not rb:
#         logger.info("No rulebook for %s — proceeding with built-in rules only",
#                     connector_type)
#         return {"rulebook": None, "chunks": []}
#     chunks: List[Any] = []
#     try:
#         chunks = search_rule_books(
#             rb["rulebook_content"][:2000], top_k=10,
#             collection=collection_name(connector_type),
#         )
#     except TypeError:
#         try:
#             chunks = search_rule_books(rb["rulebook_content"][:2000], top_k=10)
#         except Exception as e:
#             logger.warning("Rulebook chunk fetch (fallback) failed: %s", e)
#     except Exception as e:
#         logger.warning("Rulebook chunk fetch failed: %s", e)
#     return {"rulebook": rb, "chunks": chunks}


# # ======================================================================
# #  PREVIOUS PYTHON RESULT (for differences computation)
# # ======================================================================
# def _load_previous_py_result(dataset_id: int) -> Optional[dict]:
#     row = fetch_one(
#         "SELECT ai_analysis_json FROM datasets WHERE id=%s", (dataset_id,)
#     )
#     if not row or not row.get("ai_analysis_json"):
#         return None
#     try:
#         return json.loads(row["ai_analysis_json"]).get("python")
#     except Exception:
#         return None


# # ======================================================================
# #  CHECK 1 — MySQL / MSSQL TABLE
# # ======================================================================
# def _check_mysql_table(dataset_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
#     """Deterministic checks for a MySQL table/view."""
#     rules: List[qe.RuleResult] = []
#     schema_name = ds["schema_name"] or cfg.get("database")
#     name = ds["dataset_name"]
#     full = f"`{schema_name}`.`{name}`"

#     total = 0
#     pii_cols: List[str] = []
#     total_outliers = 0
#     total_columns_scanned = 0
#     outlier_reasons: List[Dict[str, Any]] = []
#     columns: List[dict] = []
#     primary_keys: List[str] = []
#     foreign_keys: List[Dict[str, Any]] = []

#     total_null_cells      = 0
#     total_value_samples   = 0
#     total_junk_values     = 0
#     total_numeric_samples = 0

#     cn = _mysql_conn(cfg, database=schema_name)
#     try:
#         with cn.cursor() as cur:
#             cur.execute(f"SELECT COUNT(*) AS c FROM {full}")
#             total = (cur.fetchone() or {}).get("c", 0) or 0
#             if total == 0:
#                 rules.append(qe.RuleResult(
#                     "row_count", "Row count", "completeness",
#                     False, 40.0, ["Table is empty"], {"row_count": 0}))
#             else:
#                 rules.append(qe.RuleResult(
#                     "row_count", "Row count", "completeness",
#                     True, 100.0, [], {"row_count": total}))

#             cur.execute(
#                 "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY "
#                 "FROM information_schema.columns "
#                 "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                 "ORDER BY ORDINAL_POSITION",
#                 (schema_name, name))
#             columns = cur.fetchall() or []
#             total_columns_scanned = len(columns)
#             timestamp_cols: List[str] = []

#             for col in columns:
#                 col_name = col["COLUMN_NAME"]
#                 dtype = (col["DATA_TYPE"] or "").lower()

#                 try:
#                     cur.execute(
#                         f"SELECT SUM(CASE WHEN `{col_name}` IS NULL THEN 1 ELSE 0 END) "
#                         f"AS n FROM {full}")
#                     n_null = (cur.fetchone() or {}).get("n", 0) or 0
#                 except Exception:
#                     n_null = 0
#                 total_null_cells += int(n_null)

#                 try:
#                     cur.execute(f"SELECT COUNT(DISTINCT `{col_name}`) AS d FROM {full}")
#                     distinct = (cur.fetchone() or {}).get("d", 0) or 0
#                 except Exception:
#                     distinct = 0

#                 samples: List[Any] = []
#                 numeric_samples: List[float] = []
#                 try:
#                     cur.execute(
#                         f"SELECT `{col_name}` AS v FROM {full} "
#                         f"WHERE `{col_name}` IS NOT NULL LIMIT 500")
#                     for r in cur.fetchall():
#                         v = r["v"]
#                         samples.append(v)
#                         f = qe._to_float(v)
#                         if f is not None:
#                             numeric_samples.append(f)
#                 except Exception:
#                     pass

#                 total_value_samples   += len(samples)
#                 total_numeric_samples += len(numeric_samples)

#                 rules.append(qe.rule_null_completeness(col_name, n_null, total))

#                 blank_rule = qe.rule_blank_garbage(col_name, samples)
#                 rules.append(blank_rule)
#                 bm = blank_rule.metrics or {}
#                 total_junk_values += int(
#                     bm.get("garbage_count")
#                     or bm.get("blank_count")
#                     or bm.get("invalid_count")
#                     or (0 if blank_rule.passed else max(1, len(samples) // 20))
#                 )

#                 rules.append(qe.rule_duplicate_check(col_name, total, distinct))

#                 misp_rule = qe.rule_misplaced_data(col_name, samples, dtype)
#                 rules.append(misp_rule)
#                 mm = misp_rule.metrics or {}
#                 total_junk_values += int(
#                     mm.get("misplaced_count")
#                     or mm.get("invalid_count")
#                     or (0 if misp_rule.passed else max(1, len(samples) // 20))
#                 )

#                 if numeric_samples:
#                     outlier_rule = qe.rule_outlier_detection(col_name, numeric_samples)
#                     rules.append(outlier_rule)
#                     om = outlier_rule.metrics or {}
#                     n_iqr = om.get("iqr_outliers", 0)
#                     n_z   = om.get("z_outliers", 0)
#                     n_out = max(n_iqr, n_z)
#                     total_outliers += n_out
#                     if n_out > 0:
#                         outlier_reasons.append({
#                             "column":        col_name,
#                             "iqr_outliers":  n_iqr,
#                             "z_outliers":    n_z,
#                             "lower_bound":   om.get("lower_bound"),
#                             "upper_bound":   om.get("upper_bound"),
#                             "sample_size":   len(numeric_samples),
#                             "reason":        f"{n_out} value(s) outside expected range "
#                                              f"[{om.get('lower_bound')}, {om.get('upper_bound')}] "
#                                              f"based on {len(numeric_samples)} sampled values.",
#                         })
#                     if _is_non_negative_column(col_name, dtype):
#                         rules.append(qe.rule_invalid_sign(
#                             col_name, numeric_samples, expect_positive=True))

#                 pii_cat = detect_pii_in_column_name(col_name)
#                 if not pii_cat and samples:
#                     pii_cat = detect_pii_in_samples([str(s) for s in samples[:50]])
#                 if pii_cat:
#                     pii_cols.append(col_name)

#                 if dtype in ("datetime", "timestamp", "date"):
#                     timestamp_cols.append(col_name)

#             primary_keys = [c["COLUMN_NAME"] for c in columns if c["COLUMN_KEY"] == "PRI"]

#             try:
#                 cur.execute(
#                     "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, "
#                     "CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "AND REFERENCED_TABLE_NAME IS NOT NULL",
#                     (schema_name, name))
#                 for fk in cur.fetchall():
#                     foreign_keys.append({
#                         "column":     fk["COLUMN_NAME"],
#                         "ref_table":  fk["REFERENCED_TABLE_NAME"],
#                         "ref_column": fk["REFERENCED_COLUMN_NAME"],
#                         "constraint": fk["CONSTRAINT_NAME"],
#                     })
#             except Exception:
#                 pass

#             if primary_keys and total > 0:
#                 pk_expr = ", ".join([f"`{c}`" for c in primary_keys])
#                 try:
#                     cur.execute(
#                         f"SELECT COUNT(*) - COUNT(DISTINCT {pk_expr}) AS d FROM {full}")
#                     pk_dup = (cur.fetchone() or {}).get("d", 0) or 0
#                     rules.append(qe.rule_pk_uniqueness(",".join(primary_keys), pk_dup))
#                 except Exception:
#                     pass

#             if timestamp_cols:
#                 ts = timestamp_cols[0]
#                 try:
#                     cur.execute(f"SELECT MAX(`{ts}`) AS m FROM {full}")
#                     last = (cur.fetchone() or {}).get("m")
#                     rules.append(qe.rule_freshness(ts, last, threshold_days=7))
#                 except Exception:
#                     pass

#             rules.append(qe.rule_pii_governance(pii_cols))
#     finally:
#         cn.close()

#     aggregated = qe.aggregate(rules)
#     pii_pct = (len(pii_cols) / total_columns_scanned * 100) if total_columns_scanned else 0.0

#     total_cells = total * total_columns_scanned
#     missing_data_pct = (total_null_cells / total_cells * 100) if total_cells else 0.0
#     junk_data_pct    = (total_junk_values / total_value_samples * 100) if total_value_samples else 0.0
#     outlier_pct      = (total_outliers / total_numeric_samples * 100) if total_numeric_samples else 0.0

#     tables_summary = [{
#         "schema":       schema_name,
#         "table_name":   name,
#         "row_count":    total,
#         "column_count": total_columns_scanned,
#         "primary_keys": primary_keys,
#         "foreign_keys": foreign_keys,
#     }]

#     return {
#         "score":           aggregated["final_score"],
#         "confidence":      aggregated["confidence"],
#         "severity":        aggregated["severity"],
#         "pii_percentage":  round(pii_pct, 2),
#         "outlier_count":   total_outliers,
#         "pii_columns":     pii_cols,
#         "total_rules":     aggregated["total_rules"],
#         "passed":          aggregated["passed"],
#         "failed":          aggregated["failed"],
#         "by_category":     aggregated["by_category"],
#         "failed_rules": [
#             {"rule": r["rule_name"], "category": r["category"],
#              "score": r["score"], "reason": "; ".join(r["findings"])}
#             for r in aggregated["rules"] if not r["passed"]
#         ],
#         "findings":        aggregated["findings"],
#         "row_count":       total,
#         "columns_scanned": total_columns_scanned,
#         "asset_kind":      "table",
#         "table_info": {
#             "table_name":   name,
#             "schema":       schema_name,
#             "row_count":    total,
#             "column_count": total_columns_scanned,
#             "columns": [
#                 {
#                     "name":     c["COLUMN_NAME"],
#                     "type":     c["DATA_TYPE"],
#                     "nullable": c["IS_NULLABLE"] == "YES",
#                     "is_pk":    c["COLUMN_KEY"] == "PRI",
#                 }
#                 for c in columns
#             ],
#             "primary_keys": primary_keys,
#             "foreign_keys": foreign_keys,
#         },
#         "outlier_reasons":  outlier_reasons,
#         "missing_data_pct": round(missing_data_pct, 2),
#         "junk_data_pct":    round(junk_data_pct, 2),
#         "outlier_pct":      round(outlier_pct, 2),
#         "tables_summary":   tables_summary,
#     }


# # ======================================================================
# #  CHECK 2 — ADF / DATABRICKS PIPELINE
# # ======================================================================
# def _suggest_pipeline_fix(error_message: str, activity_logs: List[dict]) -> str:
#     msg = (error_message or "").lower()
#     if "permission" in msg or "unauthorized" in msg or "403" in msg or "forbidden" in msg:
#         return ("Verify the service principal has 'Data Factory Contributor' role "
#                 "and the linked service credentials are not expired.")
#     if "timeout" in msg or "timed out" in msg:
#         return ("Increase the activity timeout setting or check the source/sink "
#                 "for slow response. Investigate network latency.")
#     if "not found" in msg or "404" in msg or "doesnotexist" in msg or "blobnotexist" in msg:
#         return ("The referenced source path/blob/table no longer exists. "
#                 "Check upstream job dependency or re-run the producer.")
#     if "credentials" in msg or "authentication" in msg or "401" in msg:
#         return ("Linked service credentials are invalid or expired. "
#                 "Rotate the secret in Key Vault and update the linked service.")
#     if "schema" in msg or "column" in msg or "type mismatch" in msg:
#         return ("Source schema has drifted. Update the dataset definition or "
#                 "enable schema-drift handling in the copy activity.")
#     if "throttl" in msg or "rate limit" in msg or "429" in msg:
#         return ("Downstream system throttled the request. Add retry policy "
#                 "with exponential backoff and reduce parallelism.")
#     if "out of memory" in msg or "outofmemory" in msg or "executor" in msg:
#         return ("Increase the data integration runtime / cluster memory, or "
#                 "partition the source for smaller batches.")
#     if activity_logs:
#         a = activity_logs[0]
#         return (f"Investigate failed activity '{a.get('activity')}' "
#                 f"({a.get('activity_type')}) — see error_message in logs.")
#     return ("Review the run logs and the activity error details, then "
#             "re-trigger after fixing the upstream issue.")


# def _check_pipeline(connector_id: int, cfg: dict, ds: dict, ctype: str) -> Dict[str, Any]:
#     rules: List[qe.RuleResult] = []
#     name = ds["dataset_name"]
#     total_runs = 0
#     failed_runs = 0
#     run_details: List[Dict[str, Any]] = []
#     pipeline_meta: Dict[str, Any] = {
#         "pipeline_id":   None,
#         "pipeline_name": name,
#         "created_time":  None,
#         "last_modified": None,
#         "activities":    [],
#     }

#     try:
#         if ctype == "azure_adf":
#             token_r = requests.post(
#                 f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
#                 data={
#                     "grant_type":    "client_credentials",
#                     "client_id":     cfg["client_id"],
#                     "client_secret": cfg["client_secret"],
#                     "scope":         "https://management.azure.com/.default",
#                 }, timeout=30,
#             )
#             if token_r.status_code != 200:
#                 raise RuntimeError(f"ADF auth failed: {token_r.status_code}")
#             tok = token_r.json()["access_token"]
#             base_url = (
#                 f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
#                 f"/resourceGroups/{cfg['resource_group']}"
#                 f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
#             )
#             headers = {"Authorization": f"Bearer {tok}"}

#             pl_r = requests.get(
#                 f"{base_url}/pipelines/{name}?api-version=2018-06-01",
#                 headers=headers, timeout=30)
#             if pl_r.status_code == 200:
#                 pl = pl_r.json()
#                 pipeline_meta["pipeline_id"]   = pl.get("id")
#                 pipeline_meta["created_time"]  = (pl.get("properties") or {}).get("createdDate") \
#                                                   or pl.get("systemData", {}).get("createdAt")
#                 pipeline_meta["last_modified"] = pl.get("systemData", {}).get("lastModifiedAt")
#                 pipeline_meta["activities"] = [
#                     {"name": a.get("name"), "type": a.get("type")}
#                     for a in (pl.get("properties") or {}).get("activities", [])
#                 ]

#             runs_r = requests.post(
#                 f"{base_url}/queryPipelineRuns?api-version=2018-06-01",
#                 headers=headers,
#                 json={
#                     "lastUpdatedAfter":  (datetime.datetime.utcnow()
#                                           - datetime.timedelta(days=7)).isoformat(),
#                     "lastUpdatedBefore": datetime.datetime.utcnow().isoformat(),
#                     "filters": [{"operand":  "PipelineName",
#                                  "operator": "Equals",
#                                  "values":   [name]}],
#                 }, timeout=20,
#             )
#             if runs_r.status_code == 200:
#                 runs = runs_r.json().get("value", []) or []
#                 total_runs = len(runs)
#                 for r in runs:
#                     status  = r.get("status")
#                     is_fail = status == "Failed"
#                     if is_fail:
#                         failed_runs += 1

#                     activity_logs: List[Dict[str, Any]] = []
#                     if is_fail and r.get("runId"):
#                         try:
#                             act_r = requests.post(
#                                 f"{base_url}/pipelineruns/{r['runId']}/queryActivityruns?api-version=2018-06-01",
#                                 headers=headers,
#                                 json={
#                                     "lastUpdatedAfter":  (datetime.datetime.utcnow()
#                                                           - datetime.timedelta(days=7)).isoformat(),
#                                     "lastUpdatedBefore": datetime.datetime.utcnow().isoformat(),
#                                 }, timeout=30)
#                             if act_r.status_code == 200:
#                                 for a in act_r.json().get("value", []):
#                                     if a.get("status") == "Failed":
#                                         err = (a.get("error") or {}).get("message", "")
#                                         activity_logs.append({
#                                             "activity":      a.get("activityName"),
#                                             "activity_type": a.get("activityType"),
#                                             "status":        a.get("status"),
#                                             "error_message": err[:500],
#                                         })
#                         except Exception:
#                             pass

#                     run_details.append({
#                         "pipeline_id":          r.get("pipelineName"),
#                         "run_id":               r.get("runId"),
#                         "status":               status,
#                         "is_success":           status == "Succeeded",
#                         "failure_reason":       (r.get("message") or "")[:500] if is_fail else "",
#                         "recommended_solution": _suggest_pipeline_fix(r.get("message", ""), activity_logs) if is_fail else "",
#                         "run_start":            r.get("runStart"),
#                         "run_end":              r.get("runEnd"),
#                         "duration_ms":          r.get("durationInMs"),
#                         "duration_minutes":     round((r.get("durationInMs") or 0) / 60000, 2),
#                         "activity_logs":        activity_logs,
#                     })

#         elif ctype == "databricks":
#             base_url = cfg["workspace_url"].rstrip("/")
#             headers = {"Authorization": f"Bearer {cfg['token']}"}
#             jr = requests.get(f"{base_url}/api/2.1/jobs/list?limit=100",
#                               headers=headers, timeout=20)
#             if jr.status_code != 200:
#                 jr = requests.get(f"{base_url}/api/2.0/jobs/list",
#                                   headers=headers, timeout=20)
#             if jr.status_code == 200:
#                 jobs = jr.json().get("jobs", []) or []
#                 match = next((j for j in jobs
#                               if (j.get("settings") or {}).get("name") == name), None)
#                 if match:
#                     job_id = match.get("job_id")
#                     pipeline_meta["pipeline_id"] = job_id
#                     if match.get("created_time"):
#                         pipeline_meta["created_time"] = datetime.datetime.utcfromtimestamp(
#                             match["created_time"] / 1000).isoformat()
#                     pipeline_meta["activities"] = [
#                         {"name": t.get("task_key"), "type": "task"}
#                         for t in (match.get("settings") or {}).get("tasks", [])
#                     ]

#                     runs_r = requests.get(
#                         f"{base_url}/api/2.1/jobs/runs/list?job_id={job_id}&limit=20",
#                         headers=headers, timeout=30)
#                     if runs_r.status_code != 200:
#                         runs_r = requests.get(
#                             f"{base_url}/api/2.0/jobs/runs/list?job_id={job_id}&limit=20",
#                             headers=headers, timeout=30)
#                     if runs_r.status_code == 200:
#                         runs = runs_r.json().get("runs", []) or []
#                         total_runs = len(runs)
#                         for run in runs:
#                             state = run.get("state") or {}
#                             result_state = state.get("result_state") or state.get("life_cycle_state")
#                             is_fail = result_state == "FAILED"
#                             if is_fail:
#                                 failed_runs += 1
#                             start_ms = run.get("start_time") or 0
#                             end_ms   = run.get("end_time") or 0
#                             err_msg  = (state.get("state_message") or "")[:500]
#                             run_details.append({
#                                 "pipeline_id":          job_id,
#                                 "run_id":               run.get("run_id"),
#                                 "status":               result_state,
#                                 "is_success":           result_state == "SUCCESS",
#                                 "failure_reason":       err_msg if is_fail else "",
#                                 "recommended_solution": _suggest_pipeline_fix(err_msg, []) if is_fail else "",
#                                 "run_start":            datetime.datetime.utcfromtimestamp(start_ms / 1000).isoformat() if start_ms else None,
#                                 "run_end":              datetime.datetime.utcfromtimestamp(end_ms / 1000).isoformat() if end_ms else None,
#                                 "duration_ms":          (end_ms - start_ms) if end_ms and start_ms else None,
#                                 "duration_minutes":     round(((end_ms - start_ms) / 60000), 2) if end_ms and start_ms else None,
#                                 "activity_logs":        [],
#                             })

#         if total_runs == 0:
#             rules.append(qe.RuleResult(
#                 f"no_runs_{name}", "No recent runs", "integrity",
#                 True, 85.0, [f"No runs in the last 7 days for {name}"],
#                 {"total_runs": 0}))
#         else:
#             rules.append(qe.rule_pipeline_failure(name, total_runs, failed_runs))

#     except Exception as e:
#         rules.append(qe.RuleResult(
#             f"pipeline_err_{name}", f"Pipeline check {name}", "integrity",
#             False, 30.0, [f"Pipeline check error: {e}"], {}))

#     aggregated = qe.aggregate(rules)
#     return {
#         "score":           aggregated["final_score"],
#         "confidence":      aggregated["confidence"],
#         "severity":        aggregated["severity"],
#         "pii_percentage":  0.0,
#         "outlier_count":   0,
#         "pii_columns":     [],
#         "total_rules":     aggregated["total_rules"],
#         "passed":          aggregated["passed"],
#         "failed":          aggregated["failed"],
#         "by_category":     aggregated["by_category"],
#         "failed_rules": [
#             {"rule": r["rule_name"], "category": r["category"],
#              "score": r["score"], "reason": "; ".join(r["findings"])}
#             for r in aggregated["rules"] if not r["passed"]
#         ],
#         "findings":        aggregated["findings"],
#         "row_count":       None,
#         "columns_scanned": 0,
#         "total_runs":      total_runs,
#         "failed_runs":     failed_runs,
#         "run_details":     run_details,
#         "pipeline_meta":   pipeline_meta,
#         "asset_kind":      "pipeline",
#         "outlier_reasons": [],
#         "missing_data_pct": None,
#         "junk_data_pct":    None,
#         "outlier_pct":      None,
#         "tables_summary":   [],
#     }


# # ======================================================================
# #  CHECK 3 — ADF DATASET (linked service + underlying table)
# # ======================================================================
# def _check_adf_dataset(connector_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
#     rules: List[qe.RuleResult] = []
#     name = ds["dataset_name"]

#     dataset_info = {
#         "type":           None,
#         "linked_service": None,
#         "table_count":    0,
#         "tables":         [],
#     }

#     try:
#         token_r = requests.post(
#             f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/token",
#             data={
#                 "grant_type":    "client_credentials",
#                 "client_id":     cfg["client_id"],
#                 "client_secret": cfg["client_secret"],
#                 "scope":         "https://management.azure.com/.default",
#             }, timeout=30,
#         )
#         if token_r.status_code != 200:
#             raise RuntimeError(f"Token fetch failed: {token_r.status_code}")

#         tok = token_r.json()["access_token"]
#         base_url = (
#             f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
#             f"/resourceGroups/{cfg['resource_group']}"
#             f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
#         )
#         headers = {"Authorization": f"Bearer {tok}"}

#         ds_r = requests.get(
#             f"{base_url}/datasets/{name}?api-version=2018-06-01",
#             headers=headers, timeout=30,
#         )
#         if ds_r.status_code == 200:
#             props = ds_r.json().get("properties", {}) or {}
#             dataset_info["type"] = props.get("type")
#             ls_ref = (props.get("linkedServiceName") or {}).get("referenceName")
#             dataset_info["linked_service"] = ls_ref
#             type_props = props.get("typeProperties") or {}

#             schema_name = type_props.get("schema") or "dbo"
#             table_name  = type_props.get("table") or type_props.get("tableName")

#             if ls_ref and table_name:
#                 ls_meta = _resolve_adf_linked_service(base_url, headers, ls_ref)
#                 tbl = _probe_table_via_linked_service(ls_meta, schema_name, table_name)
#                 if tbl:
#                     dataset_info["tables"].append(tbl)
#                     dataset_info["table_count"] = 1

#         if dataset_info["table_count"] > 0:
#             rules.append(qe.RuleResult(
#                 f"linked_service_reach_{name}", "Linked service reachable",
#                 "integrity", True, 100.0, [],
#                 {"linked_service": dataset_info["linked_service"]}))
#         else:
#             rules.append(qe.RuleResult(
#                 f"linked_service_reach_{name}", "Linked service reachable",
#                 "integrity", False, 50.0,
#                 ["Could not resolve underlying table via linked service"],
#                 {"linked_service": dataset_info["linked_service"]}))

#     except Exception as e:
#         rules.append(qe.RuleResult(
#             f"ds_err_{name}", f"Dataset check {name}", "integrity",
#             False, 30.0, [f"Dataset check error: {e}"], {}))

#     aggregated = qe.aggregate(rules)

#     tables_summary = [
#         {
#             "schema":       t.get("schema"),
#             "table_name":   t.get("table_name"),
#             "row_count":    t.get("row_count"),
#             "column_count": t.get("column_count"),
#             "primary_keys": t.get("primary_keys", []),
#             "foreign_keys": t.get("foreign_keys", []),
#         }
#         for t in dataset_info["tables"]
#     ]

#     return {
#         "score":           aggregated["final_score"],
#         "confidence":      aggregated["confidence"],
#         "severity":        aggregated["severity"],
#         "pii_percentage":  0.0,
#         "outlier_count":   0,
#         "pii_columns":     [],
#         "total_rules":     aggregated["total_rules"],
#         "passed":          aggregated["passed"],
#         "failed":          aggregated["failed"],
#         "by_category":     aggregated["by_category"],
#         "failed_rules": [
#             {"rule": r["rule_name"], "category": r["category"],
#              "score": r["score"], "reason": "; ".join(r["findings"])}
#             for r in aggregated["rules"] if not r["passed"]
#         ],
#         "findings":        aggregated["findings"],
#         "row_count":       sum(t.get("row_count") or 0 for t in dataset_info["tables"]) or None,
#         "columns_scanned": sum(len(t.get("columns") or []) for t in dataset_info["tables"]),
#         "asset_kind":      "dataset",
#         "outlier_reasons": [],
#         "dataset_info":    dataset_info,
#         "run_details":     [],
#         "missing_data_pct": None,
#         "junk_data_pct":    None,
#         "outlier_pct":      None,
#         "tables_summary":   tables_summary,
#     }


# # ======================================================================
# #  ADF LINKED SERVICE + DB PROBES
# # ======================================================================
# def _resolve_adf_linked_service(base_url: str, headers: dict, ls_name: str) -> dict:
#     r = requests.get(
#         f"{base_url}/linkedservices/{ls_name}?api-version=2018-06-01",
#         headers=headers, timeout=30,
#     )
#     if r.status_code != 200:
#         return {}
#     return (r.json().get("properties", {}) or {}).get("typeProperties", {}) or {}


# def _parse_conn_string(cs: str) -> dict:
#     out = {}
#     for part in (cs or "").split(";"):
#         if "=" in part:
#             k, v = part.split("=", 1)
#             out[k.strip().lower()] = v.strip()
#     return out


# def _probe_table_via_linked_service(ls_props: dict, schema: str, table: str) -> Optional[dict]:
#     conn_string = ls_props.get("connectionString")
#     if not conn_string:
#         return None

#     parsed = _parse_conn_string(conn_string)
#     server   = parsed.get("server") or parsed.get("host")
#     database = parsed.get("database") or parsed.get("initial catalog")
#     user     = parsed.get("user id") or parsed.get("user") or parsed.get("uid")
#     password = parsed.get("password") or parsed.get("pwd") or ""

#     if not (server and database):
#         return None

#     cs_lower = (conn_string or "").lower()
#     server_lower = (server or "").lower()
#     if "pgsql" in server_lower or "postgres" in cs_lower:
#         return _probe_postgres_table(server, database, user, password, schema, table)
#     if "mysql" in cs_lower:
#         return _probe_mysql_table(server, database, user, password, schema, table)
#     return _probe_mssql_table(server, database, user, password, schema, table)


# def _probe_mssql_table(server, database, user, password, schema, table) -> Optional[dict]:
#     try:
#         import pymssql
#         cn = pymssql.connect(server=server, user=user, password=password,
#                              database=database, login_timeout=10)
#         try:
#             with cn.cursor(as_dict=True) as cur:
#                 cur.execute(
#                     "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
#                     "       CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION "
#                     "FROM INFORMATION_SCHEMA.COLUMNS "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "ORDER BY ORDINAL_POSITION",
#                     (schema, table))
#                 cols = [
#                     {"name": c["COLUMN_NAME"], "type": c["DATA_TYPE"],
#                      "nullable": c["IS_NULLABLE"] == "YES",
#                      "max_length": c.get("CHARACTER_MAXIMUM_LENGTH")}
#                     for c in cur.fetchall()
#                 ]
#                 cur.execute(f"SELECT COUNT(*) AS c FROM [{schema}].[{table}]")
#                 row_count = cur.fetchone()["c"]
#                 cur.execute(
#                     "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
#                     "WHERE OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + "
#                     "QUOTENAME(CONSTRAINT_NAME)), 'IsPrimaryKey')=1 "
#                     "AND TABLE_SCHEMA=%s AND TABLE_NAME=%s",
#                     (schema, table))
#                 pks = [r["COLUMN_NAME"] for r in cur.fetchall()]
#                 cur.execute(
#                     "SELECT fk.name AS fk_name, c1.name AS column_name, "
#                     "       OBJECT_NAME(fkc.referenced_object_id) AS ref_table, "
#                     "       c2.name AS ref_column "
#                     "FROM sys.foreign_keys fk "
#                     "JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id "
#                     "JOIN sys.columns c1 ON fkc.parent_object_id = c1.object_id "
#                     "                    AND fkc.parent_column_id = c1.column_id "
#                     "JOIN sys.columns c2 ON fkc.referenced_object_id = c2.object_id "
#                     "                    AND fkc.referenced_column_id = c2.column_id "
#                     "WHERE OBJECT_NAME(fk.parent_object_id)=%s",
#                     (table,))
#                 fks = [{"column": r["column_name"], "ref_table": r["ref_table"],
#                         "ref_column": r["ref_column"]} for r in cur.fetchall()]
#         finally:
#             cn.close()
#         return {"schema": schema, "table_name": table, "row_count": row_count,
#                 "column_count": len(cols), "columns": cols,
#                 "primary_keys": pks, "foreign_keys": fks}
#     except Exception as e:
#         logger.warning("MSSQL probe failed: %s", e)
#         return None


# def _probe_postgres_table(server, database, user, password, schema, table) -> Optional[dict]:
#     try:
#         import psycopg2
#         import psycopg2.extras
#         cn = psycopg2.connect(host=server, user=user, password=password,
#                               dbname=database, connect_timeout=10)
#         try:
#             with cn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
#                 cur.execute(
#                     "SELECT column_name, data_type, is_nullable, character_maximum_length "
#                     "FROM information_schema.columns "
#                     "WHERE table_schema=%s AND table_name=%s "
#                     "ORDER BY ordinal_position",
#                     (schema, table))
#                 cols = [
#                     {"name": c["column_name"], "type": c["data_type"],
#                      "nullable": c["is_nullable"] == "YES",
#                      "max_length": c["character_maximum_length"]}
#                     for c in cur.fetchall()
#                 ]
#                 cur.execute(f'SELECT COUNT(*) AS c FROM "{schema}"."{table}"')
#                 row_count = cur.fetchone()["c"]
#                 cur.execute(
#                     "SELECT kc.column_name FROM information_schema.table_constraints tc "
#                     "JOIN information_schema.key_column_usage kc "
#                     "  ON kc.constraint_name = tc.constraint_name "
#                     "WHERE tc.constraint_type='PRIMARY KEY' "
#                     "  AND tc.table_schema=%s AND tc.table_name=%s",
#                     (schema, table))
#                 pks = [r["column_name"] for r in cur.fetchall()]
#                 cur.execute(
#                     "SELECT kcu.column_name, ccu.table_name AS ref_table, "
#                     "       ccu.column_name AS ref_column "
#                     "FROM information_schema.table_constraints tc "
#                     "JOIN information_schema.key_column_usage kcu "
#                     "  ON tc.constraint_name = kcu.constraint_name "
#                     "JOIN information_schema.constraint_column_usage ccu "
#                     "  ON ccu.constraint_name = tc.constraint_name "
#                     "WHERE tc.constraint_type='FOREIGN KEY' "
#                     "  AND tc.table_schema=%s AND tc.table_name=%s",
#                     (schema, table))
#                 fks = [{"column": r["column_name"], "ref_table": r["ref_table"],
#                         "ref_column": r["ref_column"]} for r in cur.fetchall()]
#         finally:
#             cn.close()
#         return {"schema": schema, "table_name": table, "row_count": row_count,
#                 "column_count": len(cols), "columns": cols,
#                 "primary_keys": pks, "foreign_keys": fks}
#     except Exception as e:
#         logger.warning("Postgres probe failed: %s", e)
#         return None


# def _probe_mysql_table(server, database, user, password, schema, table) -> Optional[dict]:
#     try:
#         cn = pymysql.connect(host=server, user=user, password=password,
#                              database=database, connect_timeout=10,
#                              cursorclass=pymysql.cursors.DictCursor)
#         try:
#             with cn.cursor() as cur:
#                 cur.execute(
#                     "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
#                     "       CHARACTER_MAXIMUM_LENGTH, COLUMN_KEY "
#                     "FROM information_schema.columns "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "ORDER BY ORDINAL_POSITION",
#                     (database, table))
#                 rows = cur.fetchall()
#                 cols = [
#                     {"name": c["COLUMN_NAME"], "type": c["DATA_TYPE"],
#                      "nullable": c["IS_NULLABLE"] == "YES",
#                      "max_length": c["CHARACTER_MAXIMUM_LENGTH"]}
#                     for c in rows
#                 ]
#                 pks = [c["COLUMN_NAME"] for c in rows if c.get("COLUMN_KEY") == "PRI"]
#                 cur.execute(f"SELECT COUNT(*) AS c FROM `{database}`.`{table}`")
#                 row_count = cur.fetchone()["c"]
#                 cur.execute(
#                     "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
#                     "FROM information_schema.KEY_COLUMN_USAGE "
#                     "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
#                     "  AND REFERENCED_TABLE_NAME IS NOT NULL",
#                     (database, table))
#                 fks = [{"column": r["COLUMN_NAME"],
#                         "ref_table": r["REFERENCED_TABLE_NAME"],
#                         "ref_column": r["REFERENCED_COLUMN_NAME"]}
#                        for r in cur.fetchall()]
#         finally:
#             cn.close()
#         return {"schema": database, "table_name": table, "row_count": row_count,
#                 "column_count": len(cols), "columns": cols,
#                 "primary_keys": pks, "foreign_keys": fks}
#     except Exception as e:
#         logger.warning("MySQL probe failed: %s", e)
#         return None


# # ======================================================================
# #  DISPATCHER + DRIVER
# # ======================================================================
# def _empty_py_result(asset_kind: str, finding: str, severity: str = "low",
#                      failed: int = 0) -> Dict[str, Any]:
#     return {
#         "score": 0, "confidence": 0, "severity": severity,
#         "pii_percentage": 0, "outlier_count": 0,
#         "pii_columns": [], "total_rules": 0, "passed": 0, "failed": failed,
#         "by_category": {}, "failed_rules": [],
#         "findings": [finding],
#         "row_count": None, "columns_scanned": 0,
#         "asset_kind": asset_kind, "outlier_reasons": [],
#         "missing_data_pct": None, "junk_data_pct": None,
#         "outlier_pct": None, "tables_summary": [],
#     }


# def _run_quality_for_dataset(dataset_id: int, rb_ctx: Dict[str, Any]) -> Dict[str, Any]:
#     """Pick the right Python check, run it, format with LLM, persist."""
#     ds = fetch_one(
#         "SELECT d.*, c.type AS connector_type, c.config_json, c.name AS connector_name "
#         "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
#         (dataset_id,))
#     if not ds:
#         raise RuntimeError(f"Dataset {dataset_id} not found")

#     cfg = decrypt_config(ds["config_json"])
#     ctype  = ds["connector_type"]
#     dstype = (ds.get("dataset_type") or "").lower()

#     previous_py = _load_previous_py_result(dataset_id)

#     try:
#         if ctype in ("mysql", "mssql") and dstype in ("table", "view"):
#             py_result = _check_mysql_table(dataset_id, cfg, ds)
#         elif ctype == "azure_adf" and dstype == "pipeline":
#             py_result = _check_pipeline(ds["connector_id"], cfg, ds, ctype)
#         elif ctype == "azure_adf" and dstype == "dataset":
#             py_result = _check_adf_dataset(ds["connector_id"], cfg, ds)
#         elif ctype == "databricks" and dstype in ("pipeline", "job"):
#             py_result = _check_pipeline(ds["connector_id"], cfg, ds, ctype)
#         else:
#             py_result = _empty_py_result(
#                 dstype, f"No checker available for {ctype}/{dstype}")
#     except Exception as e:
#         logger.exception("Quality check raised for dataset %s", dataset_id)
#         py_result = _empty_py_result(
#             dstype, str(e)[:200], severity="critical", failed=1)
#         py_result["failed_rules"] = [{
#             "rule": "exception", "category": "integrity",
#             "score": 0, "reason": str(e)[:200]
#         }]

#     llm_report = format_quality_report(
#         dataset_metadata={
#             "id":             ds["id"],
#             "name":           ds["dataset_name"],
#             "schema":         ds["schema_name"],
#             "type":           ds["dataset_type"],
#             "connector_type": ctype,
#             "connector_name": ds["connector_name"],
#         },
#         py_result=py_result,
#         rulebook=rb_ctx.get("rulebook"),
#         rulebook_chunks=rb_ctx.get("chunks") or [],
#         previous_report=previous_py,
#     )

#     execute(
#         "UPDATE datasets SET "
#         "confidence_score=%s, pii_percentage=%s, outlier_count=%s, "
#         "quality_score=%s, last_profiled_at=%s, ai_analysis_json=%s "
#         "WHERE id=%s",
#         (
#             float(llm_report.get("confidence_score") or py_result["confidence"] * 100),
#             float(py_result["pii_percentage"]),
#             int(py_result["outlier_count"]),
#             float(py_result["score"]),
#             datetime.datetime.utcnow(),
#             safe_json_dumps({"python": py_result, "llm": llm_report}),
#             dataset_id,
#         ),
#     )

#     execute(
#         "INSERT INTO monitoring_runs (connector_id, dataset_id, run_type, status, "
#         "message, metrics_json, finished_at) "
#         "VALUES (%s, %s, 'quality', 'success', %s, %s, %s)",
#         (ds["connector_id"], dataset_id,
#          f"score={py_result['score']:.1f}",
#          safe_json_dumps({"python": py_result, "llm": llm_report}),
#          datetime.datetime.utcnow()),
#     )
#     return llm_report


# def run_quality_for_connector_type(db_connector_type: str,
#                                     triggered_by_rulebook_id: int = 0) -> Dict[str, Any]:
#     """Top-level entry. triggered_by_rulebook_id=0 → auto-trigger (no rulebook)."""
#     trigger_label = (f"rulebook {triggered_by_rulebook_id}"
#                      if triggered_by_rulebook_id
#                      else "auto (no rulebook)")
#     logger.info("Quality scan triggered by %s for connector_type=%s",
#                 trigger_label, db_connector_type)

#     rb_ctx = _load_rulebook_context(db_connector_type)
#     datasets = fetch_all(
#         "SELECT d.id FROM datasets d JOIN connectors c ON c.id=d.connector_id "
#         "WHERE c.type=%s", (db_connector_type,))

#     processed, failed = 0, 0
#     for d in datasets:
#         try:
#             _run_quality_for_dataset(d["id"], rb_ctx)
#             processed += 1
#         except Exception:
#             logger.exception("Quality check failed for dataset %s", d["id"])
#             failed += 1

#     summary = {
#         "connector_type":  db_connector_type,
#         "triggered_by":    trigger_label,
#         "rulebook_id":     triggered_by_rulebook_id,
#         "datasets_total":  len(datasets),
#         "datasets_passed": processed,
#         "datasets_failed": failed,
#         "completed_at":    datetime.datetime.utcnow().isoformat(),
#     }
#     logger.info("Quality scan complete: %s", summary)
#     return summary


# # ======================================================================
# #  ROUTES — read-only history
# # ======================================================================
# @router.get("/runs")
# def list_runs(limit: int = 50, user: dict = Depends(get_current_user)):
#     return fetch_all(
#         "SELECT r.*, c.name AS connector_name, d.dataset_name "
#         "FROM monitoring_runs r LEFT JOIN connectors c ON c.id=r.connector_id "
#         "LEFT JOIN datasets d ON d.id=r.dataset_id "
#         "ORDER BY r.started_at DESC LIMIT %s", (limit,))


# @router.get("/dataset-report/{dataset_id}")
# def get_dataset_report(dataset_id: int, user: dict = Depends(get_current_user)):
#     """Return the latest quality report for one dataset."""
#     ds = fetch_one(
#         "SELECT id, dataset_name, dataset_type, schema_name, "
#         "confidence_score, pii_percentage, outlier_count, quality_score, "
#         "ai_analysis_json, last_profiled_at FROM datasets WHERE id=%s",
#         (dataset_id,))
#     if not ds:
#         raise HTTPException(status_code=404, detail="Dataset not found")
#     report = {}
#     if ds.get("ai_analysis_json"):
#         try:
#             report = json.loads(ds["ai_analysis_json"])
#         except Exception:
#             report = {}
#     return {
#         "dataset":       ds,
#         "python_result": report.get("python"),
#         "llm_report":    report.get("llm"),
#     }



"""Monitoring controller — quality scans only.

Triggered by either:
  • connector create (auto, no rulebook needed) — triggered_by_rulebook_id=0
  • rulebook upload                              — triggered_by_rulebook_id=<rb_id>

For each dataset of the connector type:
   → run the right Python deterministic check (table / pipeline / dataset)
   → write confidence_score, pii_percentage, outlier_count, quality_score
   → LLM wraps the Python result into the dashboard JSON
"""

import json
import datetime
from typing import Dict, Any, List, Optional

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
#  MySQL helper
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
#  CHECK 1 — MySQL / MSSQL TABLE
# ======================================================================
def _check_mysql_table(dataset_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
    rules: List[qe.RuleResult] = []
    schema_name = ds["schema_name"] or cfg.get("database")
    name = ds["dataset_name"]
    full = f"`{schema_name}`.`{name}`"

    total = 0
    pii_cols: List[str] = []
    total_outliers = 0
    total_columns_scanned = 0
    outlier_reasons: List[Dict[str, Any]] = []
    columns: List[dict] = []
    primary_keys: List[str] = []
    foreign_keys: List[Dict[str, Any]] = []

    total_null_cells      = 0
    total_value_samples   = 0
    total_junk_values     = 0
    total_numeric_samples = 0

    cn = _mysql_conn(cfg, database=schema_name)
    try:
        with cn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM {full}")
            total = (cur.fetchone() or {}).get("c", 0) or 0
            if total == 0:
                rules.append(qe.RuleResult(
                    "row_count", "Row count", "completeness",
                    False, 40.0, ["Table is empty"], {"row_count": 0}))
            else:
                rules.append(qe.RuleResult(
                    "row_count", "Row count", "completeness",
                    True, 100.0, [], {"row_count": total}))

            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY "
                "FROM information_schema.columns "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                "ORDER BY ORDINAL_POSITION",
                (schema_name, name))
            columns = cur.fetchall() or []
            total_columns_scanned = len(columns)
            timestamp_cols: List[str] = []

            for col in columns:
                col_name = col["COLUMN_NAME"]
                dtype = (col["DATA_TYPE"] or "").lower()

                try:
                    cur.execute(
                        f"SELECT SUM(CASE WHEN `{col_name}` IS NULL THEN 1 ELSE 0 END) "
                        f"AS n FROM {full}")
                    n_null = (cur.fetchone() or {}).get("n", 0) or 0
                except Exception:
                    n_null = 0
                total_null_cells += int(n_null)

                try:
                    cur.execute(f"SELECT COUNT(DISTINCT `{col_name}`) AS d FROM {full}")
                    distinct = (cur.fetchone() or {}).get("d", 0) or 0
                except Exception:
                    distinct = 0

                samples: List[Any] = []
                numeric_samples: List[float] = []
                try:
                    cur.execute(
                        f"SELECT `{col_name}` AS v FROM {full} "
                        f"WHERE `{col_name}` IS NOT NULL LIMIT 500")
                    for r in cur.fetchall():
                        v = r["v"]
                        samples.append(v)
                        f = qe._to_float(v)
                        if f is not None:
                            numeric_samples.append(f)
                except Exception:
                    pass

                total_value_samples   += len(samples)
                total_numeric_samples += len(numeric_samples)

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
                            "column":        col_name,
                            "iqr_outliers":  n_iqr,
                            "z_outliers":    n_z,
                            "lower_bound":   om.get("lower_bound"),
                            "upper_bound":   om.get("upper_bound"),
                            "sample_size":   len(numeric_samples),
                            "reason":        f"{n_out} value(s) outside expected range "
                                             f"[{om.get('lower_bound')}, {om.get('upper_bound')}] "
                                             f"based on {len(numeric_samples)} sampled values.",
                        })
                    if _is_non_negative_column(col_name, dtype):
                        rules.append(qe.rule_invalid_sign(
                            col_name, numeric_samples, expect_positive=True))

                pii_cat = detect_pii_in_column_name(col_name)
                if not pii_cat and samples:
                    pii_cat = detect_pii_in_samples([str(s) for s in samples[:50]])
                if pii_cat:
                    pii_cols.append(col_name)

                if dtype in ("datetime", "timestamp", "date"):
                    timestamp_cols.append(col_name)

            primary_keys = [c["COLUMN_NAME"] for c in columns if c["COLUMN_KEY"] == "PRI"]

            try:
                cur.execute(
                    "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, "
                    "CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "AND REFERENCED_TABLE_NAME IS NOT NULL",
                    (schema_name, name))
                for fk in cur.fetchall():
                    foreign_keys.append({
                        "column":     fk["COLUMN_NAME"],
                        "ref_table":  fk["REFERENCED_TABLE_NAME"],
                        "ref_column": fk["REFERENCED_COLUMN_NAME"],
                        "constraint": fk["CONSTRAINT_NAME"],
                    })
            except Exception:
                pass

            if primary_keys and total > 0:
                pk_expr = ", ".join([f"`{c}`" for c in primary_keys])
                try:
                    cur.execute(
                        f"SELECT COUNT(*) - COUNT(DISTINCT {pk_expr}) AS d FROM {full}")
                    pk_dup = (cur.fetchone() or {}).get("d", 0) or 0
                    rules.append(qe.rule_pk_uniqueness(",".join(primary_keys), pk_dup))
                except Exception:
                    pass

            if timestamp_cols:
                ts = timestamp_cols[0]
                try:
                    cur.execute(f"SELECT MAX(`{ts}`) AS m FROM {full}")
                    last = (cur.fetchone() or {}).get("m")
                    rules.append(qe.rule_freshness(ts, last, threshold_days=7))
                except Exception:
                    pass

            rules.append(qe.rule_pii_governance(pii_cols))
    finally:
        cn.close()

    aggregated = qe.aggregate(rules)
    pii_pct = (len(pii_cols) / total_columns_scanned * 100) if total_columns_scanned else 0.0

    total_cells = total * total_columns_scanned
    missing_data_pct = (total_null_cells / total_cells * 100) if total_cells else 0.0
    junk_data_pct    = (total_junk_values / total_value_samples * 100) if total_value_samples else 0.0
    outlier_pct      = (total_outliers / total_numeric_samples * 100) if total_numeric_samples else 0.0

    tables_summary = [{
        "schema":       schema_name,
        "table_name":   name,
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
            "table_name":   name,
            "schema":       schema_name,
            "row_count":    total,
            "column_count": total_columns_scanned,
            "columns": [
                {
                    "name":     c["COLUMN_NAME"],
                    "type":     c["DATA_TYPE"],
                    "nullable": c["IS_NULLABLE"] == "YES",
                    "is_pk":    c["COLUMN_KEY"] == "PRI",
                }
                for c in columns
            ],
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
        },
        "outlier_reasons":  outlier_reasons,
        "missing_data_pct": round(missing_data_pct, 2),
        "junk_data_pct":    round(junk_data_pct, 2),
        "outlier_pct":      round(outlier_pct, 2),
        "tables_summary":   tables_summary,
    }


# ======================================================================
#  CHECK 2 — ADF / DATABRICKS PIPELINE
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
                pipeline_meta["created_time"]  = (pl.get("properties") or {}).get("createdDate") \
                                                  or pl.get("systemData", {}).get("createdAt")
                pipeline_meta["last_modified"] = pl.get("systemData", {}).get("lastModifiedAt")
                # pipeline_meta["activities"] = [
                #     {"name": a.get("name"), "type": a.get("type")}
                #     for a in (pl.get("properties") or {}).get("activities", [])
                # ]
                pipeline_meta["activities"] = []

                for a in (pl.get("properties") or {}).get("activities", []):

                        tp = a.get("typeProperties") or {}

                        pipeline_meta["activities"].append({

                            "name": a.get("name"),
                            "type": a.get("type"),

                            "inputs": a.get("inputs", []),
                            "outputs": a.get("outputs", []),

                            "source": tp.get("source", {}),
                            "sink": tp.get("sink", {}),

                            "translator": tp.get("translator", {}),

                            "sql_reader_query": tp.get("sqlReaderQuery"),

                            "raw_activity": a
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
#  CHECK 3 — ADF DATASET
# ======================================================================
def _check_adf_dataset(connector_id: int, cfg: dict, ds: dict) -> Dict[str, Any]:
    rules: List[qe.RuleResult] = []
    name = ds["dataset_name"]

    dataset_info = {
        "type":           None,
        "linked_service": None,
        "table_count":    0,
        "tables":         [],
    }

    try:
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
            raise RuntimeError(f"Token fetch failed: {token_r.status_code}")

        tok = token_r.json()["access_token"]
        base_url = (
            f"https://management.azure.com/subscriptions/{cfg['subscription_id']}"
            f"/resourceGroups/{cfg['resource_group']}"
            f"/providers/Microsoft.DataFactory/factories/{cfg['factory_name']}"
        )
        headers = {"Authorization": f"Bearer {tok}"}

        ds_r = requests.get(
            f"{base_url}/datasets/{name}?api-version=2018-06-01",
            headers=headers, timeout=30,
        )
        if ds_r.status_code == 200:
            props = ds_r.json().get("properties", {}) or {}
            dataset_info["type"] = props.get("type")
            ls_ref = (props.get("linkedServiceName") or {}).get("referenceName")
            dataset_info["linked_service"] = ls_ref
            type_props = props.get("typeProperties") or {}

            schema_name = type_props.get("schema") or "dbo"
            table_name  = type_props.get("table") or type_props.get("tableName")

            if ls_ref and table_name:
                ls_meta = _resolve_adf_linked_service(base_url, headers, ls_ref, cfg)
                tbl = _probe_table_via_linked_service(ls_meta, schema_name, table_name)
                if tbl:
                    dataset_info["tables"].append(tbl)
                    dataset_info["table_count"] = 1

        if dataset_info["table_count"] > 0:
            rules.append(qe.RuleResult(
                f"linked_service_reach_{name}", "Linked service reachable",
                "integrity", True, 100.0, [],
                {"linked_service": dataset_info["linked_service"]}))
        else:
            rules.append(qe.RuleResult(
                f"linked_service_reach_{name}", "Linked service reachable",
                "integrity", False, 50.0,
                ["Could not resolve underlying table via linked service"],
                {"linked_service": dataset_info["linked_service"]}))

    except Exception as e:
        rules.append(qe.RuleResult(
            f"ds_err_{name}", f"Dataset check {name}", "integrity",
            False, 30.0, [f"Dataset check error: {e}"], {}))

    aggregated = qe.aggregate(rules)

    tables_summary = [
        {
            "schema":       t.get("schema"),
            "table_name":   t.get("table_name"),
            "row_count":    t.get("row_count"),
            "column_count": t.get("column_count"),
            "primary_keys": t.get("primary_keys", []),
            "foreign_keys": t.get("foreign_keys", []),
        }
        for t in dataset_info["tables"]
    ]

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
        "row_count":       sum(t.get("row_count") or 0 for t in dataset_info["tables"]) or None,
        "columns_scanned": sum(len(t.get("columns") or []) for t in dataset_info["tables"]),
        "asset_kind":      "dataset",
        "outlier_reasons": [],
        "dataset_info":    dataset_info,
        "run_details":     [],
        "missing_data_pct": None,
        "junk_data_pct":    None,
        "outlier_pct":      None,
        "tables_summary":   tables_summary,
    }


# ======================================================================
#  ADF LINKED SERVICE + DB PROBES
# ======================================================================
# def _resolve_adf_linked_service(base_url: str, headers: dict, ls_name: str) -> dict:
#     r = requests.get(
#         f"{base_url}/linkedservices/{ls_name}?api-version=2018-06-01",
#         headers=headers, timeout=30,
#     )
#     if r.status_code != 200:
#         return {}
#     return (r.json().get("properties", {}) or {}).get("typeProperties", {}) or {}

# def _resolve_adf_linked_service(base_url: str, headers: dict, ls_name: str) -> dict:
def _resolve_adf_linked_service(base_url: str, headers: dict, ls_name: str, cfg: dict) -> dict:

    r = requests.get(
        f"{base_url}/linkedservices/{ls_name}?api-version=2018-06-01",
        headers=headers,
        timeout=30,
    )

    if r.status_code != 200:
        return {}

    js = r.json() or {}

    props = (js.get("properties") or {})
    tp = (props.get("typeProperties") or {})

    # unwrap SecureString connectionString
    cs = tp.get("connectionString")

    if isinstance(cs, dict):
        tp["connectionString"] = (
            cs.get("value")
            or cs.get("secretName")
            or ""
        )

    # unwrap password SecureString
    pwd = tp.get("password")

    if isinstance(pwd, dict):
        tp["password"] = (
            pwd.get("value")
            or pwd.get("secretName")
            or ""
        )

    logger.info(
        "ADF linked service resolved: %s",
        json.dumps(tp, indent=2)
    )

    # fallback password from config
    if not tp.get("password"):
        tp["password"] = cfg.get("db_password")

    return tp
    
def _parse_conn_string(cs: str) -> dict:
    out = {}
    for part in (cs or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out
def _probe_table_via_linked_service(ls_props: dict, schema: str, table: str) -> Optional[dict]:

    # ------------------------------------------------------------------
    # ADF linked service often DOES NOT expose plain connectionString.
    # So read direct properties first.
    # ------------------------------------------------------------------

    server = (
        ls_props.get("server")
        or ls_props.get("host")
        or ls_props.get("dataSource")
    )

    database = (
        ls_props.get("database")
        or ls_props.get("initialCatalog")
    )

    user = (
        ls_props.get("userName")
        or ls_props.get("username")
        or ls_props.get("user")
        or ls_props.get("uid")
    )

    password = (
        ls_props.get("password")
        or ls_props.get("pwd")
        or ""
    )

    # ------------------------------------------------------------------
    # fallback → connection string parsing
    # ------------------------------------------------------------------

    conn_string = ls_props.get("connectionString")

    if conn_string and isinstance(conn_string, str):

        parsed = _parse_conn_string(conn_string)

        server = (
            server
            or parsed.get("server")
            or parsed.get("host")
        )

        database = (
            database
            or parsed.get("database")
            or parsed.get("initial catalog")
        )

        user = (
            user
            or parsed.get("user id")
            or parsed.get("user")
            or parsed.get("uid")
        )

        password = (
            password
            or parsed.get("password")
            or parsed.get("pwd")
            or ""
        )

    # ------------------------------------------------------------------
    # mandatory validation
    # ------------------------------------------------------------------

    if not (server and database):
        logger.warning(
            "ADF linked service missing server/database: %s",
            ls_props
        )
        return None

    server_lower = str(server).lower()
    ls_lower = str(ls_props).lower()
    cs_lower = str(conn_string).lower() if conn_string else ""

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------

    if (
        "postgres" in server_lower
        or "postgres" in ls_lower
        or "pgsql" in server_lower
        or "postgres" in cs_lower
    ):
        return _probe_postgres_table(
            server,
            database,
            user,
            password,
            schema,
            table
        )

    # ------------------------------------------------------------------
    # MySQL
    # ------------------------------------------------------------------

    if (
        "mysql" in server_lower
        or "mysql" in ls_lower
        or "mysql" in cs_lower
    ):
        return _probe_mysql_table(
            server,
            database,
            user,
            password,
            schema,
            table
        )

    # ------------------------------------------------------------------
    # Default → MSSQL
    # ------------------------------------------------------------------

    return _probe_mssql_table(
        server,
        database,
        user,
        password,
        schema,
        table
    )

# def _probe_table_via_linked_service(ls_props: dict, schema: str, table: str) -> Optional[dict]:
#     conn_string = ls_props.get("connectionString")
#     if not conn_string:
#         return None

#     parsed = _parse_conn_string(conn_string)
#     server   = parsed.get("server") or parsed.get("host")
#     database = parsed.get("database") or parsed.get("initial catalog")
#     user     = parsed.get("user id") or parsed.get("user") or parsed.get("uid")
#     password = parsed.get("password") or parsed.get("pwd") or ""

#     if not (server and database):
#         return None

#     cs_lower = (conn_string or "").lower()
#     server_lower = (server or "").lower()
#     if "pgsql" in server_lower or "postgres" in cs_lower:
#         return _probe_postgres_table(server, database, user, password, schema, table)
#     if "mysql" in cs_lower:
#         return _probe_mysql_table(server, database, user, password, schema, table)
#     return _probe_mssql_table(server, database, user, password, schema, table)


def _probe_mssql_table(server, database, user, password, schema, table) -> Optional[dict]:
    try:
        import pymssql
        cn = pymssql.connect(server=server, user=user, password=password,
                             database=database, login_timeout=10)
        try:
            with cn.cursor(as_dict=True) as cur:
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
                    "       CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION "
                    "FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "ORDER BY ORDINAL_POSITION",
                    (schema, table))
                cols = [
                    {"name": c["COLUMN_NAME"], "type": c["DATA_TYPE"],
                     "nullable": c["IS_NULLABLE"] == "YES",
                     "max_length": c.get("CHARACTER_MAXIMUM_LENGTH")}
                    for c in cur.fetchall()
                ]
                cur.execute(f"SELECT COUNT(*) AS c FROM [{schema}].[{table}]")
                row_count = cur.fetchone()["c"]
                cur.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
                    "WHERE OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + "
                    "QUOTENAME(CONSTRAINT_NAME)), 'IsPrimaryKey')=1 "
                    "AND TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                    (schema, table))
                pks = [r["COLUMN_NAME"] for r in cur.fetchall()]
                cur.execute(
                    "SELECT fk.name AS fk_name, c1.name AS column_name, "
                    "       OBJECT_NAME(fkc.referenced_object_id) AS ref_table, "
                    "       c2.name AS ref_column "
                    "FROM sys.foreign_keys fk "
                    "JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id "
                    "JOIN sys.columns c1 ON fkc.parent_object_id = c1.object_id "
                    "                    AND fkc.parent_column_id = c1.column_id "
                    "JOIN sys.columns c2 ON fkc.referenced_object_id = c2.object_id "
                    "                    AND fkc.referenced_column_id = c2.column_id "
                    "WHERE OBJECT_NAME(fk.parent_object_id)=%s",
                    (table,))
                fks = [{"column": r["column_name"], "ref_table": r["ref_table"],
                        "ref_column": r["ref_column"]} for r in cur.fetchall()]
        finally:
            cn.close()
        return {"schema": schema, "table_name": table, "row_count": row_count,
                "column_count": len(cols), "columns": cols,
                "primary_keys": pks, "foreign_keys": fks}
    except Exception as e:
        logger.warning("MSSQL probe failed: %s", e)
        return None


def _probe_postgres_table(server, database, user, password, schema, table) -> Optional[dict]:
    try:
        import psycopg2
        import psycopg2.extras
        cn = psycopg2.connect(host=server, user=user, password=password,
                              dbname=database,port=5432,sslmode="require", connect_timeout=10)
        try:
            with cn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT column_name, data_type, is_nullable, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_schema=%s AND table_name=%s "
                    "ORDER BY ordinal_position",
                    (schema, table))
                cols = [
                    {"name": c["column_name"], "type": c["data_type"],
                     "nullable": c["is_nullable"] == "YES",
                     "max_length": c["character_maximum_length"]}
                    for c in cur.fetchall()
                ]
                cur.execute(f'SELECT COUNT(*) AS c FROM "{schema}"."{table}"')
                row_count = cur.fetchone()["c"]
                cur.execute(
                    "SELECT kc.column_name FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kc "
                    "  ON kc.constraint_name = tc.constraint_name "
                    "WHERE tc.constraint_type='PRIMARY KEY' "
                    "  AND tc.table_schema=%s AND tc.table_name=%s",
                    (schema, table))
                pks = [r["column_name"] for r in cur.fetchall()]
                cur.execute(
                    "SELECT kcu.column_name, ccu.table_name AS ref_table, "
                    "       ccu.column_name AS ref_column "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON tc.constraint_name = kcu.constraint_name "
                    "JOIN information_schema.constraint_column_usage ccu "
                    "  ON ccu.constraint_name = tc.constraint_name "
                    "WHERE tc.constraint_type='FOREIGN KEY' "
                    "  AND tc.table_schema=%s AND tc.table_name=%s",
                    (schema, table))
                fks = [{"column": r["column_name"], "ref_table": r["ref_table"],
                        "ref_column": r["ref_column"]} for r in cur.fetchall()]
        finally:
            cn.close()
        return {"schema": schema, "table_name": table, "row_count": row_count,
                "column_count": len(cols), "columns": cols,
                "primary_keys": pks, "foreign_keys": fks}
    except Exception as e:
        # logger.warning("Postgres probe failed: %s", e)
        
        logger.warning(
            "Postgres probe failed | server=%s db=%s user=%s schema=%s table=%s err=%s",
            server,
            database,
            user,
            schema,
            table,
            str(e)
        )
        return None


def _probe_mysql_table(server, database, user, password, schema, table) -> Optional[dict]:
    try:
        cn = pymysql.connect(host=server, user=user, password=password,
                             database=database, connect_timeout=10,
                             cursorclass=pymysql.cursors.DictCursor)
        try:
            with cn.cursor() as cur:
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
                    "       CHARACTER_MAXIMUM_LENGTH, COLUMN_KEY "
                    "FROM information_schema.columns "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "ORDER BY ORDINAL_POSITION",
                    (database, table))
                rows = cur.fetchall()
                cols = [
                    {"name": c["COLUMN_NAME"], "type": c["DATA_TYPE"],
                     "nullable": c["IS_NULLABLE"] == "YES",
                     "max_length": c["CHARACTER_MAXIMUM_LENGTH"]}
                    for c in rows
                ]
                pks = [c["COLUMN_NAME"] for c in rows if c.get("COLUMN_KEY") == "PRI"]
                cur.execute(f"SELECT COUNT(*) AS c FROM `{database}`.`{table}`")
                row_count = cur.fetchone()["c"]
                cur.execute(
                    "SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                    "FROM information_schema.KEY_COLUMN_USAGE "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "  AND REFERENCED_TABLE_NAME IS NOT NULL",
                    (database, table))
                fks = [{"column": r["COLUMN_NAME"],
                        "ref_table": r["REFERENCED_TABLE_NAME"],
                        "ref_column": r["REFERENCED_COLUMN_NAME"]}
                       for r in cur.fetchall()]
        finally:
            cn.close()
        return {"schema": database, "table_name": table, "row_count": row_count,
                "column_count": len(cols), "columns": cols,
                "primary_keys": pks, "foreign_keys": fks}
    except Exception as e:
        logger.warning("MySQL probe failed: %s", e)
        return None


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


def _run_quality_for_dataset(dataset_id: int, rb_ctx: Dict[str, Any]) -> Dict[str, Any]:
    ds = fetch_one(
        "SELECT d.*, c.type AS connector_type, c.config_json, c.name AS connector_name "
        "FROM datasets d JOIN connectors c ON c.id=d.connector_id WHERE d.id=%s",
        (dataset_id,))
    if not ds:
        raise RuntimeError(f"Dataset {dataset_id} not found")

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
        else:
            py_result = _empty_py_result(
                dstype, f"No checker available for {ctype}/{dstype}")
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
        },
        py_result=py_result,
        rulebook=rb_ctx.get("rulebook"),
        rulebook_chunks=rb_ctx.get("chunks") or [],
        previous_report=previous_py,
    )

    execute(
        "UPDATE datasets SET "
        "confidence_score=%s, pii_percentage=%s, outlier_count=%s, "
        "quality_score=%s, last_profiled_at=%s, ai_analysis_json=%s "
        "WHERE id=%s",
        (
            float(llm_report.get("confidence_score") or py_result["confidence"] * 100),
            float(py_result["pii_percentage"]),
            int(py_result["outlier_count"]),
            float(py_result["score"]),
            datetime.datetime.utcnow(),
            safe_json_dumps({"python": py_result, "llm": llm_report}),
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


def run_quality_for_connector_type(db_connector_type: str,
                                    triggered_by_rulebook_id: int = 0) -> Dict[str, Any]:
    trigger_label = (f"rulebook {triggered_by_rulebook_id}"
                     if triggered_by_rulebook_id
                     else "auto (no rulebook)")
    logger.info("Quality scan triggered by %s for connector_type=%s",
                trigger_label, db_connector_type)

    rb_ctx = _load_rulebook_context(db_connector_type)
    datasets = fetch_all(
        "SELECT d.id FROM datasets d JOIN connectors c ON c.id=d.connector_id "
        "WHERE c.type=%s", (db_connector_type,))

    processed, failed = 0, 0
    for d in datasets:
        try:
            _run_quality_for_dataset(d["id"], rb_ctx)
            processed += 1
        except Exception:
            logger.exception("Quality check failed for dataset %s", d["id"])
            failed += 1

    summary = {
        "connector_type":  db_connector_type,
        "triggered_by":    trigger_label,
        "rulebook_id":     triggered_by_rulebook_id,
        "datasets_total":  len(datasets),
        "datasets_passed": processed,
        "datasets_failed": failed,
        "completed_at":    datetime.datetime.utcnow().isoformat(),
    }
    logger.info("Quality scan complete: %s", summary)
    return summary


# ======================================================================
#  ROUTES — read-only history
# ======================================================================
@router.get("/runs")
def list_runs(limit: int = 50, user: dict = Depends(get_current_user)):
    return fetch_all(
        "SELECT r.*, c.name AS connector_name, d.dataset_name "
        "FROM monitoring_runs r LEFT JOIN connectors c ON c.id=r.connector_id "
        "LEFT JOIN datasets d ON d.id=r.dataset_id "
        "ORDER BY r.started_at DESC LIMIT %s", (limit,))


@router.get("/dataset-report/{dataset_id}")
def get_dataset_report(dataset_id: int, user: dict = Depends(get_current_user)):
    """Return the latest quality report for one dataset."""
    ds = fetch_one(
        "SELECT id, dataset_name, dataset_type, schema_name, "
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