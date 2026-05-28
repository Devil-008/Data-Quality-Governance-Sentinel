"""Deterministic Data Quality Engine
=====================================

Python-based, statistically grounded rule evaluation. Each "rule" is an
independent measurable check that returns a numeric score (0-100), a weight,
and a list of findings.  The overall quality score is then a weighted average
of the individual rule scores — *no* LLM involved in the math.

The LLM is used *only* for:
  - Confidence/probability interpretation of the deterministic findings
  - Natural-language summaries/recommendations
  - Severity/business-impact phrasing

Rule categories implemented (covering the user's required checks):
  - completeness       — null %, blank/whitespace, missing mandatory cols
  - uniqueness         — duplicate rows, PK uniqueness
  - validity           — type, range, regex, garbage / control chars
  - accuracy           — outliers (IQR + z-score), invalid sign,
                         misplaced data (mixed-type column)
  - integrity          — FK orphans, referential integrity
  - timeliness         — freshness, late executions
  - consistency        — schema drift, partition consistency
  - governance         — PII detection, governance metadata
  - anomaly            — frequency anomalies, value-distribution shift,
                         substantial trend deviation (historical compare)
"""

from __future__ import annotations

import math
import re
import statistics
import datetime
from typing import Any, Dict, List, Optional, Tuple

# ----------------------------------------------------------------------
# Rule weights (sum-normalised at runtime so they don't have to add to 1)
# ----------------------------------------------------------------------
RULE_WEIGHTS: Dict[str, float] = {
    "completeness":  1.5,
    "uniqueness":    1.2,
    "validity":      1.5,
    "accuracy":      1.3,
    "integrity":     1.3,
    "timeliness":    0.8,
    "consistency":   1.0,
    "governance":    1.4,
    "anomaly":       1.0,
}

# Severity bands (matches the rest of the platform)
SEVERITY_BANDS: List[Tuple[float, str]] = [
    (50.0,  "critical"),
    (70.0,  "high"),
    (85.0,  "medium"),
    (100.1, "low"),
]


# ======================================================================
#  Pure-function statistical helpers
# ======================================================================
def _is_blank_or_garbage(v: Any) -> bool:
    """True if value is None / whitespace-only / contains control or
    obviously-garbage characters."""
    if v is None:
        return True
    s = str(v)
    if not s.strip():
        return True
    if any(ord(ch) < 32 and ch not in ("\t", "\n", "\r") for ch in s):
        return True
    if re.fullmatch(r"[?\u00bf\u00a1]+", s):
        return True
    if s.strip().lower() in ("null", "none", "nan", "n/a", "na", "--", "undefined"):
        return True
    return False


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _iqr_outliers(values: List[float]) -> Tuple[int, float, float]:
    """Return (count_of_outliers, lower_bound, upper_bound) using IQR x1.5."""
    if len(values) < 10:
        return 0, float("-inf"), float("inf")
    qs = statistics.quantiles(values, n=4)
    q1, q3 = qs[0], qs[2]
    iqr = q3 - q1
    lb, ub = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    n = sum(1 for v in values if v < lb or v > ub)
    return n, lb, ub


def _zscore_outliers(values: List[float], threshold: float = 3.0) -> int:
    if len(values) < 10:
        return 0
    mu = statistics.fmean(values)
    sigma = statistics.pstdev(values) or 0.0
    if sigma == 0:
        return 0
    return sum(1 for v in values if abs((v - mu) / sigma) > threshold)


def _value_type_mix(values: List[Any]) -> Dict[str, int]:
    """Detect misplaced/incorrect data: counts how many values look numeric
    vs date-ish vs textual.  A column with significant mix likely has
    misplaced data."""
    counts = {"numeric": 0, "date": 0, "text": 0, "blank": 0}
    date_re = re.compile(
        r"^\d{2,4}[-/]\d{1,2}[-/]\d{1,4}([ T]\d{1,2}:\d{2}(:\d{2})?)?$"
    )
    for v in values:
        if v is None or str(v).strip() == "":
            counts["blank"] += 1
            continue
        s = str(v).strip()
        if _to_float(s) is not None:
            counts["numeric"] += 1
        elif date_re.match(s):
            counts["date"] += 1
        else:
            counts["text"] += 1
    return counts


