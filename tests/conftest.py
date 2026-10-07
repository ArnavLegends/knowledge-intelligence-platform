"""Pytest configuration and global fixtures."""

from __future__ import annotations

import hashlib
import os
import uuid

import pytest
from fastapi.testclient import TestClient

# Enforce ephemeral (in-memory) ChromaDB for all tests to prevent
# .chroma_data directory generation in the project root.
os.environ["VECTOR_STORE_PERSIST_DIRECTORY"] = ""
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from app.main import app
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.service import ChunkingService
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingRequest
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.service import DocumentIndexingService, get_indexing_service
from app.services.llm.base import LLMProvider
from app.services.llm.manager import LLMManager
from app.services.llm.models import LLMRequest, LLMResponse
from app.services.llm.service import LLMService, get_llm_service
from app.services.rag.service import RAGService, get_rag_service
from app.services.retrieval.service import RetrievalService
from app.services.vector_store.manager import VectorStoreManager
from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
from app.services.vector_store.service import VectorStoreService

_EMBEDDING_DIMS = 8


def _text_to_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i] / 255.0 for i in range(_EMBEDDING_DIMS)]


class DeterministicEmbeddingProvider(EmbeddingProvider):
    @property
    def name(self) -> str:
        return "deterministic-fake"

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        return [
            Embedding(
                source_id=inp.source_id,
                vector=_text_to_vector(inp.text),
                dimensions=_EMBEDDING_DIMS,
                metadata=inp.metadata.copy(),
                provider="deterministic-fake",
                model="fake-v1",
            )
            for inp in request.inputs
        ]


class DeterministicLLMProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "deterministic-fake-llm"

    def generate(self, request: LLMRequest) -> LLMResponse:
        user_content = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_content = msg.content
                break
        return LLMResponse(
            content=f"ANSWER: {user_content[:120]}",
            model="fake-llm-v1",
            provider="deterministic-fake-llm",
            usage=None,
        )


@pytest.fixture
def e2e_pipeline():
    """Fully wired KIP pipeline with deterministic fakes and ephemeral ChromaDB.

    Returns (TestClient, VectorStoreService) for direct inspection.
    Each invocation uses a unique collection to guarantee test isolation.
    """
    collection_name = f"e2e_test_{uuid.uuid4().hex[:12]}"

    emb_service = EmbeddingService(
        manager=EmbeddingManager(provider=DeterministicEmbeddingProvider())
    )
    vs_provider = ChromaVectorStoreProvider(
        collection_name=collection_name, persist_directory=None
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

    client = TestClient(
        app,
        headers={"X-KIP-Workspace-ID": "test-default-workspace"},
        raise_server_exceptions=False,
    )
    yield client, vs_service
    app.dependency_overrides.clear()


@pytest.fixture
def deterministic_indexing_service():
    """Isolated deterministic indexing service for direct unit testing."""
    collection_name = f"idx_test_{uuid.uuid4().hex[:12]}"

    emb_service = EmbeddingService(
        manager=EmbeddingManager(provider=DeterministicEmbeddingProvider())
    )
    vs_provider = ChromaVectorStoreProvider(
        collection_name=collection_name, persist_directory=None
    )
    vs_service = VectorStoreService(manager=VectorStoreManager(provider=vs_provider))

    indexing_service = DocumentIndexingService(
        chunking_service=ChunkingService(
            chunker=FixedSizeChunker(chunk_size=200, chunk_overlap=20)
        ),
        embedding_service=emb_service,
        vector_store_service=vs_service,
    )

    app.dependency_overrides[get_indexing_service] = lambda: indexing_service

    yield indexing_service

    app.dependency_overrides.pop(get_indexing_service, None)


@pytest.fixture
def in_memory_qdrant_provider():
    """In-memory Qdrant provider for unit and integration testing."""
    from app.services.vector_store.providers.qdrant import QdrantVectorStoreProvider

    col_name = f"test_col_{uuid.uuid4().hex[:8]}"
    return QdrantVectorStoreProvider(
        collection_name=col_name,
        url=":memory:",
        embedding_dimensions=_EMBEDDING_DIMS,
    )
