"""Rule book controller - manage data quality rules and validation."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional
import os
import json

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user
from utils.vector_helper import add_rule_book_to_index, search_rule_books, delete_rule_book_from_index
from utils.common import logger

router = APIRouter(prefix="/api/rule-books", tags=["rule-books"])

UPLOAD_DIR = os.getenv("RULE_BOOK_UPLOAD_DIR", "./data/rule_books")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _extract_text_from_file(file: UploadFile) -> str:
    """Extract text content from uploaded file."""
    content = file.file.read()
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return content.decode("latin-1")
        except Exception as e:
            logger.error("Failed to decode file: %s", e)
            raise HTTPException(status_code=400, detail="Could not decode file content")


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
        
        if rule_book.get("file_path") and os.path.exists(rule_book["file_path"]):
            try:
                with open(rule_book["file_path"], "r", encoding="utf-8") as f:
                    rule_book["content"] = f.read()
            except Exception as e:
                logger.warning("Failed to read rule book file: %s", e)
        
        return rule_book
    except Exception as e:
        logger.warning("rule_books table not found: %s", e)
        raise HTTPException(status_code=404, detail="Rule book not found")


@router.post("/create")
def create_rule_book(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    connector_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Create a rule book by uploading a TXT file."""
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="Only TXT files are supported")
    
    try:
        content = _extract_text_from_file(file)
        
        if not content.strip():
            raise HTTPException(status_code=400, detail="File content is empty")
        
        file_ext = os.path.splitext(file.filename)[1]
        safe_filename = f"rule_book_{int(os.times()[4])}{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        result = execute(
            "INSERT INTO rule_books (name, description, filename, file_path, connector_type, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
            (name, description, file.filename, file_path, connector_type, user.get("id") or user.get("user_id")),
        )
        rule_book_id = result["last_insert_id"]
        
        try:
            metadata = {
                "filename": file.filename,
                "uploaded_by": user.get("id") or user.get("user_id"),
                "connector_type": connector_type,
                "created_at": str(os.times()[4]),
            }
            add_rule_book_to_index(content, rule_book_id, name, metadata)
        except Exception as e:
            logger.warning("Failed to add rule book to vector index: %s", e)
        
        return fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create rule book: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create rule book")


@router.delete("/{rule_book_id}")
def delete_rule_book(rule_book_id: int, user: dict = Depends(get_current_user)):
    try:
        rule_book = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
        
        if rule_book:
            if rule_book.get("file_path") and os.path.exists(rule_book["file_path"]):
                try:
                    os.remove(rule_book["file_path"])
                except Exception as e:
                    logger.warning("Failed to delete rule book file: %s", e)
            
            try:
                delete_rule_book_from_index(rule_book_id)
            except Exception as e:
                logger.warning("Failed to delete rule book from index: %s", e)
        
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
        
        content = ""
        if rule_book.get("file_path") and os.path.exists(rule_book["file_path"]):
            try:
                with open(rule_book["file_path"], "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.warning("Failed to read rule book file: %s", e)
        
        if not content:
            return []
        
        try:
            results = search_rule_books(content, top_k=top_k, connector_type=rule_book.get("connector_type"))
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