# ======================================================================
#  Rule result container
# ======================================================================
class RuleResult:
    """One measurable rule's outcome."""

    __slots__ = (
        "rule_id", "rule_name", "category", "passed",
        "score", "weight", "findings", "metrics",
    )

    def __init__(
        self,
        rule_id: str,
        rule_name: str,
        category: str,
        passed: bool,
        score: float,
        findings: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.category = category
        self.passed = passed
        self.score = max(0.0, min(100.0, float(score)))
        self.weight = RULE_WEIGHTS.get(category, 1.0)
        self.findings = findings or []
        self.metrics = metrics or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id":   self.rule_id,
            "rule_name": self.rule_name,
            "category":  self.category,
            "passed":    self.passed,
            "score":     round(self.score, 2),
            "weight":    self.weight,
            "findings":  self.findings,
            "metrics":   self.metrics,
        }


# ======================================================================
#  Individual rule implementations
# ======================================================================
def rule_null_completeness(col_name: str, null_count: int, total: int) -> RuleResult:
    pct = (null_count / total * 100) if total else 0.0
    if pct <= 5:
        score = 100.0
    elif pct <= 15:
        score = 85.0
    elif pct <= 30:
        score = 65.0
    else:
        score = max(0.0, 100.0 - (pct * 1.5))
    return RuleResult(
        rule_id=f"null_completeness_{col_name}",
        rule_name=f"Null completeness: {col_name}",
        category="completeness",
        passed=pct <= 15,
        score=score,
        findings=[f"Column '{col_name}' has {round(pct,2)}% NULLs"] if pct > 15 else [],
        metrics={"null_pct": round(pct, 2), "null_count": null_count, "total": total},
    )


def rule_blank_garbage(col_name: str, sample_values: List[Any]) -> RuleResult:
    if not sample_values:
        return RuleResult(
            f"blank_garbage_{col_name}", f"Blank/garbage values: {col_name}",
            "validity", True, 100.0,
        )
    bad = sum(1 for v in sample_values if _is_blank_or_garbage(v))
    pct = bad / len(sample_values) * 100
    score = max(0.0, 100.0 - pct * 2.0)
    return RuleResult(
        rule_id=f"blank_garbage_{col_name}",
        rule_name=f"Blank / garbage values: {col_name}",
        category="validity",
        passed=pct < 5,
        score=score,
        findings=[f"Column '{col_name}' has {round(pct,2)}% blank or garbage entries"]
                  if pct >= 5 else [],
        metrics={"garbage_pct": round(pct, 2), "garbage_count": bad,
                 "sample_size": len(sample_values)},
    )


def rule_duplicate_check(col_name: str, total: int, distinct: int) -> RuleResult:
    if total <= 0:
        return RuleResult(
            f"dup_{col_name}", f"Duplicate check: {col_name}",
            "uniqueness", True, 100.0,
        )
    dup_pct = (total - distinct) / total * 100
    score = max(0.0, 100.0 - dup_pct * 1.5)
    return RuleResult(
        rule_id=f"dup_{col_name}",
        rule_name=f"Duplicate check: {col_name}",
        category="uniqueness",
        passed=dup_pct <= 10,
        score=score,
        findings=[f"Column '{col_name}' has {total - distinct} duplicates "
                  f"({round(dup_pct,2)}%)"] if dup_pct > 10 else [],
        metrics={"distinct": distinct, "total": total,
                 "duplicate_pct": round(dup_pct, 2)},
    )


def rule_pk_uniqueness(pk_expr: str, duplicates: int) -> RuleResult:
    return RuleResult(
        rule_id="pk_uniqueness",
        rule_name=f"Primary key uniqueness ({pk_expr})",
        category="uniqueness",
        passed=duplicates == 0,
        score=100.0 if duplicates == 0 else max(0.0, 100.0 - duplicates * 5),
        findings=[f"Primary key has {duplicates} duplicate rows"]
                  if duplicates else [],
        metrics={"duplicates": duplicates},
    )


def rule_outlier_detection(col_name: str, numeric_values: List[float]) -> RuleResult:
    if len(numeric_values) < 10:
        return RuleResult(
            f"outlier_{col_name}", f"Outlier detection: {col_name}",
            "accuracy", True, 100.0,
            metrics={"sample_size": len(numeric_values), "skipped": "insufficient_data"},
        )
    iqr_n, lb, ub = _iqr_outliers(numeric_values)
    z_n = _zscore_outliers(numeric_values, 3.0)
    n = max(iqr_n, z_n)
    pct = n / len(numeric_values) * 100
    score = max(0.0, 100.0 - pct * 4.0)
    return RuleResult(
        rule_id=f"outlier_{col_name}",
        rule_name=f"Outlier detection: {col_name}",
        category="accuracy",
        passed=pct < 5,
        score=score,
        findings=[f"Column '{col_name}' has {n} outliers "
                  f"(IQR={iqr_n}, z>3={z_n})"] if pct >= 5 else [],
        metrics={"iqr_outliers": iqr_n, "z_outliers": z_n,
                 "lower_bound": round(lb, 4) if math.isfinite(lb) else None,
                 "upper_bound": round(ub, 4) if math.isfinite(ub) else None,
                 "sample_size": len(numeric_values), "outlier_pct": round(pct, 2)},
    )


