# =========================
# Imports
# =========================
import logging
import os

from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from openai import OpenAI

from app.db.chroma import get_collection
from app.schemas.query import QueryRequest, QueryResponse, Source
from app.services.bm25_client import search_bm25, BM25SearchHit
from app.services.llm import generate_answer
from app.services.neighbors import make_chroma_chunk_id, fetch_with_neighbors

load_dotenv()

router = APIRouter()
logger = logging.getLogger("query_service.query")

DEFAULT_MODEL_CHAT = os.getenv("MODEL_CHAT", "ai/qwen3:latest")


# =============================================================================
# High-level: What this file does
# =============================================================================
# This file implements the Query API for our RAG system.
#
# The /query route:
# 1) Embeds the user's question
# 2) Retrieves relevant chunks from Chroma using an industry-standard hybrid flow:
#       BM25 (chunk candidates) -> Chroma get() (centers) -> rerank/fuse -> neighbors stitching
# 3) Builds a context string
# 4) Calls the LLM with (question + context)
# 5) Returns the answer + ranked/deduped source citations
#
# Important:
# - We must be "numpy-safe" when handling Chroma results (embeddings may come back as numpy arrays).
#   Never write:  embs = got.get("embeddings", []) or []
#   because numpy arrays cannot be used in boolean checks (truth value is ambiguous).
# =============================================================================


# =============================================================================
# How the user's question relates to this file
# =============================================================================
# User sends a question to POST /query:
# - If question is "how much experience does ali haider has?"
#     -> BM25 should surface "cover latter::0" strongly, and hybrid should ensure it becomes
#        a center (or at least neighbors) so sources include the cover letter chunk.
#
# - If question is "tell me about vpc"
#     -> BM25 should surface the VPC chunk region from AWS slides; center rerank + neighbors
#        should pull contiguous VPC-related chunks, and sources should cite those.
# =============================================================================


# =============================================================================
# /query route
# =============================================================================
@router.post("/query", response_model=QueryResponse)
def query_rag(request: QueryRequest) -> QueryResponse:
    """
    /query (single route)

    Flow:
    - Embed question
    - Retrieve context (hybrid BM25->vector->neighbors by default)
    - Generate answer with LLM
    - Return answer + ranked source citations
    """
    model_name = request.model_name or DEFAULT_MODEL_CHAT

    logger.info(
        "Received RAG query",
        extra={
            "model": model_name,
            "top_k": request.top_k,
            "question_length": len(request.question or ""),
        },
    )

    # 1) Embed question
    try:
        query_embedding = embed_query(request.question)
    except Exception as e:
        logger.exception("Embedding error")
        raise HTTPException(status_code=500, detail=f"Embedding error: {str(e)}")

    # 2) Retrieve context
    try:
        documents, metadatas = retrieve_context(
            embedding=query_embedding,
            top_k=request.top_k,
            document_id=request.document_id,
            question=request.question,
        )
    except Exception as e:
        logger.exception("Vector store error")
        raise HTTPException(status_code=500, detail=f"Vector store error: {str(e)}")

    # Normalize to python lists (works for list OR numpy arrays)
    documents = _safe_list(documents)
    metadatas = _safe_list(metadatas)

    n = min(len(documents), len(metadatas))
    documents = documents[:n]
    metadatas = metadatas[:n]

    if n == 0:
        return QueryResponse(
            answer="I don't know based on the provided document(s).",
            sources=[],
            context_used=0,
            model_used=model_name,
        )

    # 3) Build context string
    context = build_context(documents)
    logger.info("Built context for LLM", extra={"context_chars": len(context)})

    # 4) Generate answer
    try:
        answer = generate_answer(
            question=request.question, context=context, model_name=model_name
        )
    except Exception as e:
        logger.exception("LLM error")
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    # 5) Build sources (ranked by evidence_score, deduped)
    sources = build_sources(
        documents=documents,
        metadatas=metadatas,
        top_k=request.top_k,
    )

    return QueryResponse(
        answer=answer,
        sources=sources,
        context_used=len(context),
        model_used=model_name,
    )


