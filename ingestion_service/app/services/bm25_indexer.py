# ingestion_service/app/services/bm25_indexer.py

import os
import logging
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

SEARCH_SERVICE_URL = os.getenv("SEARCH_SERVICE_URL", "http://search-service:8003")


def index_chunk_bm25(
    *,
    document_id: str,
    chunk_id: int,
    source: Optional[str],
    page: Optional[int],
    text: str,
    tags: Optional[List[str]] = None,
) -> None:
    """
    Send one chunk to the search-service /index endpoint (BM25 index).

    We intentionally swallow most errors so that Chroma ingestion is not blocked
    if OpenSearch is temporarily unavailable.
    """
    if not text.strip():
        return  # don't index empty chunks

    payload = {
        "document_id": document_id,
        "chunk_id": chunk_id,
        "source": source,
        "page": page,
        "text": text,
        "tags": tags or [],
    }

    url = f"{SEARCH_SERVICE_URL.rstrip('/')}/index"

    try:
        resp = requests.post(url, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        logger.info(
            "Indexed chunk into BM25: doc_id=%s chunk_id=%s index=%s result=%s",
            document_id,
            chunk_id,
            data.get("index"),
            data.get("result"),
        )
    except requests.exceptions.RequestException as e:
        # In prod you’d use proper structured logging & metrics
        logger.error(
            "BM25 indexing failed for doc_id=%s chunk_id=%s: %s",
            document_id,
            chunk_id,
            e,
        )
        raise e
        # Do NOT raise – we don't want ingestion to fail just because OpenSearch is down.