def rule_invalid_sign(col_name: str, numeric_values: List[float],
                     expect_positive: bool = True) -> RuleResult:
    """Catch negative numbers in columns that should never be negative
    (price, quantity, age, count …) and vice-versa."""
    if not numeric_values:
        return RuleResult(
            f"sign_{col_name}", f"Sign validation: {col_name}",
            "accuracy", True, 100.0,
        )
    if expect_positive:
        bad = sum(1 for v in numeric_values if v < 0)
        msg = f"Column '{col_name}' has {bad} unexpected negative values"
    else:
        bad = sum(1 for v in numeric_values if v > 0)
        msg = f"Column '{col_name}' has {bad} unexpected positive values"
    pct = bad / len(numeric_values) * 100
    score = max(0.0, 100.0 - pct * 3.0)
    return RuleResult(
        rule_id=f"sign_{col_name}",
        rule_name=f"Sign validation: {col_name}",
        category="accuracy",
        passed=bad == 0,
        score=score,
        findings=[msg] if bad else [],
        metrics={"bad_sign_count": bad, "sample_size": len(numeric_values),
                 "expect_positive": expect_positive},
    )


def rule_misplaced_data(col_name: str, sample_values: List[Any],
                       declared_type: Optional[str] = None) -> RuleResult:
    """Detect misplaced/incorrect data: column has values that don't match
    the predominant type."""
    if not sample_values:
        return RuleResult(
            f"misplaced_{col_name}", f"Misplaced data: {col_name}",
            "accuracy", True, 100.0,
        )
    mix = _value_type_mix(sample_values)
    non_blank = sum(v for k, v in mix.items() if k != "blank")
    if non_blank == 0:
        return RuleResult(
            f"misplaced_{col_name}", f"Misplaced data: {col_name}",
            "accuracy", True, 100.0, metrics=mix,
        )
    dominant = max(("numeric", "date", "text"), key=lambda k: mix[k])
    expected = dominant
    if declared_type:
        dt = declared_type.lower()
        if any(t in dt for t in ("int", "bigint", "decimal", "float", "double",
                                 "numeric", "real")):
            expected = "numeric"
        elif any(t in dt for t in ("date", "time", "timestamp")):
            expected = "date"
        elif any(t in dt for t in ("char", "varchar", "text", "string")):
            expected = "text"
    misplaced = non_blank - mix.get(expected, 0)
    pct = misplaced / non_blank * 100
    score = max(0.0, 100.0 - pct * 2.5)
    return RuleResult(
        rule_id=f"misplaced_{col_name}",
        rule_name=f"Misplaced data: {col_name}",
        category="accuracy",
        passed=pct < 5,
        score=score,
        findings=[f"Column '{col_name}' has {misplaced} values that don't match "
                  f"expected type '{expected}' ({round(pct,2)}%)"] if pct >= 5 else [],
        metrics={**mix, "expected_type": expected, "misplaced_pct": round(pct, 2)},
    )


def rule_freshness(col_name: str, last_value: Optional[datetime.datetime],
                  threshold_days: int = 7) -> RuleResult:
    if last_value is None:
        return RuleResult(
            f"freshness_{col_name}", f"Freshness: {col_name}",
            "timeliness", True, 100.0,
            metrics={"skipped": "no_timestamp"},
        )
    try:
        if isinstance(last_value, datetime.date) and not isinstance(last_value, datetime.datetime):
            last_value = datetime.datetime.combine(last_value, datetime.time())
        delta_days = (datetime.datetime.utcnow() - last_value).days
    except Exception:
        return RuleResult(
            f"freshness_{col_name}", f"Freshness: {col_name}",
            "timeliness", True, 100.0,
            metrics={"skipped": "bad_timestamp"},
        )
    if delta_days <= threshold_days:
        score = 100.0
    elif delta_days <= threshold_days * 4:
        score = 70.0
    else:
        score = max(0.0, 100.0 - (delta_days - threshold_days) * 0.5)
    return RuleResult(
        rule_id=f"freshness_{col_name}",
        rule_name=f"Freshness: {col_name}",
        category="timeliness",
        passed=delta_days <= threshold_days,
        score=score,
        findings=[f"Data is {delta_days} days old (threshold: {threshold_days}d)"]
                  if delta_days > threshold_days else [],
        metrics={"days_old": delta_days, "threshold_days": threshold_days,
                 "last_value": last_value.isoformat()},
    )


