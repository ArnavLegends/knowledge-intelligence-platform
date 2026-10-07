"""Tests for the vector storage subsystem."""

import uuid

import pytest

from app.core.config import Settings
from app.core.exceptions import AppException, VectorStoreError
from app.services.embeddings.models import Embedding
from app.services.vector_store.manager import VectorStoreManager
from app.services.vector_store.models import StoredVector
from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
from app.services.vector_store.providers.qdrant import (
    QdrantVectorStoreProvider,
    _deterministic_point_id,
)
from app.services.vector_store.service import VectorStoreService


def test_stored_vector_valid():
    """Test valid StoredVector."""
    vec = StoredVector(id="v1", vector=[0.1, 0.2], metadata={"key": "val"})
    assert vec.id == "v1"
    assert vec.vector == [0.1, 0.2]
    assert vec.metadata == {"key": "val"}


def test_stored_vector_rejects_empty():
    """Test StoredVector rejects empty vector."""
    with pytest.raises(ValueError):
        StoredVector(id="v1", vector=[])


@pytest.fixture
def chroma_provider():
    """Return an ephemeral Chroma provider for testing."""
    name = f"test_collection_{uuid.uuid4().hex}"
    return ChromaVectorStoreProvider(collection_name=name, persist_directory=None)


def test_chroma_provider_initialization():
    """Test Chroma provider initializes successfully."""
    provider = ChromaVectorStoreProvider(
        collection_name="test_init", persist_directory=None
    )
    assert provider.name == "chroma"


def test_chroma_provider_upsert_and_retrieve(chroma_provider):
    """Test Chroma provider upserts and retrieves records correctly."""
    vec1 = StoredVector(id="v1", vector=[0.1, 0.1], metadata={"source": "doc1"})
    vec2 = StoredVector(id="v2", vector=[0.2, 0.2], metadata={"source": "doc2"})

    chroma_provider.upsert([vec1, vec2], workspace_id="ws1")

    assert chroma_provider.count(workspace_id="ws1") == 2

    retrieved = chroma_provider.retrieve(["v1", "v2"], workspace_id="ws1")

    assert len(retrieved) == 2
    retrieved_sorted = sorted(retrieved, key=lambda x: x.id)

    assert retrieved_sorted[0].id == "v1"
    assert retrieved_sorted[0].vector == pytest.approx([0.1, 0.1])
    assert retrieved_sorted[0].metadata["source"] == "doc1"

    assert retrieved_sorted[1].id == "v2"
    assert retrieved_sorted[1].vector == pytest.approx([0.2, 0.2])
    assert retrieved_sorted[1].metadata["source"] == "doc2"


def test_chroma_provider_delete(chroma_provider):
    """Test Chroma provider deletes records correctly."""
    vec1 = StoredVector(id="v1", vector=[0.1, 0.1])
    vec2 = StoredVector(id="v2", vector=[0.2, 0.2])

    chroma_provider.upsert([vec1, vec2], workspace_id="ws1")
    assert chroma_provider.count(workspace_id="ws1") == 2

    chroma_provider.delete(["v1"], workspace_id="ws1")
    assert chroma_provider.count(workspace_id="ws1") == 1

    retrieved = chroma_provider.retrieve(["v1"], workspace_id="ws1")
    assert len(retrieved) == 0


def test_chroma_provider_handles_empty_inputs(chroma_provider):
    """Test Chroma provider handles empty inputs gracefully."""
    chroma_provider.upsert([], workspace_id="ws1")
    assert chroma_provider.retrieve([], workspace_id="ws1") == []
    chroma_provider.delete([], workspace_id="ws1")


def test_manager_selects_chroma():
    """Test VectorStoreManager selects configured provider."""
    settings = Settings(
        vector_store_provider="chroma", vector_store_persist_directory=""
    )
    manager = VectorStoreManager(settings=settings)
    assert manager.provider.name == "chroma"


def test_manager_selects_qdrant():
    """Test VectorStoreManager selects Qdrant provider."""
    settings = Settings(
        vector_store_provider="qdrant",
        qdrant_url=":memory:",
        embedding_dimensions=8,
    )
    manager = VectorStoreManager(settings=settings)
    assert manager.provider.name == "qdrant"


def test_manager_rejects_unsupported():
    """Test VectorStoreManager rejects unsupported provider."""
    settings = Settings(vector_store_provider="fake-provider")
    with pytest.raises(AppException) as exc:
        VectorStoreManager(settings=settings)
    assert exc.value.code == "unsupported_vector_store_provider"


def test_service_store_and_retrieve_flow(chroma_provider):
    """Test VectorStoreService orchestrates correctly."""
    manager = VectorStoreManager(provider=chroma_provider)
    service = VectorStoreService(manager=manager)

    emb1 = Embedding(
        source_id="c1", vector=[1.0, 2.0], dimensions=2, metadata={"m": "1"}
    )
    emb2 = Embedding(
        source_id="c2", vector=[3.0, 4.0], dimensions=2, metadata={"m": "2"}
    )

    service.store_embeddings([emb1, emb2], workspace_id="ws1")

    assert service.count("ws1") == 2

    retrieved = service.retrieve(["c1", "c2"], workspace_id="ws1")
    assert len(retrieved) == 2

    retrieved.sort(key=lambda x: x.id)
    assert retrieved[0].id == "c1"
    assert retrieved[0].metadata["m"] == "1"
    assert retrieved[1].id == "c2"
    assert retrieved[1].metadata["m"] == "2"

    service.delete(["c1"], workspace_id="ws1")
    assert service.count("ws1") == 1


