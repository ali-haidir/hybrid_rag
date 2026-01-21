from typing import List, Optional
from app.db.chroma import get_collection
from app.services.bm25_indexer import index_chunk_bm25


def persist_chunks(
    document_id: str,
    chunks: List[str],
    embeddings: List[List[float]],
    source: str,
    pages_for_chunks: List[int],
    tags: Optional[List[str]] = None,
):
    print(f"[CHROMA] Persisting {len(chunks)} chunks for {document_id}")
    client, collection = get_collection()

    if not (len(chunks) == len(embeddings) == len(pages_for_chunks)):
        raise ValueError("chunks/embeddings/pages_for_chunks length mismatch")

    # Normalize the document_id so IDs stay consistent across services
    doc_key = document_id.strip()

    # store tags as a comma-separated string in Chroma (if provided)
    tags_value = ",".join(tags) if tags else None

    # Deterministic, addressable IDs for Chroma so we can fetch exact chunks + neighbors later
    # Format: <document_id>::<chunk_id>
    ids: List[str] = []
    metadatas: List[dict] = []

    for i, chunk in enumerate(chunks):
        ids.append(make_chroma_chunk_id(doc_key, i))

        meta = {
            "document_id": doc_key,
            "chunk_id": i,  # keep numeric for neighbor math (i-1, i+1)
            "source": source,
            "page": int(pages_for_chunks[i]),
        }
        # Only include 'tags' in Chroma metadata if we actually have a value
        if tags_value is not None:
            meta["tags"] = tags_value
        metadatas.append(meta)

        # Index into BM25 via search-service (OpenSearch) using the same normalized doc id
        index_chunk_bm25(
            document_id=doc_key,
            chunk_id=i,
            source=source,
            page=int(pages_for_chunks[i]),
            text=chunk,
            tags=tags,  # OpenSearch is fine with list-or-None
        )

    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )


# helper Function for upserting chunks into Chroma
def make_chroma_chunk_id(document_id: str, chunk_id: int | str) -> str:
    return f"{str(document_id).strip()}::{int(chunk_id)}"
