"""Chroma DB integration for vector storage of rulebooks."""

import json
import os
from typing import Dict, Any, List, Optional
import chromadb

from utils.common import logger

# Global Chroma client
_chroma_client = None
_chroma_db = None

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
CHROMA_COLLECTION_NAME = "rulebooks"


def init_chroma():
    """Initialize Chroma DB client using new PersistentClient API."""
    global _chroma_client, _chroma_db
    try:
        # Use new PersistentClient for Chroma 0.4.x
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        # Get or create collection with cosine distance metric
        _chroma_db = _chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )

        logger.info(f"Chroma DB initialized at {CHROMA_DB_PATH}")
        return _chroma_db
    except Exception as e:
        logger.error(f"Failed to initialize Chroma DB: {e}")
        raise


def get_chroma_db():
    """Get Chroma DB collection."""
    global _chroma_db
    if _chroma_db is None:
        init_chroma()
    return _chroma_db


def add_rulebook_to_chroma(
    rulebook_id: int,
    rulebook_name: str,
    content: str,
    connector_type: Optional[str] = None,
) -> bool:
    """Add rulebook to Chroma vector DB."""
    try:
        db = get_chroma_db()

        # Parse content to extract rules
        rules_text = _extract_rules_from_content(content)

        # Store in Chroma with metadata
        metadata = {
            "rulebook_id": str(rulebook_id),
            "rulebook_name": rulebook_name,
            "connector_type": connector_type or "general",
            "type": "rulebook",
        }

        db.add(
            ids=[f"rulebook_{rulebook_id}"],
            documents=[rules_text],
            metadatas=[metadata],
        )

        logger.info(f"Rulebook {rulebook_id} added to Chroma DB")
        return True
    except Exception as e:
        logger.error(f"Failed to add rulebook to Chroma: {e}")
        return False


def search_rulebooks(
    query: str, top_k: int = 5, connector_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search rulebooks in Chroma based on query."""
    try:
        db = get_chroma_db()

        where_filter = None
        if connector_type:
            where_filter = {"connector_type": {"$eq": connector_type}}

        results = db.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
        )

        return _format_chroma_results(results)
    except Exception as e:
        logger.error(f"Failed to search Chroma: {e}")
        return []


def get_rulebook_content(rulebook_id: int) -> Optional[str]:
    """Retrieve full rulebook content from Chroma."""
    try:
        db = get_chroma_db()
        result = db.get(
            ids=[f"rulebook_{rulebook_id}"], include=["documents", "metadatas"]
        )

        if result["documents"]:
            return result["documents"][0]
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve rulebook: {e}")
        return None


def delete_rulebook_from_chroma(rulebook_id: int) -> bool:
    """Delete rulebook from Chroma."""
    try:
        db = get_chroma_db()
        db.delete(ids=[f"rulebook_{rulebook_id}"])
        logger.info(f"Rulebook {rulebook_id} deleted from Chroma")
        return True
    except Exception as e:
        logger.error(f"Failed to delete rulebook from Chroma: {e}")
        return False


def _extract_rules_from_content(content: str) -> str:
    """Extract and format rules from rulebook content for embedding."""
    try:
        lines = content.split("\n")
        rules_text = []

        current_rule = []
        for line in lines:
            # Extract rule lines
            if line.startswith(
                ("- Purpose:", "- Penalty:", "- Rule Type:", "- Parameters:", "- SQL:")
            ):
                current_rule.append(line)
            elif re.match(r"^\d+\.\s+", line):
                if current_rule:
                    rules_text.append("\n".join(current_rule))
                current_rule = [line]
            elif current_rule:
                current_rule.append(line)

        if current_rule:
            rules_text.append("\n".join(current_rule))

        return "\n\n".join(rules_text)
    except Exception as e:
        logger.warning(f"Failed to extract rules: {e}")
        return content


def _format_chroma_results(results: Dict) -> List[Dict[str, Any]]:
    """Format Chroma query results."""
    formatted = []

    if not results.get("documents"):
        return formatted

    for i, doc in enumerate(results["documents"][0]):
        metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
        distance = results["distances"][0][i] if results.get("distances") else 0

        formatted.append(
            {
                "id": metadata.get("rulebook_id"),
                "name": metadata.get("rulebook_name"),
                "connector_type": metadata.get("connector_type"),
                "content": doc,
                "similarity": 1 - distance,  # Convert distance to similarity
            }
        )

    return formatted


# Import regex for extraction
import re

__all__ = [
    "init_chroma",
    "get_chroma_db",
    "add_rulebook_to_chroma",
    "search_rulebooks",
    "get_rulebook_content",
    "delete_rulebook_from_chroma",
]