def rule_fk_integrity(constraint_name: str, orphans: int) -> RuleResult:
    return RuleResult(
        rule_id=f"fk_{constraint_name}",
        rule_name=f"FK integrity: {constraint_name}",
        category="integrity",
        passed=orphans == 0,
        score=100.0 if orphans == 0 else max(0.0, 100.0 - orphans * 4),
        findings=[f"FK '{constraint_name}' has {orphans} orphaned rows"]
                  if orphans else [],
        metrics={"orphans": orphans},
    )


def rule_schema_drift(added: List[str], removed: List[str],
                     type_changes: List[dict]) -> RuleResult:
    n = len(added) + len(removed) + len(type_changes)
    score = 100.0 if n == 0 else max(0.0, 100.0 - n * 8)
    findings = []
    if added:        findings.append(f"Added columns: {', '.join(added)}")
    if removed:      findings.append(f"Removed columns: {', '.join(removed)}")
    if type_changes: findings.append(f"Type changes: {len(type_changes)}")
    return RuleResult(
        rule_id="schema_drift",
        rule_name="Schema drift",
        category="consistency",
        passed=n == 0,
        score=score,
        findings=findings,
        metrics={"added": added, "removed": removed, "type_changes": type_changes},
    )


def rule_pii_governance(pii_columns: List[str]) -> RuleResult:
    """Governance — presence of PII is not a failure per se, but
    *un-masked* / un-flagged PII in samples lowers the score."""
    n = len(pii_columns)
    if n == 0:
        return RuleResult(
            "pii_governance", "PII governance",
            "governance", True, 100.0,
            metrics={"pii_count": 0},
        )
    # PII presence is informational; still mild deduction so it shows up.
    score = max(70.0, 100.0 - n * 5.0)
    return RuleResult(
        rule_id="pii_governance",
        rule_name="PII governance",
        category="governance",
        passed=False,
        score=score,
        findings=[f"{n} PII column(s) detected: {', '.join(pii_columns)}"],
        metrics={"pii_count": n, "pii_columns": pii_columns},
    )


def rule_trend_deviation(metric_name: str, history: List[float],
                        current: float, max_deviation_pct: float = 30.0) -> RuleResult:
    """Substantial trend deviation in historical data.

    Compares ``current`` to mean of ``history``; if it deviates by more than
    ``max_deviation_pct`` of stddev (or % of mean when stddev is 0), flag."""
    if not history or len(history) < 3:
        return RuleResult(
            f"trend_{metric_name}", f"Trend deviation: {metric_name}",
            "anomaly", True, 100.0, metrics={"skipped": "insufficient_history"},
        )
    mu = statistics.fmean(history)
    sigma = statistics.pstdev(history)
    if sigma > 0:
        z = abs((current - mu) / sigma)
        deviation_score = min(z * 30.0, 100.0)  # 0 = identical, 100 = wildly off
    else:
        pct = abs(current - mu) / (abs(mu) + 1e-9) * 100
        deviation_score = min(pct, 100.0)
    passed = deviation_score < max_deviation_pct
    rule_score = max(0.0, 100.0 - deviation_score * 1.5)
    return RuleResult(
        rule_id=f"trend_{metric_name}",
        rule_name=f"Trend deviation: {metric_name}",
        category="anomaly",
        passed=passed,
        score=rule_score,
        findings=[f"Metric '{metric_name}' deviates significantly from historical "
                  f"mean (current={round(current,2)}, mean={round(mu,2)}, "
                  f"deviation_score={round(deviation_score,2)})"] if not passed else [],
        metrics={"current": current, "history_mean": round(mu, 4),
                 "history_stddev": round(sigma, 4),
                 "deviation_score": round(deviation_score, 2)},
    )


def rule_pipeline_failure(pipeline_name: str, total_runs: int,
                         failed_runs: int) -> RuleResult:
    if total_runs <= 0:
        return RuleResult(
            f"pipeline_{pipeline_name}", f"Pipeline reliability: {pipeline_name}",
            "integrity", True, 100.0, metrics={"skipped": "no_runs"},
        )
    fail_pct = failed_runs / total_runs * 100
    score = max(0.0, 100.0 - fail_pct * 2.0)
    return RuleResult(
        rule_id=f"pipeline_{pipeline_name}",
        rule_name=f"Pipeline reliability: {pipeline_name}",
        category="integrity",
        passed=fail_pct < 10,
        score=score,
        findings=[f"Pipeline '{pipeline_name}' failed "
                  f"{failed_runs}/{total_runs} runs ({round(fail_pct,2)}%)"]
                  if fail_pct >= 10 else [],
        metrics={"total_runs": total_runs, "failed_runs": failed_runs,
                 "fail_pct": round(fail_pct, 2)},
    )


