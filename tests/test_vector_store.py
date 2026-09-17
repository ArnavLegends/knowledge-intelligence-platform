"""Tests for the vector storage subsystem."""

import uuid

import pytest

from app.core.config import Settings
from app.core.exceptions import AppException
from app.services.embeddings.models import Embedding
from app.services.vector_store.manager import VectorStoreManager
from app.services.vector_store.models import StoredVector
from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
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

    chroma_provider.upsert([vec1, vec2])

    assert chroma_provider.count() == 2

    retrieved = chroma_provider.retrieve(["v1", "v2"])

    assert len(retrieved) == 2
    # Order from chromadb retrieve is not guaranteed, so sort by id
    retrieved_sorted = sorted(retrieved, key=lambda x: x.id)

    assert retrieved_sorted[0].id == "v1"
    # Note: floating point precision might differ slightly in chromadb response
    assert retrieved_sorted[0].vector == pytest.approx([0.1, 0.1])
    assert retrieved_sorted[0].metadata == {"source": "doc1"}

    assert retrieved_sorted[1].id == "v2"
    assert retrieved_sorted[1].vector == pytest.approx([0.2, 0.2])
    assert retrieved_sorted[1].metadata == {"source": "doc2"}


def test_chroma_provider_delete(chroma_provider):
    """Test Chroma provider deletes records correctly."""
    vec1 = StoredVector(id="v1", vector=[0.1, 0.1])
    vec2 = StoredVector(id="v2", vector=[0.2, 0.2])

    chroma_provider.upsert([vec1, vec2])
    assert chroma_provider.count() == 2

    chroma_provider.delete(["v1"])
    assert chroma_provider.count() == 1

    retrieved = chroma_provider.retrieve(["v1"])
    assert len(retrieved) == 0


def test_chroma_provider_handles_empty_inputs(chroma_provider):
    """Test Chroma provider handles empty inputs gracefully."""
    chroma_provider.upsert([])
    assert chroma_provider.retrieve([]) == []
    chroma_provider.delete([])


def test_manager_selects_chroma():
    """Test VectorStoreManager selects configured provider."""
    settings = Settings(
        vector_store_provider="chroma", vector_store_persist_directory=""
    )
    manager = VectorStoreManager(settings=settings)
    assert manager.provider.name == "chroma"


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

    service.store_embeddings([emb1, emb2])

    assert service.count() == 2

    retrieved = service.retrieve(["c1", "c2"])
    assert len(retrieved) == 2

    # Sort for deterministic assertion
    retrieved.sort(key=lambda x: x.id)
    assert retrieved[0].id == "c1"
    assert retrieved[0].metadata == {"m": "1"}
    assert retrieved[1].id == "c2"
    assert retrieved[1].metadata == {"m": "2"}

    service.delete(["c1"])
    assert service.count() == 1


def test_service_handles_empty_inputs():
    """Test VectorStoreService handles empty inputs gracefully."""
    service = VectorStoreService()
    service.store_embeddings([])


def test_chroma_provider_search(chroma_provider):
    """Test Chroma provider similarity search."""
    vec1 = StoredVector(id="v1", vector=[1.0, 0.0], metadata={"doc": "1"})
    vec2 = StoredVector(id="v2", vector=[0.0, 1.0], metadata={"doc": "2"})

    chroma_provider.upsert([vec1, vec2])

    # Query vector close to vec1
    results = chroma_provider.search(query_vector=[0.9, 0.1], top_k=1)
    assert len(results) == 1
    assert results[0].id == "v1"
    assert results[0].distance is not None
    assert results[0].metadata == {"doc": "1"}


def test_chroma_provider_search_empty_store(chroma_provider):
    """Test search against an empty store."""
    results = chroma_provider.search(query_vector=[1.0, 1.0], top_k=5)
    assert results == []


def test_chroma_provider_search_threshold(chroma_provider):
    """Test search with distance threshold."""
    vec1 = StoredVector(id="v1", vector=[1.0, 0.0])
    vec2 = StoredVector(
        id="v2", vector=[-1.0, 0.0]
    )  # opposite direction, high distance

    chroma_provider.upsert([vec1, vec2])

    # Should exclude vec2 if threshold is low enough
    results = chroma_provider.search(query_vector=[1.0, 0.0], top_k=2, threshold=0.5)
    assert len(results) == 1
    assert results[0].id == "v1"
