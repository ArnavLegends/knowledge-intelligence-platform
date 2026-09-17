"""Integration tests for the full indexing pipeline."""

import pytest

from app.core.config import Settings
from app.services.chunking.models import Chunk
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingRequest
from app.services.embeddings.service import EmbeddingService
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService
from app.services.vector_store.manager import VectorStoreManager
from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
from app.services.vector_store.service import VectorStoreService


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic fake provider for integration tests."""

    @property
    def name(self) -> str:
        return "fake"

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        results = []
        for idx, inp in enumerate(request.inputs):
            # A simple deterministic vector based on source text length
            vec = [float(len(inp.text)), float(idx)]
            results.append(
                Embedding(
                    source_id=inp.source_id,
                    vector=vec,
                    dimensions=2,
                    metadata=inp.metadata.copy(),
                    provider="fake",
                    model="fake-model",
                )
            )
        return results


@pytest.fixture
def test_pipeline():
    """Build a real pipeline with a fake embedding provider and ephemeral chroma."""
    settings = Settings(
        embedding_model="fake-model",
        vector_store_provider="chroma",
        vector_store_persist_directory="",
    )

    # Embedding
    emb_provider = FakeEmbeddingProvider()
    emb_manager = EmbeddingManager(settings=settings, provider=emb_provider)
    emb_service = EmbeddingService(manager=emb_manager)

    # Vector store (ephemeral chroma)
    vs_provider = ChromaVectorStoreProvider(
        collection_name="test_collection", persist_directory=None
    )
    vs_manager = VectorStoreManager(settings=settings, provider=vs_provider)
    vs_service = VectorStoreService(manager=vs_manager)

    # Retrieval
    retrieval_service = RetrievalService(
        embedding_service=emb_service,
        vector_store_service=vs_service,
        settings=settings,
    )

    return emb_service, vs_service, retrieval_service


def test_provenance_flows_through_pipeline(test_pipeline):
    """Prove that chunks -> embeddings -> storage -> retrieval preserves provenance."""
    emb_service, vs_service, retrieval_service = test_pipeline

    # 1. Create a known chunk
    chunk = Chunk(
        id="chunk-123",
        document_id="doc-456",
        index=0,
        text="This is a very specific piece of knowledge about quantum computing.",
        character_count=65,
        metadata={"custom": "value"},
    )

    # 2. Embed and Store
    embeddings = emb_service.embed_chunks([chunk])
    vs_service.store_embeddings(embeddings)

    # 3. Retrieve
    query = RetrievalQuery(text="quantum computing", top_k=1)
    results = retrieval_service.search(query)

    # 4. Verify
    assert len(results) == 1
    retrieved = results[0]

    assert retrieved.id == "chunk-123"
    assert retrieved.document_id == "doc-456"
    assert (
        retrieved.text
        == "This is a very specific piece of knowledge about quantum computing."
    )
    assert retrieved.metadata.get("custom") == "value"