# =============================================================================
# Helper functions (route-specific) — in order of importance
# =============================================================================
def embed_query(text: str) -> List[float]:
    """Create an embedding for the user's question."""
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "dummy"),
        base_url=os.getenv("BASE_URL"),
    )

    model = os.getenv("MODEL_EMBED")
    if not model:
        raise RuntimeError("MODEL_EMBED is not set")

    resp = client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def retrieve_context(
    embedding: List[float],
    top_k: int = 5,
    document_id: Optional[str] = None,
    question: Optional[str] = None,
) -> Tuple[List[str], List[dict]]:
    """
    Wrapper so the route stays simple.

    - If question is None -> legacy behavior: pure Chroma vector search
    - Else -> hybrid BM25 -> center rerank/fuse -> neighbor stitching
    """
    collection = _get_collection_obj()

    if question is None:
        where = {"document_id": document_id} if document_id else None
        res = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas"],
        )
        docs_outer = res.get("documents", None)
        metas_outer = res.get("metadatas", None)

        if docs_outer is None or len(docs_outer) == 0:
            docs = []
        else:
            docs = _safe_list(docs_outer[0])

        if metas_outer is None or len(metas_outer) == 0:
            metas = []
        else:
            metas = _safe_list(metas_outer[0])

        n = min(len(docs), len(metas))
        return docs[:n], metas[:n]

    chroma_res, bm25_hits = hybrid_retrieve(
        question=question,
        query_embedding=embedding,
        top_k=top_k,
        document_id=document_id,
    )

    docs_outer = chroma_res.get("documents", None)
    metas_outer = chroma_res.get("metadatas", None)

    docs = (
        _safe_list(docs_outer[0]) if docs_outer is not None and len(docs_outer) else []
    )
    metas = (
        _safe_list(metas_outer[0])
        if metas_outer is not None and len(metas_outer)
        else []
    )

    n = min(len(docs), len(metas))
    docs = docs[:n]
    metas = metas[:n]

    logger.info(
        "Hybrid retrieve used",
        extra={"bm25_hits": len(bm25_hits), "returned_docs": len(_safe_list(docs))},
    )

    return _safe_list(docs), _safe_list(metas)


def build_context(docs: List[str], max_chars: int = 12000) -> str:
    """Build a single context string for the LLM."""
    buf: List[str] = []
    total = 0

    for i, d in enumerate(docs):
        if not d:
            continue
        chunk = f"[Chunk {i+1}]\n{d.strip()}\n"
        if total + len(chunk) > max_chars:
            break
        buf.append(chunk)
        total += len(chunk)

    return "\n".join(buf)


def build_sources(
    documents: List[str], metadatas: List[dict], top_k: int
) -> List[Source]:
    pairs = [(d, m) for d, m in zip(documents, metadatas) if isinstance(m, dict)]

    def score_of(meta: dict) -> float:
        try:
            return float(
                meta.get(
                    "evidence_score", meta.get("center_score", meta.get("score", 0.0))
                )
                or 0.0
            )
        except Exception:
            return 0.0

    def norm_key(meta: dict) -> tuple[str, str]:
        did = str(meta.get("document_id", "unknown")).strip()
        try:
            cid = str(int(meta.get("chunk_id")))
        except Exception:
            cid = str(meta.get("chunk_id", "unknown")).strip()
        return did, cid

    # 1) Centers first (guarantee each selected center can appear in citations)
    centers = [(d, m) for (d, m) in pairs if m.get("is_center") is True]
    non_centers = [(d, m) for (d, m) in pairs if m.get("is_center") is not True]

    centers_sorted = sorted(centers, key=lambda p: score_of(p[1]), reverse=True)
    non_sorted = sorted(non_centers, key=lambda p: score_of(p[1]), reverse=True)

    ordered = centers_sorted + non_sorted

    # 2) Dedupe + cap
    sources: List[Source] = []
    seen: set[tuple[str, str]] = set()

    for doc_text, meta in ordered:
        key = norm_key(meta)
        if key in seen:
            continue
        seen.add(key)

        did, cid = key
        snippet = doc_text[:200] if doc_text else None
        sources.append(
            Source(
                document_id=did,
                chunk_id=cid,
                source=meta.get("source"),
                page=meta.get("page"),
                snippet=snippet,
            )
        )

        if len(sources) >= top_k:
            break

    return sources


