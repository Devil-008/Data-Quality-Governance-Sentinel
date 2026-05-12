"""LLM-based rule evaluation for quality checks using Chroma DB."""

import json
import os
from typing import Dict, Any, List, Optional, Tuple
from utils.chroma_helper import search_rulebooks, get_rulebook_content
from utils.common import logger

try:
    from mistralai.client import MistralClient
    from mistralai.models.chat_message import ChatMessage

    HAS_MISTRAL = True
except ImportError:
    HAS_MISTRAL = False

# Get Mistral config from environment
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")


def get_llm_client():
    """Get Mistral client for LLM evaluation."""
    if not HAS_MISTRAL:
        logger.warning("Mistral SDK not installed. LLM evaluation disabled.")
        return None
    
    if not MISTRAL_API_KEY:
        logger.warning("MISTRAL_API_KEY not configured. LLM evaluation disabled.")
        return None
    
    try:
        return MistralClient(api_key=MISTRAL_API_KEY)
    except Exception as e:
        logger.error("Failed to initialize Mistral client: %s", e)
        return None


def fetch_applicable_rules(dataset_info: Dict[str, Any], connector_type: str) -> str:
    """Fetch applicable rules from Chroma DB based on dataset and connector type."""
    try:
        # Search for rules matching the dataset/connector type
        query = f"Quality check rules for {connector_type} datasets"
        results = search_rulebooks(query, top_k=10, connector_type=connector_type)

        if not results:
            logger.warning(
                "No rules found in Chroma for connector type: %s", connector_type
            )
            return ""

        # Combine relevant rules
        rules_text = "\n\n".join(
            [
                f"Rulebook: {r['name']}\nContent:\n{r['content']}"
                for r in results
                if r.get("content")
            ]
        )

        return rules_text
    except Exception as e:
        logger.error("Failed to fetch rules from Chroma: %s", e)
        return ""


def evaluate_quality_with_llm(
    dataset_info: Dict[str, Any],
    dataset_metrics: Dict[str, Any],
    connector_type: str,
    sample_data: Optional[Dict[str, Any]] = None,
) -> Tuple[float, List[str], Dict[str, Any]]:
    """Use LLM to evaluate dataset quality based on rulebook rules."""

    client = get_llm_client()
    if not client:
        logger.warning("LLM evaluation not available")
        return 100.0, [], {}

    try:
        # Fetch applicable rules from Chroma
        rules_content = fetch_applicable_rules(dataset_info, connector_type)

        if not rules_content:
            logger.warning("No rules available for evaluation")
            return 100.0, [], {}

        # Prepare context for LLM
        prompt = f"""You are a data quality expert. Evaluate the following dataset based on the provided rulebook rules.

RULEBOOK RULES:
{rules_content}

DATASET INFORMATION:
- Name: {dataset_info.get('dataset_name')}
- Schema: {dataset_info.get('schema_name')}
- Type: {dataset_info.get('dataset_type')}
- Row Count: {dataset_info.get('row_count')}
- Column Count: {dataset_info.get('column_count')}

DATASET METRICS:
{json.dumps(dataset_metrics, indent=2)}

Based on the rules and metrics, provide:
1. A quality score (0-100)
2. List of specific issues found
3. Recommendations for improvement

Format your response as JSON with keys: "score", "issues", "recommendations"
"""

        # Call Mistral API
        message = client.chat(
            model=MISTRAL_MODEL,
            messages=[ChatMessage(role="user", content=prompt)]
        )

        response_text = message.choices[0].message.content

        # Parse JSON response
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)

                score = float(result.get("score", 100))
                issues = result.get("issues", [])
                recommendations = result.get("recommendations", [])

                return (
                    score,
                    issues,
                    {"recommendations": recommendations, "llm_evaluation": True},
                )
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response: %s", e)
            return 100.0, [], {"error": str(e)}

    except Exception as e:
        logger.error("LLM evaluation failed: %s", e)
        return 100.0, [], {"error": str(e)}


def evaluate_pii_with_llm(
    dataset_info: Dict[str, Any], column_info: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Use LLM to identify PII in dataset based on rulebook patterns."""

    client = get_llm_client()
    if not client:
        logger.warning("LLM PII evaluation not available")
        return {"contains_pii": False, "pii_categories": []}

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text

        # Parse JSON response
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)

                score = float(result.get("score", 100))
                issues = result.get("issues", [])
                recommendations = result.get("recommendations", [])

                return (
                    score,
                    issues,
                    {"recommendations": recommendations, "llm_evaluation": True},
                )
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response: %s", e)
            return 100.0, [], {"error": str(e)}

    except Exception as e:
        logger.error("LLM evaluation failed: %s", e)
        return 100.0, [], {"error": str(e)}


def evaluate_pii_with_llm(
    dataset_info: Dict[str, Any], column_info: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Use LLM to identify PII in dataset based on rulebook patterns."""

    client = get_llm_client()
    if not client:
        logger.warning("LLM PII evaluation not available")
        return {"contains_pii": False, "pii_categories": []}

    try:
        prompt = f"""You are a data privacy expert. Analyze the following dataset columns and identify any Personally Identifiable Information (PII).

DATASET: {dataset_info.get('dataset_name')}
CONNECTOR TYPE: {dataset_info.get('connector_type')}

COLUMNS:
{json.dumps(column_info, indent=2)}

Based on the column names and data types, identify:
1. Which columns contain PII
2. Category of PII (email, phone, ssn, credit_card, address, dob, etc.)
3. Risk level (high, medium, low)
4. Recommended actions

Format your response as JSON with keys: "contains_pii", "pii_columns", "pii_categories", "risk_level", "recommended_actions"
"""

        # Call Mistral API
        message = client.chat(
            model=MISTRAL_MODEL,
            messages=[ChatMessage(role="user", content=prompt)]
        )

        response_text = message.choices[0].message.content

        # Parse JSON response
        try:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                return result
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse PII response: %s", e)
            return {"contains_pii": False, "pii_categories": []}

    except Exception as e:
        logger.error("PII evaluation failed: %s", e)
        return {"contains_pii": False, "pii_categories": [], "error": str(e)}


__all__ = [
    "get_llm_client",
    "fetch_applicable_rules",
    "evaluate_quality_with_llm",
    "evaluate_pii_with_llm",
]
