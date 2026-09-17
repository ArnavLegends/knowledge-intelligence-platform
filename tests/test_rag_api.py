"""Tests for the RAG API."""

from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.v1.endpoints.rag import get_rag_service
from app.main import app
from app.services.rag.models import ContextItem, RAGResponse


def test_rag_answer_endpoint_success():
    """Test successful RAG API."""
    mock_service = Mock()
    mock_service.answer.return_value = RAGResponse(
        answer="Hello World",
        sources=[
            ContextItem(chunk_id="c1", document_id="d1", text="some context", rank=1)
        ],
    )

    app.dependency_overrides[get_rag_service] = lambda: mock_service

    client = TestClient(app)
    response = client.post(
        "/api/v1/rag/answer", json={"query": "test query", "top_k": 3}
    )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert data["answer"] == "Hello World"
    assert "sources" in data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["chunk_id"] == "c1"

    app.dependency_overrides.clear()


def test_rag_answer_endpoint_rejects_invalid():
    """Test search API validates payload."""
    mock_service = Mock()
    app.dependency_overrides[get_rag_service] = lambda: mock_service

    client = TestClient(app)
    response = client.post("/api/v1/rag/answer", json={"top_k": 3})  # Missing query

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_rag_answer_endpoint_handles_rag_error():
    """Test API maps RAGError to 500 status code."""
    from app.core.exceptions import RAGError

    mock_service = Mock()
    mock_service.answer.side_effect = RAGError("Something went wrong.")
    app.dependency_overrides[get_rag_service] = lambda: mock_service

    client = TestClient(app)
    response = client.post("/api/v1/rag/answer", json={"query": "test query"})

    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "rag_error"
    assert "Something went wrong" in data["error"]["message"]

    app.dependency_overrides.clear()
