from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from opensearchpy import OpenSearch, exceptions as os_exceptions

from .config import get_opensearch_settings
from .index import get_os_client, ensure_index
from .schemas import IndexDocument, SearchRequest, SearchResponse, SearchHit

app = FastAPI(title="OPEN search-service", version="0.1.0")


@app.on_event("startup")
def on_startup():
    # Ensure the BM25 index exists when service starts
    try:
        ensure_index()
    except Exception as e:
        # For now, just log to stdout; in prod you'd use logging
        print(f"[search-service] Failed to ensure index: {e}")


@app.get("/health")
def health():
    """
    Simple health check that verifies we can talk to OpenSearch.
    """
    try:
        client = get_os_client()
        info = client.info()
        settings = get_opensearch_settings()

        return {
            "status": "ok",
            "opensearch": {
                "cluster_name": info.get("cluster_name"),
                "cluster_uuid": info.get("cluster_uuid"),
                "version": info.get("version", {}).get("number"),
                "index": settings.index_name,
            },
        }
    except os_exceptions.AuthenticationException:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "reason": "auth_failed"},
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "reason": str(e)},
        )


@app.post("/index")
def index_document(doc: IndexDocument):
    """
    Index a single text chunk into the BM25 index.
    This will be called by ingestion-service for every chunk.
    """
    client: OpenSearch = get_os_client()
    settings = get_opensearch_settings()
    index_name = settings.index_name

    body = {
        "document_id": doc.document_id,
        "chunk_id": doc.chunk_id,
        "source": doc.source,
        "page": doc.page,
        "text": doc.text,
        "tags": doc.tags or [],
    }

    try:
        resp = client.index(index=index_name, body=body)
    except os_exceptions.ConnectionError as e:
        # OpenSearch is down or unreachable
        raise HTTPException(status_code=503, detail=f"opensearch_unreachable: {e}")
    except Exception as e:
        # Any other unexpected error
        raise HTTPException(status_code=500, detail=f"indexing_error: {e}")

    return {
        "index": resp.get("_index"),
        "id": resp.get("_id"),
        "result": resp.get("result"),
    }



@app.post("/search", response_model=SearchResponse)
def search_documents(req: SearchRequest):
    """
    BM25 search over indexed chunks in OpenSearch.

    Later, query-service will call this as:
      1) BM25 search to get candidate chunks
      2) Re-embed & rerank those candidates with Chroma (Pattern A).
    """
    client: OpenSearch = get_os_client()
    settings = get_opensearch_settings()
    index_name = settings.index_name

    # Build BM25 query
    must_clause = [
        {"match": {"text": req.query}}  # BM25 over the 'text' field
    ]

    filter_clause = []

    if req.document_ids:
        filter_clause.append({"terms": {"document_id": req.document_ids}})

    if req.sources:
        filter_clause.append({"terms": {"source": req.sources}})

    query_body = {
        "query": {
            "bool": {
                "must": must_clause,
                "filter": filter_clause,
            }
        },
        "size": req.top_k,
    }

    try:
        resp = client.search(index=index_name, body=query_body)
    except os_exceptions.ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"opensearch_unreachable: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"search_error: {e}")

    hits = []
    for h in resp["hits"]["hits"]:
        src = h.get("_source", {})
        hits.append(
            SearchHit(
                document_id=src.get("document_id", ""),
                chunk_id=src.get("chunk_id", 0),
                source=src.get("source"),
                page=src.get("page"),
                text=src.get("text", ""),
                tags=src.get("tags") or [],
                score=h.get("_score", 0.0),
            )
        )

    # OpenSearch total can be dict or int depending on version
    total_raw = resp["hits"]["total"]
    if isinstance(total_raw, dict):
        total = total_raw.get("value", 0)
    else:
        total = total_raw

    return SearchResponse(hits=hits, total=total)