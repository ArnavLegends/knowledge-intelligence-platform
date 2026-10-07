"""Exception handling tests for the backend API."""

from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError, register_exception_handlers


def _exception_test_client() -> TestClient:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/not-found")
    def raise_not_found() -> None:
        raise NotFoundError("Item was not found.")

    @test_app.get("/http-bad-request")
    def raise_http_bad_request() -> None:
        raise HTTPException(status_code=400, detail="Missing required header.")

    @test_app.get("/http-forbidden")
    def raise_http_forbidden() -> None:
        raise HTTPException(status_code=403, detail="Access denied.")

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


def test_http_exception_preserves_status_code_and_not_swallowed_by_500() -> None:
    client = _exception_test_client()

    response_400 = client.get("/http-bad-request")
    assert response_400.status_code == 400
    assert response_400.status_code != 500
    assert response_400.json() == {
        "error": {
            "code": "bad_request",
            "message": "Missing required header.",
        }
    }

    response_403 = client.get("/http-forbidden")
    assert response_403.status_code == 403
    assert response_403.status_code != 500
    assert response_403.json() == {
        "error": {
            "code": "forbidden",
            "message": "Access denied.",
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
