# """Mistral AI helper — analyzes REAL monitoring data and returns structured
# insights.

# In this version the LLM never produces the *final quality score*. All
# mathematical scoring is done by `utils.quality_engine`. The LLM is used
# purely to write narrative paragraphs grounded strictly in Python-supplied
# data.
# """

# import os
# import json
# import requests
# from typing import Dict, Any, List, Optional
# from dotenv import load_dotenv

# from utils.common import logger

# load_dotenv()

# MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
# MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
# MISTRAL_API_URL = os.getenv(
#     "MISTRAL_API_URL",
#     "https://api.mistral.ai/v1/chat/completions",
# )


# # ----------------------------------------------------------------------
# # Low-level chat helper
# # ----------------------------------------------------------------------
# def _chat(system: str, user: str, timeout: int = 60, max_tokens: int = 1500) -> str:
#     """Send a chat completion to Mistral and return assistant text."""
#     if not MISTRAL_API_KEY:
#         return ""
#     try:
#         resp = requests.post(
#             MISTRAL_API_URL,
#             headers={
#                 "Authorization": f"Bearer {MISTRAL_API_KEY}",
#                 "Content-Type": "application/json",
#             },
#             json={
#                 "model": MISTRAL_MODEL,
#                 "messages": [
#                     {"role": "system", "content": system},
#                     {"role": "user", "content": user},
#                 ],
#                 "temperature": 0.1,
#                 "max_tokens": max_tokens,
#             },
#             timeout=timeout,
#         )
#         if resp.status_code != 200:
#             logger.warning(
#                 "Mistral API non-200: %s %s", resp.status_code, resp.text[:200]
#             )
#             return ""
#         data = resp.json()
#         return (
#             (data.get("choices") or [{}])[0]
#             .get("message", {})
#             .get("content", "")
#             .strip()
#         )
#     except Exception as e:
#         logger.error("Mistral call failed: %s", e)
#         return ""


# def _parse_json_block(text: str) -> Dict[str, Any]:
#     """Extract a JSON object from model output (tolerant)."""
#     if not text:
#         return {}
#     text = text.strip()
#     if text.startswith("```"):
#         parts = text.split("```")
#         for p in parts:
#             p = p.strip()
#             if p.startswith("{") or p.startswith("json"):
#                 if p.startswith("json"):
#                     p = p[4:].strip()
#                 try:
#                     return json.loads(p)
#                 except Exception:
#                     continue
#     try:
#         return json.loads(text)
#     except Exception:
#         start, end = text.find("{"), text.rfind("}")
#         if start >= 0 and end > start:
#             try:
#                 return json.loads(text[start : end + 1])
#             except Exception:
#                 return {}
#         return {}


# # ----------------------------------------------------------------------
# # Generic event analyser (used elsewhere — kept as-is for compatibility)
# # ----------------------------------------------------------------------
# SYSTEM_PROMPT = (
#     "You are an enterprise data observability assistant. You analyse REAL "
#     "monitoring metrics provided in the user message. Never invent datasets, "
#     "columns, numbers, or events. If a field is missing, omit it. Respond ONLY "
#     'with a JSON object with keys: "summary", "root_cause", "impact", '
#     '"recommendation". Each value must be a short paragraph (<= 60 words).'
# )


# def analyze_issue(payload: Dict[str, Any]) -> Dict[str, str]:
#     """Analyse a generic monitoring event."""
#     if not MISTRAL_API_KEY:
#         return {
#             "summary": "AI disabled (no MISTRAL_API_KEY configured).",
#             "root_cause": "",
#             "impact": "",
#             "recommendation": "",
#         }
#     user_msg = (
#         "Analyse the following monitoring event and respond with JSON only.\n\n"
#         f"EVENT JSON:\n{json.dumps(payload, default=str)[:6000]}"
#     )
#     text = _chat(SYSTEM_PROMPT, user_msg)
#     parsed = _parse_json_block(text)
#     return {
#         "summary":        parsed.get("summary", "")[:1000],
#         "root_cause":     parsed.get("root_cause", "")[:1000],
#         "impact":         parsed.get("impact", "")[:1000],
#         "recommendation": parsed.get("recommendation", "")[:1000],
#     }


# def summarize_monitoring_snapshot(snapshot: Dict[str, Any]) -> str:
#     """Plain-text rollup summary of overall platform health."""
#     if not MISTRAL_API_KEY:
#         return ""
#     sys = (
#         "You write short, factual executive summaries of data platform health. "
#         "Use only the metrics in the user message. <= 120 words. Plain prose."
#     )
#     user = "METRICS:\n" + json.dumps(snapshot, default=str)[:5000]
#     return _chat(sys, user)


# # ----------------------------------------------------------------------
# # Deterministic-only fallbacks
# # ----------------------------------------------------------------------
# def _fallback_recommendations(det: Dict[str, Any]) -> List[str]:
#     recs: List[str] = []
#     bc = det.get("by_category", {})
#     for cat, info in bc.items():
#         if info.get("failed", 0) > 0 and info.get("score", 100) < 85:
#             recs.append(
#                 f"Investigate {info['failed']} failed {cat} check(s) — "
#                 f"category score {info.get('score', 0)}/100."
#             )
#     if not recs:
#         recs.append("No critical actions required — dataset is within quality thresholds.")
#     return recs[:6]


# def _format_rulebook_chunks(chunks: List[Any]) -> List[str]:
#     """Normalize ChromaDB search hits into plain strings for the LLM prompt."""
#     if not chunks:
#         return []
#     out: List[str] = []
#     for c in chunks[:6]:
#         if isinstance(c, str):
#             out.append(c[:600])
#         elif isinstance(c, dict):
#             text = (c.get("document") or c.get("text") or c.get("content") or "")
#             if text:
#                 out.append(str(text)[:600])
#         else:
#             out.append(str(c)[:600])
#     return out


