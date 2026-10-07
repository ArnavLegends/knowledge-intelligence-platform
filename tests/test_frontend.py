"""Tests for Streamlit frontend helpers, cold-start handling, and connection UX."""

from unittest.mock import MagicMock, patch

import pytest
import requests
import streamlit as st
from frontend.app import (
    _api_error_message,
    _backend_healthy,
    _check_backend_status,
    _fetch_workspace_documents,
    _is_local_url,
)


@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    """Ensure Streamlit cache is clean between tests."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


class TestUrlClassification:
    """Test environment detection for local vs remote URLs."""

    def test_local_urls(self):
        assert _is_local_url("http://127.0.0.1:8000") is True
        assert _is_local_url("http://localhost:8000") is True
        assert _is_local_url("http://0.0.0.0:8000") is True
        assert _is_local_url("http://localhost:8501") is True

    def test_remote_urls(self):
        assert _is_local_url("https://kip-api-no1h.onrender.com") is False
        assert _is_local_url("https://api.example.com") is False
        assert _is_local_url("http://api.production.internal") is False


class TestBackendHealthChecks:
    """Test health checking behavior with mocked requests."""

    REMOTE_URL = "https://kip-api-no1h.onrender.com"
    LOCAL_URL = "http://127.0.0.1:8000"

    @patch("frontend.app.requests.get")
    def test_backend_healthy_200(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert _backend_healthy(self.REMOTE_URL) is True
        healthy, msg = _check_backend_status(self.REMOTE_URL)
        assert healthy is True
        assert "Backend is running" in msg

    @patch("frontend.app.requests.get")
    def test_remote_timeout_messaging(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        assert _backend_healthy(self.REMOTE_URL) is False
        healthy, msg = _check_backend_status(self.REMOTE_URL)
        assert healthy is False
        assert "waking up" in msg
        assert "free Render instance" in msg
        assert "uvicorn" not in msg

    @patch("frontend.app.requests.get")
    def test_remote_connection_error_messaging(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        assert _backend_healthy(self.REMOTE_URL) is False
        healthy, msg = _check_backend_status(self.REMOTE_URL)
        assert healthy is False
        assert "waking up" in msg
        assert "uvicorn" not in msg

    @patch("frontend.app.requests.get")
    def test_local_connection_error_messaging(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        healthy, msg = _check_backend_status(self.LOCAL_URL)
        assert healthy is False
        assert "uvicorn app.main:app" in msg
        assert "waking up" not in msg

    @patch("frontend.app.requests.get")
    def test_remote_non_200_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_get.return_value = mock_resp

        assert _backend_healthy(self.REMOTE_URL) is False
        healthy, msg = _check_backend_status(self.REMOTE_URL)
        assert healthy is False
        assert "503" in msg
        assert "unexpected status" in msg.lower()
        assert "uvicorn" not in msg

    @patch("frontend.app.requests.get")
    def test_health_check_timeout_selection(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        # Remote URL defaults to 10s timeout
        _check_backend_status(self.REMOTE_URL)
        mock_get.assert_called_with(f"{self.REMOTE_URL}/health", timeout=10)

        st.cache_data.clear()

        # Local URL defaults to 3s timeout
        _check_backend_status(self.LOCAL_URL)
        mock_get.assert_called_with(f"{self.LOCAL_URL}/health", timeout=3)


class TestWorkspaceDocuments:
    """Test workspace document fetching and timeout tolerances."""

    @patch("frontend.app.requests.get")
    def test_fetch_workspace_documents_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "doc-1", "filename": "sample.pdf", "chunks_indexed": 3}
        ]
        mock_get.return_value = mock_resp

        docs = _fetch_workspace_documents()
        assert len(docs) == 1
        assert docs[0]["filename"] == "sample.pdf"

    @patch("frontend.app.requests.get")
    def test_fetch_workspace_documents_failure_returns_empty_list(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")

        docs = _fetch_workspace_documents()
        assert docs == []

    @patch("frontend.app.requests.get")
    def test_fetch_workspace_documents_custom_timeout(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        _fetch_workspace_documents(timeout=45)
        _, kwargs = mock_get.call_args
        assert kwargs["timeout"] == 45


class TestApiErrorMessage:
    """Test API error message extraction."""

    def test_detail_in_response(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": "Workspace token invalid"}
        err = requests.HTTPError(response=mock_response)
        assert _api_error_message(err) == "Workspace token invalid"

    def test_error_dict_in_response(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": {"code": "bad_request", "message": "Missing header"}
        }
        err = requests.HTTPError(response=mock_response)
        assert "[bad_request] Missing header" in _api_error_message(err)

    def test_fallback_on_parse_error(self):
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Not JSON")
        err = requests.HTTPError("Server 500 error", response=mock_response)
        assert "Server 500 error" in _api_error_message(err)
