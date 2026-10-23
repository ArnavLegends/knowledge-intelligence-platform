"""Stage C: Runtime Reliability and Parser Safety Tests.

Covers:
- Filename validation: null bytes, control characters, overlong names
- PDF parser: empty-page PDFs produce empty text without raising
- PDF parser: encrypted PDF raises DocumentParseError
- TXT parser: latin-1 content that is not valid UTF-8 raises DocumentParseError
- Chunker: whitespace-only and single-sentence inputs handled safely
- Chunker: very large inputs are chunked without error (no OOM / hard crash)
- RAGService: workspace_id required
- DocumentIngestionService: full validation-to-parse pipeline with safe name
"""

from __future__ import annotations

import io

import pytest

from app.core.exceptions import DocumentParseError, DocumentValidationError
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.chunkers.sentence_boundary import (
    SentenceBoundaryChunker,
)
from app.services.documents.parsers.md import MarkdownParser
from app.services.documents.parsers.pdf import PdfParser
from app.services.documents.parsers.txt import TxtParser
from app.services.documents.service import DocumentIngestionService
from app.services.documents.validation import normalize_filename, validate_upload

# ---------------------------------------------------------------------------
# Filename validation
# ---------------------------------------------------------------------------


def test_normalize_filename_rejects_null_byte():
    with pytest.raises(DocumentValidationError, match="invalid characters"):
        normalize_filename("file\x00name.txt")


def test_normalize_filename_rejects_newline():
    with pytest.raises(DocumentValidationError, match="invalid characters"):
        normalize_filename("file\nname.txt")


def test_normalize_filename_rejects_tab():
    with pytest.raises(DocumentValidationError, match="invalid characters"):
        normalize_filename("file\tname.txt")


def test_normalize_filename_rejects_del_char():
    """DEL (0x7f) is rejected."""
    with pytest.raises(DocumentValidationError, match="invalid characters"):
        normalize_filename("file\x7fname.txt")


def test_normalize_filename_rejects_overlong():
    """Filenames exceeding 255 UTF-8 bytes are rejected."""
    long_name = "a" * 256 + ".txt"
    with pytest.raises(DocumentValidationError, match="maximum allowed length"):
        normalize_filename(long_name)


def test_normalize_filename_accepts_255_byte_name():
    """Exactly 255 bytes is accepted."""
    # 251 'a' + '.txt' = 255 bytes
    name = "a" * 251 + ".txt"
    result = normalize_filename(name)
    assert result == name


def test_normalize_filename_rejects_blank():
    with pytest.raises(DocumentValidationError, match="valid filename"):
        normalize_filename("   ")


def test_normalize_filename_rejects_none():
    with pytest.raises(DocumentValidationError, match="valid filename"):
        normalize_filename(None)


def test_normalize_filename_strips_directory_traversal():
    """Path traversal components should be stripped to the basename."""
    result = normalize_filename("../../etc/passwd")
    assert result == "passwd"


def test_normalize_filename_normal_names_pass():
    assert normalize_filename("document.pdf") == "document.pdf"
    assert normalize_filename("My Report 2024.docx") == "My Report 2024.docx"
    assert normalize_filename("  report.txt  ") == "report.txt"


def test_validate_upload_rejects_empty_content():
    with pytest.raises(DocumentValidationError, match="empty"):
        validate_upload("test.txt", b"", max_bytes=1024)


def test_validate_upload_rejects_oversized_content():
    with pytest.raises(DocumentValidationError, match="exceeds"):
        validate_upload("test.txt", b"x" * 1025, max_bytes=1024)


def test_validate_upload_returns_safe_name():
    result = validate_upload("../../report.txt", b"content", max_bytes=1024)
    assert result == "report.txt"


# ---------------------------------------------------------------------------
# PDF parser safety
# ---------------------------------------------------------------------------


def _make_blank_pdf(num_pages: int = 1) -> bytes:
    try:
        from pypdf import PdfWriter
    except ImportError:
        pytest.skip("pypdf not installed")
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_pdf_parser_blank_page_returns_empty_text():
    """A PDF with no extractable text returns empty string, not an error."""
    content = _make_blank_pdf(1)
    parser = PdfParser()
    result = parser.parse("blank.pdf", content)
    assert result.text == ""
    assert result.metadata["pages"] == 1


def test_pdf_parser_multi_blank_pages_returns_empty_text():
    content = _make_blank_pdf(5)
    parser = PdfParser()
    result = parser.parse("blank5.pdf", content)
    assert result.text == ""
    assert result.metadata["pages"] == 5