# def _compute_differences(
#     current: Dict[str, Any],
#     previous: Optional[Dict[str, Any]],
# ) -> Dict[str, Any]:
#     """Used internally only — feeds the LLM prompt and fallback paragraph."""
#     if not previous:
#         return {
#             "is_first_run":       True,
#             "score_delta":        None,
#             "confidence_delta":   None,
#             "pii_delta":          None,
#             "outlier_delta":      None,
#             "rules_failed_delta": None,
#             "new_failed_rules":   [],
#             "resolved_rules":     [],
#         }
#     cur_score   = float(current.get("score", 0))
#     cur_conf    = float(current.get("confidence", 0)) * 100
#     cur_pii     = float(current.get("pii_percentage", 0))
#     cur_out     = int(current.get("outlier_count", 0))
#     cur_failed  = int(current.get("failed", 0))
#     prev_score  = float(previous.get("score", 0))
#     prev_conf   = float(previous.get("confidence", 0)) * 100
#     prev_pii    = float(previous.get("pii_percentage", 0))
#     prev_out    = int(previous.get("outlier_count", 0))
#     prev_failed = int(previous.get("failed", 0))
#     cur_rule_ids  = {r.get("rule") for r in (current.get("failed_rules") or [])}
#     prev_rule_ids = {r.get("rule") for r in (previous.get("failed_rules") or [])}
#     return {
#         "is_first_run":       False,
#         "score_delta":        round(cur_score - prev_score, 2),
#         "confidence_delta":   round(cur_conf - prev_conf, 2),
#         "pii_delta":          round(cur_pii - prev_pii, 2),
#         "outlier_delta":      cur_out - prev_out,
#         "rules_failed_delta": cur_failed - prev_failed,
#         "new_failed_rules":   sorted(cur_rule_ids - prev_rule_ids),
#         "resolved_rules":     sorted(prev_rule_ids - cur_rule_ids),
#     }


# def _fallback_contextual_paragraph(metadata: Dict[str, Any],
#                                     py_result: Dict[str, Any]) -> str:
#     name  = metadata.get("name") or "This asset"
#     kind  = (py_result.get("asset_kind") or metadata.get("type") or "asset").lower()
#     ctype = (metadata.get("connector_type") or "an upstream source").lower()

#     if kind == "pipeline":
#         meta = py_result.get("pipeline_meta") or {}
#         acts = meta.get("activities") or []
#         if acts:
#             act_names = ", ".join(a.get("name") for a in acts[:5] if a.get("name"))
#             return (f"{name} is a pipeline on {ctype} composed of the activities: "
#                     f"{act_names}. The pipeline id is {meta.get('pipeline_id') or 'not available'} "
#                     f"and it was created on {meta.get('created_time') or 'unknown'}.")
#         return (f"{name} is a pipeline on {ctype}. No activity metadata could be "
#                 f"retrieved from the source, so its internal structure is unknown.")

#     if kind == "dataset":
#         info = py_result.get("dataset_info") or {}
#         tables = info.get("tables") or []
#         if tables:
#             t = tables[0]
#             return (f"{name} is an ADF dataset of type {info.get('type')} bound to "
#                     f"linked service {info.get('linked_service')}. It resolves to "
#                     f"the underlying table {t.get('schema')}.{t.get('table_name')} "
#                     f"({t.get('row_count')} rows, {t.get('column_count')} columns).")
#         return (f"{name} is an ADF dataset of type {info.get('type') or 'unknown'} "
#                 f"on linked service {info.get('linked_service') or 'unknown'}. "
#                 f"No underlying table could be probed.")

#     if kind == "table":
#         info = py_result.get("table_info") or {}
#         return (f"{name} is a table {info.get('schema')}.{info.get('table_name')} "
#                 f"on {ctype} with {info.get('row_count')} rows and "
#                 f"{info.get('column_count')} columns.")

#     return f"{name} is a {kind} on {ctype}."


# def _fallback_technical_paragraph(py_result: Dict[str, Any]) -> str:
#     kind  = (py_result.get("asset_kind") or "asset").lower()
#     total = py_result.get("total_rules", 0)
#     passed = py_result.get("passed", 0)
#     failed = py_result.get("failed", 0)
#     outliers = py_result.get("outlier_count", 0)

#     if kind == "pipeline":
#         runs = py_result.get("total_runs", 0)
#         fails = py_result.get("failed_runs", 0)
#         details = py_result.get("run_details") or []
#         if runs == 0:
#             return (f"No pipeline runs were recorded in the last 7 days. "
#                     f"Deterministic engine evaluated {total} rule(s), "
#                     f"{passed} passed and {failed} failed.")
#         last_fail = next((d for d in details if not d.get("is_success")), None)
#         fail_clause = ""
#         if last_fail:
#             fail_clause = (f" Most recent failure: '{last_fail.get('failure_reason')}'.")
#         return (f"The pipeline reported {runs} run(s) in the last 7 days of which "
#                 f"{fails} failed. Engine ran {total} rule(s): {passed} passed, "
#                 f"{failed} failed.{fail_clause}")

#     if kind == "dataset":
#         info = py_result.get("dataset_info") or {}
#         tables = info.get("tables") or []
#         if tables:
#             t = tables[0]
#             pk = ", ".join(t.get("primary_keys") or []) or "none"
#             fks = t.get("foreign_keys") or []
#             fk_text = "; ".join(f"{f.get('column')} → {f.get('ref_table')}.{f.get('ref_column')}"
#                                 for f in fks) or "none"
#             return (f"The underlying table {t.get('schema')}.{t.get('table_name')} "
#                     f"contains {t.get('row_count')} rows across "
#                     f"{t.get('column_count')} columns. Primary key: {pk}. "
#                     f"Foreign keys: {fk_text}. Engine ran {total} rule(s) — "
#                     f"{passed} passed, {failed} failed.")
#         return (f"No underlying table could be probed. Engine ran {total} rule(s): "
#                 f"{passed} passed, {failed} failed.")

#     if kind == "table":
#         info = py_result.get("table_info") or {}
#         pk = ", ".join(info.get("primary_keys") or []) or "none"
#         fks = info.get("foreign_keys") or []
#         fk_text = "; ".join(f"{f.get('column')} → {f.get('ref_table')}.{f.get('ref_column')}"
#                             for f in fks) or "none"
#         out_text = ""
#         if outliers > 0:
#             reasons = py_result.get("outlier_reasons") or []
#             cols = ", ".join(r.get("column") for r in reasons[:3])
#             out_text = f" {outliers} outlier(s) detected in: {cols}."
#         return (f"Table {info.get('schema')}.{info.get('table_name')} contains "
#                 f"{info.get('row_count')} rows across {info.get('column_count')} "
#                 f"columns. PK: {pk}. FK: {fk_text}. Engine ran {total} rule(s): "
#                 f"{passed} passed, {failed} failed.{out_text}")

#     return (f"Engine evaluated {total} rule(s): {passed} passed, {failed} failed. "
#             f"{outliers} outlier(s) detected.")


