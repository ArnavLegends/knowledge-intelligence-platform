"""Indexing domain models."""

from pydantic import BaseModel


class IndexingResult(BaseModel):
    """Result of an indexing operation."""

    document_id: str
    chunks_indexed: int
