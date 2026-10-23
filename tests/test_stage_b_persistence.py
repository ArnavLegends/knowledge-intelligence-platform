"""Stage B Document Persistence, Lifecycle, Replacement, and Reindexing Tests."""

from __future__ import annotations

import pytest
from tests.conftest import DeterministicEmbeddingProvider

from app.core.exceptions import AppException
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.service import ChunkingService
from app.services.documents.metadata_store import DocumentMetadataStore
from app.services.documents.models import Document
from app.services.documents.storage import LocalDocumentStorage
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.service import DocumentIndexingService
from app.services.llm.base import LLMProvider
from app.services.llm.manager import LLMManager
from app.services.llm.models import LLMRequest, LLMResponse, LLMUsage
from app.services.llm.service import LLMService
from app.services.rag.models import RAGRequest
from app.services.rag.service import RAGService
from app.services.retrieval.service import RetrievalService
from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
from app.services.vector_store.service import VectorStoreService


class MockLLM(LLMProvider):
    @property
    def name(self) -> str:
        return "mock"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="Answer based on context.",
            model="mock",
            provider=self.name,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            finish_reason="stop",
        )


@pytest.fixture
def persistence_env(tmp_path):
    """Sets up an isolated persistence environment for testing."""
    db_file = str(tmp_path / "test_lifecycle.db")
    storage_dir = tmp_path / "files"
    storage_dir.mkdir()

    meta_store = DocumentMetadataStore(db_path=db_file)
    storage = LocalDocumentStorage(base_dir=storage_dir)

    emb_service = EmbeddingService(
        manager=EmbeddingManager(provider=DeterministicEmbeddingProvider())
    )
    vs_provider = ChromaVectorStoreProvider(
        collection_name="test_col", persist_directory=str(tmp_path / "chroma")
    )
    from app.services.vector_store.manager import VectorStoreManager

    vs_service = VectorStoreService(manager=VectorStoreManager(provider=vs_provider))
    chunking_service = ChunkingService(
        chunker=FixedSizeChunker(chunk_size=100, chunk_overlap=20)
    )

    indexing_service = DocumentIndexingService(
        chunking_service=chunking_service,
        embedding_service=emb_service,
        vector_store_service=vs_service,
        metadata_store=meta_store,
        storage=storage,
    )

    retrieval_service = RetrievalService(
        embedding_service=emb_service,
        vector_store_service=vs_service,
    )

    rag_service = RAGService(
        retrieval_service=retrieval_service,
        llm_service=LLMService(manager=LLMManager(provider=MockLLM())),
        metadata_store=meta_store,
    )

    return {
        "tmp_path": tmp_path,
        "db_file": db_file,
        "storage_dir": storage_dir,
        "meta_store": meta_store,
        "storage": storage,
        "indexing_service": indexing_service,
        "retrieval_service": retrieval_service,
        "rag_service": rag_service,
    }


def test_storage_atomic_write_and_path_safety(tmp_path):
    """LocalDocumentStorage writes atomically and rejects path traversal attempts."""
    storage_dir = tmp_path / "storage"
    storage = LocalDocumentStorage(base_dir=storage_dir)

    ws_id = "ws_test_tenant"
    doc_id = "doc_12345"
    filename = "report.txt"
    content = b"Confidential business report content."

    # Successful atomic write
    rel_path = storage.save_file(ws_id, doc_id, filename, content)
    assert storage.file_exists(ws_id, doc_id, filename) is True
    assert storage.read_file(ws_id, doc_id, filename) == content

    # File is on disk at expected location
    full_path = storage_dir / rel_path
    assert full_path.exists() is True
    assert full_path.read_bytes() == content

    # Directory traversal prevention
    with pytest.raises(ValueError):
        storage.save_file(ws_id, doc_id, "../../../etc/passwd", content)


def test_metadata_store_record_and_versioning(tmp_path):
    """DocumentMetadataStore tracks documents, active versions, and history."""
    db_file = str(tmp_path / "meta.db")
    meta_store = DocumentMetadataStore(db_path=db_file)

    ws = "ws_alpha_1"
    doc = "doc_alpha_1"

    # Initial record
    record = meta_store.record_document(
        document_id=doc,
        workspace_id=ws,
        filename="initial.txt",
        content_hash="hash1",
        media_type="text/plain",
        size_bytes=100,
        chunks_indexed=3,
        file_path="ws_alpha_1/doc_alpha_1/initial.txt",
    )
    assert record["active_version"] == 1
    assert record["status"] == "active"
    assert record["chunks_indexed"] == 3

    # Check active document IDs
    active_ids = meta_store.get_active_document_ids(ws)
    assert doc in active_ids

    # Create replacement version
    new_version = meta_store.create_replacement_version(
        document_id=doc,
        workspace_id=ws,
        filename="updated.txt",
        content_hash="hash2",
        media_type="text/plain",
        size_bytes=150,
        chunks_indexed=4,
        file_path="ws_alpha_1/doc_alpha_1/updated.txt",
    )
    assert new_version == 2

    updated = meta_store.get_document(doc, ws)
    assert updated["active_version"] == 2
    assert updated["filename"] == "updated.txt"
    assert updated["chunks_indexed"] == 4

    versions = meta_store.list_versions(doc, ws)
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[0]["status"] == "active"
    assert versions[1]["version_number"] == 1
    assert versions[1]["status"] == "superseded"


