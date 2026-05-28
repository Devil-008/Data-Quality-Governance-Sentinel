# """Rule book controller - manage data quality rules and validation."""

# from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
# from typing import Optional
# import os
# import json
# import time

# from database.db_connection import fetch_all, fetch_one, execute
# from middleware.auth_middleware import get_current_user
# from utils.vector_helper import (
#     add_rule_book_to_index,
#     search_rule_books,
#     delete_rule_book_from_index,
# )
# from utils.common import logger

# router = APIRouter(prefix="/api/rule-books", tags=["rule-books"])

# UPLOAD_DIR = os.getenv("RULE_BOOK_UPLOAD_DIR", "./data/rule_books")
# os.makedirs(UPLOAD_DIR, exist_ok=True)


# def _extract_text_from_file(file: UploadFile) -> str:
#     """Extract text content from uploaded file."""
#     content = file.file.read()
#     try:
#         return content.decode("utf-8")
#     except UnicodeDecodeError:
#         try:
#             return content.decode("latin-1")
#         except Exception as e:
#             logger.error("Failed to decode file: %s", e)
#             raise HTTPException(status_code=400, detail="Could not decode file content")


# @router.get("/list")
# def list_rule_books(user: dict = Depends(get_current_user)):
#     try:
#         rule_books = fetch_all("SELECT * FROM rule_books ORDER BY created_at DESC")
#         # Filter: only return rule books that are properly indexed (file exists + in ChromaDB)
#         valid_books = []
#         for rb in rule_books:
#             if rb.get("file_path") and os.path.exists(rb["file_path"]):
#                 valid_books.append(rb)
#             else:
#                 logger.warning(
#                     "Rule book %d (%s) file missing, removing from index",
#                     rb.get("id"),
#                     rb.get("name"),
#                 )
#                 try:
#                     delete_rule_book_from_index(rb.get("id"))
#                     execute("DELETE FROM rule_books WHERE id=%s", (rb.get("id"),))
#                 except Exception as e:
#                     logger.warning("Failed to cleanup orphaned rule book %d: %s", rb.get("id"), e)
#         return valid_books
#     except Exception as e:
#         logger.warning("rule_books table not found: %s", e)
#         return []


# @router.get("/{rule_book_id}")
# def get_rule_book(rule_book_id: int, user: dict = Depends(get_current_user)):
#     try:
#         rule_book = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
#         if not rule_book:
#             raise HTTPException(status_code=404, detail="Rule book not found")

#         if rule_book.get("file_path") and os.path.exists(rule_book["file_path"]):
#             try:
#                 with open(rule_book["file_path"], "r", encoding="utf-8") as f:
#                     rule_book["content"] = f.read()
#             except Exception as e:
#                 logger.warning("Failed to read rule book file: %s", e)

#         return rule_book
#     except Exception as e:
#         logger.warning("rule_books table not found: %s", e)
#         raise HTTPException(status_code=404, detail="Rule book not found")


# @router.post("/create")
# def create_rule_book(
#     file: UploadFile = File(...),
#     user: dict = Depends(get_current_user),
# ):
#     """Create a rule book by uploading a TXT file. Name is auto-generated from filename."""
#     if not file.filename.endswith(".txt"):
#         raise HTTPException(status_code=400, detail="Only TXT files are supported")

#     try:
#         content = _extract_text_from_file(file)

#         if not content.strip():
#             raise HTTPException(status_code=400, detail="File content is empty")

#         # Auto-generate name from filename (remove .txt and replace _ with space)
#         auto_name = file.filename.replace(".txt", "").replace("_", " ").strip()
#         if not auto_name:
#             auto_name = file.filename

#         file_ext = os.path.splitext(file.filename)[1]
#         safe_filename = f"rule_book_{int(time.time())}{file_ext}"
#         file_path = os.path.join(UPLOAD_DIR, safe_filename)

#         with open(file_path, "w", encoding="utf-8") as f:
#             f.write(content)

#         result = execute(
#             "INSERT INTO rule_books (name, description, filename, file_path, connector_type, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
#             (
#                 auto_name,
#                 None,
#                 file.filename,
#                 file_path,
#                 None,
#                 user.get("id") or user.get("user_id"),
#             ),
#         )
#         rule_book_id = result