# def _fallback_differences_paragraph(diff: Dict[str, Any]) -> str:
#     if not diff or diff.get("is_first_run"):
#         return "This is the first recorded quality run; no baseline exists for comparison."
#     sd = diff.get("score_delta") or 0
#     od = diff.get("outlier_delta") or 0
#     fd = diff.get("rules_failed_delta") or 0
#     new_r = diff.get("new_failed_rules") or []
#     res_r = diff.get("resolved_rules") or []
#     if sd == 0 and od == 0 and fd == 0 and not new_r and not res_r:
#         return "No change versus the previous run; all metrics are stable."
#     parts = []
#     if sd:
#         direction = "improved" if sd > 0 else "declined"
#         parts.append(f"score {direction} by {abs(sd):.2f}")
#     if od:
#         parts.append(f"outlier count moved by {od:+d}")
#     if fd:
#         parts.append(f"failing rules changed by {fd:+d}")
#     deltas = ", ".join(parts) or "minor changes"
#     rules_part = ""
#     if new_r:
#         rules_part += f" New failures: {', '.join(new_r)}."
#     if res_r:
#         rules_part += f" Resolved: {', '.join(res_r)}."
#     return f"Compared with the previous run: {deltas}.{rules_part}"


# def _build_pipeline_recommendations(py_result: Dict[str, Any]) -> List[str]:
#     """Pull deterministic recommended_solution values out of run_details."""
#     recs: List[str] = []
#     for run in (py_result.get("run_details") or []):
#         sol = run.get("recommended_solution")
#         if sol and sol not in recs:
#             recs.append(sol)
#         if len(recs) >= 4:
#             break
#     return recs


# def _build_outlier_recommendations(py_result: Dict[str, Any]) -> List[str]:
#     """Build one recommendation per column that has outliers."""
#     recs: List[str] = []
#     for r in (py_result.get("outlier_reasons") or [])[:4]:
#         col = r.get("column")
#         recs.append(
#             f"Investigate {max(r.get('iqr_outliers', 0), r.get('z_outliers', 0))} "
#             f"outlier value(s) in column '{col}' outside the expected range "
#             f"[{r.get('lower_bound')}, {r.get('upper_bound')}]."
#         )
#     return recs


# def _final_recommendations(py_result: Dict[str, Any]) -> List[str]:
#     """Deterministic default recommendations grounded in py_result."""
#     recs: List[str] = []
#     recs.extend(_build_pipeline_recommendations(py_result))
#     recs.extend(_build_outlier_recommendations(py_result))
#     if not recs:
#         if py_result.get("failed", 0) == 0 and py_result.get("score", 0) >= 85:
#             recs.append("Monitor for stability on subsequent runs.")
#         else:
#             recs.extend(_fallback_recommendations({
#                 "by_category": py_result.get("by_category", {})
#             }))
#     return recs[:5]


# # ----------------------------------------------------------------------
# # Main entry: format_quality_report
# # ----------------------------------------------------------------------
# def format_quality_report(
#     dataset_metadata: Dict[str, Any],
#     py_result: Dict[str, Any],
#     rulebook: Optional[Dict[str, Any]] = None,
#     rulebook_chunks: Optional[List[Any]] = None,
#     previous_report: Optional[Dict[str, Any]] = None,
# ) -> Dict[str, Any]:
#     """Wrap Python deterministic result into the analysis-results JSON.

#     Output keys:
#       • Numeric (Python-owned): quality_score, data_quality, confidence_score,
#         pii_percentage, outlier_count, severity, rules_passed, rules_failed
#       • Structured (Python-owned): pipeline_meta, run_details, table_info,
#         dataset_info, outlier_reasons, failed_rules, asset_kind
#       • Narrative (LLM-written, grounded in Python data):
#         contextual_summary, technical_summary, differences
#       • Action list: recommendations
#     """
#     py_score      = float(py_result.get("score", 0))
#     py_conf       = float(py_result.get("confidence", 0))
#     pii_pct       = float(py_result.get("pii_percentage", 0))
#     outlier_count = int(py_result.get("outlier_count", 0))
#     severity      = py_result.get("severity", "low")
#     failed_rules  = py_result.get("failed_rules", [])
#     findings      = py_result.get("findings", [])
#     by_category   = py_result.get("by_category", {})

#     diff_struct = _compute_differences(py_result, previous_report)

#     technical_struct = {
#         "row_count":        py_result.get("row_count"),
#         "columns_scanned":  py_result.get("columns_scanned", 0),
#         "total_runs":       py_result.get("total_runs"),
#         "failed_runs":      py_result.get("failed_runs"),
#         "pii_columns":      py_result.get("pii_columns", []),
#         "rules_evaluated":  py_result.get("total_rules", 0),
#         "rules_passed":     py_result.get("passed", 0),
#         "rules_failed":     py_result.get("failed", 0),
#         "category_scores":  {k: v.get("score") for k, v in (by_category or {}).items()},
#     }

#     # ============== OUTPUT SHELL ==============
#     base = {
#         "dataset_id":          dataset_metadata.get("id"),
#         "dataset_name":        dataset_metadata.get("name"),
#         "dataset_type":        dataset_metadata.get("type"),
#         "connector_type":      dataset_metadata.get("connector_type"),

#         # Numeric fields — Python-owned
#         "quality_score":       round(py_score, 2),
#         "data_quality":        round(py_score, 2),
#         "confidence_score":    round(py_conf * 100, 2),
#         "pii_percentage":      round(pii_pct, 2),
#         "outlier_count":       outlier_count,
#         "severity":            severity,
#         "rules_passed":        py_result.get("passed", 0),
#         "rules_failed":        py_result.get("failed", 0),
#         "rulebook_used":       (rulebook or {}).get("rulebook_name"),
#         "failed_rules":        failed_rules,

#         # Structured asset details (Python-owned)
#         "asset_kind":          py_result.get("asset_kind"),
#         "pipeline_meta":       py_result.get("pipeline_meta"),
#         "run_details":         py_result.get("run_details", []),
#         "table_info":          py_result.get("table_info"),
#         "dataset_info":        py_result.get("dataset_info"),
#         "outlier_reasons":     py_result.get("outlier_reasons", []),

#         # Narrative paragraphs — LLM fills these in
#         "contextual_summary":  "",
#         "technical_summary":   "",
#         "differences":         "",
#         "recommendations":     [],

#         "status":              "deterministic_only",
#     }

#     # ============== LLM DISABLED → DETERMINISTIC FALLBACK ==============
#     if not MISTRAL_API_KEY:
#         base["contextual_summary"] = _fallback_contextual_paragraph(dataset_metadata, py_result)
#         base["technical_summary"]  = _fallback_technical_paragraph(py_result)
#         base["differences"]        = _fallback_differences_paragraph(diff_struct)
#         base["recommendations"]    = _final_recommendations(py_result)
#         return base

