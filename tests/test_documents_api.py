"""HTTP tests for POST /api/v1/documents."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.services.indexing.models import IndexingResult
from app.services.indexing.service import get_indexing_service

UPLOAD_URL = "/api/v1/documents"


def _mock_indexing_service(chunks_indexed: int = 1) -> MagicMock:
    """Build a mock DocumentIndexingService for tests that don't test indexing."""
    mock = MagicMock()
    mock.document_exists.return_value = False
    mock.index_document.return_value = IndexingResult(
        document_id="test-doc-id", chunks_indexed=chunks_indexed
    )
    return mock


def _client(mock_indexer=None) -> TestClient:
    if mock_indexer is not None:
        app.dependency_overrides[get_indexing_service] = lambda: mock_indexer
    return TestClient(
        app,
        headers={"X-KIP-Workspace-ID": "test-workspace-123"},
        raise_server_exceptions=False,
    )


def test_document_upload_success() -> None:
    mock_indexer = _mock_indexing_service(chunks_indexed=1)
    client = _client(mock_indexer)
    try:
        response = client.post(
            UPLOAD_URL,
            files={"file": ("notes.txt", "hello café".encode(), "text/plain")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["filename"] == "notes.txt"
        assert body["media_type"] == "text/plain"
        assert body["text"] == "hello café"
        assert body["source"] == "upload"
        assert body["id"]
        assert body["ingested_at"]
        assert body["metadata"]["parser"] == "txt"
        assert body["chunks_indexed"] == 1
    finally:
        app.dependency_overrides.clear()


def test_document_upload_rejects_empty_file() -> None:
    mock_indexer = _mock_indexing_service()
    client = _client(mock_indexer)
    try:
        response = client.post(
            UPLOAD_URL,
            files={"file": ("notes.txt", b"", "text/plain")},
        )

        assert response.status_code == 400
        assert response.json() == {
            "error": {
                "code": "invalid_document",
                "message": "Uploaded file is empty.",
            }
        }
    finally:
        app.dependency_overrides.clear()


def test_document_upload_rejects_unsupported_format() -> None:
    mock_indexer = _mock_indexing_service()
    client = _client(mock_indexer)
    try:
        response = client.post(
            UPLOAD_URL,
            files={
                "file": ("notes.unknown", b"fake content", "application/octet-stream")
            },
        )

        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_format"
    finally:
        app.dependency_overrides.clear()


def test_document_upload_rejects_invalid_utf8() -> None:
    mock_indexer = _mock_indexing_service()
    client = _client(mock_indexer)
    try:
        response = client.post(
            UPLOAD_URL,
            files={"file": ("notes.txt", b"\xff\xfe", "text/plain")},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "document_parse_error"
        assert "UTF-8" in response.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_document_upload_requires_file() -> None:
    mock_indexer = _mock_indexing_service()
    client = _client(mock_indexer)
    try:
        response = client.post(UPLOAD_URL)
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_document_upload_rejects_missing_or_invalid_workspace() -> None:
    mock_indexer = _mock_indexing_service()
    app.dependency_overrides[get_indexing_service] = lambda: mock_indexer
    raw_client = TestClient(app, raise_server_exceptions=False)
    try:
        # 1. Missing header
        res1 = raw_client.post(
            UPLOAD_URL,
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert res1.status_code == 400

        # 2. Invalid short token
        res2 = raw_client.post(
            UPLOAD_URL,
            headers={"X-KIP-Workspace-ID": "short"},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert res2.status_code == 400
    finally:
        app.dependency_overrides.clear()
