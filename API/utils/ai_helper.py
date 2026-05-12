"""Mistral AI helper — analyzes real monitoring data and returns structured insights.

Used by the monitoring/alerts pipeline and by the AI controller. Never invents
data — caller passes real metrics in, the model produces analysis only.
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


def _chat(system: str, user: str, timeout: int = 60, max_tokens: int = 2000) -> str:
    """Send a chat completion to Mistral and return assistant text."""
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
            logger.warning("Mistral API non-200: %s %s", resp.status_code, resp.text[:200])
            return ""
        data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error("Mistral call failed: %s", e)
        return ""


def _parse_json_block(text: str) -> Dict[str, Any]:
    """Extract a JSON object from model output (tolerant)."""
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        # strip code fences
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
        # last-ditch: try to find a {...} block
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return {"summary": text}
        return {"summary": text}


SYSTEM_PROMPT = (
    "You are an enterprise data observability assistant. You analyze REAL monitoring "
    "metrics provided in the user message. Never invent datasets, columns, numbers, "
    "or events. If a field is missing, omit it. Respond ONLY with a JSON object "
    'with keys: "summary", "root_cause", "impact", "recommendation". '
    "Each value must be a short paragraph (<= 60 words)."
)


QUALITY_VALIDATION_SYSTEM_PROMPT = """You are an expert data quality engineer. Your task is to validate dataset quality using the provided Rule Books.

Respond ONLY with a JSON object containing:
- "quality_score": number 0-100
- "issues": array of strings describing quality issues found
- "pii_columns": array of column names containing PII/sensitive data
- "pii_categories": array of PII categories detected (e.g., "email", "phone", "aadhaar")
- "anomalies": array of anomaly descriptions
- "recommendations": array of improvement recommendations

Be factual and use only the information provided. Do not invent data."""


def analyze_issue(payload: Dict[str, Any]) -> Dict[str, str]:
    """Analyze any monitoring event (quality / drift / pii / pipeline / cloud).

    payload should contain keys like: category, dataset, connector, severity,
    metrics, before, after, error.
    """
    if not MISTRAL_API_KEY:
        return {
            "summary": "AI disabled (no MISTRAL_API_KEY configured).",
            "root_cause": "",
            "impact": "",
            "recommendation": "",
        }
    user_msg = (
        "Analyze the following monitoring event and respond with JSON only.\n\n"
        f"EVENT JSON:\n{json.dumps(payload, default=str)[:6000]}"
    )
    text = _chat(SYSTEM_PROMPT, user_msg)
    parsed = _parse_json_block(text)
    return {
        "summary": parsed.get("summary", "")[:1000],
        "root_cause": parsed.get("root_cause", "")[:1000],
        "impact": parsed.get("impact", "")[:1000],
        "recommendation": parsed.get("recommendation", "")[:1000],
    }


def validate_dataset_quality(
    dataset_metadata: Dict[str, Any],
    schema: List[Dict[str, Any]],
    sample_rows: Optional[List[Dict[str, Any]]] = None,
    rule_chunks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Validate dataset quality using LLM and provided Rule Books."""
    if not MISTRAL_API_KEY:
        logger.warning("AI quality validation disabled: no MISTRAL_API_KEY")
        return {
            "quality_score": 80.0,
            "issues": ["AI validation disabled"],
            "pii_columns": [],
            "pii_categories": [],
            "anomalies": [],
            "recommendations": ["Enable AI for comprehensive quality checks"],
        }
    
    user_input = {
        "dataset_metadata": dataset_metadata,
        "schema": schema,
        "sample_rows": sample_rows or [],
        "rule_books": rule_chunks or [],
    }
    
    user_msg = f"""Validate the quality of this dataset using the provided Rule Books.

DATASET INFORMATION:
{json.dumps(user_input, default=str, indent=2)}

Respond with JSON only as specified."""
    
    text = _chat(QUALITY_VALIDATION_SYSTEM_PROMPT, user_msg, timeout=90, max_tokens=3000)
    parsed = _parse_json_block(text)
    
    # Ensure we have valid defaults
    return {
        "quality_score": float(parsed.get("quality_score", 80.0)),
        "issues": parsed.get("issues", []),
        "pii_columns": parsed.get("pii_columns", []),
        "pii_categories": parsed.get("pii_categories", []),
        "anomalies": parsed.get("anomalies", []),
        "recommendations": parsed.get("recommendations", []),
    }


def summarize_monitoring_snapshot(snapshot: Dict[str, Any]) -> str:
    """Plain-text rollup summary of overall platform health."""
    if not MISTRAL_API_KEY:
        return ""
    sys = (
        "You write short, factual executive summaries of data platform health. "
        "Use only the metrics in the user message. <= 120 words. Plain prose."
    )
    user = "METRICS:\n" + json.dumps(snapshot, default=str)[:5000]
    return _chat(sys, user)
