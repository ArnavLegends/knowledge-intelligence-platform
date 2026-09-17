"""HTTP tests for POST /api/v1/documents."""

from fastapi.testclient import TestClient

from app.main import app

UPLOAD_URL = "/api/v1/documents"


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_document_upload_success() -> None:
    client = _client()
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


def test_document_upload_rejects_empty_file() -> None:
    client = _client()
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


def test_document_upload_rejects_unsupported_format() -> None:
    client = _client()
    response = client.post(
        UPLOAD_URL,
        files={"file": ("notes.pdf", b"%PDF-fake", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_format"


def test_document_upload_rejects_invalid_utf8() -> None:
    client = _client()
    response = client.post(
        UPLOAD_URL,
        files={"file": ("notes.txt", b"\xff\xfe", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "document_parse_error"
    assert "UTF-8" in response.json()["error"]["message"]


def test_document_upload_requires_file() -> None:
    client = _client()
    response = client.post(UPLOAD_URL)
    assert response.status_code == 422
