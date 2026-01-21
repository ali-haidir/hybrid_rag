# app/services/bm25_client.py

import os
import logging
from typing import List, Optional

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# Base URL for the search-service (BM25 / OpenSearch gateway)
SEARCH_SERVICE_URL = os.getenv("SEARCH_SERVICE_URL", "http://search-service:8003")


class BM25SearchHit(BaseModel):
    document_id: str
    chunk_id: int
    source: str
    page: int
    text: str
    score: float


class BM25SearchResponse(BaseModel):
    hits: List[BM25SearchHit]
    total: int


def search_bm25(
    query: str,
    top_k: int = 5,
    sources: Optional[List[str]] = None,
) -> List[BM25SearchHit]:
    """
    Call search-service /search endpoint and return BM25 hits.

    This is synchronous on purpose to match the rest of the query-service
    code style (embed_query, LLM calls, etc.).
    """
    base = SEARCH_SERVICE_URL.rstrip("/")
    url = f"{base}/search"

    payload = {
        "query": query,
        "top_k": top_k,
    }
    if sources:
        payload["sources"] = sources

    try:
        logger.info("[BM25] Calling search-service at %s with top_k=%d", url, top_k)
        resp = httpx.post(url, json=payload, timeout=5.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("[BM25] HTTP error talking to search-service: %s", exc)
        return []
    except Exception as exc:
        logger.exception("[BM25] Unexpected error: %s", exc)
        return []

    data = resp.json()
    try:
        parsed = BM25SearchResponse.model_validate(data)
        # logger.info("this is the BM25 response data: %s", data)
    except ValidationError as ve:
        logger.warning(
            "[BM25] Failed to validate /search response: %s; raw data=%s",
            ve,
            data,
        )
        return []

    logger.info("[BM25] Got %d hits (total=%d)", len(parsed.hits), parsed.total)
    return parsed.hits
