"""Idempotency tests for document ingestion and indexing.

These tests must be fully offline and require no external API credentials.
The deterministic_indexing_service fixture (defined in conftest.py) wires
an ephemeral Chroma collection with a DeterministicEmbeddingProvider so
that no real LLM or embedding provider is ever instantiated.
"""

import hashlib

import pytest

from app.api.v1.documents import upload_document
from app.services.documents.service import DocumentIngestionService


class MockUploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str = "text/plain"):
        self.filename = filename
        self._content = content
        self.content_type = content_type

    async def read(self):
        return self._content


@pytest.mark.anyio
async def test_duplicate_upload_prevents_duplicate_indexing(
    deterministic_indexing_service,
):
    """Identical content uploaded twice: second upload must be a no-op."""
    ingestion = DocumentIngestionService()
    indexing = deterministic_indexing_service

    file1 = MockUploadFile("test.txt", b"Hello idempotency")
    file2 = MockUploadFile("test.txt", b"Hello idempotency")

    res1 = await upload_document(file1, ingestion, indexing)
    assert res1.chunks_indexed > 0

    res2 = await upload_document(file2, ingestion, indexing)
    assert res2.chunks_indexed == 0
    assert res1.id == res2.id


@pytest.mark.anyio
async def test_same_filename_different_content_creates_new_document(
    deterministic_indexing_service,
):
    """Same filename but different content must produce distinct documents."""
    ingestion = DocumentIngestionService()
    indexing = deterministic_indexing_service

    file1 = MockUploadFile("test.txt", b"Hello A")
    file2 = MockUploadFile("test.txt", b"Hello B")

    res1 = await upload_document(file1, ingestion, indexing)
    res2 = await upload_document(file2, ingestion, indexing)

    assert res1.id != res2.id
    assert res1.chunks_indexed > 0
    assert res2.chunks_indexed > 0


@pytest.mark.anyio
async def test_different_filename_same_content_is_idempotent(
    deterministic_indexing_service,
):
    """Different filenames with identical content must collapse to one document."""
    ingestion = DocumentIngestionService()
    indexing = deterministic_indexing_service

    file1 = MockUploadFile("test1.txt", b"Hello exact content")
    file2 = MockUploadFile("test2.txt", b"Hello exact content")

    res1 = await upload_document(file1, ingestion, indexing)
    res2 = await upload_document(file2, ingestion, indexing)

    assert res1.id == res2.id
    assert res1.chunks_indexed > 0
    assert res2.chunks_indexed == 0


def test_deterministic_identity_across_process_instances():
    """SHA-256 document IDs must be stable regardless of instantiation context."""
    content = b"Process A"
    expected_id = hashlib.sha256(content).hexdigest()

    svc1 = DocumentIngestionService()
    doc1 = svc1.ingest("a.txt", content)

    svc2 = DocumentIngestionService()
    doc2 = svc2.ingest("b.txt", content)

    assert doc1.id == expected_id
    assert doc2.id == expected_id


@pytest.mark.anyio
async def test_same_file_different_workspaces_are_independent(
    deterministic_indexing_service,
):
    """Same content uploaded in different workspaces must index independently."""
    ingestion = DocumentIngestionService()
    indexing = deterministic_indexing_service

    file_a = MockUploadFile("shared.txt", b"Identical knowledge payload")
    file_b = MockUploadFile("shared.txt", b"Identical knowledge payload")

    res_a = await upload_document(
        file_a, ingestion, indexing, workspace_id="workspace_alpha"
    )
    assert res_a.chunks_indexed > 0

    res_b = await upload_document(
        file_b, ingestion, indexing, workspace_id="workspace_beta"
    )
    assert res_b.chunks_indexed > 0
    assert res_a.id == res_b.id
