"""Tests for Streamlit frontend helpers, cold-start handling, and interaction UX."""

from pathlib import Path
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
    _resolve_document_name,
)
from streamlit.testing.v1 import AppTest

FRONTEND_APP_PATH = str(Path(__file__).parent.parent / "frontend" / "app.py")


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


class TestDocumentNameResolution:
    """Test resolving document IDs to original filenames with graceful fallbacks."""

    def test_resolve_matching_document(self):
        docs = [
            {"document_id": "doc-hash-1234567890", "filename": "financial_report.pdf"},
            {"id": "doc-hash-9876543210", "filename": "notes.md"},
        ]
        assert (
            _resolve_document_name("doc-hash-1234567890", docs)
            == "financial_report.pdf"
        )
        assert _resolve_document_name("doc-hash-9876543210", docs) == "notes.md"

    def test_resolve_long_hash_fallback(self):
        long_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        # When not in uploaded_docs list, avoid raw 64-character hex label
        resolved = _resolve_document_name(long_hash, [])
        assert resolved == "Document a1b2c3d4…"

    def test_resolve_short_identifier_fallback(self):
        assert _resolve_document_name("doc-1", []) == "doc-1"
        assert _resolve_document_name("", []) == "Document"


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


class TestFrontendInteractionFlows:
    """Test decoupled file selection, explicit indexing, and rerun stability."""

    def _mock_get_healthy(self, mock_get, docs=None):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = docs or []
        mock_get.return_value = mock_resp

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_file_selection_alone_does_not_upload(self, mock_post, mock_get):
        """A: Selecting a file alone must NOT call POST /documents."""
        self._mock_get_healthy(mock_get)

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("research.pdf", b"Test PDF contents")
        at.run()

        # Selection alone must not trigger POST
        mock_post.assert_not_called()
        # Verify 'Index 1 Document' button is now available
        button_labels = [b.label for b in at.button]
        assert "Index 1 Document" in button_labels

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_click_index_document_calls_post_once(self, mock_post, mock_get):
        """B: Clicking Index Document calls POST /documents exactly once."""
        self._mock_get_healthy(mock_get)
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"filename": "research.pdf", "chunks_indexed": 5},
        )

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("research.pdf", b"Test PDF contents")
        at.run()

        index_btn = [b for b in at.button if b.label == "Index 1 Document"][0]
        index_btn.click().run()

        assert mock_post.call_count == 1
        # Post should have targeted /api/v1/documents
        call_url = mock_post.call_args[0][0]
        assert call_url.endswith("/api/v1/documents")

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_rerun_after_file_selection_does_not_upload(self, mock_post, mock_get):
        """C: A Streamlit rerun after file selection does NOT cause an upload."""
        self._mock_get_healthy(mock_get)

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("research.pdf", b"Test PDF contents")
        at.run()

        # Multiple subsequent reruns without clicking Index Document
        at.run()
        at.run()
        mock_post.assert_not_called()

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_click_ask_does_not_upload_selected_file(self, mock_post, mock_get):
        """D: Clicking Ask does NOT upload the selected file."""
        self._mock_get_healthy(mock_get)
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"answer": "Grounded answer", "sources": []},
        )

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("research.pdf", b"Test PDF contents")
        at.run()

        # Input question and click Ask
        at.text_area[0].input("What is in this document?").run()
        ask_btn = [b for b in at.button if b.label == "Ask"][0]
        ask_btn.click().run()

        # Post was called for /rag/answer, but NEVER for /documents
        for call in mock_post.call_args_list:
            url = call[0][0]
            assert not url.endswith("/api/v1/documents")
            assert url.endswith("/api/v1/rag/answer")

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_click_connect_does_not_upload_selected_file(self, mock_post, mock_get):
        """E: Clicking Connect does NOT upload the selected file."""
        self._mock_get_healthy(mock_get)

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("research.pdf", b"Test PDF contents")
        at.run()

        # Input existing token and connect
        at.text_input(key="resume_input").input("another-workspace-token-123").run()
        connect_btn = [b for b in at.button if b.label == "Connect"][0]
        connect_btn.click().run()

        # Connecting must never upload the selected file
        mock_post.assert_not_called()

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_click_reload_documents_does_not_upload_selected_file(
        self, mock_post, mock_get
    ):
        """F: Clicking Reload Documents does NOT upload the selected file."""
        self._mock_get_healthy(mock_get)

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("research.pdf", b"Test PDF contents")
        at.run()

        reload_btn = [b for b in at.button if b.label == "Reload Documents"][0]
        reload_btn.click().run()

        mock_post.assert_not_called()

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_successful_indexing_clears_selected_file_state(self, mock_post, mock_get):
        """G: Successful indexing clears/resets selected file state."""
        self._mock_get_healthy(mock_get)
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"filename": "doc.txt", "chunks_indexed": 3},
        )

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("doc.txt", b"Content")
        at.run()

        idx_btn = [b for b in at.button if b.label == "Index 1 Document"][0]
        idx_btn.click().run()

        # Success banner should be visible
        success_texts = [s.value for s in at.success]
        assert any(
            "doc.txt" in s and "indexed successfully" in s for s in success_texts
        )

        # File uploader key incremented and file cleared
        assert at.file_uploader[0].value is None or at.file_uploader[0].value == []
        # Index button should no longer be present
        button_labels = [b.label for b in at.button]
        assert not any(b.startswith("Index ") for b in button_labels)

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_multi_file_selection_and_button_label(self, mock_post, mock_get):
        """Verify selecting multiple files displays count and does not upload prematurely."""
        self._mock_get_healthy(mock_get)

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("doc1.pdf", b"Doc 1 content")
        at.file_uploader[0].upload("doc2.docx", b"Doc 2 content")
        at.file_uploader[0].upload("doc3.txt", b"Doc 3 content")
        at.run()

        # No automatic upload
        mock_post.assert_not_called()

        # Button indicates exact document count
        button_labels = [b.label for b in at.button]
        assert "Index 3 Documents" in button_labels

        # UI displays selected files
        markdown_texts = [m.value for m in at.markdown]
        assert any("doc1.pdf" in m for m in markdown_texts)
        assert any("doc2.docx" in m for m in markdown_texts)
        assert any("doc3.txt" in m for m in markdown_texts)

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_multi_file_indexing_sent_independently(self, mock_post, mock_get):
        """Verify multiple files are sent sequentially to existing single-doc endpoint."""
        self._mock_get_healthy(mock_get)
        mock_post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"filename": "alpha.pdf", "chunks_indexed": 6}),
            MagicMock(status_code=200, json=lambda: {"filename": "beta.docx", "chunks_indexed": 4}),
        ]

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("alpha.pdf", b"Alpha content")
        at.file_uploader[0].upload("beta.docx", b"Beta content")
        at.run()

        index_btn = [b for b in at.button if b.label == "Index 2 Documents"][0]
        index_btn.click().run()

        # Both documents sent independently
        assert mock_post.call_count == 2
        call_ws_headers = [
            c[1].get("headers", {}).get("X-KIP-Workspace-ID")
            for c in mock_post.call_args_list
        ]
        # Both must share the same workspace
        assert call_ws_headers[0] == call_ws_headers[1]
        assert len(call_ws_headers[0]) >= 8

        # Feedback displays per-document success
        success_texts = [s.value for s in at.success]
        assert any("alpha.pdf" in s and "6 chunks" in s for s in success_texts)
        assert any("beta.docx" in s and "4 chunks" in s for s in success_texts)

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_multi_file_failure_resilience(self, mock_post, mock_get):
        """Verify failure of one document does NOT stop remaining documents."""
        self._mock_get_healthy(mock_get)
        err_resp = MagicMock(status_code=500)
        err_resp.json.return_value = {"detail": "Parser crashed"}
        http_err = requests.HTTPError("500 Server Error", response=err_resp)

        mock_post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"filename": "good1.txt", "chunks_indexed": 2}),
            http_err,
            MagicMock(status_code=200, json=lambda: {"filename": "good2.txt", "chunks_indexed": 5}),
        ]

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("good1.txt", b"Good 1")
        at.file_uploader[0].upload("bad.docx", b"Corrupt")
        at.file_uploader[0].upload("good2.txt", b"Good 2")
        at.run()

        index_btn = [b for b in at.button if b.label == "Index 3 Documents"][0]
        index_btn.click().run()

        # All 3 files attempted despite failure of the second
        assert mock_post.call_count == 3

        # Successes reported
        success_texts = [s.value for s in at.success]
        assert any("good1.txt" in s for s in success_texts)
        assert any("good2.txt" in s for s in success_texts)

        # Failure reported for bad.docx
        error_texts = [e.value for e in at.error]
        assert any("bad.docx" in e and "Parser crashed" in e for e in error_texts)

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_multi_file_duplicate_idempotency_feedback(self, mock_post, mock_get):
        """Verify already indexed document produces ALREADY INDEXED info message."""
        self._mock_get_healthy(mock_get)
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"filename": "existing.pdf", "chunks_indexed": 0},
        )

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.file_uploader[0].upload("existing.pdf", b"Content")
        at.run()

        index_btn = [b for b in at.button if b.label == "Index 1 Document"][0]
        index_btn.click().run()

        info_texts = [i.value for i in at.info]
        assert any("existing.pdf" in i and "already indexed" in i for i in info_texts)


    @patch("frontend.app.requests.get")
    def test_workspace_switching_fetches_new_documents(self, mock_get):
        """H: Workspace switching fetches the new workspace's documents."""
        self._mock_get_healthy(mock_get, docs=[{"id": "d1", "filename": "ws2_doc.pdf"}])

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()

        at.text_input(key="resume_input").input("new-target-token-xyz123").run()
        connect_btn = [b for b in at.button if b.label == "Connect"][0]
        connect_btn.click().run()

        assert at.session_state["workspace_id"] == "new-target-token-xyz123"
        # Verify headers used X-KIP-Workspace-ID with the new token
        headers_found = [
            call[1].get("headers", {}).get("X-KIP-Workspace-ID")
            for call in mock_get.call_args_list
        ]
        assert "new-target-token-xyz123" in headers_found

    @patch("frontend.app.requests.get")
    @patch("frontend.app.requests.post")
    def test_source_presentation_maps_filenames_and_hides_excerpt(
        self, mock_post, mock_get
    ):
        """I & J: Maps doc IDs to filenames and collapses excerpts by default."""
        self._mock_get_healthy(
            mock_get,
            docs=[{"document_id": "doc-hash-999", "filename": "architecture.pdf"}],
        )
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "answer": "KIP uses a decoupled indexing pipeline.",
                "sources": [
                    {
                        "document_id": "doc-hash-999",
                        "chunk_id": "chunk-42",
                        "score": 0.9412,
                        "text": "Secret inner text excerpt that must be hidden",
                    }
                ],
            },
        )

        at = AppTest.from_file(FRONTEND_APP_PATH)
        at.run()
        at.text_area[0].input("Explain the architecture").run()
        ask_btn = [b for b in at.button if b.label == "Ask"][0]
        ask_btn.click().run()

        # Answer is rendered
        assert any("decoupled indexing pipeline" in m.value for m in at.markdown)

        # Source is mapped to filename
        assert any("architecture.pdf" in m.value for m in at.markdown)

        # Excerpt expander is present and collapsed by default
        excerpt_expanders = [e for e in at.expander if "retrieved excerpt" in e.label]
        assert len(excerpt_expanders) == 1
        assert excerpt_expanders[0].proto.expanded is False
