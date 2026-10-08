"""Targeted tests for feedback submission API — GET-based Apps Script transport."""

from unittest.mock import MagicMock, patch

import requests as requests_lib
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIGURED_SETTINGS = dict(
    feedback_webhook_url="https://script.google.com/macros/s/FAKE/exec",
    feedback_webhook_token="test-secret-token",
    llm_api_key="fake",
)


def _ok_get_mock() -> MagicMock:
    """Return a mock requests.Response that simulates a successful Apps Script doGet."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _override(settings_kwargs: dict):
    """Apply dependency override and return cleanup callable."""
    override = Settings(**settings_kwargs)
    app.dependency_overrides[get_settings] = lambda: override
    return lambda: app.dependency_overrides.pop(get_settings, None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_submit_feedback_success_returns_recorded():
    """Valid feedback forwarded via GET returns 200 with 'recorded' status."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        with patch(
            "app.api.v1.feedback.requests.get", return_value=_ok_get_mock()
        ) as mock_get:
            payload = {
                "category": "Bug",
                "message": "Found an issue with docx parsing on table headers.",
                "workspace_id": "test-ws-123",
            }
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert "Thanks" in data["message"]
        assert "timestamp" in data

        mock_get.assert_called_once()
    finally:
        cleanup()


def test_submit_feedback_get_params_contain_token_and_workspace():
    """Verify GET params include token, category, message, word_count, workspace_id."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        with patch(
            "app.api.v1.feedback.requests.get", return_value=_ok_get_mock()
        ) as mock_get:
            payload = {
                "category": "UX",
                "message": "The sidebar is hard to navigate.",
                "workspace_id": "ws-abc",
            }
            resp = client.post("/api/v1/feedback", json=payload)
            assert resp.status_code == 200

        _, kwargs = mock_get.call_args
        params = kwargs["params"]
        assert params["token"] == "test-secret-token"
        assert params["category"] == "UX"
        assert params["message"] == "The sidebar is hard to navigate."
        assert params["word_count"] == 6
        assert params["workspace_id"] == "ws-abc"
        assert "timestamp" in params
    finally:
        cleanup()


def test_submit_feedback_no_workspace_id_sends_empty_string():
    """workspace_id absent → GET param sent as empty string, not None/omitted."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        with patch(
            "app.api.v1.feedback.requests.get", return_value=_ok_get_mock()
        ) as mock_get:
            payload = {"category": "Other", "message": "General observation."}
            resp = client.post("/api/v1/feedback", json=payload)
            assert resp.status_code == 200

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["workspace_id"] == ""
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# Response body inspection
# ---------------------------------------------------------------------------


def test_webhook_http_200_but_body_not_ok_is_502():
    """HTTP 200 with non-OK body must produce 502 feedback_delivery_failed."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "INVALID"
        mock_resp.raise_for_status.return_value = None

        with patch("app.api.v1.feedback.requests.get", return_value=mock_resp):
            payload = {"category": "Bug", "message": "Something seems wrong."}
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "feedback_delivery_failed"
    finally:
        cleanup()


def test_webhook_http_200_unauthorized_body_is_502():
    """Apps Script returning 'UNAUTHORIZED' (wrong token at runtime) → 502."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "UNAUTHORIZED"
        mock_resp.raise_for_status.return_value = None

        with patch("app.api.v1.feedback.requests.get", return_value=mock_resp):
            payload = {"category": "Bug", "message": "Something seems wrong."}
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "feedback_delivery_failed"
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# HTTP-level failures
# ---------------------------------------------------------------------------


def test_webhook_http_404_produces_502():
    """HTTP 404 from Apps Script → raise_for_status raises → 502 delivery_failed."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = ""
        mock_resp.raise_for_status.side_effect = requests_lib.HTTPError("404 Not Found")

        with patch("app.api.v1.feedback.requests.get", return_value=mock_resp):
            payload = {
                "category": "Performance",
                "message": "Slow response on large uploads.",
            }
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "feedback_delivery_failed"
    finally:
        cleanup()


def test_webhook_timeout_produces_502():
    """requests.Timeout → 502 feedback_delivery_failed without leaking internals."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        with patch(
            "app.api.v1.feedback.requests.get",
            side_effect=requests_lib.Timeout("timed out"),
        ):
            payload = {
                "category": "Performance",
                "message": "Retrieval feels slow with many documents.",
            }
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 502
        data = resp.json()
        assert data["error"]["code"] == "feedback_delivery_failed"
        # Secret must not appear in error response
        assert "test-secret-token" not in data["error"]["message"]
    finally:
        cleanup()


def test_webhook_connection_error_produces_502():
    """requests.ConnectionError → 502 feedback_delivery_failed."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        with patch(
            "app.api.v1.feedback.requests.get",
            side_effect=requests_lib.ConnectionError("refused"),
        ):
            payload = {"category": "Bug", "message": "App crashes on upload."}
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "feedback_delivery_failed"
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


def test_missing_webhook_url_produces_503():
    """Missing FEEDBACK_WEBHOOK_URL → 503 feedback_destination_unconfigured."""
    cleanup = _override(
        {
            "feedback_webhook_url": None,
            "feedback_webhook_token": "tok",
            "llm_api_key": "fake",
        }
    )
    try:
        payload = {
            "category": "Improvement Idea",
            "message": "Allow exporting answers to markdown.",
        }
        resp = client.post("/api/v1/feedback", json=payload)
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "feedback_destination_unconfigured"
        assert "FEEDBACK_WEBHOOK_URL" in data["error"]["message"]
    finally:
        cleanup()


def test_missing_webhook_token_produces_503():
    """Missing FEEDBACK_WEBHOOK_TOKEN → 503 feedback_destination_unconfigured."""
    cleanup = _override(
        {
            "feedback_webhook_url": "https://script.google.com/macros/s/FAKE/exec",
            "feedback_webhook_token": None,
            "llm_api_key": "fake",
        }
    )
    try:
        payload = {"category": "Bug", "message": "Something is broken here."}
        resp = client.post("/api/v1/feedback", json=payload)
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"]["code"] == "feedback_destination_unconfigured"
        assert "FEEDBACK_WEBHOOK_TOKEN" in data["error"]["message"]
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# Input validation (unchanged public API contract)
# ---------------------------------------------------------------------------


def test_invalid_category_rejected():
    """Invalid category → 400 Bad Request."""
    payload = {"category": "RandomCategory", "message": "Some message"}
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 400
    assert "Invalid feedback category" in resp.json()["error"]["message"]


def test_empty_message_rejected():
    """Whitespace-only message → 400 Bad Request."""
    payload = {"category": "Bug", "message": "   "}
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 400
    assert "Feedback message cannot be empty" in resp.json()["error"]["message"]


def test_exceeds_30_words_rejected():
    """31-word message → 400 Bad Request."""
    long_msg = "word " * 31
    payload = {"category": "UX", "message": long_msg.strip()}
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 400
    assert "exceeds 30 words" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Secret isolation
# ---------------------------------------------------------------------------


def test_webhook_token_not_exposed_in_error_response():
    """Delivery failure response must never contain the configured token."""
    cleanup = _override(_CONFIGURED_SETTINGS)
    try:
        with patch(
            "app.api.v1.feedback.requests.get",
            side_effect=requests_lib.RequestException("fail"),
        ):
            payload = {"category": "Other", "message": "Delivery will fail."}
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 502
        body_text = resp.text
        assert "test-secret-token" not in body_text
        assert "FAKE" not in body_text  # no webhook URL fragment either
    finally:
        cleanup()
