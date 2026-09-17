"""Tests for the retrieval subsystem."""

from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.core.exceptions import RetrievalError
from app.services.embeddings.models import Embedding
from app.services.retrieval.models import RetrievalQuery, RetrievedChunk
from app.services.retrieval.service import RetrievalService
from app.services.vector_store.models import VectorSearchResult


def test_retrieval_query_valid():
    """Test valid RetrievalQuery."""
    q = RetrievalQuery(text="test query", top_k=10, threshold=0.5)
    assert q.text == "test query"
    assert q.top_k == 10
    assert q.threshold == 0.5


def test_retrieval_query_invalid_top_k():
    """Test RetrievalQuery rejects invalid top_k."""
    with pytest.raises(ValueError):
        RetrievalQuery(text="test query", top_k=0)


def test_retrieved_chunk_valid():
    """Test valid RetrievedChunk."""
    chunk = RetrievedChunk(
        id="c1",
        document_id="d1",
        text="some text",
        score=0.1,
        metadata={"k": "v"},
    )
    assert chunk.id == "c1"
    assert chunk.score == 0.1
    assert chunk.metadata == {"k": "v"}


def test_retrieval_service_flow():
    """Test the complete retrieval service orchestration."""
    mock_emb_service = Mock()
    mock_vs_service = Mock()
    settings = Settings()

    # Setup mock embedding
    mock_emb = Embedding(
        source_id="query", vector=[0.1, 0.2], dimensions=2, metadata={}
    )
    mock_emb_service.embed_texts.return_value = [mock_emb]

    # Setup mock vector search result
    mock_res1 = VectorSearchResult(
        id="c1",
        vector=[0.1, 0.2],
        metadata={"document_id": "d1", "text": "text1"},
        distance=0.1,
    )
    mock_res2 = VectorSearchResult(
        id="c2",
        vector=[0.3, 0.4],
        metadata={"document_id": "d1", "text": "text2"},
        distance=0.5,
    )
    mock_vs_service.search.return_value = [mock_res1, mock_res2]

    service = RetrievalService(
        embedding_service=mock_emb_service,
        vector_store_service=mock_vs_service,
        settings=settings,
    )

    query = RetrievalQuery(text="test", top_k=2)
    results = service.search(query)

    assert len(results) == 2
    assert results[0].id == "c1"
    assert results[0].text == "text1"
    assert results[0].document_id == "d1"
    assert results[0].score == 0.1

    assert results[1].id == "c2"
    assert results[1].text == "text2"
    assert results[1].score == 0.5

    # Verify delegations
    mock_emb_service.embed_texts.assert_called_once()
    mock_vs_service.search.assert_called_once_with(
        query_vector=[0.1, 0.2], top_k=2, threshold=None
    )


def test_retrieval_service_empty_query():
    """Test retrieval service handles empty queries by returning empty results."""
    service = RetrievalService(embedding_service=Mock(), vector_store_service=Mock())
    results = service.search(RetrievalQuery(text="   ", top_k=5))
    assert results == []


def test_retrieval_service_handles_embedding_failure():
    """Test retrieval service propagates embedding failures."""
    mock_emb_service = Mock()
    mock_emb_service.embed_texts.side_effect = Exception("API error")
    service = RetrievalService(
        embedding_service=mock_emb_service, vector_store_service=Mock()
    )

    with pytest.raises(RetrievalError):
        service.search(RetrievalQuery(text="test"))


def test_retrieval_service_handles_vector_store_failure():
    """Test retrieval service propagates vector store failures."""
    mock_emb_service = Mock()
    mock_emb = Embedding(source_id="query", vector=[0.1], dimensions=1, metadata={})
    mock_emb_service.embed_texts.return_value = [mock_emb]

    mock_vs_service = Mock()
    mock_vs_service.search.side_effect = Exception("DB error")

    service = RetrievalService(
        embedding_service=mock_emb_service,
        vector_store_service=mock_vs_service,
    )

    with pytest.raises(RetrievalError):
        service.search(RetrievalQuery(text="test"))
