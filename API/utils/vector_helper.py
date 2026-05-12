"""Vector DB helper using Chroma DB for rule books and monitoring logs."""
import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions

from utils.common import logger

load_dotenv()

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
MODEL_NAME = os.getenv("VECTOR_MODEL", "all-MiniLM-L6-v2")

_client: Optional[chromadb.Client] = None
_rule_book_collection: Optional[chromadb.Collection] = None
_monitoring_log_collection: Optional[chromadb.Collection] = None


def _get_client() -> chromadb.Client:
    global _client
    if _client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        logger.info("Chroma DB client initialized at %s", CHROMA_PERSIST_DIR)
    return _client


def _get_embedding_function():
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=MODEL_NAME)


def _get_rule_book_collection() -> chromadb.Collection:
    global _rule_book_collection
    if _rule_book_collection is None:
        client = _get_client()
        _rule_book_collection = client.get_or_create_collection(
            name="rule_books",
            embedding_function=_get_embedding_function(),
            metadata={"description": "Data quality rule books"},
        )
        logger.info("Rule book collection ready")
    return _rule_book_collection


def _get_monitoring_log_collection() -> chromadb.Collection:
    global _monitoring_log_collection
    if _monitoring_log_collection is None:
        client = _get_client()
        _monitoring_log_collection = client.get_or_create_collection(
            name="monitoring_logs",
            embedding_function=_get_embedding_function(),
            metadata={"description": "Monitoring logs for AI analysis"},
        )
        logger.info("Monitoring log collection ready")
    return _monitoring_log_collection


def add_rule_book_to_index(text: str, rule_book_id: int, name: str) -> str:
    collection = _get_rule_book_collection()
    doc_id = f"rule_book_{rule_book_id}"
    collection.add(
        documents=[text],
        metadatas=[{"type": "rule_book", "id": rule_book_id, "name": name}],
        ids=[doc_id],
    )
    logger.info("Rule book added to Chroma DB: id=%s", rule_book_id)
    return doc_id


def add_monitoring_log_to_index(text: str, log_id: int, log_type: str) -> str:
    collection = _get_monitoring_log_collection()
    doc_id = f"monitoring_log_{log_id}"
    collection.add(
        documents=[text],
        metadatas=[{"type": "monitoring_log", "id": log_id, "log_type": log_type}],
        ids=[doc_id],
    )
    logger.info("Monitoring log added to Chroma DB: id=%s", log_id)
    return doc_id


def search_rule_books(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    collection = _get_rule_book_collection()
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )
    output = []
    for i in range(len(results["ids"][0])):
        output.append({
            **(results["metadatas"][0][i] if results["metadatas"] else {}),
            "distance": results["distances"][0][i] if results["distances"] else 0,
        })
    return output


def search_monitoring_logs(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    collection = _get_monitoring_log_collection()
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )
    output = []
    for i in range(len(results["ids"][0])):
        output.append({
            **(results["metadatas"][0][i] if results["metadatas"] else {}),
            "distance": results["distances"][0][i] if results["distances"] else 0,
        })
    return output


def clear_index():
    global _client, _rule_book_collection, _monitoring_log_collection
    _rule_book_collection = None
    _monitoring_log_collection = None
    if _client:
        try:
            _client.delete_collection("rule_books")
            _client.delete_collection("monitoring_logs")
        except Exception as e:
            logger.warning("Failed to delete collections: %s", e)
    _client = None
    import shutil
    if os.path.exists(CHROMA_PERSIST_DIR):
        shutil.rmtree(CHROMA_PERSIST_DIR, ignore_errors=True)
    logger.info("Chroma DB index cleared")


def add_to_index(text: str, metadata: Dict[str, Any]) -> int:
    if metadata.get("type") == "rule_book":
        add_rule_book_to_index(text, metadata.get("id"), metadata.get("name"))
    elif metadata.get("type") == "monitoring_log":
        add_monitoring_log_to_index(text, metadata.get("id"), metadata.get("log_type"))
    return 0
