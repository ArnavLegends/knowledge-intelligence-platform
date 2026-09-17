"""Chunk models representing segmented text."""

from typing import Any

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A deterministic text segment from a source document."""

    id: str
    document_id: str
    index: int
    text: str
    character_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
