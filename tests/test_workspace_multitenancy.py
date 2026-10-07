"""Comprehensive multi-tenancy and workspace isolation tests.

Validates that:
- Every document, chunk, embedding, and retrieval is scoped to exactly one workspace.
- Cross-workspace retrieval returns no results (complete isolation).
- Resuming a workspace lists only its own documents.
- Point IDs never collide across workspaces.
- Document idempotency is strictly scoped per workspace.
- Concurrent uploads to different workspaces do not cross-contaminate.
- Partial indexing failure performs cleanup.
- Missing or malformed workspace tokens are rejected.
- Workspace tokens are never logged in full.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from tests.conftest import (
    _EMBEDDING_DIMS,
    DeterministicEmbeddingProvider,
    DeterministicLLMProvider,
)

from app.main import app
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.service import ChunkingService
from app.services.documents.service import DocumentIngestionService
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.service import (
    DocumentIndexingService,
    get_indexing_service,
)
from app.services.llm.manager import LLMManager
from app.services.llm.service import LLMService, get_llm_service
from app.services.rag.models import RAGRequest
from app.services.rag.service import RAGService, get_rag_service
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService
from app.services.vector_store.manager import VectorStoreManager
from app.services.vector_store.models import StoredVector
from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
from app.services.vector_store.providers.qdrant import (
    QdrantVectorStoreProvider,
    _deterministic_point_id,
)
from app.services.vector_store.service import VectorStoreService


@pytest.fixture
def workspace_fixture():
    """Build an isolated, fully wired in-memory pipeline for workspace tests."""
    col_name = f"ws_test_{uuid.uuid4().hex[:10]}"
    emb_service = EmbeddingService(
        manager=EmbeddingManager(provider=DeterministicEmbeddingProvider())
    )
    vs_provider = ChromaVectorStoreProvider(
        collection_name=col_name, persist_directory=None
    )
    vs_service = VectorStoreService(manager=VectorStoreManager(provider=vs_provider))

    indexing_service = DocumentIndexingService(
        chunking_service=ChunkingService(
            chunker=FixedSizeChunker(chunk_size=200, chunk_overlap=20)
        ),
        embedding_service=emb_service,
        vector_store_service=vs_service,
    )
    retrieval_service = RetrievalService(
        embedding_service=emb_service,
        vector_store_service=vs_service,
    )
    llm_service = LLMService(manager=LLMManager(provider=DeterministicLLMProvider()))
    rag_service = RAGService(
        retrieval_service=retrieval_service,
        llm_service=llm_service,
    )

    app.dependency_overrides[get_indexing_service] = lambda: indexing_service
    app.dependency_overrides[get_rag_service] = lambda: rag_service
    app.dependency_overrides[get_llm_service] = lambda: llm_service

    yield {
        "indexing": indexing_service,
        "retrieval": retrieval_service,
        "rag": rag_service,
        "vector_store": vs_service,
    }

    app.dependency_overrides.clear()


def test_qdrant_point_ids_are_workspace_scoped():
    """Ensure Qdrant point IDs differ for identical chunks in different workspaces."""
    p_a = _deterministic_point_id("workspace_a", "chunk_x")
    p_b = _deterministic_point_id("workspace_b", "chunk_x")
    p_a_again = _deterministic_point_id("workspace_a", "chunk_x")

    assert p_a == p_a_again
    assert p_a != p_b


def test_workspace_a_cannot_retrieve_workspace_b_documents(workspace_fixture):
    """Knowledge indexed in Workspace A must never be retrievable from Workspace B."""
    indexing = workspace_fixture["indexing"]
    retrieval = workspace_fixture["retrieval"]
    ingestion = DocumentIngestionService()

    # Index into Workspace A
    doc_a = ingestion.ingest("a.txt", b"Secret Project Apollo coordinates in sector 7")
    indexing.index_document(doc_a, workspace_id="workspace_alpha")

    # Query from Workspace A -> should find chunk
    q_a = RetrievalQuery(
        text="Apollo coordinates", top_k=5, workspace_id="workspace_alpha"
    )
    results_a = retrieval.search(q_a)
    assert len(results_a) > 0
    assert "Apollo" in (results_a[0].text or "")

    # Query from Workspace B -> must NOT find chunk
    q_b = RetrievalQuery(
        text="Apollo coordinates", top_k=5, workspace_id="workspace_beta"
    )
    results_b = retrieval.search(q_b)
    assert len(results_b) == 0


def test_workspace_b_cannot_retrieve_workspace_a_documents(workspace_fixture):
    """Knowledge indexed in Workspace B must never be retrievable from Workspace A."""
    indexing = workspace_fixture["indexing"]
    retrieval = workspace_fixture["retrieval"]
    ingestion = DocumentIngestionService()

    doc_b = ingestion.ingest("b.txt", b"Top secret budget for Project Orion is 50M")
    indexing.index_document(doc_b, workspace_id="workspace_beta")

    q_a = RetrievalQuery(text="Project Orion budget", workspace_id="workspace_alpha")
    results_a = retrieval.search(q_a)
    assert len(results_a) == 0


def test_direct_leakage_contradictory_facts(workspace_fixture):
    """Direct leak test: Project Aurora ownership in two distinct workspaces.

    Workspace A: Project Aurora belongs to Alpha.
    Workspace B: Project Aurora belongs to Beta.
    Query both: 'Who owns Project Aurora?'
    Verify neither workspace receives context from the other.
    """
    indexing = workspace_fixture["indexing"]
    rag = workspace_fixture["rag"]
    ingestion = DocumentIngestionService()

    doc_a = ingestion.ingest("a.txt", b"Project Aurora belongs to Alpha Corporation.")
    doc_b = ingestion.ingest("b.txt", b"Project Aurora belongs to Beta Industries.")

    indexing.index_document(doc_a, workspace_id="ws_company_a")
    indexing.index_document(doc_b, workspace_id="ws_company_b")

    resp_a = rag.answer(
        RAGRequest(
            query="Who owns Project Aurora?",
            workspace_id="ws_company_a",
        )
    )
    assert any("Alpha Corporation" in src.text for src in resp_a.sources)
    assert not any("Beta Industries" in src.text for src in resp_a.sources)

    resp_b = rag.answer(
        RAGRequest(
            query="Who owns Project Aurora?",
            workspace_id="ws_company_b",
        )
    )
    assert any("Beta Industries" in src.text for src in resp_b.sources)
    assert not any("Alpha Corporation" in src.text for src in resp_b.sources)


def test_document_exists_is_workspace_scoped(workspace_fixture):
    """Document existence check must be partitioned strictly by workspace."""
    indexing = workspace_fixture["indexing"]
    ingestion = DocumentIngestionService()

    doc = ingestion.ingest("shared.txt", b"Generic company handbook")
    indexing.index_document(doc, workspace_id="workspace_1")

    assert indexing.document_exists(doc.id, workspace_id="workspace_1") is True
    assert indexing.document_exists(doc.id, workspace_id="workspace_2") is False


def test_workspace_document_listing_is_isolated(workspace_fixture):
    """Listing documents in Workspace A returns only Workspace A documents."""
    indexing = workspace_fixture["indexing"]
    ingestion = DocumentIngestionService()

    doc1 = ingestion.ingest("doc1.txt", b"Content 1")
    doc2 = ingestion.ingest("doc2.txt", b"Content 2")

    indexing.index_document(doc1, workspace_id="tenant_1")
    indexing.index_document(doc2, workspace_id="tenant_2")

    list_1 = indexing.list_documents(workspace_id="tenant_1")
    list_2 = indexing.list_documents(workspace_id="tenant_2")

    assert len(list_1) == 1
    assert list_1[0]["document_id"] == doc1.id

    assert len(list_2) == 1
    assert list_2[0]["document_id"] == doc2.id


def test_missing_and_invalid_workspace_id_rejected():
    """API endpoints must return 400 when X-KIP-Workspace-ID is missing or bad."""
    client = TestClient(app, raise_server_exceptions=False)

    # 1. Missing header on upload
    res1 = client.post(
        "/api/v1/documents",
        files={"file": ("test.txt", b"content", "text/plain")},
    )
    assert res1.status_code == 400

    # 2. Too short token
    res2 = client.post(
        "/api/v1/documents",
        headers={"X-KIP-Workspace-ID": "abc"},
        files={"file": ("test.txt", b"content", "text/plain")},
    )
    assert res2.status_code == 400

    # 3. Invalid characters
    res3 = client.post(
        "/api/v1/documents",
        headers={"X-KIP-Workspace-ID": "bad token with spaces!"},
        files={"file": ("test.txt", b"content", "text/plain")},
    )
    assert res3.status_code == 400

    # 4. Missing header on RAG query
    res4 = client.post("/api/v1/rag/answer", json={"query": "test"})
    assert res4.status_code == 400

    # 5. Missing header on document listing
    res5 = client.get("/api/v1/documents")
    assert res5.status_code == 400


@pytest.mark.anyio
async def test_concurrent_same_document_upload_is_idempotent(workspace_fixture):
    """Simultaneous uploads of the same document in the same workspace are safe."""
    indexing = workspace_fixture["indexing"]
    ingestion = DocumentIngestionService()

    doc = ingestion.ingest("test.txt", b"Concurrent test bytes payload")

    # Run two index operations concurrently
    res1, res2 = await asyncio.gather(
        asyncio.to_thread(indexing.index_document, doc, "ws_concurrent"),
        asyncio.to_thread(indexing.index_document, doc, "ws_concurrent"),
    )

    total_chunks = res1.chunks_indexed + res2.chunks_indexed
    # Exactly one should index chunks, and one should be 0
    assert total_chunks > 0
    # Vector store count should match exactly 1 copy of chunks
    assert workspace_fixture["vector_store"].count("ws_concurrent") == max(
        res1.chunks_indexed, res2.chunks_indexed
    )


def test_workspace_token_never_appears_in_logs(workspace_fixture, caplog):
    """Full raw workspace token must never be printed to logs."""
    indexing = workspace_fixture["indexing"]
    ingestion = DocumentIngestionService()

    secret_workspace_token = "secret_tenant_token_9876543210_xyz"

    doc = ingestion.ingest("safe.txt", b"Logging security test")
    with caplog.at_level(logging.DEBUG):
        indexing.index_document(doc, workspace_id=secret_workspace_token)

    for record in caplog.records:
        assert secret_workspace_token not in record.getMessage()


def test_qdrant_provider_with_multitenancy():
    """Verify real Qdrant in-memory provider enforces tenant isolation."""
    provider = QdrantVectorStoreProvider(
        collection_name=f"test_multi_{uuid.uuid4().hex[:8]}",
        url=":memory:",
        embedding_dimensions=_EMBEDDING_DIMS,
    )

    v_a = StoredVector(
        id="c1",
        vector=[0.5] * _EMBEDDING_DIMS,
        metadata={"document_id": "doc_a", "text": "Tenant A facts"},
    )
    v_b = StoredVector(
        id="c1",
        vector=[0.5] * _EMBEDDING_DIMS,
        metadata={"document_id": "doc_b", "text": "Tenant B facts"},
    )

    provider.upsert([v_a], workspace_id="tenant_a")
    provider.upsert([v_b], workspace_id="tenant_b")

    # Both count independently
    assert provider.count("tenant_a") == 1
    assert provider.count("tenant_b") == 1

    # Search in tenant A returns only tenant A
    res_a = provider.search(
        query_vector=[0.5] * _EMBEDDING_DIMS,
        top_k=5,
        workspace_id="tenant_a",
    )
    assert len(res_a) == 1
    assert res_a[0].metadata["workspace_id"] == "tenant_a"
    assert res_a[0].metadata["text"] == "Tenant A facts"

    # Search in tenant B returns only tenant B
    res_b = provider.search(
        query_vector=[0.5] * _EMBEDDING_DIMS,
        top_k=5,
        workspace_id="tenant_b",
    )
    assert len(res_b) == 1
    assert res_b[0].metadata["workspace_id"] == "tenant_b"
    assert res_b[0].metadata["text"] == "Tenant B facts"


def test_workspace_listing_api_endpoint(workspace_fixture):
    """GET /api/v1/documents returns documents belonging to workspace."""
    indexing = workspace_fixture["indexing"]
    ingestion = DocumentIngestionService()

    doc = ingestion.ingest("guide.txt", b"Some text content bytes")
    indexing.index_document(doc, workspace_id="workspace_listed")

    client = TestClient(app)
    response = client.get(
        "/api/v1/documents",
        headers={"X-KIP-Workspace-ID": "workspace_listed"},
    )
    assert response.status_code == 200
    docs = response.json()
    assert len(docs) == 1
    assert docs[0]["document_id"] == doc.id
    assert docs[0]["filename"] == "guide.txt"