#         # Add to ChromaDB - if this fails, delete from DB
#         try:
#             metadata = {
#                 "filename": file.filename,
#                 "uploaded_by": user.get("id") or user.get("user_id"),
#                 "created_at": str(int(time.time())),
#             }
#             add_rule_book_to_index(content, rule_book_id, auto_name, metadata)
#             logger.info("Rule book %d added to vector index", rule_book_id)
#         except Exception as e:
#             logger.exception("Failed to add rule book to ChromaDB, rolling back")
#             # Rollback: delete from DB and disk
#             try:
#                 execute("DELETE FROM rule_books WHERE id=%s", (rule_book_id,))
#                 if os.path.exists(file_path):
#                     os.remove(file_path)
#             except Exception as cleanup_e:
#                 logger.warning("Cleanup failed: %s", cleanup_e)
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Failed to index rule book: {str(e)[:100]}",
#             )

#         logger.info(
#             "Created rule book: id=%d, name=%s, file=%s (indexed)",
#             rule_book_id,
#             auto_name,
#             file.filename,
#         )
#         return fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.exception("Failed to create rule book")
#         raise HTTPException(status_code=500, detail="Failed to create rule book")


# @router.delete("/{rule_book_id}")
# def delete_rule_book(rule_book_id: int, user: dict = Depends(get_current_user)):
#     try:
#         rule_book = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))

#         if rule_book:
#             if rule_book.get("file_path") and os.path.exists(rule_book["file_path"]):
#                 try:
#                     os.remove(rule_book["file_path"])
#                 except Exception as e:
#                     logger.warning("Failed to delete rule book file: %s", e)

#             try:
#                 delete_rule_book_from_index(rule_book_id)
#             except Exception as e:
#                 logger.warning("Failed to delete rule book from index: %s", e)

#         execute("DELETE FROM rule_books WHERE id=%s", (rule_book_id,))
#         return {"status": "success", "message": "Rule book deleted"}
#     except Exception as e:
#         logger.warning("rule_books table not found: %s", e)
#         return {"status": "success", "message": "Rule book deleted"}


# @router.get("/{rule_book_id}/search-similar")
# def search_similar_rules(
#     rule_book_id: int, top_k: int = 5, user: dict = Depends(get_current_user)
# ):
#     try:
#         rule_book = fetch_one("SELECT * FROM rule_books WHERE id=%s", (rule_book_id,))
#         if not rule_book:
#             raise HTTPException(status_code=404, detail="Rule book not found")

#         content = ""
#         if rule_book.get("file_path") and os.path.exists(rule_book["file_path"]):
#             try:
#                 with open(rule_book["file_path"], "r", encoding="utf-8") as f:
#                     content = f.read()
#             except Exception as e:
#                 logger.warning("Failed to read rule book file: %s", e)

#         if not content:
#             return []

#         try:
#             results = search_rule_books(
#                 content, top_k=top_k, connector_type=rule_book.get("connector_type")
#             )
#             return results
#         except Exception as e:
#             logger.warning("Vector search failed: %s", e)
#             return []
#     except Exception as e:
#         logger.warning("rule_books table not found: %s", e)
#         raise HTTPException(status_code=404, detail="Rule book not found")


# @router.get("/datasets/{dataset_id}/rules")
# def get_dataset_rules(dataset_id: int, user: dict = Depends(get_current_user)):
#     try:
#         return fetch_all(
#             "SELECT * FROM dataset_validation_rules WHERE dataset_id=%s ORDER BY created_at DESC",
#             (dataset_id,),
#         )
#     except Exception as e:
#         logger.warning("dataset_validation_rules table not found: %s", e)
#         return []


# @router.post("/datasets/{dataset_id}/rules")
# def create_dataset_rule(
#     dataset_id: int,
#     rule_name: str,
#     rule_type: str,
#     rule_config: str,
#     rule_book_id: Optional[int] = None,
#     user: dict = Depends(get_current_user),
# ):
#     try:
#         result = execute(
#             "INSERT INTO dataset_validation_rules (dataset_id, rule_book_id, rule_name, rule_type, rule_config) VALUES (%s, %s, %s, %s, %s)",
#             (dataset_id, rule_book_id, rule_name, rule_type, rule_config),
#         )
#         return fetch_one(
#             "SELECT * FROM dataset_validation_rules WHERE id=%s",
#             (result["last_insert_id"],),
#         )
#     except Exception as e:
#         logger.error("Failed to create dataset rule: %s", e)
#         raise HTTPException(status_code=500, detail="Failed to create dataset rule")


