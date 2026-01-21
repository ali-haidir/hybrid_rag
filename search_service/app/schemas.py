from pydantic import BaseModel , Field
from typing import List, Optional


class IndexDocument(BaseModel):
    document_id: str
    chunk_id: int
    source: Optional[str] = None
    page: Optional[int] = None
    text: str
    tags: Optional[List[str]] = None


class SearchRequest(BaseModel):
    """
    Request body for BM25 search.
    """

    query: str = Field(
        ...,
        min_length=1,
        description="User's search query (BM25).",
    )
    top_k: int = Field(
        10,
        ge=1,
        le=50,
        description="How many hits to return from OpenSearch.",
    )
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional filter: only search these document_ids.",
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="Optional filter: only search these source filenames.",
    )


class SearchHit(BaseModel):
    """
    One BM25 hit (one chunk) returned from OpenSearch.
    """

    document_id: str
    chunk_id: int
    source: Optional[str] = None
    page: Optional[int] = None
    text: str
    tags: List[str] = []
    score: float


class SearchResponse(BaseModel):
    """
    BM25 search result wrapper.
    """

    hits: List[SearchHit]
    total: int
