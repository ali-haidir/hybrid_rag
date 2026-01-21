from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.processing.loader import DocumentLoader
from app.processing.chunker import fixed_chunk_text
from app.processing.embeddings import embed_texts
from app.processing.persist import persist_chunks
from pathlib import Path


router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    # add more later if needed
}


@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    document_id: str | None = Form(None),
    source: str | None = Form(None),
    version: str | None = Form(None),
):
    try:
        # 0️⃣ Basic validation – content type
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported content type: {file.content_type}. "
                f"Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}",
            )

        # Decide a source/filename
        filename = file.filename or source or "uploaded_document.pdf"

        # If no explicit document_id, derive from filename (without extension)
        if document_id is None:
            document_id = Path(filename).stem

        # Normalize document_id (no crazy spaces, keep it simple)
        document_id = document_id.strip()
        if not document_id:
            raise HTTPException(status_code=400, detail="document_id cannot be empty")

        # 1️⃣ Load pages with page numbers
        pages = DocumentLoader.load_pages(file)  # [{ "page": int, "text": str }, ...]

        all_chunks: list[str] = []
        pages_for_chunks: list[int] = []

        # 2️⃣ Chunk per page and remember which page each chunk came from
        for p in pages:
            page_no = p["page"]
            text = p["text"]
            chunks = fixed_chunk_text(text)

            for chunk in chunks:
                all_chunks.append(chunk)
                pages_for_chunks.append(page_no)

        if not all_chunks:
            raise ValueError("No chunks produced from document.")

        # 3️⃣ Embed all chunks
        embeddings = embed_texts(all_chunks)

        # 4️⃣ Persist with page + source info (you will adjust persist_chunks accordingly)
        persist_chunks(
            document_id=document_id,
            chunks=all_chunks,
            embeddings=embeddings,
            source=filename,
            pages_for_chunks=pages_for_chunks,
        )

    except HTTPException:
        # Re-raise HTTPException as-is, so FastAPI formats it
        raise

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "embedded",
        "document_id": document_id,
        "characters": sum(len(c) for c in all_chunks),
        "chunks": len(all_chunks),
        "embedding_dim": len(embeddings[0]) if embeddings else 0,
        "preview": all_chunks[0][:200] if all_chunks else None,
    }
