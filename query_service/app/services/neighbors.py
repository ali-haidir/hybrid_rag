# query_service/app/services/neighbors.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from app.db.chroma import get_collection


def make_chroma_chunk_id(document_id: str, chunk_id: int) -> str:
    doc_key = document_id.strip()
    return f"{doc_key}::{int(chunk_id)}"


def fetch_with_neighbors(
    document_id: str,
    chunk_id: int,
    window: int = 2,
    include_self: bool = True,
) -> List[Dict[str, Any]]:
    """
    Returns chunks for [chunk_id-window .. chunk_id+window] that exist in Chroma.
    Output is ordered by chunk_id ascending.
    """
    col = _get_collection_obj()

    center = int(chunk_id)
    offsets = list(range(-window, window + 1))
    if not include_self:
        offsets = [o for o in offsets if o != 0]

    # candidate ids (skip negatives)
    ids = []
    for off in offsets:
        cid = center + off
        if cid < 0:
            continue
        ids.append(make_chroma_chunk_id(document_id, cid))

    if not ids:
        return []

    res = col.get(ids=ids, include=["documents", "metadatas"])

    # Chroma returns parallel arrays
    out = []
    for doc_text, meta in zip(res.get("documents", []), res.get("metadatas", [])):
        if not meta:
            continue
        # chunk_id should now be int in metadata, but be defensive
        meta_chunk_id = meta.get("chunk_id")
        try:
            meta_chunk_id = int(meta_chunk_id)
        except Exception:
            meta_chunk_id = None

        out.append(
            {
                "id": (
                    make_chroma_chunk_id(document_id, meta_chunk_id)
                    if meta_chunk_id is not None
                    else None
                ),
                "document_id": meta.get("document_id", document_id),
                "chunk_id": meta_chunk_id,
                "source": meta.get("source"),
                "page": meta.get("page"),
                "text": doc_text,
                "metadata": meta,
            }
        )

    # sort by chunk_id so context is contiguous
    out.sort(key=lambda x: (x["chunk_id"] is None, x["chunk_id"]))
    return out


def expand_hits_with_neighbors(
    hits: List[Dict[str, Any]],
    window: int = 2,
    max_chunks: int = 30,
) -> List[Dict[str, Any]]:
    """
    hits: list of {document_id, chunk_id, ...}
    Expands each hit with neighbors and dedupes by (document_id, chunk_id).
    """
    seen: set[Tuple[str, int]] = set()
    expanded: List[Dict[str, Any]] = []

    for h in hits:
        doc_id = h["document_id"]
        chunk_id = int(h["chunk_id"])

        neighbors = fetch_with_neighbors(
            doc_id, chunk_id, window=window, include_self=True
        )

        for n in neighbors:
            key = (n["document_id"], int(n["chunk_id"]))
            if key in seen:
                continue
            seen.add(key)
            expanded.append(n)

            if len(expanded) >= max_chunks:
                return expanded

    return expanded


def _get_collection_obj():
    maybe = get_collection()
    # ingestion-service style: (client, collection)
    if isinstance(maybe, tuple) and len(maybe) == 2:
        return maybe[1]
    # query-service style: collection only
    return maybe