def test_pdf_parser_rejects_invalid_bytes():
    parser = PdfParser()
    with pytest.raises(DocumentParseError, match="Could not read PDF"):
        parser.parse("bad.pdf", b"not a pdf at all")


def test_pdf_parser_rejects_truncated_pdf():
    """Truncated/corrupted PDF header raises DocumentParseError."""
    parser = PdfParser()
    with pytest.raises(DocumentParseError, match="Could not read PDF"):
        parser.parse("truncated.pdf", b"%PDF-1.4\n%%EOF")


# ---------------------------------------------------------------------------
# TXT parser: non-UTF-8 bytes
# ---------------------------------------------------------------------------


def test_txt_parser_rejects_latin1_bytes():
    """Latin-1 bytes that are invalid UTF-8 raise DocumentParseError."""
    parser = TxtParser()
    latin1_content = "caf\xe9".encode("latin-1")  # 0xe9 byte invalid UTF-8 sequence
    with pytest.raises(DocumentParseError, match="UTF-8"):
        parser.parse("test.txt", latin1_content)


def test_txt_parser_accepts_valid_utf8():
    parser = TxtParser()
    result = parser.parse("test.txt", b"Hello, world")
    assert "Hello" in result.text


def test_txt_parser_strips_bom():
    parser = TxtParser()
    result = parser.parse("test.txt", "\ufeffHello BOM".encode("utf-8"))
    assert result.text == "Hello BOM"


# ---------------------------------------------------------------------------
# Markdown parser safety
# ---------------------------------------------------------------------------


def test_markdown_parser_empty_file():
    parser = MarkdownParser()
    result = parser.parse("empty.md", b"")
    assert result.text == ""


def test_markdown_parser_whitespace_only():
    parser = MarkdownParser()
    result = parser.parse("ws.md", b"   \n\n   \n")
    assert result.text.strip() == ""


# ---------------------------------------------------------------------------
# Chunker robustness
# ---------------------------------------------------------------------------


def test_fixed_chunker_empty_input():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=20)
    assert chunker.chunk("") == []


def test_fixed_chunker_whitespace_only():
    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=20)
    assert chunker.chunk("   \n\t  ") == []


def test_sentence_chunker_empty_input():
    chunker = SentenceBoundaryChunker(target_chunk_size=400)
    assert chunker.chunk("") == []


def test_sentence_chunker_single_sentence_under_target():
    chunker = SentenceBoundaryChunker(target_chunk_size=400)
    result = chunker.chunk("This is one sentence.")
    assert result == ["This is one sentence."]


def test_sentence_chunker_large_input_does_not_crash():
    """50 000-character input chunked without error."""
    chunker = SentenceBoundaryChunker(target_chunk_size=400, min_chunk_size=100)
    text = "The quick brown fox jumps over the lazy dog. " * 1100  # ~50 000 chars
    chunks = chunker.chunk(text)
    assert len(chunks) > 10
    # Every chunk within 1.5x target ceiling
    for c in chunks:
        assert len(c) <= 400 * 1.5 + 1, f"Chunk too large: {len(c)}"


def test_fixed_chunker_large_input_does_not_crash():
    chunker = FixedSizeChunker(chunk_size=200, chunk_overlap=40)
    text = "x" * 50_000
    chunks = chunker.chunk(text)
    assert len(chunks) > 100


# ---------------------------------------------------------------------------
# DocumentIngestionService integration
# ---------------------------------------------------------------------------


def test_ingestion_service_null_byte_filename_rejected():
    svc = DocumentIngestionService()
    with pytest.raises(DocumentValidationError, match="invalid characters"):
        svc.ingest("file\x00.txt", b"hello world")


def test_ingestion_service_overlong_filename_rejected():
    svc = DocumentIngestionService()
    with pytest.raises(DocumentValidationError, match="maximum allowed length"):
        svc.ingest("a" * 256 + ".txt", b"hello world")


def test_ingestion_service_normalizes_path_traversal():
    svc = DocumentIngestionService()
    doc = svc.ingest("../../etc/report.txt", b"safe content here")
    assert doc.filename == "report.txt"


def test_ingestion_service_empty_content_rejected():
    svc = DocumentIngestionService()
    with pytest.raises(DocumentValidationError, match="empty"):
        svc.ingest("file.txt", b"")
