"""Rule book controller - manage data quality rules and validation."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional, Dict, Any, List
import json
import re

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user
from utils.chroma_helper import (
    add_rulebook_to_chroma,
    delete_rulebook_from_chroma,
    search_rulebooks,
)
from utils.common import logger

router = APIRouter(prefix="/api/rule-books", tags=["rule-books"])


@router.get("/list")
def list_rule_books(user: dict = Depends(get_current_user)):
    try:
        return fetch_all("SELECT * FROM rule_books ORDER BY created_at DESC")
    except Exception as e:
        logger.warning("rule_books table not found: %s", e)
        return []


@router.get("/{rule_book_id}")
def get_rule_book(rule_book_id: int, user: dict = Depends(get_current_user)):
    try:
        rule_book = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
        if not rule_book:
            raise HTTPException(status_code=404, detail="Rule book not found")
        return rule_book
    except Exception as e:
        logger.warning("rule_books table not found: %s", e)
        raise HTTPException(status_code=404, detail="Rule book not found")


def _parse_rulebook_txt(content: str) -> Dict[str, Any]:
    """Parse rulebook TXT format and extract structured rules."""
    lines = content.split("\n")
    result = {
        "name": "",
        "connector_type": "",
        "description": "",
        "rules": [],
        "quality_score_formula": "",
        "typical_alert_category": "",
    }

    current_rule = None
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Extract Rule Book Name
        if "Rule Book Name:" in line:
            result["name"] = lines[i + 1].strip() if i + 1 < len(lines) else ""
            i += 2
            continue

        # Extract Connector Type
        if "Connector Type:" in line:
            result["connector_type"] = (
                lines[i + 1].strip() if i + 1 < len(lines) else ""
            )
            i += 2
            continue

        # Extract Description
        if "Description:" in line:
            result["description"] = lines[i + 1].strip() if i + 1 < len(lines) else ""
            i += 2
            continue

        # Match rule header (e.g., "1. Rule Name")
        rule_match = re.match(r"^(\d+)\.\s+(.+)$", line)
        if rule_match:
            if current_rule:
                result["rules"].append(current_rule)
            current_rule = {
                "number": int(rule_match.group(1)),
                "name": rule_match.group(2),
                "purpose": "",
                "penalty": "",
                "rule_type": "custom_sql",
                "config": {},
            }
            i += 1
            continue

        # Extract Purpose
        if current_rule and "- Purpose:" in line:
            current_rule["purpose"] = line.replace("- Purpose:", "").strip()
            i += 1
            continue

        # Extract Penalty
        if current_rule and "- Penalty:" in line:
            current_rule["penalty"] = line.replace("- Penalty:", "").strip()
            i += 1
            continue

        # Extract Rule Type
        if current_rule and "- Rule Type:" in line:
            current_rule["rule_type"] = line.replace("- Rule Type:", "").strip()
            i += 1
            continue

        # Extract Quality Score Formula
        if "Quality Score Formula:" in line:
            result["quality_score_formula"] = (
                lines[i + 1].strip() if i + 1 < len(lines) else ""
            )
            i += 2
            continue

        # Extract Alert Category
        if "Typical Alert Category:" in line:
            result["typical_alert_category"] = (
                lines[i + 1].strip() if i + 1 < len(lines) else ""
            )
            i += 2
            continue

        i += 1

    if current_rule:
        result["rules"].append(current_rule)

    return result

    return result


@router.post("/create")
def create_rule_book(
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    connector_type: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user),
):
    """Create a new rulebook from uploaded TXT file."""
    content = None

    if file:
        try:
            content = file.file.read().decode("utf-8")
        except Exception as e:
            logger.error("Failed to read uploaded file: %s", e)
            raise HTTPException(status_code=400, detail="Failed to read file")
    else:
        raise HTTPException(status_code=400, detail="File upload is required")

    if not content:
        raise HTTPException(status_code=400, detail="File content cannot be empty")

    try:
        # Parse rulebook
        parsed = _parse_rulebook_txt(content)
        final_name = name or parsed.get("name") or "Imported Rulebook"
        final_description = description or parsed.get("description") or ""
        final_connector_type = connector_type or parsed.get("connector_type") or None

        # Save to database (without dataset_type)
        rule_book_id = execute(
            "INSERT INTO rule_books (name, description, rule_content, connector_type, created_by) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                final_name,
                final_description,
                content,
                final_connector_type,
                user["user_id"],
            ),
        )

        # Add extracted rules to database
        rules_created = 0
        for rule in parsed.get("rules", []):
            try:
                rule_config = json.dumps(rule.get("config", {}))
                execute(
                    "INSERT INTO dataset_validation_rules (rule_book_id, rule_name, rule_type, rule_config, is_active) "
                    "VALUES (%s, %s, %s, %s, 1)",
                    (
                        rule_book_id,
                        rule.get("name", f"Rule {rule.get('number')}"),
                        rule.get("rule_type", "custom_sql"),
                        rule_config,
                    ),
                )
                rules_created += 1
            except Exception as e:
                logger.warning("Failed to add rule %s: %s", rule.get("name"), e)

        # Add to Chroma vector DB
        try:
            add_rulebook_to_chroma(
                rule_book_id, final_name, content, final_connector_type
            )
        except Exception as e:
            logger.warning("Failed to add rulebook to Chroma: %s", e)

        logger.info("Created rulebook %s with %d rules", rule_book_id, rules_created)

        response = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
        if response:
            response["rules_created"] = rules_created
        return response
    except Exception as e:
        logger.error("Failed to create rule book: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to create rule book: {str(e)}"
        )


@router.delete("/{rule_book_id}")
def delete_rule_book(rule_book_id: int, user: dict = Depends(get_current_user)):
    try:
        # Delete from Chroma DB first
        try:
            delete_rulebook_from_chroma(rule_book_id)
        except Exception as e:
            logger.warning("Failed to delete from Chroma: %s", e)

        # Delete from database
        execute(
            "DELETE FROM dataset_validation_rules WHERE rule_book_id=%s",
            (rule_book_id,),
        )
        execute("DELETE FROM rule_books WHERE id=%s", (rule_book_id,))
        return {"status": "success", "message": "Rule book deleted"}
    except Exception as e:
        logger.error("Failed to delete rule book: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete rule book")


@router.get("/{rule_book_id}/search-similar")
def search_similar_rules(
    rule_book_id: int, top_k: int = 5, user: dict = Depends(get_current_user)
):
    """Search for similar rules in Chroma DB."""
    try:
        rule_book = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
        if not rule_book:
            raise HTTPException(status_code=404, detail="Rule book not found")

        try:
            # Search in Chroma DB
            results = search_rulebooks(
                rule_book["rule_content"],
                top_k=top_k,
                connector_type=rule_book.get("connector_type"),
            )
            return results
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to search similar rules: %s", e)
        raise HTTPException(status_code=500, detail="Failed to search")


@router.get("/datasets/{dataset_id}/rules")
def get_dataset_rules(dataset_id: int, user: dict = Depends(get_current_user)):
    try:
        return fetch_all(
            "SELECT * FROM dataset_validation_rules WHERE dataset_id=%s ORDER BY created_at DESC",
            (dataset_id,),
        )
    except Exception as e:
        logger.warning("dataset_validation_rules table not found: %s", e)
        return []


@router.post("/datasets/{dataset_id}/rules")
def create_dataset_rule(
    dataset_id: int,
    rule_name: str,
    rule_type: str,
    rule_config: str,
    rule_book_id: Optional[int] = None,
    user: dict = Depends(get_current_user),
):
    try:
        rule_id = execute(
            "INSERT INTO dataset_validation_rules (dataset_id, rule_book_id, rule_name, rule_type, rule_config) VALUES (%s, %s, %s, %s, %s)",
            (dataset_id, rule_book_id, rule_name, rule_type, rule_config),
        )
        return fetch_one(
            "SELECT * FROM dataset_validation_rules WHERE id=%s",
            (rule_id,),
        )
    except Exception as e:
        logger.error("Failed to create dataset rule: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create dataset rule")


@router.post("/{rule_book_id}/rules")
def add_rule_to_rule_book(
    rule_book_id: int,
    rule_name: str,
    rule_type: str,
    rule_config: str,
    user: dict = Depends(get_current_user),
):
    try:
        rule_id = execute(
            "INSERT INTO dataset_validation_rules (rule_book_id, rule_name, rule_type, rule_config, is_active) VALUES (%s, %s, %s, %s, 1)",
            (rule_book_id, rule_name, rule_type, rule_config),
        )
        return fetch_one(
            "SELECT * FROM dataset_validation_rules WHERE id=%s",
            (rule_id,),
        )
    except Exception as e:
        logger.error("Failed to add rule to rule book: %s", e)
        raise HTTPException(status_code=500, detail="Failed to add rule")


@router.get("/{rule_book_id}/rules")
def get_rule_book_rules(rule_book_id: int, user: dict = Depends(get_current_user)):
    try:
        return fetch_all(
            "SELECT * FROM dataset_validation_rules WHERE rule_book_id=%s ORDER BY created_at DESC",
            (rule_book_id,),
        )
    except Exception as e:
        logger.warning("dataset_validation_rules table not found: %s", e)
        return []


@router.delete("/datasets/{dataset_id}/rules/{rule_id}")
def delete_dataset_rule(
    dataset_id: int, rule_id: int, user: dict = Depends(get_current_user)
):
    try:
        execute(
            "DELETE FROM dataset_validation_rules WHERE id=%s AND dataset_id=%s",
            (rule_id, dataset_id),
        )
        return {"status": "success", "message": "Rule deleted"}
    except Exception as e:
        logger.warning("dataset_validation_rules table not found: %s", e)
        return {"status": "success", "message": "Rule deleted"}


@router.delete("/{rule_book_id}/rules/{rule_id}")
def delete_rule_from_rule_book(
    rule_book_id: int, rule_id: int, user: dict = Depends(get_current_user)
):
    try:
        execute(
            "DELETE FROM dataset_validation_rules WHERE id=%s AND rule_book_id=%s",
            (rule_id, rule_book_id),
        )
        return {"status": "success", "message": "Rule deleted"}
    except Exception as e:
        logger.warning("dataset_validation_rules table not found: %s", e)
        return {"status": "success", "message": "Rule deleted"}
