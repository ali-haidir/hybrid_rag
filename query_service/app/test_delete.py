from app.api.query import embed_query
from app.db.chroma import get_collection

question = "tell me about JPMorganChase's ?"

TARGET_DOC_ID = "cover latter"  # or "JP cover Latter" if that's how it's stored

embedding = embed_query(question)
col = get_collection()


def check_top_k(k: int):
    res = col.query(
        query_embeddings=[embedding],
        n_results=k,
        include=["metadatas", "documents", "distances"],
    )

    metadatas_list = res["metadatas"][0]
    distances = res["distances"][0]

    print(f"\n=== top_k = {k} ===")
    found_rank = None

    for i, (meta, dist) in enumerate(zip(metadatas_list, distances)):
        doc_id = meta.get("document_id")
        src = meta.get("source")
        page = meta.get("page")
        print(
            f"Rank {i} | dist={dist:.4f} | doc_id={doc_id} | source={src} | page={page}"
        )
        if doc_id == TARGET_DOC_ID and found_rank is None:
            found_rank = i

    if found_rank is not None:
        print(
            f"--> FIRST hit for {TARGET_DOC_ID!r} at rank {found_rank} "
            f"(within top_k={k})"
        )
    else:
        print(f"--> No hit for {TARGET_DOC_ID!r} within top_k={k}")


if __name__ == "__main__":
    for k in [1, 3, 5, 10, 20, 50, 100 , 500]:
        check_top_k(k)
