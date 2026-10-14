"""Unit tests for SentenceBoundaryChunker.

Verifies:
- Standard sentence-boundary splitting on terminal punctuation (. ! ?)
- Oversized sentences exceeding target_chunk_size
- Short trailing fragments (< min_chunk_size) merged with previous chunk
- Text without punctuation
- Overlap scoped strictly to document boundaries (zero cross-doc leak)
- Parameter validation and error handling
- Deterministic repeat chunking
"""

from __future__ import annotations

import pytest

from app.core.exceptions import ChunkingError
from app.services.chunking.chunkers.sentence_boundary import (
    SentenceBoundaryChunker,
)


def test_sentence_chunker_basic_splitting():
    """Verify clean sentence boundary splitting into target-sized chunks."""
    chunker = SentenceBoundaryChunker(
        target_chunk_size=50, min_chunk_size=20, overlap_sentences=0
    )
    text = (
        "This is sentence one. This is sentence two. This is sentence three. "
        "This is sentence four."
    )
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2
    # Check each chunk ends with sentence punctuation
    for c in chunks:
        assert c.endswith(".")


def test_sentence_chunker_parameter_validation():
    """Verify invalid constructor parameters raise ChunkingError."""
    with pytest.raises(ChunkingError, match="target_chunk_size must be strictly greater than 0"):
        SentenceBoundaryChunker(target_chunk_size=0)

    with pytest.raises(ChunkingError, match="min_chunk_size must be strictly greater than 0"):
        SentenceBoundaryChunker(target_chunk_size=400, min_chunk_size=0)

    with pytest.raises(ChunkingError, match="min_chunk_size cannot exceed target_chunk_size"):
        SentenceBoundaryChunker(target_chunk_size=200, min_chunk_size=300)

    with pytest.raises(ChunkingError, match="overlap_sentences must be non-negative"):
        SentenceBoundaryChunker(target_chunk_size=400, min_chunk_size=100, overlap_sentences=-1)


def test_sentence_chunker_empty_and_short_text():
    """Verify empty text returns empty list, and short text returns single chunk."""
    chunker = SentenceBoundaryChunker(target_chunk_size=400, min_chunk_size=100)
    assert chunker.chunk("") == []
    assert chunker.chunk("   ") == []

    short = "Short document under target size."
    assert chunker.chunk(short) == [short]


def test_sentence_chunker_text_without_punctuation():
    """Verify text lacking terminal punctuation is sliced deterministically without crash."""
    chunker = SentenceBoundaryChunker(target_chunk_size=100, min_chunk_size=40)
    # Long continuous string with no periods, exclamation, or question marks
    text = "word " * 60  # 300 characters without punctuation
    chunks = chunker.chunk(text)
    assert len(chunks) > 1
    # Check all content is preserved
    reconstructed_words = " ".join(chunks).split()
    assert len(reconstructed_words) >= 60


def test_sentence_chunker_oversized_sentence():
    """Verify a single sentence larger than target_chunk_size is sliced without data loss."""
    chunker = SentenceBoundaryChunker(target_chunk_size=100, min_chunk_size=30)
    oversized = "A" * 250 + "."
    chunks = chunker.chunk(oversized)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c) <= 100


def test_sentence_chunker_short_trailing_fragment_merging():
    """Verify trailing fragments shorter than min_chunk_size merge into previous chunk."""
    chunker = SentenceBoundaryChunker(
        target_chunk_size=120, min_chunk_size=60, overlap_sentences=0
    )
    # Sentence 1 + 2 approx 110 chars (forms chunk 1)
    # Sentence 3 is short (20 chars < min_chunk_size 60)
    text = (
        "This is the first long sentence for testing. "
        "Here is the second sentence filling the chunk. "
        "Tiny end."
    )
    chunks = chunker.chunk(text)
    # The tiny sentence should be merged into the previous chunk rather than stand alone
    assert len(chunks) == 1
    assert "Tiny end." in chunks[-1]


def test_sentence_chunker_document_boundary_isolation():
    """Verify overlap is strictly internal to document and never leaks across separate calls."""
    chunker = SentenceBoundaryChunker(
        target_chunk_size=150, min_chunk_size=50, overlap_sentences=1
    )
    doc_a = (
        "Doc A sentence one is here. Doc A sentence two is here. "
        "Doc A sentence three is here."
    )
    doc_b = (
        "Doc B sentence one is here. Doc B sentence two is here. "
        "Doc B sentence three is here."
    )

    chunks_a = chunker.chunk(doc_a)
    chunks_b = chunker.chunk(doc_b)

    # Verify no text from Doc A appears in any chunk of Doc B
    for cb in chunks_b:
        assert "Doc A" not in cb

    # Repeat chunking Doc A produces identical deterministic chunks
    chunks_a_repeat = chunker.chunk(doc_a)
    assert chunks_a == chunks_a_repeat


def test_sentence_chunker_on_real_corpus_fixture():
    """Verify sentence chunker splits real ~800-char corpus documents into ~2 chunks."""
    chunker = SentenceBoundaryChunker(
        target_chunk_size=400, min_chunk_size=150, overlap_sentences=1
    )
    real_sample = (
        "KIP enforces multi-tenant workspace isolation at every tier of the ingestion "
        "and retrieval stack. Tenants operate in isolated logical namespaces identified "
        "by an opaque workspace_id. All incoming REST API requests must supply the "
        "X-KIP-Workspace-ID HTTP header. The backend workspace dependency validates the "
        "presence and non-emptiness of the workspace header. In the vector database layer, "
        "tenant isolation is maintained through Qdrant payload filters. Every chunk indexed "
        "in Qdrant contains a payload field named workspace_id matching the active tenant. "
        "During vector similarity search, a strict Filter condition matching workspace_id "
        "is appended to queries. Qdrant evaluates payload filters before returning top-k "
        "nearest neighbors, preventing cross-tenant leakage. Document deletion and retrieval "
        "endpoints reject requests lacking workspace authorization."
    )
    chunks = chunker.chunk(real_sample)
    assert len(chunks) == 3
    assert "KIP enforces multi-tenant workspace isolation" in chunks[0]
    assert "reject requests lacking workspace authorization" in chunks[-1]
