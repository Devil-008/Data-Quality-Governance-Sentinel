"""Vector DB helper using Chroma DB for rule books and monitoring logs."""

import os
import json
import uuid
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions

from utils.common import logger

load_dotenv()

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
MODEL_NAME = os.getenv("VECTOR_MODEL", "all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))

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
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=MODEL_NAME
    )


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


def _chunk_text_generator(
    text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP
):
    """Generate overlapping chunks from text (memory-efficient generator)."""
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        if end < text_length:
            last_space = text.rfind(" ", start, end)
            last_newline = text.rfind("\n", start, end)
            if last_newline > start:
                end = last_newline + 1
            elif last_space > start:
                end = last_space + 1

        yield text[start:end]
        start = end - chunk_overlap

        if start < 0:
            start = 0


def _chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP
) -> List[str]:
    """Split text into overlapping chunks. Use generator version for large texts."""
    return list(_chunk_text_generator(text, chunk_size, chunk_overlap))


def add_rule_book_to_index(
    text: str, rule_book_id: int, name: str, metadata: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Add rule book to Chroma DB with proper chunking and metadata."""
    try:
        logger.debug(
            "Getting rule book collection for indexing rule book %d", rule_book_id
        )
        collection = _get_rule_book_collection()

        logger.debug(
            "Chunking text for rule book %d (size=%d)", rule_book_id, len(text)
        )

        # Process chunks in batches to avoid memory overflow
        batch_size = 100  # Process 100 chunks at a time
        doc_ids = []
        chunk_index = 0

        batch_docs = []
        batch_metadatas = []
        batch_ids = []

        for chunk in _chunk_text_generator(text):
            doc_id = (
                f"rule_book_{rule_book_id}_chunk_{chunk_index}_{uuid.uuid4().hex[:8]}"
            )
            chunk_metadata = {
                "type": "rule_book",
                "rulebook_id": rule_book_id,
                "name": name,
                "chunk_index": chunk_index,
            }
            if metadata:
                chunk_metadata.update(metadata)

            batch_docs.append(chunk)
            batch_metadatas.append(chunk_metadata)
            batch_ids.append(doc_id)
            doc_ids.append(doc_id)
            chunk_index += 1

            # Add batch to ChromaDB when batch size is reached
            if len(batch_docs) >= batch_size:
                logger.debug(
                    "Adding batch of %d chunks for rule book %d",
                    len(batch_docs),
                    rule_book_id,
                )
                collection.add(
                    documents=batch_docs,
                    metadatas=batch_metadatas,
                    ids=batch_ids,
                )
                batch_docs = []
                batch_metadatas = []
                batch_ids = []

        # Add remaining chunks
        if batch_docs:
            logger.debug(
                "Adding final batch of %d chunks for rule book %d",
                len(batch_docs),
                rule_book_id,
            )
            collection.add(
                documents=batch_docs,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )

        logger.info(
            "Rule book added to Chroma DB: id=%s, chunks=%d", rule_book_id, chunk_index
        )
        return doc_ids
    except Exception as e:
        logger.exception(
            "Failed to add rule book %d to ChromaDB: %s", rule_book_id, str(e)
        )
        raise


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


def search_rule_books(
    query: str, top_k: int = 5, connector_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search rule books with optional connector_type filter."""
    collection = _get_rule_book_collection()

    where = {}
    if connector_type:
        where["connector_type"] = connector_type

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where if where else None,
    )

    output = []
    for i in range(len(results["ids"][0])):
        output.append(
            {
                "id": results["ids"][0][i],
                "document": (
                    results["documents"][0][i] if results["documents"] else None
                ),
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0,
            }
        )
    return output


def search_monitoring_logs(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    collection = _get_monitoring_log_collection()
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )
    output = []
    for i in range(len(results["ids"][0])):
        output.append(
            {
                **(results["metadatas"][0][i] if results["metadatas"] else {}),
                "distance": results["distances"][0][i] if results["distances"] else 0,
            }
        )
    return output


def delete_rule_book_from_index(rule_book_id: int) -> None:
    """Delete all chunks for a specific rule book."""
    collection = _get_rule_book_collection()
    try:
        collection.delete(where={"rulebook_id": rule_book_id})
        logger.info("Rule book deleted from Chroma DB: id=%s", rule_book_id)
    except Exception as e:
        logger.warning("Failed to delete rule book from index: %s", e)


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
