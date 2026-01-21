# query_service/app/schemas/query.py

from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        description="User question in natural language.",
        example="What is this document about?",
    )
    top_k: int = Field(
        5,
        ge=1,
        le=20,
        description="How many chunks to retrieve from Chroma (1–20).",
        example=5,
    )
    model_name: Optional[str] = Field(
        default=None,
        description="LLM model id. If omitted, defaults to MODEL_CHAT env var.",
        example="ai/qwen3:latest",
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Restrict search to this document_id if provided.",
        example="cover latter",
    )


class Source(BaseModel):
    document_id: str = Field(..., description="Logical id used at ingest time.")
    chunk_id: str = Field(..., description="Chunk index within the document.")
    source: Optional[str] = Field(
        default=None,
        description="Original filename or source label.",
    )
    page: Optional[int] = Field(
        default=None,
        description="Page number in original document (if available).",
    )
    snippet: Optional[str] = Field(
        default=None,
        description="Short excerpt of the chunk used for the answer.",
    )


class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    context_used: int = Field(
        ...,
        description="Total number of characters from retrieved context sent to the LLM.",
    )
    model_used: str = Field(
        ...,
        description="LLM model id that was actually used to generate the answer.",
        example="ai/qwen3:latest",
    )
