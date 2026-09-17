"""Tests for the RAG subsystem."""

from unittest.mock import Mock

import pytest

from app.core.config import Settings
from app.core.exceptions import RAGError
from app.services.llm.models import LLMResponse
from app.services.rag.context import ContextBuilder
from app.services.rag.models import ContextItem, RAGRequest
from app.services.rag.service import RAGService
from app.services.retrieval.models import RetrievedChunk


def test_rag_request_valid():
    """Test valid RAGRequest."""
    req = RAGRequest(query="test", top_k=2, threshold=0.1)
    assert req.query == "test"
    assert req.top_k == 2


def test_context_item_valid():
    """Test ContextItem model."""
    item = ContextItem(chunk_id="c1", document_id="d1", text="abc", rank=1)
    assert item.chunk_id == "c1"
    assert item.rank == 1


def test_context_builder_builds_items():
    """Test ContextBuilder converts chunks correctly."""
    chunks = [
        RetrievedChunk(id="c1", document_id="d1", text="text1", score=0.1, metadata={}),
        RetrievedChunk(id="c2", document_id="d2", text="text2", score=0.2, metadata={}),
    ]
    items = ContextBuilder.build_context_items(chunks)
    assert len(items) == 2
    assert items[0].rank == 1
    assert items[0].text == "text1"
    assert items[1].rank == 2
    assert items[1].text == "text2"


def test_context_builder_builds_string():
    """Test ContextBuilder formats strings deterministically."""
    items = [
        ContextItem(chunk_id="c1", document_id="d1", text="text1", rank=1),
        ContextItem(chunk_id="c2", text="text2", rank=2),  # no document_id
    ]
    ctx_str = ContextBuilder.build_context_string(items)
    assert "--- START Source 1 (Document: d1) ---" in ctx_str
    assert "text1" in ctx_str
    assert "--- START Source 2 ---" in ctx_str
    assert "text2" in ctx_str


def test_rag_service_flow():
    """Test complete RAG orchestration."""
    mock_retrieval = Mock()
    mock_llm = Mock()
    settings = Settings()

    # Mock retrieval
    mock_retrieval.search.return_value = [
        RetrievedChunk(
            id="c1", document_id="d1", text="chunk text", score=0.1, metadata={}
        )
    ]

    # Mock LLM
    mock_llm.generate.return_value = LLMResponse(
        content="My answer.", model="fake", provider="fake", usage=None
    )

    service = RAGService(
        retrieval_service=mock_retrieval,
        llm_service=mock_llm,
        settings=settings,
    )

    req = RAGRequest(query="test question", top_k=2)
    resp = service.answer(req)

    assert resp.answer == "My answer."
    assert len(resp.sources) == 1
    assert resp.sources[0].chunk_id == "c1"

    # Verify retrieval
    mock_retrieval.search.assert_called_once()

    # Verify LLM call
    mock_llm.generate.assert_called_once()
    llm_req = mock_llm.generate.call_args[0][0]

    assert len(llm_req.messages) == 2
    assert llm_req.messages[0].role == "system"
    assert "ONLY the provided context" in llm_req.messages[0].content

    assert llm_req.messages[1].role == "user"
    assert "Context Information:" in llm_req.messages[1].content
    assert "test question" in llm_req.messages[1].content
    assert "chunk text" in llm_req.messages[1].content


def test_rag_service_empty_query():
    """Test empty query is rejected."""
    service = RAGService(retrieval_service=Mock(), llm_service=Mock())
    with pytest.raises(RAGError):
        service.answer(RAGRequest(query="   "))


def test_rag_service_empty_context():
    """Test RAG service gracefully handles empty retrieval results."""
    mock_retrieval = Mock()
    mock_retrieval.search.return_value = []

    mock_llm = Mock()
    settings = Settings(rag_empty_context_message="No info found.")

    service = RAGService(
        retrieval_service=mock_retrieval,
        llm_service=mock_llm,
        settings=settings,
    )

    resp = service.answer(RAGRequest(query="test"))
    assert resp.answer == "No info found."
    assert resp.sources == []

    # LLM should not be called
    mock_llm.generate.assert_not_called()


def test_rag_service_propagates_retrieval_failure():
    """Test retrieval failures become RAGErrors."""
    mock_retrieval = Mock()
    mock_retrieval.search.side_effect = Exception("Search failed")

    service = RAGService(retrieval_service=mock_retrieval, llm_service=Mock())

    with pytest.raises(RAGError):
        service.answer(RAGRequest(query="test"))


def test_rag_service_propagates_llm_failure():
    """Test LLM failures become RAGErrors."""
    mock_retrieval = Mock()
    mock_retrieval.search.return_value = [
        RetrievedChunk(id="c1", text="abc", metadata={})
    ]

    mock_llm = Mock()
    mock_llm.generate.side_effect = Exception("API error")

    service = RAGService(retrieval_service=mock_retrieval, llm_service=mock_llm)

    with pytest.raises(RAGError):
        service.answer(RAGRequest(query="test"))
