"""Mistral AI helper — analyzes real monitoring data and returns structured insights.

Used by the monitoring/alerts pipeline and by the AI controller. Never invents
data — caller passes real metrics in, the model produces analysis only.
"""
import os
import json
import requests
from typing import Dict, Any
from dotenv import load_dotenv

from utils.common import logger

load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_API_URL = os.getenv(
    "MISTRAL_API_URL",
    "https://api.mistral.ai/v1/chat/completions",
)


def _chat(system: str, user: str, timeout: int = 30) -> str:
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
                "temperature": 0.2,
                "max_tokens": 700,
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
