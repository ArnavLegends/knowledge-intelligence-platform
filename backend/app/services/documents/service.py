"""Application-facing document ingestion service."""

from uuid import uuid4

from app.core.config import settings as default_settings
from app.services.documents.models import Document
from app.services.documents.parsers.base import DocumentParser
from app.services.documents.parsers.registry import (
    ParserRegistry,
    build_default_registry,
)
from app.services.documents.validation import validate_upload


class DocumentIngestionService:
    """Validate, select a parser, and produce a normalized Document."""

    def __init__(
        self,
        registry: ParserRegistry | None = None,
        max_upload_bytes: int | None = None,
    ) -> None:
        self._registry = registry or build_default_registry()
        self._max_upload_bytes = (
            max_upload_bytes
            if max_upload_bytes is not None
            else default_settings.max_upload_bytes
        )

    def ingest(
        self,
        filename: str | None,
        content: bytes,
        media_type: str | None = None,
    ) -> Document:
        safe_name = validate_upload(filename, content, self._max_upload_bytes)
        parser: DocumentParser = self._registry.select(safe_name, media_type)
        parsed = parser.parse(safe_name, content)
        return Document.create(
            document_id=str(uuid4()),
            filename=safe_name,
            media_type=parsed.media_type,
            text=parsed.text,
            metadata=parsed.metadata,
        )


def get_document_ingestion_service() -> DocumentIngestionService:
    """FastAPI dependency for document ingestion."""
    return DocumentIngestionService()
