"""Document model and parser tests."""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import (
    DocumentParseError,
    DocumentValidationError,
    UnsupportedFormatError,
)
from app.services.documents.models import Document
from app.services.documents.parsers.registry import (
    ParserRegistry,
    build_default_registry,
)
from app.services.documents.parsers.txt import TxtParser
from app.services.documents.validation import validate_upload


def test_document_model_contains_required_fields() -> None:
    ingested_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    document = Document.create(
        document_id="doc-1",
        filename="notes.txt",
        media_type="text/plain",
        text="hello",
        metadata={"parser": "txt", "size_bytes": 5},
        ingested_at=ingested_at,
    )

    assert document.id == "doc-1"
    assert document.filename == "notes.txt"
    assert document.media_type == "text/plain"
    assert document.text == "hello"
    assert document.metadata["parser"] == "txt"
    assert document.source == "upload"
    assert document.ingested_at == ingested_at


def test_txt_parser_extracts_utf8_text() -> None:
    parser = TxtParser()
    content = "café\r\nnaïve".encode()
    result = parser.parse("notes.txt", content)

    assert result.media_type == "text/plain"
    assert result.text == "café\nnaïve"
    assert result.metadata["parser"] == "txt"
    assert result.metadata["encoding"] == "utf-8"


def test_txt_parser_strips_bom() -> None:
    parser = TxtParser()
    result = parser.parse("notes.txt", "\ufeffhello".encode())
    assert result.text == "hello"


def test_txt_parser_rejects_invalid_utf8() -> None:
    parser = TxtParser()
    with pytest.raises(DocumentParseError) as exc_info:
        parser.parse("notes.txt", b"\xff\xfe not utf-8")

    assert exc_info.value.code == "document_parse_error"
    assert "UTF-8" in exc_info.value.message


def test_validate_upload_rejects_empty_file() -> None:
    with pytest.raises(DocumentValidationError) as exc_info:
        validate_upload("notes.txt", b"", max_bytes=100)

    assert exc_info.value.code == "invalid_document"
    assert "empty" in exc_info.value.message.lower()


def test_validate_upload_rejects_oversized_file() -> None:
    with pytest.raises(DocumentValidationError):
        validate_upload("notes.txt", b"hello", max_bytes=2)


def test_validate_upload_normalizes_filename() -> None:
    name = validate_upload("../secret/notes.txt", b"hello", max_bytes=100)
    assert name == "notes.txt"


def test_parser_registry_selects_txt_parser() -> None:
    registry = build_default_registry()
    parser = registry.select("README.TXT")
    assert isinstance(parser, TxtParser)
    assert parser.name == "txt"


def test_parser_registry_selects_by_media_type_when_extension_missing() -> None:
    registry = build_default_registry()
    parser = registry.select("notes", media_type="text/plain; charset=utf-8")
    assert isinstance(parser, TxtParser)


def test_parser_registry_rejects_unsupported_format() -> None:
    registry = ParserRegistry()
    registry.register(TxtParser())

    with pytest.raises(UnsupportedFormatError) as exc_info:
        registry.select("paper.pdf")

    assert exc_info.value.code == "unsupported_format"
    assert exc_info.value.status_code == 415
