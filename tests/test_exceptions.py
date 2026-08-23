"""Exception handling tests for the backend API."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError, register_exception_handlers


def _exception_test_client() -> TestClient:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/not-found")
    def raise_not_found() -> None:
        raise NotFoundError("Item was not found.")

    @test_app.get("/crash")
    def raise_unexpected() -> None:
        raise RuntimeError("secret internals must not leak")

    return TestClient(test_app, raise_server_exceptions=False)


def test_application_exception_returns_expected_error_structure() -> None:
    client = _exception_test_client()
    response = client.get("/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Item was not found.",
        }
    }


def test_unexpected_exception_returns_safe_500_response() -> None:
    client = _exception_test_client()

    with patch("app.core.exceptions.logger.exception") as mock_exception:
        response = client.get("/crash")

    mock_exception.assert_called_once()
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
        }
    }
    body = response.text
    assert "secret" not in body
    assert "traceback" not in body.lower()
    assert "RuntimeError" not in body
