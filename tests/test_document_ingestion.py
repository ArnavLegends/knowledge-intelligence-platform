"""Document ingestion service tests."""

import pytest

from app.core.exceptions import (
    DocumentParseError,
    DocumentValidationError,
    UnsupportedFormatError,
)
from app.services.documents.service import DocumentIngestionService


def test_ingestion_service_returns_normalized_document() -> None:
    service = DocumentIngestionService(max_upload_bytes=1024)
    document = service.ingest("notes.txt", b"hello world", "text/plain")

    assert document.filename == "notes.txt"
    assert document.media_type == "text/plain"
    assert document.text == "hello world"
    assert document.source == "upload"
    assert document.id
    assert document.ingested_at.tzinfo is not None
    assert document.metadata["parser"] == "txt"
    assert document.metadata["size_bytes"] == 11


def test_ingestion_service_rejects_empty_file() -> None:
    service = DocumentIngestionService()
    with pytest.raises(DocumentValidationError):
        service.ingest("notes.txt", b"")


def test_ingestion_service_rejects_unsupported_format() -> None:
    service = DocumentIngestionService()
    with pytest.raises(UnsupportedFormatError):
        service.ingest("notes.pdf", b"%PDF-fake")


def test_ingestion_service_rejects_invalid_utf8() -> None:
    service = DocumentIngestionService()
    with pytest.raises(DocumentParseError):
        service.ingest("notes.txt", b"\xff\xfe")
