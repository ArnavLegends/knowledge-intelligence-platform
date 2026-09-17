"""Normalized document produced by ingestion."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Provider-agnostic ingested document."""

    id: str
    filename: str
    media_type: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = "upload"
    ingested_at: datetime

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        filename: str,
        media_type: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        source: str = "upload",
        ingested_at: datetime | None = None,
    ) -> "Document":
        return cls(
            id=document_id,
            filename=filename,
            media_type=media_type,
            text=text,
            metadata=metadata or {},
            source=source,
            ingested_at=ingested_at or datetime.now(UTC),
        )