# @router.post("/{rule_book_id}/rules")
# def add_rule_to_rule_book(
#     rule_book_id: int,
#     rule_name: str,
#     rule_type: str,
#     rule_config: str,
#     user: dict = Depends(get_current_user),
# ):
#     try:
#         result = execute(
#             "INSERT INTO dataset_validation_rules (rule_book_id, rule_name, rule_type, rule_config, is_active) VALUES (%s, %s, %s, %s, 1)",
#             (rule_book_id, rule_name, rule_type, rule_config),
#         )
#         return fetch_one(
#             "SELECT * FROM dataset_validation_rules WHERE id=%s",
#             (result["last_insert_id"],),
#         )
#     except Exception as e:
#         logger.error("Failed to add rule to rule book: %s", e)
#         raise HTTPException(status_code=500, detail="Failed to add rule")


# @router.get("/{rule_book_id}/rules")
# def get_rule_book_rules(rule_book_id: int, user: dict = Depends(get_current_user)):
#     try:
#         return fetch_all(
#             "SELECT * FROM dataset_validation_rules WHERE rule_book_id=%s ORDER BY created_at DESC",
#             (rule_book_id,),
#         )
#     except Exception as e:
#         logger.warning("dataset_validation_rules table not found: %s", e)
#         return []


# @router.delete("/datasets/{dataset_id}/rules/{rule_id}")
# def delete_dataset_rule(
#     dataset_id: int, rule_id: int, user: dict = Depends(get_current_user)
# ):
#     try:
#         execute(
#             "DELETE FROM dataset_validation_rules WHERE id=%s AND dataset_id=%s",
#             (rule_id, dataset_id),
#         )
#         return {"status": "success", "message": "Rule deleted"}
#     except Exception as e:
#         logger.warning("dataset_validation_rules table not found: %s", e)
#         return {"status": "success", "message": "Rule deleted"}


# @router.delete("/{rule_book_id}/rules/{rule_id}")
# def delete_rule_from_rule_book(
#     rule_book_id: int, rule_id: int, user: dict = Depends(get_current_user)
# ):
#     try:
#         execute(
#             "DELETE FROM dataset_validation_rules WHERE id=%s AND rule_book_id=%s",
#             (rule_id, rule_book_id),
#         )
#         return {"status": "success", "message": "Rule deleted"}
#     except Exception as e:
#         logger.warning("dataset_validation_rules table not found: %s", e)
#         return {"status": "success", "message": "Rule deleted"}


"""Rule book controller — upload triggers automatic quality scan across all
datasets of the matching connector type. No jobs, no manual triggers."""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks

from database.db_connection import fetch_all, fetch_one, execute
from middleware.auth_middleware import get_current_user
from utils.common import logger
from utils.vector_helper import add_rule_book_to_index, delete_rule_book_from_index

router = APIRouter(prefix="/api/rule-books", tags=["rulebooks"])


# Connector-type normalization
_TYPE_TO_RULEBOOK = {
    "azure_adf": "ADF", "adf": "ADF",
    "mysql": "MYSQL", "mssql": "MSSQL",
    "databricks": "DATABRICKS", "github": "GITHUB",
}
_RULEBOOK_TO_DB_TYPE = {
    "ADF": "azure_adf", "MYSQL": "mysql", "MSSQL": "mssql",
    "DATABRICKS": "databricks", "GITHUB": "github",
}
_VALID_RULEBOOK_TYPES = {"ADF", "MYSQL", "MSSQL", "DATABRICKS", "GITHUB"}


def normalize_connector_type(ctype: str) -> str:
    if not ctype:
        return ""
    return _TYPE_TO_RULEBOOK.get(ctype.strip().lower(), ctype.strip().upper())


def db_connector_type(rulebook_type: str) -> str:
    """Convert rulebook type (ADF) → DB connector type (azure_adf)."""
    return _RULEBOOK_TO_DB_TYPE.get(rulebook_type.upper(), rulebook_type.lower())


def collection_name(ctype: str) -> str:
    return f"{normalize_connector_type(ctype).lower()}_rulebook"