#     # ============== LLM CALL ==============
#     rb_excerpts = _format_rulebook_chunks(rulebook_chunks or [])
#     payload = {
#         "dataset":             dataset_metadata,
#         "asset_kind":          py_result.get("asset_kind"),
#         "asset_details": {
#             "pipeline_meta":   py_result.get("pipeline_meta"),
#             "run_details":     (py_result.get("run_details") or [])[:5],
#             "table_info":      py_result.get("table_info"),
#             "dataset_info":    py_result.get("dataset_info"),
#             "outlier_reasons": py_result.get("outlier_reasons") or [],
#         },
#         "technical_context":   technical_struct,
#         "differences_context": diff_struct,
#         "python_findings": {
#             "quality_score":    py_score,
#             "confidence_score": round(py_conf * 100, 2),
#             "pii_percentage":   pii_pct,
#             "outlier_count":    outlier_count,
#             "severity":         severity,
#             "rules_passed":     py_result.get("passed", 0),
#             "rules_failed":     py_result.get("failed", 0),
#             "failed_rules":     failed_rules[:10],
#         },
#         "rulebook": {
#             "name":     (rulebook or {}).get("rulebook_name"),
#             "excerpts": rb_excerpts,
#         },
#     }

#     sys = (
#         "You are a data quality REPORT FORMATTER for Python-computed findings.\n\n"
#         "STRICT INSTRUCTIONS:\n"
#         " 1. NEVER invent any number, dataset name, column name, pipeline "
#         "    activity, table, or rule. Use ONLY what is in the payload.\n"
#         " 2. NEVER output quality_score, confidence_score, pii_percentage, "
#         "    or outlier_count keys. Python owns them.\n"
#         " 3. If the payload shows no runs / no rows / no columns / no "
#         "    activities / first run — state that plainly. Do not pad with "
#         "    generic prose about 'data integration' or 'business intelligence'.\n"
#         " 4. Each text field is 2-4 sentences of FACTS from the payload only. "
#         "    No hypothetical scenarios. No 'this could mean' speculation.\n"
#         " 5. For pipelines with empty activities AND zero runs, write only: "
#         "    'No execution history or activities available for this pipeline.'\n"
#         " 6. Treat the dataset name as an opaque identifier — do NOT infer "
#         "    business purpose unless asset_details contains activity names, "
#         "    table names, or column names that reveal it.\n\n"
#         "Return JSON ONLY with these four keys:\n"
#         "  contextual_summary  — What the asset IS, based on asset_kind, name, "
#         "    pipeline_meta.activities, dataset_info.tables, or table_info. "
#         "    Quote names and types exactly.\n"
#         "  technical_summary   — Concrete numbers: row count, column count, "
#         "    primary keys, foreign keys, total_runs/failed_runs, rules "
#         "    passed/failed, outlier_reasons. Mention 'no data available' when "
#         "    a field is null/zero.\n"
#         "  differences         — If is_first_run is true: 'This is the first "
#         "    recorded run; no baseline exists.' Otherwise quote score_delta, "
#         "    outlier_delta, new_failed_rules, resolved_rules verbatim.\n"
#         "  recommendations     — JSON list of 2-4 action items. For failed "
#         "    pipeline runs, surface the recommended_solution already in "
#         "    run_details. For outliers, recommend investigating the columns "
#         "    in outlier_reasons. For first run with score >= 85, recommend "
#         "    'Monitor for stability on subsequent runs.'\n\n"
#         "Do NOT include summary, user_context, more_accurate, or "
#         "business_impact keys. Only the four keys above."
#     )

#     user_msg = (
#         "Generate the analysis-results JSON from the payload below. "
#         "Numbers come from the payload; you only write the three paragraphs "
#         "and the recommendations list. JSON only.\n\n"
#         f"{json.dumps(payload, default=str)[:7500]}"
#     )

#     text   = _chat(sys, user_msg, timeout=120, max_tokens=2000)
#     parsed = _parse_json_block(text)

#     base["contextual_summary"] = parsed.get("contextual_summary") or \
#                                  _fallback_contextual_paragraph(dataset_metadata, py_result)
#     base["technical_summary"]  = parsed.get("technical_summary") or \
#                                  _fallback_technical_paragraph(py_result)
#     base["differences"]        = parsed.get("differences") or \
#                                  _fallback_differences_paragraph(diff_struct)
#     parsed_recs = parsed.get("recommendations")
#     base["recommendations"]    = parsed_recs if isinstance(parsed_recs, list) and parsed_recs \
#                                  else _final_recommendations(py_result)
#     base["status"]             = "success"
#     return base


# # ----------------------------------------------------------------------
# # Backwards-compatibility shims (kept for older imports)
# # ----------------------------------------------------------------------
# def interpret_quality_findings(
#     dataset_metadata: Dict[str, Any],
#     deterministic_result: Dict[str, Any],
#     schema: Optional[List[Dict[str, Any]]] = None,
# ) -> Dict[str, Any]:
#     """Backwards-compat. Prefer format_quality_report."""
#     py_result = {
#         "score":          deterministic_result.get("final_score", 100.0),
#         "confidence":     deterministic_result.get("confidence", 1.0),
#         "severity":       deterministic_result.get("severity", "low"),
#         "passed":         deterministic_result.get("passed", 0),
#         "failed":         deterministic_result.get("failed", 0),
#         "by_category":    deterministic_result.get("by_category", {}),
#         "findings":       deterministic_result.get("findings", []),
#         "failed_rules":   [],
#         "pii_percentage": 0,
#         "outlier_count":  0,
#         "total_rules":    deterministic_result.get("total_rules", 0),
#     }
#     rep = format_quality_report(dataset_metadata, py_result)
#     return {
#         "quality_score":     rep["quality_score"],
#         "confidence_rating": rep["confidence_score"] / 100,
#         "severity":          rep["severity"],
#         "summary":           rep["technical_summary"],
#         "critical_findings": deterministic_result.get("findings", [])[:5],
#         "recommendations":   rep["recommendations"],
#         "business_impact":   "",
#         "interpretation":    rep["contextual_summary"],
#         "status":            rep["status"],
#     }


