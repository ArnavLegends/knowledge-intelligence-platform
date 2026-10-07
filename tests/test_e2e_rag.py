"""End-to-end RAG workflow test.

This test exercises the complete KIP pipeline without real external services:
    POST /api/v1/documents  →  ingestion  →  indexing  →  vector store
    POST /api/v1/rag/answer →  retrieval  →  context  →  LLM  →  response

External boundaries (embedding model, LLM) are replaced with deterministic fakes.
Internal KIP orchestration (ingestion, chunking, indexing, retrieval, RAG service)
uses real implementations.

ENGINEERING VALIDATION — this test proves functional correctness of the end-to-end
integration. It does not evaluate RAG quality, accuracy, or production performance.
"""

from __future__ import annotations

import hashlib

import pytest

# The e2e_pipeline fixture and DeterministicEmbeddingProvider /
# DeterministicLLMProvider are injected from conftest.py automatically.
# Service imports needed by test helper functions in this module.
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.service import ChunkingService
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.service import DocumentIndexingService

# ---------------------------------------------------------------------------
# Helpers used only within this test module
# ---------------------------------------------------------------------------

_EMBEDDING_DIMS = 8


def _text_to_vector(text: str) -> list[float]:
    """Produce a stable 8-dim float vector from the SHA-256 hash of text."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i] / 255.0 for i in range(_EMBEDDING_DIMS)]


# ---------------------------------------------------------------------------
# E2E: Complete upload → query workflow
# ---------------------------------------------------------------------------

DOCUMENT_TEXT = (
    "KIP Knowledge Base Entry: The mitochondria is the powerhouse of the cell. "
    "This well-known biological fact describes how mitochondria produce ATP through "
    "cellular respiration, providing energy for the cell's functions. "
    "The process involves the electron transport chain and oxidative phosphorylation."
)


def test_e2e_document_upload_and_rag_answer(e2e_pipeline):
    """Core E2E test: upload a document, query it, verify sourced answer.

    Steps:
    1. Upload a real text document via POST /api/v1/documents
    2. Verify the upload response reports success and chunks_indexed > 0
    3. Verify content reached the ephemeral vector store
    4. Call POST /api/v1/rag/answer with a related question
    5. Verify the response contains an answer and non-empty sources
    6. Verify the sources reference the uploaded document
    """
    client, vs_service = e2e_pipeline

    # Step 1 & 2: Upload document
    upload_response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "biology_notes.txt",
                DOCUMENT_TEXT.encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 200, f"Upload failed: {upload_response.text}"
    upload_body = upload_response.json()

    assert upload_body["filename"] == "biology_notes.txt"
    assert upload_body["media_type"] == "text/plain"
    assert upload_body["id"]  # Non-empty document ID
    assert upload_body["chunks_indexed"] > 0, (
        "Document must be indexed: chunks_indexed should be > 0"
    )

    document_id = upload_body["id"]

    # Step 3: Verify content reached the vector store
    count_before_query = vs_service.count()
    assert count_before_query == upload_body["chunks_indexed"], (
        f"Vector store should contain {upload_body['chunks_indexed']} chunks, "
        f"found {count_before_query}"
    )

    # Step 4: Query with a question whose answer is in the document
    rag_response = client.post(
        "/api/v1/rag/answer",
        json={
            "query": "What is the mitochondria?",
            "top_k": 3,
        },
    )

    assert rag_response.status_code == 200, f"RAG query failed: {rag_response.text}"
    rag_body = rag_response.json()

    # Step 5: Verify answer structure
    assert "answer" in rag_body
    assert rag_body["answer"]  # Non-empty answer
    assert "sources" in rag_body
    assert len(rag_body["sources"]) > 0, (
        "RAG response must contain at least one source. "
        "This fails if retrieval is broken or indexing was disconnected."
    )

    # Step 6: Verify provenance — sources should reference the uploaded document
    source_doc_ids = [s.get("document_id") for s in rag_body["sources"]]
    assert document_id in source_doc_ids, (
        f"Expected document_id={document_id} in sources, got {source_doc_ids}. "
        "Provenance was lost in the pipeline."
    )

    # Verify source chunk_ids are present (non-empty)
    for source in rag_body["sources"]:
        assert source.get("chunk_id"), "Each source must have a non-empty chunk_id"
        assert source.get("text"), "Each source must have non-empty text"
        assert source.get("rank") is not None, "Each source must have a rank"


def test_e2e_upload_indexes_correctly(e2e_pipeline):
    """Verify that upload correctly routes through indexing, not just ingestion."""
    client, vs_service = e2e_pipeline

    # Vector store is initially empty
    assert vs_service.count() == 0

    # Upload
    response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "test.txt",
                b"Hello, this is test content for indexing.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    body = response.json()
    chunks_indexed = body["chunks_indexed"]
    assert chunks_indexed > 0

    # Vector store must now contain data — proves indexing actually ran
    assert vs_service.count() == chunks_indexed, (
        "If this fails, the upload endpoint is not calling the indexing service."
    )


def test_e2e_rag_empty_context_when_no_documents(e2e_pipeline):
    """RAG must gracefully return empty-context message when no docs are indexed."""
    client, vs_service = e2e_pipeline

    # No documents uploaded — vector store is empty
    assert vs_service.count() == 0

    rag_response = client.post(
        "/api/v1/rag/answer",
        json={"query": "What is the capital of France?"},
    )

    assert rag_response.status_code == 200
    body = rag_response.json()
    assert body["answer"]  # Should be the empty-context message
    assert body["sources"] == []  # No sources when no documents


# ---------------------------------------------------------------------------
# Idempotency: deterministic chunk IDs + upsert behavior
# ---------------------------------------------------------------------------


def test_deterministic_chunk_ids_stable_across_runs():
    """Prove that chunking the same document twice yields identical chunk IDs.

    This verifies the SHA-256-based deterministic ID implementation.
    """
    from datetime import UTC, datetime

    from app.services.documents.models import Document

    chunker = FixedSizeChunker(chunk_size=50, chunk_overlap=5)
    service = ChunkingService(chunker=chunker)

    doc = Document.create(
        document_id="stable-doc-id",
        filename="stable.txt",
        media_type="text/plain",
        text=(
            "Deterministic chunking produces stable identifiers. "
            "This text will be chunked twice to verify ID stability."
        ),
        metadata={},
        ingested_at=datetime.now(UTC),
    )

    chunks_run1 = service.chunk_document(doc)
    chunks_run2 = service.chunk_document(doc)

    assert len(chunks_run1) == len(chunks_run2), "Chunk count must be deterministic"

    for c1, c2 in zip(chunks_run1, chunks_run2, strict=True):
        assert c1.id == c2.id, (
            f"Chunk IDs must be identical across runs. "
            f"Got {c1.id} vs {c2.id} at index {c1.index}"
        )
        assert c1.index == c2.index
        assert c1.text == c2.text
        assert c1.document_id == c2.document_id


def test_different_documents_produce_different_chunk_ids():
    """Prove that different document IDs produce different chunk IDs."""
    from datetime import UTC, datetime

    from app.services.documents.models import Document

    chunker = FixedSizeChunker(chunk_size=100, chunk_overlap=0)
    service = ChunkingService(chunker=chunker)

    doc1 = Document.create(
        document_id="doc-aaa",
        filename="a.txt",
        media_type="text/plain",
        text="Same text content here.",
        metadata={},
        ingested_at=datetime.now(UTC),
    )
    doc2 = Document.create(
        document_id="doc-bbb",
        filename="b.txt",
        media_type="text/plain",
        text="Same text content here.",
        metadata={},
        ingested_at=datetime.now(UTC),
    )

    chunks1 = service.chunk_document(doc1)
    chunks2 = service.chunk_document(doc2)

    assert len(chunks1) == len(chunks2) == 1
    # Different document IDs → different chunk IDs even for identical text
    assert chunks1[0].id != chunks2[0].id, (
        "Different documents must produce different chunk IDs"
    )


def test_idempotent_indexing_does_not_duplicate(e2e_pipeline):
    """Prove that indexing the same document twice does not increase the store size.

    This is the idempotency test: upsert behavior must prevail over insert.
    """
    client, vs_service = e2e_pipeline

    file_content = b"Idempotency test content. This exact document is indexed twice."
    filename = "idempotent.txt"

    # First upload
    resp1 = client.post(
        "/api/v1/documents",
        files={"file": (filename, file_content, "text/plain")},
    )
    assert resp1.status_code == 200
    body1 = resp1.json()
    doc1_id = body1["id"]
    count_after_first = vs_service.count()
    assert count_after_first == body1["chunks_indexed"]

    # Second upload of the SAME binary content — same chunk positions
    # NOTE: document_id is generated fresh (uuid4) so chunk IDs will differ.
    # This is correct: idempotency applies to RE-INDEXING the same document
    # (same document_id), not uploading as a new document.
    # We test true idempotency at the service level below.
    _ = doc1_id  # suppress unused warning

    # True idempotency test: index the same Document object twice
    from datetime import UTC, datetime

    from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
    from app.services.chunking.service import ChunkingService
    from app.services.documents.models import Document

    doc = Document.create(
        document_id="fixed-doc-for-idempotency",
        filename="idem.txt",
        media_type="text/plain",
        text="Idempotency check: same document ID, same chunks, same vector store IDs.",
        metadata={},
        ingested_at=datetime.now(UTC),
    )

    # Build a fresh indexing service backed by the same vs_service from the fixture
    from conftest import DeterministicEmbeddingProvider

    emb_provider = DeterministicEmbeddingProvider()
    emb_manager = EmbeddingManager(provider=emb_provider)
    emb_service = EmbeddingService(manager=emb_manager)

    chunking_svc = ChunkingService(FixedSizeChunker(chunk_size=200, chunk_overlap=20))
    indexing_svc = DocumentIndexingService(
        chunking_service=chunking_svc,
        embedding_service=emb_service,
        vector_store_service=vs_service,  # Same store as the fixture
    )

    result1 = indexing_svc.index_document(doc)
    count_mid = vs_service.count()

    result2 = indexing_svc.index_document(doc)
    count_end = vs_service.count()

    assert result1.chunks_indexed == result2.chunks_indexed, (
        "Same document must produce the same number of chunks on both runs"
    )
    assert count_end == count_mid, (
        f"Vector store size must NOT grow on re-indexing. "
        f"Before second index: {count_mid}, After: {count_end}. "
        "This means upsert is not working correctly."
    )


def test_e2e_provenance_chain_integrity(e2e_pipeline):
    """Verify provenance chain: document → chunk → embedding → retrieved chunk → source.

    This test directly inspects the vector store after upload to confirm
    that metadata (document_id, text) is preserved end-to-end.
    """
    client, vs_service = e2e_pipeline

    text = "Provenance test: unique phrase zeta-gamma-delta-epsilon for retrieval."
    response = client.post(
        "/api/v1/documents",
        files={"file": ("provenance.txt", text.encode(), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    document_id = body["id"]
    assert body["chunks_indexed"] > 0

    # Query for the unique phrase to trigger retrieval
    rag_resp = client.post(
        "/api/v1/rag/answer",
        json={"query": "zeta-gamma-delta-epsilon", "top_k": 1},
    )
    assert rag_resp.status_code == 200
    rag_body = rag_resp.json()

    assert len(rag_body["sources"]) > 0, "Should retrieve the uploaded chunk"
    source = rag_body["sources"][0]

    # Verify provenance fields
    assert source["document_id"] == document_id, (
        "Source document_id must match the uploaded document's ID"
    )
    assert source["chunk_id"], "chunk_id must not be empty"
    assert source["rank"] == 1, "First source must have rank 1"
    # The retrieved text must be from our document
    assert "zeta-gamma-delta-epsilon" in source["text"] or source["text"] in text, (
        "Retrieved text must come from the uploaded document"
    )


def test_e2e_markdown_upload_and_rag_answer(e2e_pipeline):
    """Test full RAG pipeline using a Markdown file."""
    client, vs_service = e2e_pipeline

    md_text = "# KIP Architecture\n\nThe system uses *ChromaDB* for vector storage."

    upload_response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "architecture.md",
                md_text.encode("utf-8"),
                "text/markdown",
            )
        },
    )

    assert upload_response.status_code == 200, f"Upload failed: {upload_response.text}"
    upload_body = upload_response.json()
    assert upload_body["chunks_indexed"] > 0

    rag_response = client.post(
        "/api/v1/rag/answer",
        json={"query": "What database is used?", "top_k": 1},
    )

    assert rag_response.status_code == 200
    rag_body = rag_response.json()
    assert len(rag_body["sources"]) > 0
    assert rag_body["sources"][0]["document_id"] == upload_body["id"]
    assert "ChromaDB" in rag_body["sources"][0]["text"]


def test_e2e_docx_upload_and_rag_answer(e2e_pipeline):
    """Test full RAG pipeline using a DOCX file."""
    try:
        import docx
    except ImportError:
        pytest.skip("python-docx not installed")

    client, vs_service = e2e_pipeline

    import io

    doc = docx.Document()
    doc.add_paragraph("DOCX Integration Document")
    doc.add_paragraph("KIP supports Microsoft Word formats out of the box.")

    buf = io.BytesIO()
    doc.save(buf)
    content = buf.getvalue()

    upload_response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "integration.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert upload_response.status_code == 200, f"Upload failed: {upload_response.text}"
    upload_body = upload_response.json()
    assert upload_body["chunks_indexed"] > 0

    rag_response = client.post(
        "/api/v1/rag/answer",
        json={"query": "What formats does KIP support?", "top_k": 1},
    )

    assert rag_response.status_code == 200
    rag_body = rag_response.json()
    assert len(rag_body["sources"]) > 0
    assert rag_body["sources"][0]["document_id"] == upload_body["id"]
    assert "Microsoft Word formats" in rag_body["sources"][0]["text"]