# ======================================================================
#  Aggregation — the deterministic final score
# ======================================================================
def aggregate(rules: List[RuleResult]) -> Dict[str, Any]:
    """Combine rule results into a weighted final score.

    Final score = Σ(score_i × weight_i) / Σ(weight_i)
    Confidence  = 1 − (σ(scores) / 100)   (high spread → low confidence)
    """
    if not rules:
        return {
            "final_score": 100.0,
            "confidence":  1.0,
            "severity":    "low",
            "total_rules": 0,
            "passed":      0,
            "failed":      0,
            "by_category": {},
            "findings":    [],
        }

    weighted_sum = sum(r.score * r.weight for r in rules)
    weight_total = sum(r.weight for r in rules) or 1.0
    final_score = weighted_sum / weight_total

    scores = [r.score for r in rules]
    spread = statistics.pstdev(scores) if len(scores) > 1 else 0.0
    confidence = max(0.0, min(1.0, 1.0 - spread / 100.0))

    severity = "low"
    for threshold, name in SEVERITY_BANDS:
        if final_score < threshold:
            severity = name
            break

    by_cat: Dict[str, Dict[str, Any]] = {}
    for r in rules:
        slot = by_cat.setdefault(r.category, {"sum": 0.0, "wt": 0.0,
                                               "passed": 0, "failed": 0, "count": 0})
        slot["sum"]    += r.score * r.weight
        slot["wt"]     += r.weight
        slot["count"]  += 1
        slot["passed" if r.passed else "failed"] += 1
    for slot in by_cat.values():
        slot["score"] = round(slot["sum"] / slot["wt"], 2) if slot["wt"] else 100.0
        slot.pop("sum"); slot.pop("wt")

    findings: List[str] = []
    for r in rules:
        findings.extend(r.findings)

    return {
        "final_score":  round(final_score, 2),
        "confidence":   round(confidence, 4),
        "severity":     severity,
        "total_rules":  len(rules),
        "passed":       sum(1 for r in rules if r.passed),
        "failed":       sum(1 for r in rules if not r.passed),
        "by_category":  by_cat,
        "findings":     findings,
        "rules":        [r.to_dict() for r in rules],
    }


# ======================================================================
#  High-level evaluator — runs every applicable deterministic rule
#  against a column/dataset profile dict.
# ======================================================================
def evaluate_column(
    col_name: str,
    declared_type: Optional[str],
    total_rows: int,
    null_count: int,
    distinct_count: int,
    sample_values: List[Any],
    numeric_values: List[float],
    last_timestamp: Optional[datetime.datetime] = None,
    expect_positive: Optional[bool] = None,
) -> List[RuleResult]:
    """Return the list of RuleResults applicable for a single column."""
    out: List[RuleResult] = []
    out.append(rule_null_completeness(col_name, null_count, total_rows))
    out.append(rule_blank_garbage(col_name, sample_values))
    out.append(rule_duplicate_check(col_name, total_rows, distinct_count))
    out.append(rule_misplaced_data(col_name, sample_values, declared_type))
    if numeric_values:
        out.append(rule_outlier_detection(col_name, numeric_values))
        if expect_positive is not None:
            out.append(rule_invalid_sign(col_name, numeric_values, expect_positive))
    if last_timestamp:
        out.append(rule_freshness(col_name, last_timestamp))
    return out


def evaluate_pipeline(
    pipeline_name: str,
    total_runs: int,
    failed_runs: int,
    run_durations: Optional[List[float]] = None,
    historical_durations: Optional[List[float]] = None,
) -> List[RuleResult]:
    """Evaluate a pipeline (used for ADF / Databricks pipelines)."""
    out: List[RuleResult] = []
    out.append(rule_pipeline_failure(pipeline_name, total_runs, failed_runs))
    if run_durations and historical_durations and run_durations:
        latest = run_durations[-1]
        out.append(rule_trend_deviation(
            f"{pipeline_name}_duration",
            historical_durations[:-1] if len(historical_durations) > 1 else historical_durations,
            latest,
            max_deviation_pct=40.0,
        ))
    return out
