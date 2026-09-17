"""Retrieval domain models."""

from typing import Any

from pydantic import BaseModel, Field


class RetrievalQuery(BaseModel):
    """A search query for retrieving chunks."""

    text: str
    top_k: int = Field(default=5, gt=0)
    threshold: float | None = None


class RetrievedChunk(BaseModel):
    """A chunk of text retrieved from the knowledge base."""

    id: str
    document_id: str | None = None
    text: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
