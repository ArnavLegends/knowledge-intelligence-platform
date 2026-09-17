"""Tests for the chunking subsystem."""

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.core.exceptions import ChunkingError
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.models import Chunk
from app.services.chunking.service import ChunkingService
from app.services.documents.models import Document


def test_chunk_model_construction():
    """Test valid Chunk construction and properties."""
    chunk = Chunk(
        id="c1",
        document_id="d1",
        index=0,
        text="Hello world",
        character_count=11,
        metadata={"source": "test"},
    )
    assert chunk.id == "c1"
    assert chunk.document_id == "d1"
    assert chunk.index == 0
    assert chunk.text == "Hello world"
    assert chunk.character_count == 11
    assert chunk.metadata == {"source": "test"}


def test_fixed_size_chunker_shorter_than_size():
    """Test chunker when text is shorter than chunk size."""
    chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=2)
    chunks = chunker.chunk("Short")
    assert chunks == ["Short"]


def test_fixed_size_chunker_exact_size():
    """Test chunker when text is exactly the chunk size."""
    chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=2)
    chunks = chunker.chunk("1234567890")
    assert chunks == ["1234567890"]


def test_fixed_size_chunker_larger_than_size():
    """Test chunker with normal overlap."""
    chunker = FixedSizeChunker(chunk_size=10, chunk_overlap=2)
    # step = 8
    # 0-10: 1234567890
    # 8-18: 90abcdefgh
    chunks = chunker.chunk("1234567890abcdefgh")
    assert len(chunks) == 2
    assert chunks[0] == "1234567890"
    assert chunks[1] == "90abcdefgh"


def test_fixed_size_chunker_zero_overlap():
    """Test chunker with zero overlap."""
    chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=0)
    chunks = chunker.chunk("1234567890abc")
    assert len(chunks) == 3
    assert chunks[0] == "12345"
    assert chunks[1] == "67890"
    assert chunks[2] == "abc"


def test_fixed_size_chunker_maximum_overlap():
    """Test chunker with maximum valid overlap (size - 1)."""
    chunker = FixedSizeChunker(chunk_size=3, chunk_overlap=2)
    # step = 1
    chunks = chunker.chunk("abcde")
    assert chunks == ["abc", "bcd", "cde"]


def test_fixed_size_chunker_invalid_size():
    """Test chunker raises error on invalid size."""
    with pytest.raises(ChunkingError):
        FixedSizeChunker(chunk_size=0, chunk_overlap=0)


def test_fixed_size_chunker_invalid_overlap():
    """Test chunker raises error on invalid overlap."""
    with pytest.raises(ChunkingError):
        FixedSizeChunker(chunk_size=10, chunk_overlap=-1)

    with pytest.raises(ChunkingError):
        FixedSizeChunker(chunk_size=10, chunk_overlap=10)


def test_fixed_size_chunker_deterministic():
    """Test chunker produces deterministic results."""
    chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=2)
    text = "The quick brown fox jumps over the lazy dog"
    run1 = chunker.chunk(text)
    run2 = chunker.chunk(text)
    assert run1 == run2


def test_settings_validation():
    """Test configuration validation."""
    settings = Settings(chunk_size=1000, chunk_overlap=200)
    assert settings.chunk_size == 1000

    with pytest.raises(ValueError):
        Settings(chunk_size=0, chunk_overlap=0)

    with pytest.raises(ValueError):
        Settings(chunk_size=100, chunk_overlap=-1)

    with pytest.raises(ValueError):
        Settings(chunk_size=100, chunk_overlap=100)


def test_chunking_service():
    """Test ChunkingService orchestrates chunking properly."""
    chunker = FixedSizeChunker(chunk_size=5, chunk_overlap=0)
    service = ChunkingService(chunker=chunker)

    doc = Document.create(
        document_id="doc-123",
        filename="test.txt",
        media_type="text/plain",
        text="1234567890",
        metadata={"author": "test"},
        ingested_at=datetime.now(UTC),
    )

    chunks = service.chunk_document(doc)

    assert len(chunks) == 2
    assert chunks[0].document_id == "doc-123"
    assert chunks[0].index == 0
    assert chunks[0].text == "12345"
    assert chunks[0].character_count == 5
    assert chunks[0].metadata == {"author": "test"}

    assert chunks[1].document_id == "doc-123"
    assert chunks[1].index == 1
    assert chunks[1].text == "67890"
    assert chunks[1].character_count == 5
    assert chunks[1].metadata == {"author": "test"}
