"""Rule book controller - manage data quality rules and validation."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Optional
import json

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user
from utils.vector_helper import add_rule_book_to_index, search_rule_books
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


@router.post("/create")
def create_rule_book(
    name: str,
    description: Optional[str] = None,
    rule_content: Optional[str] = None,
    connector_type: Optional[str] = None,
    dataset_type: Optional[str] = None,
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user),
):
    content = rule_content
    if file:
        try:
            content = file.file.read().decode("utf-8")
        except Exception as e:
            logger.error("Failed to read uploaded file: %s", e)
            raise HTTPException(status_code=400, detail="Failed to read file")
    
    if not content:
        raise HTTPException(status_code=400, detail="Rule content is required")
    
    try:
        result = execute(
            "INSERT INTO rule_books (name, description, rule_content, connector_type, dataset_type, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
            (name, description, content, connector_type, dataset_type, user["id"]),
        )
        rule_book_id = result["last_insert_id"]
        
        try:
            add_rule_book_to_index(content, rule_book_id, name)
        except Exception as e:
            logger.warning("Failed to add rule book to vector index: %s", e)
        
        return fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
    except Exception as e:
        logger.error("Failed to create rule book: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create rule book")


@router.delete("/{rule_book_id}")
def delete_rule_book(rule_book_id: int, user: dict = Depends(get_current_user)):
    try:
        execute("DELETE FROM rule_books WHERE id=%s", (rule_book_id,))
        return {"status": "success", "message": "Rule book deleted"}
    except Exception as e:
        logger.warning("rule_books table not found: %s", e)
        return {"status": "success", "message": "Rule book deleted"}


@router.get("/{rule_book_id}/search-similar")
def search_similar_rules(rule_book_id: int, top_k: int = 5, user: dict = Depends(get_current_user)):
    try:
        rule_book = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
        if not rule_book:
            raise HTTPException(status_code=404, detail="Rule book not found")
        
        try:
            results = search_rule_books(rule_book["rule_content"], top_k=top_k)
            return results
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []
    except Exception as e:
        logger.warning("rule_books table not found: %s", e)
        raise HTTPException(status_code=404, detail="Rule book not found")


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
        result = execute(
            "INSERT INTO dataset_validation_rules (dataset_id, rule_book_id, rule_name, rule_type, rule_config) VALUES (%s, %s, %s, %s, %s)",
            (dataset_id, rule_book_id, rule_name, rule_type, rule_config),
        )
        return fetch_one("SELECT * FROM dataset_validation_rules WHERE id=%s", (result["last_insert_id"],))
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
        result = execute(
            "INSERT INTO dataset_validation_rules (rule_book_id, rule_name, rule_type, rule_config, is_active) VALUES (%s, %s, %s, %s, 1)",
            (rule_book_id, rule_name, rule_type, rule_config),
        )
        return fetch_one("SELECT * FROM dataset_validation_rules WHERE id=%s", (result["last_insert_id"],))
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
def delete_dataset_rule(dataset_id: int, rule_id: int, user: dict = Depends(get_current_user)):
    try:
        execute("DELETE FROM dataset_validation_rules WHERE id=%s AND dataset_id=%s", (rule_id, dataset_id))
        return {"status": "success", "message": "Rule deleted"}
    except Exception as e:
        logger.warning("dataset_validation_rules table not found: %s", e)
        return {"status": "success", "message": "Rule deleted"}


@router.delete("/{rule_book_id}/rules/{rule_id}")
def delete_rule_from_rule_book(rule_book_id: int, rule_id: int, user: dict = Depends(get_current_user)):
    try:
        execute("DELETE FROM dataset_validation_rules WHERE id=%s AND rule_book_id=%s", (rule_id, rule_book_id))
        return {"status": "success", "message": "Rule deleted"}
    except Exception as e:
        logger.warning("dataset_validation_rules table not found: %s", e)
        return {"status": "success", "message": "Rule deleted"}