# def validate_dataset_quality(*args, **kwargs):
#     """Deprecated. Returns minimal stub."""
#     return {
#         "quality_score":     None,
#         "confidence_rating": 0.0,
#         "severity":          "low",
#         "summary":           "Use format_quality_report() instead.",
#         "critical_findings": [],
#         "recommendations":   [],
#         "business_impact":   "",
#         "interpretation":    "",
#         "status":            "deprecated",
#         "failed_rules":      [],
#         "pii_detected":      [],
#     }

"""Mistral AI helper — analyzes REAL monitoring data and returns structured
insights.

LLM never produces the *final quality score*. All mathematical scoring is
done by `utils.quality_engine`. The LLM only writes narrative paragraphs
grounded strictly in Python-supplied data.
"""

import os
import json
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from utils.common import logger

load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_API_URL = os.getenv(
    "MISTRAL_API_URL",
    "https://api.mistral.ai/v1/chat/completions",
)


# ----------------------------------------------------------------------
# Low-level chat helper
# ----------------------------------------------------------------------
def _chat(system: str, user: str, timeout: int = 60, max_tokens: int = 1500) -> str:
    if not MISTRAL_API_KEY:
        return ""
    try:
        resp = requests.post(
            MISTRAL_API_URL,
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "Mistral API non-200: %s %s", resp.status_code, resp.text[:200]
            )
            return ""
        data = resp.json()
        return (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except Exception as e:
        logger.error("Mistral call failed: %s", e)
        return ""


def _parse_json_block(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("{") or p.startswith("json"):
                if p.startswith("json"):
                    p = p[4:].strip()
                try:
                    return json.loads(p)
                except Exception:
                    continue
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return {}
        return {}


# ----------------------------------------------------------------------
# Generic event analyser (kept for compatibility)
# ----------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are an enterprise data observability assistant. You analyse REAL "
    "monitoring metrics provided in the user message. Never invent datasets, "
    "columns, numbers, or events. If a field is missing, omit it. Respond ONLY "
    'with a JSON object with keys: "summary", "root_cause", "impact", '
    '"recommendation". Each value must be a short paragraph (<= 60 words).'
)


def analyze_issue(payload: Dict[str, Any]) -> Dict[str, str]:
    if not MISTRAL_API_KEY:
        return {
            "summary": "AI disabled (no MISTRAL_API_KEY configured).",
            "root_cause": "",
            "impact": "",
            "recommendation": "",
        }
    user_msg = (
        "Analyse the following monitoring event and respond with JSON only.\n\n"
        f"EVENT JSON:\n{json.dumps(payload, default=str)[:6000]}"
    )
    text = _chat(SYSTEM_PROMPT, user_msg)
    parsed = _parse_json_block(text)
    return {
        "summary":        parsed.get("summary", "")[:1000],
        "root_cause":     parsed.get("root_cause", "")[:1000],
        "impact":         parsed.get("impact", "")[:1000],
        "recommendation": parsed.get("recommendation", "")[:1000],
    }


def summarize_monitoring_snapshot(snapshot: Dict[str, Any]) -> str:
    if not MISTRAL_API_KEY:
        return ""
    sys = (
        "You write short, factual executive summaries of data platform health. "
        "Use only the metrics in the user message. <= 120 words. Plain prose."
    )
    user = "METRICS:\n" + json.dumps(snapshot, default=str)[:5000]
    return _chat(sys, user)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _rgb_band(pct: Optional[float]) -> Optional[str]:
    """Return 'green' / 'amber' / 'red' or None if pct is None."""
    if pct is None:
        return None
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return None
    if p < 33:
        return "green"
    if p < 66:
        return "amber"
    return "red"


def _format_rulebook_chunks(chunks: List[Any]) -> List[str]:
    if not chunks:
        return []
    out: List[str] = []
    for c in chunks[:6]:
        if isinstance(c, str):
            out.append(c[:600])
        elif isinstance(c, dict):
            text = (c.get("document") or c.get("text") or c.get("content") or "")
            if text:
                out.append(str(text)[:600])
        else:
            out.append(str(c)[:600])
    return out


def _compute_differences(
    current: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not previous:
        return {
            "is_first_run":       True,
            "score_delta":        None,
            "confidence_delta":   None,
            "pii_delta":          None,
            "outlier_delta":      None,
            "rules_failed_delta": None,
            "new_failed_rules":   [],
            "resolved_rules":     [],
        }
    cur_score   = float(current.get("score", 0))
    cur_conf    = float(current.get("confidence", 0)) * 100
    cur_pii     = float(current.get("pii_percentage", 0))
    cur_out     = int(current.get("outlier_count", 0))
    cur_failed  = int(current.get("failed", 0))
    prev_score  = float(previous.get("score", 0))
    prev_conf   = float(previous.get("confidence", 0)) * 100
    prev_pii    = float(previous.get("pii_percentage", 0))
    prev_out    = int(previous.get("outlier_count", 0))
    prev_failed = int(previous.get("failed", 0))
    cur_rule_ids  = {r.get("rule") for r in (current.get("failed_rules") or [])}
    prev_rule_ids = {r.get("rule") for r in (previous.get("failed_rules") or [])}
    return {
        "is_first_run":       False,
        "score_delta":        round(cur_score - prev_score, 2),
        "confidence_delta":   round(cur_conf - prev_conf, 2),
        "pii_delta":          round(cur_pii - prev_pii, 2),
        "outlier_delta":      cur_out - prev_out,
        "rules_failed_delta": cur_failed - prev_failed,
        "new_failed_rules":   sorted(cur_rule_ids - prev_rule_ids),
        "resolved_rules":     sorted(prev_rule_ids - cur_rule_ids),
    }


# ----------------------------------------------------------------------
# Deterministic fallback paragraphs
# ----------------------------------------------------------------------
def _fallback_recommendations(det: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    bc = det.get("by_category", {})
    for cat, info in bc.items():
        if info.get("failed", 0) > 0 and info.get("score", 100) < 85:
            recs.append(
                f"Investigate {info['failed']} failed {cat} check(s) — "
                f"category score {info.get('score', 0)}/100."
            )
    if not recs:
        recs.append("No critical actions required — dataset is within quality thresholds.")
    return recs[:6]


def _fallback_contextual_paragraph(metadata: Dict[str, Any],
                                    py_result: Dict[str, Any]) -> str:
    name  = metadata.get("name") or "This asset"
    kind  = (py_result.get("asset_kind") or metadata.get("type") or "asset").lower()
    ctype = (metadata.get("connector_type") or "an upstream source").lower()

    if kind == "pipeline":
        meta = py_result.get("pipeline_meta") or {}
        acts = meta.get("activities") or []
        if not acts and (py_result.get("total_runs") or 0) == 0:
            return "No execution history or activities available for this pipeline."
        if acts:
            act_names = ", ".join(a.get("name") for a in acts[:5] if a.get("name"))
            return (f"{name} is a pipeline on {ctype} composed of the activities: "
                    f"{act_names}. The pipeline id is {meta.get('pipeline_id') or 'not available'} "
                    f"and it was created on {meta.get('created_time') or 'unknown'}.")
        return (f"{name} is a pipeline on {ctype}. No activity metadata could be "
                f"retrieved from the source, so its internal structure is unknown.")

    if kind == "dataset":
        info = py_result.get("dataset_info") or {}
        tables = info.get("tables") or []
        if tables:
            t = tables[0]
            return (f"{name} is an ADF dataset of type {info.get('type')} bound to "
                    f"linked service {info.get('linked_service')}. It resolves to "
                    f"the underlying table {t.get('schema')}.{t.get('table_name')} "
                    f"({t.get('row_count')} rows, {t.get('column_count')} columns).")
        return (f"{name} is an ADF dataset of type {info.get('type') or 'unknown'} "
                f"on linked service {info.get('linked_service') or 'unknown'}. "
                f"No underlying table could be probed.")

    if kind == "table":
        info = py_result.get("table_info") or {}
        return (f"{name} is a table {info.get('schema')}.{info.get('table_name')} "
                f"on {ctype} with {info.get('row_count')} rows and "
                f"{info.get('column_count')} columns.")

    return f"{name} is a {kind} on {ctype}."


def _fallback_technical_paragraph(py_result: Dict[str, Any]) -> str:
    kind  = (py_result.get("asset_kind") or "asset").lower()
    total = py_result.get("total_rules", 0)
    passed = py_result.get("passed", 0)
    failed = py_result.get("failed", 0)
    outliers = py_result.get("outlier_count", 0)
    miss = py_result.get("missing_data_pct")
    junk = py_result.get("junk_data_pct")
    opct = py_result.get("outlier_pct")

    bars = ""
    if miss is not None or junk is not None or opct is not None:
        bits = []
        if miss is not None: bits.append(f"missing data {miss:.1f}%")
        if junk is not None: bits.append(f"junk values {junk:.1f}%")
        if opct is not None: bits.append(f"outliers {opct:.1f}%")
        bars = " " + ", ".join(bits) + "."

    if kind == "pipeline":
        runs = py_result.get("total_runs", 0)
        fails = py_result.get("failed_runs", 0)
        details = py_result.get("run_details") or []
        if runs == 0:
            return (f"No pipeline runs were recorded in the last 7 days. "
                    f"Deterministic engine evaluated {total} rule(s), "
                    f"{passed} passed and {failed} failed.")
        last_fail = next((d for d in details if not d.get("is_success")), None)
        fail_clause = (f" Most recent failure: '{last_fail.get('failure_reason')}'."
                       if last_fail else "")
        return (f"The pipeline reported {runs} run(s) in the last 7 days of which "
                f"{fails} failed. Engine ran {total} rule(s): {passed} passed, "
                f"{failed} failed.{fail_clause}")

    if kind == "dataset":
        info = py_result.get("dataset_info") or {}
        tables = info.get("tables") or []
        if tables:
            t = tables[0]
            pk = ", ".join(t.get("primary_keys") or []) or "none"
            fks = t.get("foreign_keys") or []
            fk_text = "; ".join(f"{f.get('column')} → {f.get('ref_table')}.{f.get('ref_column')}"
                                for f in fks) or "none"
            return (f"The underlying table {t.get('schema')}.{t.get('table_name')} "
                    f"contains {t.get('row_count')} rows across "
                    f"{t.get('column_count')} columns. Primary key: {pk}. "
                    f"Foreign keys: {fk_text}. Engine ran {total} rule(s) — "
                    f"{passed} passed, {failed} failed.")
        return (f"No underlying table could be probed. Engine ran {total} rule(s): "
                f"{passed} passed, {failed} failed.")

    if kind == "table":
        info = py_result.get("table_info") or {}
        pk = ", ".join(info.get("primary_keys") or []) or "none"
        fks = info.get("foreign_keys") or []
        fk_text = "; ".join(f"{f.get('column')} → {f.get('ref_table')}.{f.get('ref_column')}"
                            for f in fks) or "none"
        out_text = ""
        if outliers > 0:
            reasons = py_result.get("outlier_reasons") or []
            cols = ", ".join(r.get("column") for r in reasons[:3])
            out_text = f" {outliers} outlier(s) detected in: {cols}."
        return (f"Table {info.get('schema')}.{info.get('table_name')} contains "
                f"{info.get('row_count')} rows across {info.get('column_count')} "
                f"columns. PK: {pk}. FK: {fk_text}. Engine ran {total} rule(s): "
                f"{passed} passed, {failed} failed.{out_text}{bars}")

    return (f"Engine evaluated {total} rule(s): {passed} passed, {failed} failed. "
            f"{outliers} outlier(s) detected.{bars}")


def _fallback_differences_paragraph(diff: Dict[str, Any]) -> str:
    if not diff or diff.get("is_first_run"):
        return "This is the first recorded quality run; no baseline exists for comparison."
    sd = diff.get("score_delta") or 0
    od = diff.get("outlier_delta") or 0
    fd = diff.get("rules_failed_delta") or 0
    new_r = diff.get("new_failed_rules") or []
    res_r = diff.get("resolved_rules") or []
    if sd == 0 and od == 0 and fd == 0 and not new_r and not res_r:
        return "No change versus the previous run; all metrics are stable."
    parts = []
    if sd:
        direction = "improved" if sd > 0 else "declined"
        parts.append(f"score {direction} by {abs(sd):.2f}")
    if od:
        parts.append(f"outlier count moved by {od:+d}")
    if fd:
        parts.append(f"failing rules changed by {fd:+d}")
    deltas = ", ".join(parts) or "minor changes"
    rules_part = ""
    if new_r:
        rules_part += f" New failures: {', '.join(new_r)}."
    if res_r:
        rules_part += f" Resolved: {', '.join(res_r)}."
    return f"Compared with the previous run: {deltas}.{rules_part}"


def _fallback_trend_paragraph(diff: Dict[str, Any], py_result: Dict[str, Any]) -> str:
    if not diff or diff.get("is_first_run"):
        return ("No prior runs are available to compute deviation. Trend analysis "
                "will become available from the next run onward.")
    sd = diff.get("score_delta") or 0
    od = diff.get("outlier_delta") or 0
    pd = diff.get("pii_delta") or 0
    if sd == 0 and od == 0 and pd == 0:
        return ("Metrics are stable versus the previous run; no meaningful "
                "deviation observed in score, outliers, or PII coverage.")
    parts = []
    if sd:
        parts.append(f"quality score moved by {sd:+.2f} points")
    if od:
        parts.append(f"outlier count moved by {od:+d}")
    if pd:
        parts.append(f"PII coverage shifted by {pd:+.2f}%")
    return (f"Deviation versus the previous baseline: {', '.join(parts)}. "
            f"Review upstream changes if the movement is unexpected.")


def _fallback_pii_paragraph(py_result: Dict[str, Any]) -> str:
    pii_cols = py_result.get("pii_columns") or []
    pii_pct  = py_result.get("pii_percentage", 0)
    if not pii_cols:
        return "No PII patterns detected in the inspected columns."
    cols_text = ", ".join(pii_cols[:8])
    extra = f" (and {len(pii_cols) - 8} more)" if len(pii_cols) > 8 else ""
    return (f"PII patterns detected on {len(pii_cols)} column(s) "
            f"({pii_pct:.1f}% of scanned columns): {cols_text}{extra}. "
            f"Apply masking or access controls on these fields.")


def _build_pipeline_recommendations(py_result: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    for run in (py_result.get("run_details") or []):
        sol = run.get("recommended_solution")
        if sol and sol not in recs:
            recs.append(sol)
        if len(recs) >= 4:
            break
    return recs


def _build_outlier_recommendations(py_result: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    for r in (py_result.get("outlier_reasons") or [])[:4]:
        col = r.get("column")
        recs.append(
            f"Investigate {max(r.get('iqr_outliers', 0), r.get('z_outliers', 0))} "
            f"outlier value(s) in column '{col}' outside the expected range "
            f"[{r.get('lower_bound')}, {r.get('upper_bound')}]."
        )
    return recs


def _final_recommendations(py_result: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    recs.extend(_build_pipeline_recommendations(py_result))
    recs.extend(_build_outlier_recommendations(py_result))
    if not recs:
        if py_result.get("failed", 0) == 0 and py_result.get("score", 0) >= 85:
            recs.append("Monitor for stability on subsequent runs.")
        else:
            recs.extend(_fallback_recommendations({
                "by_category": py_result.get("by_category", {})
            }))
    return recs[:5]


# ----------------------------------------------------------------------
# Main entry: format_quality_report
# ----------------------------------------------------------------------
def format_quality_report(
    dataset_metadata: Dict[str, Any],
    py_result: Dict[str, Any],
    rulebook: Optional[Dict[str, Any]] = None,
    rulebook_chunks: Optional[List[Any]] = None,
    previous_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    py_score      = float(py_result.get("score", 0))
    py_conf       = float(py_result.get("confidence", 0))
    pii_pct       = float(py_result.get("pii_percentage", 0))
    outlier_count = int(py_result.get("outlier_count", 0))
    severity      = py_result.get("severity", "low")
    failed_rules  = py_result.get("failed_rules", [])
    by_category   = py_result.get("by_category", {})

    missing_pct = py_result.get("missing_data_pct")
    junk_pct    = py_result.get("junk_data_pct")
    out_pct     = py_result.get("outlier_pct")

    diff_struct = _compute_differences(py_result, previous_report)

    technical_struct = {
        "row_count":        py_result.get("row_count"),
        "columns_scanned":  py_result.get("columns_scanned", 0),
        "total_runs":       py_result.get("total_runs"),
        "failed_runs":      py_result.get("failed_runs"),
        "pii_columns":      py_result.get("pii_columns", []),
        "rules_evaluated":  py_result.get("total_rules", 0),
        "rules_passed":     py_result.get("passed", 0),
        "rules_failed":     py_result.get("failed", 0),
        "category_scores":  {k: v.get("score") for k, v in (by_category or {}).items()},
    }

    base = {
        # ---- Header ----
        "profile":             dataset_metadata.get("name"),
        "source":              dataset_metadata.get("connector_type"),
        "dataset_id":          dataset_metadata.get("id"),
        "dataset_name":        dataset_metadata.get("name"),
        "dataset_type":        dataset_metadata.get("type"),
        "connector_type":      dataset_metadata.get("connector_type"),

        # ---- Numeric ----
        "quality_score":       round(py_score, 2),
        "data_quality":        round(py_score, 2),
        "confidence_score":    round(py_conf * 100, 2),
        "pii_percentage":      round(pii_pct, 2),
        "outlier_count":       outlier_count,
        "severity":            severity,
        "rules_passed":        py_result.get("passed", 0),
        "rules_failed":        py_result.get("failed", 0),
        "rulebook_used":       (rulebook or {}).get("rulebook_name"),
        "failed_rules":        failed_rules,

        # ---- RGB bars ----
        "missing_data_pct":    missing_pct,
        "missing_data_band":   _rgb_band(missing_pct),
        "junk_data_pct":       junk_pct,
        "junk_data_band":      _rgb_band(junk_pct),
        "outlier_pct":         out_pct,
        "outlier_band":        _rgb_band(out_pct),

        # ---- Structured ----
        "asset_kind":          py_result.get("asset_kind"),
        "pipeline_meta":       py_result.get("pipeline_meta"),
        "run_details":         py_result.get("run_details", []),
        "table_info":          py_result.get("table_info"),
        "dataset_info":        py_result.get("dataset_info"),
        "outlier_reasons":     py_result.get("outlier_reasons", []),
        "tables_summary":      py_result.get("tables_summary", []),

        # ---- Narrative ----
        "trend":               "",
        "technical_summary":   "",
        "contextual_summary":  "",
        "pii_inspection":      "",
        "differences":         "",
        "recommendations":     [],

        "status":              "deterministic_only",
    }

    if not MISTRAL_API_KEY:
        base["contextual_summary"] = _fallback_contextual_paragraph(dataset_metadata, py_result)
        base["technical_summary"]  = _fallback_technical_paragraph(py_result)
        base["differences"]        = _fallback_differences_paragraph(diff_struct)
        base["trend"]              = _fallback_trend_paragraph(diff_struct, py_result)
        base["pii_inspection"]     = _fallback_pii_paragraph(py_result)
        base["recommendations"]    = _final_recommendations(py_result)
        return base

    rb_excerpts = _format_rulebook_chunks(rulebook_chunks or [])
    payload = {
        "dataset":             dataset_metadata,
        "asset_kind":          py_result.get("asset_kind"),
        "asset_details": {
            "pipeline_meta":   py_result.get("pipeline_meta"),
            "run_details":     (py_result.get("run_details") or [])[:5],
            "table_info":      py_result.get("table_info"),
            "dataset_info":    py_result.get("dataset_info"),
            "outlier_reasons": py_result.get("outlier_reasons") or [],
            "tables_summary":  py_result.get("tables_summary") or [],
        },
        "dashboard_metrics": {
            "quality_score":    py_score,
            "missing_data_pct": missing_pct,
            "junk_data_pct":    junk_pct,
            "outlier_pct":      out_pct,
            "pii_percentage":   pii_pct,
        },
        "technical_context":   technical_struct,
        "differences_context": diff_struct,
        "python_findings": {
            "rules_passed": py_result.get("passed", 0),
            "rules_failed": py_result.get("failed", 0),
            "failed_rules": failed_rules[:10],
            "pii_columns":  py_result.get("pii_columns", []),
        },
        "rulebook": {
            "name":     (rulebook or {}).get("rulebook_name"),
            "excerpts": rb_excerpts,
        },
    }

    sys = (
        "You are a data quality REPORT FORMATTER for Python-computed findings.\n\n"
        "STRICT INSTRUCTIONS:\n"
        " 1. NEVER invent any number, dataset name, column name, table name, "
        "    pipeline activity, or rule. Use ONLY what is in the payload.\n"
        " 2. NEVER output quality_score, confidence_score, pii_percentage, "
        "    missing_data_pct, junk_data_pct, outlier_pct, or outlier_count. "
        "    Python owns them.\n"
        " 3. If a metric or list is null / zero / empty, state it plainly. "
        "    Do not pad with generic prose about 'data integration' or "
        "    'business intelligence'.\n"
        " 4. Each paragraph is 2-4 sentences of FACTS from the payload. "
        "    No 'this could mean' speculation.\n"
        " 5. For pipelines with empty activities AND zero runs, contextual_summary "
        "    must be exactly: 'No execution history or activities available for this pipeline.'\n"
        " 6. Treat the dataset name as an opaque identifier — do NOT infer "
        "    business purpose unless asset_details reveals it.\n\n"
        "Return JSON ONLY with these six keys:\n"
        "  trend              — 2-3 sentences about deviation versus the previous run. "
        "    Quote score_delta, outlier_delta from differences_context. If is_first_run "
        "    is true, write 'No prior runs to compute deviation.'\n"
        "  technical_summary  — 2-4 sentences quoting row count, column count, PK/FK, "
        "    total_runs/failed_runs, rules passed/failed, missing/junk/outlier "
        "    percentages from dashboard_metrics. Mention 'no data' when null.\n"
        "  contextual_summary — 2-4 sentences about what the asset IS based on "
        "    asset_kind, name, pipeline_meta.activities, dataset_info.tables, "
        "    or table_info. Quote names exactly.\n"
        "  pii_inspection     — 2-3 sentences listing PII categories detected from "
        "    python_findings.pii_columns. If empty, write 'No PII patterns "
        "    detected in the inspected columns.'\n"
        "  differences        — 1-3 sentences. If is_first_run: 'This is the first "
        "    recorded run; no baseline exists.' Otherwise quote score_delta, "
        "    outlier_delta, new_failed_rules, resolved_rules.\n"
        "  recommendations    — JSON list of 2-4 action items. For failed pipeline "
        "    runs use recommended_solution from run_details. For outliers cite the "
        "    columns from outlier_reasons. For first run with score >= 85, write "
        "    'Monitor for stability on subsequent runs.'\n\n"
        "Do NOT include summary, user_context, more_accurate, or business_impact keys."
    )

    user_msg = (
        "Generate the dashboard JSON. Numbers come from the payload; you only "
        "write the five paragraphs and the recommendations list. JSON only.\n\n"
        f"{json.dumps(payload, default=str)[:7500]}"
    )

    text   = _chat(sys, user_msg, timeout=120, max_tokens=2000)
    parsed = _parse_json_block(text)

    base["trend"]              = parsed.get("trend") or \
                                 _fallback_trend_paragraph(diff_struct, py_result)
    base["technical_summary"]  = parsed.get("technical_summary") or \
                                 _fallback_technical_paragraph(py_result)
    base["contextual_summary"] = parsed.get("contextual_summary") or \
                                 _fallback_contextual_paragraph(dataset_metadata, py_result)
    base["pii_inspection"]     = parsed.get("pii_inspection") or \
                                 _fallback_pii_paragraph(py_result)
    base["differences"]        = parsed.get("differences") or \
                                 _fallback_differences_paragraph(diff_struct)
    parsed_recs = parsed.get("recommendations")
    base["recommendations"]    = parsed_recs if isinstance(parsed_recs, list) and parsed_recs \
                                 else _final_recommendations(py_result)
    base["status"]             = "success"
    return base


# ----------------------------------------------------------------------
# Backwards-compatibility shims
# ----------------------------------------------------------------------
def interpret_quality_findings(
    dataset_metadata: Dict[str, Any],
    deterministic_result: Dict[str, Any],
    schema: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    py_result = {
        "score":          deterministic_result.get("final_score", 100.0),
        "confidence":     deterministic_result.get("confidence", 1.0),
        "severity":       deterministic_result.get("severity", "low"),
        "passed":         deterministic_result.get("passed", 0),
        "failed":         deterministic_result.get("failed", 0),
        "by_category":    deterministic_result.get("by_category", {}),
        "findings":       deterministic_result.get("findings", []),
        "failed_rules":   [],
        "pii_percentage": 0,
        "outlier_count":  0,
        "total_rules":    deterministic_result.get("total_rules", 0),
    }
    rep = format_quality_report(dataset_metadata, py_result)
    return {
        "quality_score":     rep["quality_score"],
        "confidence_rating": rep["confidence_score"] / 100,
        "severity":          rep["severity"],
        "summary":           rep["technical_summary"],
        "critical_findings": deterministic_result.get("findings", [])[:5],
        "recommendations":   rep["recommendations"],
        "business_impact":   "",
        "interpretation":    rep["contextual_summary"],
        "status":            rep["status"],
    }


def validate_dataset_quality(*args, **kwargs):
    return {
        "quality_score":     None,
        "confidence_rating": 0.0,
        "severity":          "low",
        "summary":           "Use format_quality_report() instead.",
        "critical_findings": [],
        "recommendations":   [],
        "business_impact":   "",
        "interpretation":    "",
        "status":            "deprecated",
        "failed_rules":      [],
        "pii_detected":      [],
    }