def test_service_handles_empty_inputs():
    """Test VectorStoreService handles empty inputs gracefully."""
    service = VectorStoreService()
    service.store_embeddings([])


def test_chroma_provider_search(chroma_provider):
    """Test Chroma provider similarity search."""
    vec1 = StoredVector(id="v1", vector=[1.0, 0.0], metadata={"doc": "1"})
    vec2 = StoredVector(id="v2", vector=[0.0, 1.0], metadata={"doc": "2"})

    chroma_provider.upsert([vec1, vec2], workspace_id="ws1")

    results = chroma_provider.search(
        query_vector=[0.9, 0.1], top_k=1, workspace_id="ws1"
    )
    assert len(results) == 1
    assert results[0].id == "v1"
    assert results[0].distance is not None
    assert results[0].metadata["doc"] == "1"


def test_chroma_provider_search_empty_store(chroma_provider):
    """Test search against an empty store."""
    results = chroma_provider.search(
        query_vector=[1.0, 1.0], top_k=5, workspace_id="ws1"
    )
    assert results == []


def test_chroma_provider_search_threshold(chroma_provider):
    """Test search with distance threshold."""
    vec1 = StoredVector(id="v1", vector=[1.0, 0.0])
    vec2 = StoredVector(id="v2", vector=[-1.0, 0.0])

    chroma_provider.upsert([vec1, vec2], workspace_id="ws1")

    results = chroma_provider.search(
        query_vector=[1.0, 0.0], top_k=2, workspace_id="ws1", threshold=0.5
    )
    assert len(results) == 1
    assert results[0].id == "v1"


# ── Qdrant Unit Tests ────────────────────────────────────────────────────────


def test_qdrant_deterministic_point_id():
    """Point IDs must be deterministic and scoped by workspace."""
    p1 = _deterministic_point_id("workspace_a", "chunk_1")
    p2 = _deterministic_point_id("workspace_a", "chunk_1")
    p3 = _deterministic_point_id("workspace_b", "chunk_1")

    assert p1 == p2
    assert p1 != p3


def test_qdrant_in_memory_crud_and_search():
    """Test real in-memory Qdrant provider operations."""
    provider = QdrantVectorStoreProvider(
        collection_name=f"test_qdrant_{uuid.uuid4().hex[:8]}",
        url=":memory:",
        embedding_dimensions=4,
    )
    assert provider.name == "qdrant"

    v1 = StoredVector(
        id="c1", vector=[1.0, 0.0, 0.0, 0.0], metadata={"document_id": "d1"}
    )
    v2 = StoredVector(
        id="c2", vector=[0.0, 1.0, 0.0, 0.0], metadata={"document_id": "d2"}
    )

    provider.upsert([v1, v2], workspace_id="ws_alpha")
    assert provider.count("ws_alpha") == 2

    # Retrieval
    retrieved = provider.retrieve(["c1"], workspace_id="ws_alpha")
    assert len(retrieved) == 1
    assert retrieved[0].id == "c1"

    # Search
    search_res = provider.search(
        query_vector=[0.9, 0.1, 0.0, 0.0], top_k=2, workspace_id="ws_alpha"
    )
    assert len(search_res) == 2
    assert search_res[0].id == "c1"

    # Document existence
    assert provider.document_exists("d1", "ws_alpha") is True
    assert provider.document_exists("d999", "ws_alpha") is False

    # Document listing
    docs = provider.list_documents("ws_alpha")
    assert len(docs) == 2

    # Delete document
    provider.delete_document("d1", "ws_alpha")
    assert provider.document_exists("d1", "ws_alpha") is False
    assert provider.count("ws_alpha") == 1


def test_qdrant_dimension_mismatch_fails_fast():
    """Qdrant provider must reject incompatible collection dimension."""
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    col_name = f"mismatch_{uuid.uuid4().hex[:8]}"
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=col_name,
        vectors_config=qmodels.VectorParams(size=128, distance=qmodels.Distance.COSINE),
    )

    with pytest.raises(VectorStoreError) as exc:
        QdrantVectorStoreProvider(
            collection_name=col_name,
            embedding_dimensions=768,  # Expects 768, but collection is 128
            client=client,
        )
    assert "dimension mismatch" in str(exc.value)


def test_qdrant_distance_mismatch_fails_fast():
    """Qdrant provider must reject incompatible distance metric."""
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    col_name = f"dist_mismatch_{uuid.uuid4().hex[:8]}"
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=col_name,
        vectors_config=qmodels.VectorParams(size=768, distance=qmodels.Distance.EUCLID),
    )

    with pytest.raises(VectorStoreError) as exc:
        QdrantVectorStoreProvider(
            collection_name=col_name,
            embedding_dimensions=768,
            client=client,
        )
    assert "distance metric mismatch" in str(exc.value)