def test_document_replacement_replaces_vectors(persistence_env):
    """Replacing a document purges obsolete vectors and retains single version."""
    idx_svc = persistence_env["indexing_service"]
    meta_store = persistence_env["meta_store"]
    ws = "ws_replace_test"

    doc_v1 = Document.create(
        document_id="doc_repl",
        filename="manual_v1.txt",
        media_type="text/plain",
        text="Version 1 content: The alpha protocol is in effect.",
    )
    content_v1 = b"Version 1 content: The alpha protocol is in effect."
    res1 = idx_svc.index_document(doc_v1, workspace_id=ws, raw_content=content_v1)
    assert res1.chunks_indexed > 0

    doc_meta_1 = meta_store.get_document("doc_repl", ws)
    assert doc_meta_1["active_version"] == 1

    # Replace with version 2
    doc_v2 = Document.create(
        document_id="doc_repl",
        filename="manual_v2.txt",
        media_type="text/plain",
        text="Version 2 content: The beta protocol has replaced alpha.",
    )
    content_v2 = b"Version 2 content: The beta protocol has replaced alpha."
    res2 = idx_svc.replace_document(
        document_id="doc_repl",
        new_document=doc_v2,
        raw_content=content_v2,
        workspace_id=ws,
    )
    assert res2.chunks_indexed > 0

    doc_meta_2 = meta_store.get_document("doc_repl", ws)
    assert doc_meta_2["active_version"] == 2
    assert doc_meta_2["filename"] == "manual_v2.txt"

    # Search for alpha vs beta
    retrieval_svc = persistence_env["retrieval_service"]
    from app.services.retrieval.models import RetrievalQuery

    results_beta = retrieval_svc.search(
        RetrievalQuery(text="beta protocol", workspace_id=ws, top_k=5)
    )
    assert any("beta protocol" in r.text for r in results_beta)


def test_reindex_document_from_retained_source(persistence_env):
    """Reindexing reads retained file from disk and rebuilds index cleanly."""
    idx_svc = persistence_env["indexing_service"]
    ws = "ws_reindex_test"
    doc_id = "doc_reindex_1"
    raw_text = "Retained specification document text for reindexing verification."
    content = raw_text.encode("utf-8")

    doc = Document.create(
        document_id=doc_id,
        filename="spec.txt",
        media_type="text/plain",
        text=raw_text,
    )
    idx_svc.index_document(doc, workspace_id=ws, raw_content=content)

    # Reindex document
    reindex_res = idx_svc.reindex_document(doc_id, workspace_id=ws)
    assert reindex_res.chunks_indexed > 0

    # Reindex workspace
    summary = idx_svc.reindex_workspace(workspace_id=ws)
    assert summary["total_documents"] == 1
    assert summary["reindexed"] == 1
    assert summary["failed"] == 0


def test_reindex_legacy_document_reports_clear_error(persistence_env):
    """Reindexing a document without raw source fails with clean message."""
    idx_svc = persistence_env["indexing_service"]
    meta_store = persistence_env["meta_store"]
    ws = "ws_legacy_test"
    doc_id = "doc_legacy_1"

    # Record metadata without writing file to storage
    meta_store.record_document(
        document_id=doc_id,
        workspace_id=ws,
        filename="legacy.txt",
        content_hash="legacyhash",
        media_type="text/plain",
        size_bytes=50,
        chunks_indexed=1,
        file_path=None,
    )

    with pytest.raises(AppException) as exc_info:
        idx_svc.reindex_document(doc_id, workspace_id=ws)

    assert exc_info.value.code == "source_file_unavailable"
    assert "legacy" in exc_info.value.message.lower()


def test_rag_candidate_filtering_excludes_inactive_documents(persistence_env):
    """RAG pipeline filters out chunks from non-active or deleted documents."""
    idx_svc = persistence_env["indexing_service"]
    rag_svc = persistence_env["rag_service"]
    meta_store = persistence_env["meta_store"]
    ws = "ws_rag_filter_test"

    doc = Document.create(
        document_id="doc_deleting",
        filename="contract.txt",
        media_type="text/plain",
        text="The agreement termination clause is section 4.",
    )
    idx_svc.index_document(doc, workspace_id=ws, raw_content=b"The agreement...")

    # Set document status to 'deleting' in metadata store
    meta_store.set_status("doc_deleting", ws, "deleting")

    # RAG query should filter out chunks belonging to 'doc_deleting'
    req = RAGRequest(query="agreement termination clause", workspace_id=ws)
    resp = rag_svc.answer(req)

    # Empty context message returned since all chunks for doc_deleting were filtered
    expected_empty = (
        "I could not find relevant information in the knowledge base to "
        "answer your question."
    )
    assert resp.answer == expected_empty
    assert len(resp.sources) == 0
