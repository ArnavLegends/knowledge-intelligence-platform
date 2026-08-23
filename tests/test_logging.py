"""Structured logging and request middleware tests."""

import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import setup_logging
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_setup_logging_initializes_successfully() -> None:
    setup_logging(Settings(log_level="DEBUG"), force=True)

    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], logging.StreamHandler)


def test_request_middleware_does_not_break_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_request_logging_records_method_path_status() -> None:
    with patch("app.middleware.request_logging.logger.info") as mock_info:
        response = client.get("/health")

    assert response.status_code == 200
    mock_info.assert_called_once()

    message_template, method, path, status, duration_ms = mock_info.call_args[0]
    assert message_template == "method=%s path=%s status=%s duration_ms=%.2f"
    assert method == "GET"
    assert path == "/health"
    assert status == 200
    assert duration_ms >= 0