# ======================================================================
#  UPLOAD — triggers automatic quality scan in background
# ======================================================================
@router.post("/create")
def upload_rulebook(
    background: BackgroundTasks,
    # connector_type: str = Form(...),
    connector_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    # ctype = normalize_connector_type(connector_type)
    # if ctype not in _VALID_RULEBOOK_TYPES:
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"Invalid connector type. Use one of: {sorted(_VALID_RULEBOOK_TYPES)}",
    #     )

    # ==========================================================
    # AUTO-DETECT CONNECTOR TYPE FROM FILE CONTENT
    # ==========================================================

    raw = file.file.read()

    try:
        content = raw.decode("utf-8")

    except UnicodeDecodeError:
        content = raw.decode("latin-1", errors="ignore")


    if not connector_type:

        sample = content[:5000].lower()

        if any(x in sample for x in [
            "adf",
            "pipeline",
            "linkedservice",
            "integrationruntime",
            "datafactory"
        ]):
            connector_type = "ADF"

        elif any(x in sample for x in [
            "databricks",
            "delta",
            "notebook",
            "cluster",
            "spark"
        ]):
            connector_type = "DATABRICKS"

        elif any(x in sample for x in [
            "mysql",
            "innodb",
            "varchar",
            "auto_increment"
        ]):
            connector_type = "MYSQL"

        elif any(x in sample for x in [
            "mssql",
            "sql server",
            "nvarchar",
            "dbo."
        ]):
            connector_type = "MSSQL"

        elif any(x in sample for x in [
            "github",
            "workflow",
            "actions",
            ".yml"
        ]):
            connector_type = "GITHUB"

        else:
            connector_type = "MYSQL"  

    ctype = normalize_connector_type(connector_type)

    if ctype not in _VALID_RULEBOOK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid connector type. Use one of: {sorted(_VALID_RULEBOOK_TYPES)}",
        )
    
    if not content.strip():
        raise HTTPException(status_code=400, detail="File content is empty")

    rb_id = execute(
        "INSERT INTO rulebook (connector_type, rulebook_name, rulebook_content, created_at) "
        "VALUES (%s, %s, %s, %s)",
        (ctype, file.filename, content, datetime.datetime.utcnow()),
    )

    # Index into ChromaDB
    try:
        add_rule_book_to_index(
            content=content, rule_book_id=rb_id, name=file.filename,
            metadata={
                "rulebook_id": rb_id, "connector_type": ctype,
                "uploaded_by": user.get("id") or user.get("user_id"),
                "created_at":  datetime.datetime.utcnow().isoformat(),
            },
            collection=collection_name(ctype),
        )
        logger.info("Rulebook %s indexed in %s", rb_id, collection_name(ctype))
    except TypeError:
        try:
            add_rule_book_to_index(content, rb_id, file.filename,
                                   {"connector_type": ctype, "rulebook_id": rb_id})
        except Exception as e:
            logger.warning("ChromaDB index failed (compat): %s", e)
    except Exception as e:
        logger.exception("ChromaDB index failed — rolling back DB row")
        execute("DELETE FROM rulebook WHERE id=%s", (rb_id,))
        raise HTTPException(status_code=500, detail=f"Index failed: {str(e)[:120]}")

    # AUTO-TRIGGER: scan all datasets of this connector type
    db_type = db_connector_type(ctype)
    from controllers.monitoring_controller import run_quality_for_connector_type
    background.add_task(run_quality_for_connector_type, db_type, rb_id)
    logger.info(
        "Auto-triggered quality scan for connector_type=%s after rulebook %s upload",
        db_type, rb_id,
    )

    rb = fetch_one("SELECT * FROM rulebook WHERE id=%s", (rb_id,))
    return {
        **rb,
        "scan_triggered": True,
        "message": f"Rulebook uploaded. Quality scan started for all {ctype} datasets.",
    }


# ======================================================================
#  LIST — single GET API
# ======================================================================
@router.get("")
def list_rulebooks(user: dict = Depends(get_current_user)):
    return fetch_all(
        "SELECT id, connector_type, rulebook_name, rulebook_content, created_at "
        "FROM rulebook ORDER BY created_at DESC"
    )


# ======================================================================
#  DELETE
# ======================================================================
@router.delete("/{rulebook_id}")
def delete_rulebook(rulebook_id: int, user: dict = Depends(get_current_user)):
    row = fetch_one("SELECT id, connector_type FROM rulebook WHERE id=%s", (rulebook_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Rulebook not found")
    execute("DELETE FROM rulebook WHERE id=%s", (rulebook_id,))
    try:
        delete_rule_book_from_index(rulebook_id, collection=collection_name(row["connector_type"]))
    except TypeError:
        try:
            delete_rule_book_from_index(rulebook_id)
        except Exception as e:
            logger.warning("Chroma delete failed: %s", e)
    except Exception as e:
        logger.warning("Chroma delete failed: %s", e)
    return {"status": "success"}


# ======================================================================
#  HELPER — used by monitoring
# ======================================================================
def get_latest_rulebook(connector_type: str) -> Optional[dict]:
    ctype = normalize_connector_type(connector_type)
    return fetch_one(
        "SELECT id, connector_type, rulebook_name, rulebook_content, created_at "
        "FROM rulebook WHERE connector_type=%s "
        "ORDER BY created_at DESC LIMIT 1",
        (ctype,),
    )