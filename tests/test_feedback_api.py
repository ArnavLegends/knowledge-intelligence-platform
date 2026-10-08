"""Targeted tests for feedback submission API and webhook persistence."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
import requests

from app.core.config import Settings
from app.main import app

client = TestClient(app)


def test_submit_feedback_success():
    """Verify valid feedback is accepted, timestamped, and forwarded to webhook."""
    from app.core.config import get_settings

    settings_override = Settings(
        feedback_webhook_url="https://hooks.example.com/feedback",
        llm_api_key="fake",
    )
    app.dependency_overrides[get_settings] = lambda: settings_override
    try:
        with patch("app.api.v1.feedback.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            mock_post.return_value = mock_resp

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

            # Verify webhook call
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert args[0] == "https://hooks.example.com/feedback"
            sent_payload = kwargs["json"]
            assert sent_payload["category"] == "Bug"
            assert sent_payload["message"] == "Found an issue with docx parsing on table headers."
            assert sent_payload["word_count"] == 9
            assert sent_payload["workspace_id"] == "test-ws-123"
            assert "timestamp" in sent_payload
    finally:
        app.dependency_overrides.pop(get_settings, None)



def test_submit_feedback_invalid_category_rejected():
    """Verify invalid category is rejected with 400 Bad Request."""
    payload = {
        "category": "RandomCategory",
        "message": "Some message",
    }
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 400
    data = resp.json()
    assert "Invalid feedback category" in data["error"]["message"]


def test_submit_feedback_empty_message_rejected():
    """Verify empty message is rejected with 400 Bad Request."""
    payload = {
        "category": "Bug",
        "message": "   ",
    }
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 400
    data = resp.json()
    assert "Feedback message cannot be empty" in data["error"]["message"]


def test_submit_feedback_exceeds_30_words_rejected():
    """Verify message exceeding 30 words is rejected with 400 Bad Request."""
    long_msg = "word " * 31
    payload = {
        "category": "UX",
        "message": long_msg.strip(),
    }
    resp = client.post("/api/v1/feedback", json=payload)
    assert resp.status_code == 400
    data = resp.json()
    assert "exceeds 30 words" in data["error"]["message"]


def test_submit_feedback_unconfigured_webhook():
    """Verify unconfigured destination produces a clear 503 error without exposing secrets."""
    from app.core.config import get_settings

    settings_override = Settings(
        feedback_webhook_url=None,
        llm_api_key="fake",
    )
    app.dependency_overrides[get_settings] = lambda: settings_override
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
        app.dependency_overrides.pop(get_settings, None)


def test_submit_feedback_destination_failure_handled_gracefully():
    """Verify destination failure produces controlled 502 error and hides external URLs/secrets."""
    from app.core.config import get_settings

    settings_override = Settings(
        feedback_webhook_url="https://hooks.example.com/secret-token-key-12345",
        llm_api_key="fake",
    )
    app.dependency_overrides[get_settings] = lambda: settings_override
    try:
        with patch("app.api.v1.feedback.requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("Connection timeout")

            payload = {
                "category": "Performance",
                "message": "Retrieval feels slow with many documents.",
            }
            resp = client.post("/api/v1/feedback", json=payload)
            assert resp.status_code == 502
            data = resp.json()
            assert data["error"]["code"] == "feedback_delivery_failed"
            # Ensure secret webhook url is not in the error response
            assert "secret-token-key-12345" not in data["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_settings, None)