def hybrid_retrieve(
    question: str,
    query_embedding: List[float],
    top_k: int,
    document_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[BM25SearchHit]]:
    """
    Chunk-level Hybrid + Neighbors (industry standard)

    - If document_id provided: vector search inside that doc
    - Else:
        1) BM25 returns chunk candidates (doc_id + chunk_id)
        2) Fetch BM25 center chunks from Chroma by deterministic IDs
        3) Fuse score = normalized_cosine * alpha + normalized_bm25 * (1-alpha)
        4) Pick centers (relative threshold + hard-keep BM25 #1)
        5) For each center: fetch neighbor window from Chroma, stitch + dedupe
        6) Return documents+metadatas (with evidence_score etc.)
    """
    collection = _get_collection_obj()

    # Doc-scoped vector search
    if document_id:
        chroma_res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
            where={"document_id": document_id},
        )
        return chroma_res, []

    # ---- Config knobs ----
    bm25_k = _safe_int(os.getenv("HYBRID_BM25_CHUNKS", "50"), default=50)
    center_k = _safe_int(os.getenv("HYBRID_CENTER_K", "3"), default=3)
    window = _safe_int(os.getenv("HYBRID_NEIGHBOR_WINDOW", "2"), default=2)
    max_context_chunks = _safe_int(
        os.getenv("HYBRID_MAX_CONTEXT_CHUNKS", "30"), default=30
    )

    alpha = _safe_float(
        os.getenv("HYBRID_FUSION_ALPHA", "0.6"), default=0.6
    )  # cosine weight
    rel = _safe_float(os.getenv("HYBRID_CENTER_REL_THRESHOLD", "0.85"), default=0.85)
    penalty = _safe_float(os.getenv("HYBRID_DISTANCE_PENALTY", "0.02"), default=0.02)

    # 1) BM25
    try:
        bm25_hits: List[BM25SearchHit] = search_bm25(query=question, top_k=bm25_k)
        logger.info("BM25 returned %d hits", len(bm25_hits))
    except Exception as e:
        logger.warning("BM25 failed, fallback to full vector search: %s", e)
        bm25_hits = []

    if not bm25_hits:
        chroma_res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        return chroma_res, []

    # 2) Build deterministic IDs for BM25 centers (dedupe)
    center_keys: List[Tuple[str, int]] = []
    seen_centers: set[Tuple[str, int]] = set()

    for hit in bm25_hits:
        did = str(hit.document_id).strip()
        cid = int(hit.chunk_id)
        key = (did, cid)
        if key in seen_centers:
            continue
        seen_centers.add(key)
        center_keys.append(key)

    center_ids = [make_chroma_chunk_id(did, cid) for (did, cid) in center_keys]

    got = collection.get(
        ids=center_ids, include=["documents", "metadatas", "embeddings"]
    )

    returned_ids = got.get("ids")
    returned_ids = [] if returned_ids is None else list(returned_ids)

    missing = [cid for cid in center_ids if cid not in returned_ids]

    logger.info("Chroma.get requested_ids=%s", center_ids[:10])
    logger.info("Chroma.get returned_ids=%s", returned_ids[:10])
    logger.warning("Chroma.get missing_ids=%s", missing[:10])

    # IMPORTANT: numpy-safe extraction (no "or []" on numpy arrays)
    docs = _safe_list(got.get("documents", None))
    metas = _safe_list(got.get("metadatas", None))
    embs = _safe_list(got.get("embeddings", None))

    n = min(len(docs), len(metas), len(embs))
    if n == 0:
        logger.warning("Hybrid retrieve: centers not found in Chroma (ids mismatch?)")
        chroma_res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        return chroma_res, bm25_hits

    # Map bm25 scores by center-id
    bm25_score_by_id: Dict[str, float] = {}
    for h in bm25_hits:
        try:
            key = make_chroma_chunk_id(str(h.document_id).strip(), int(h.chunk_id))
            bm25_score_by_id[key] = float(h.score)
        except Exception:
            continue

    # 3) Raw center metrics: (did, cid, cosine, bm25)
    raw_centers: List[Tuple[str, int, float, float]] = []
    for i in range(n):
        meta = metas[i] or {}
        did = str(meta.get("document_id", "")).strip()
        try:
            cid = int(meta.get("chunk_id"))
        except Exception:
            continue

        cid_key = make_chroma_chunk_id(did, cid)
        cos = float(cosine_sim(query_embedding, embs[i]))
        bm25 = float(bm25_score_by_id.get(cid_key, 0.0))
        raw_centers.append((did, cid, cos, bm25))

    if not raw_centers:
        chroma_res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        return chroma_res, bm25_hits

    # Normalize + fuse
    cos_vals = [c[2] for c in raw_centers]
    bm25_vals = [c[3] for c in raw_centers]

    cos_min, cos_max = min(cos_vals), max(cos_vals)
    bm25_min, bm25_max = min(bm25_vals), max(bm25_vals)

    def norm(x: float, lo: float, hi: float) -> float:
        if hi <= lo:
            return 0.0
        return (x - lo) / (hi - lo)

    center_scored: List[Tuple[float, Dict[str, Any]]] = []
    for did, cid, cos, bm25 in raw_centers:
        fused = alpha * norm(cos, cos_min, cos_max) + (1.0 - alpha) * norm(
            bm25, bm25_min, bm25_max
        )
        center_scored.append(
            (
                fused,
                {
                    "document_id": did,
                    "chunk_id": cid,
                    "score": fused,
                    "cos": cos,
                    "bm25": bm25,
                },
            )
        )

    center_scored.sort(key=lambda x: x[0], reverse=True)

    # 4) Select centers with rel threshold
    best = center_scored[0][0] if center_scored else 0.0
    filtered = [c for (s, c) in center_scored if best == 0.0 or (s / best) >= rel]
    top_centers = filtered[: max(1, center_k)]

    # Always keep BM25 #1 center
    try:
        must_key = (str(bm25_hits[0].document_id).strip(), int(bm25_hits[0].chunk_id))

        def key_of(c: dict) -> Tuple[str, int]:
            return (str(c["document_id"]).strip(), int(c["chunk_id"]))

        if not any(key_of(c) == must_key for c in top_centers):
            must_center = next(
                (c for (_, c) in center_scored if key_of(c) == must_key), None
            )
            if must_center is not None:
                if len(top_centers) < max(1, center_k):
                    top_centers.append(must_center)
                else:
                    worst_i = min(
                        range(len(top_centers)),
                        key=lambda i: float(top_centers[i].get("score", 0.0) or 0.0),
                    )
                    top_centers[worst_i] = must_center
    except Exception:
        pass

    logger.info(
        "Hybrid retrieve: selected centers=%s",
        [
            (c["document_id"], c["chunk_id"], round(float(c["score"]), 4))
            for c in top_centers
        ],
    )

    # 5) Neighbor stitching
    out_docs: List[str] = []
    out_metas: List[dict] = []
    seen_chunks: set[Tuple[str, int]] = set()

    for center_rank, c in enumerate(top_centers):
        did = str(c["document_id"]).strip()
        cid = int(c["chunk_id"])

        neighbors = fetch_with_neighbors(did, cid, window=window, include_self=True)

        for nbh in neighbors:
            ndoc = str(nbh.get("document_id", did)).strip()
            try:
                ncid = int(nbh.get("chunk_id"))
            except Exception:
                continue

            key = (ndoc, ncid)
            if key in seen_chunks:
                continue
            seen_chunks.add(key)

            meta = dict(nbh.get("metadata") or {})

            # evidence markers (for debugging + source ranking)
            meta["retrieval_method"] = "hybrid_bm25_vector_neighbors"
            meta["center_document_id"] = did
            meta["center_chunk_id"] = cid
            meta["center_rank"] = center_rank
            meta["is_center"] = ncid == cid

            dist = abs(ncid - cid)
            meta["distance_from_center"] = dist

            center_score = float(c.get("score", 0.0) or 0.0)
            meta["center_score"] = center_score
            meta["evidence_score"] = center_score - (dist * penalty)

            out_docs.append(nbh["text"])
            out_metas.append(meta)

            if len(out_docs) >= max_context_chunks:
                break

        if len(out_docs) >= max_context_chunks:
            break

    if not out_docs:
        chroma_res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        return chroma_res, bm25_hits

    # Return same shape as Chroma query output
    chroma_res = {
        "documents": [out_docs[:max_context_chunks]],
        "metadatas": [out_metas[:max_context_chunks]],
    }

    logger.info(
        "Stitched docs sample=%s", [m.get("document_id") for m in out_metas[:15]]
    )
    logger.info(
        "Stitched docs counts=%s",
        {
            "cover": sum(
                1 for m in out_metas if m.get("document_id") == "cover latter"
            ),
            "aws": sum(1 for m in out_metas if m.get("document_id") == "aws slides"),
        },
    )
    return chroma_res, bm25_hits


def cosine_sim(a: List[float], b: List[float]) -> float:
    """Pure python cosine similarity; float-casts to be safe."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        x = float(x)
        y = float(y)
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / ((na**0.5) * (nb**0.5)))


# =============================================================================
# Small internal safety helpers (file-local)
# =============================================================================


def _safe_list(x: Any) -> List[Any]:
    """
    Converts list/tuple/numpy-array-like -> python list.
    Never triggers numpy truthiness ambiguity.
    """
    if x is None:
        return []
    if isinstance(x, list):
        return x
    try:
        return list(x)
    except Exception:
        return []


def _safe_int(v: str, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _safe_float(v: str, default: float) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _get_collection_obj():
    maybe = get_collection()
    if isinstance(maybe, tuple) and len(maybe) == 2:
        return maybe[1]
    return maybe
