"""RAG domain models."""

from typing import Any

from pydantic import BaseModel, Field


class RAGRequest(BaseModel):
    """A request to generate an answer using retrieved context."""

    query: str
    top_k: int | None = None
    threshold: float | None = None


class ContextItem(BaseModel):
    """A retrieved source chunk used as context for generation."""

    chunk_id: str
    document_id: str | None = None
    text: str
    rank: int
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGResponse(BaseModel):
    """The generated answer with provenance information."""

    answer: str
    sources: list[ContextItem]
