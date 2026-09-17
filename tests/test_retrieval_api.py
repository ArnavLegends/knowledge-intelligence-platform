"""Tests for the retrieval API."""

from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.v1.endpoints.retrieval import get_retrieval_service
from app.main import app
from app.services.retrieval.models import RetrievedChunk


def test_search_endpoint_success():
    """Test successful semantic search via API."""
    mock_service = Mock()
    mock_service.search.return_value = [
        RetrievedChunk(id="c1", document_id="d1", text="text1", score=0.1, metadata={})
    ]

    app.dependency_overrides[get_retrieval_service] = lambda: mock_service

    client = TestClient(app)
    response = client.post(
        "/api/v1/retrieval/search", json={"query": "test query", "top_k": 3}
    )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "c1"
    assert data["results"][0]["text"] == "text1"

    app.dependency_overrides.clear()


def test_search_endpoint_rejects_invalid_payload():
    """Test search API validates payload."""
    app.dependency_overrides[get_retrieval_service] = lambda: Mock()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/retrieval/search", json={"top_k": 3}
        )  # Missing query
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
