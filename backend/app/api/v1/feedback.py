"""Feedback submission endpoint with external persistence routing via GET transport."""

import logging
from datetime import UTC, datetime
from typing import Annotated

import requests
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException, BadRequestError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

ALLOWED_CATEGORIES = {
    "Bug",
    "Incorrect Answer",
    "Retrieval",
    "UX",
    "Performance",
    "Improvement Idea",
    "Other",
}


class FeedbackRequest(BaseModel):
    """User feedback submission payload."""

    category: str = Field(..., description="Feedback category")
    message: str = Field(..., description="Free-text feedback message up to 30 words")
    workspace_id: str | None = Field(
        default=None, description="Optional active workspace identifier"
    )


class FeedbackResponse(BaseModel):
    """Response returned upon feedback processing."""

    status: str = "recorded"
    message: str = "Thanks — your feedback has been recorded."
    timestamp: datetime


@router.post("", response_model=FeedbackResponse)
def submit_feedback(
    request: FeedbackRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FeedbackResponse:
    """Validate, timestamp, and forward feedback to an external destination."""
    # ── Input validation ─────────────────────────────────────────────────────
    category = request.category.strip()
    if category not in ALLOWED_CATEGORIES:
        allowed = ", ".join(sorted(ALLOWED_CATEGORIES))
        raise BadRequestError(
            f"Invalid feedback category '{category}'. Allowed categories: {allowed}."
        )

    msg = request.message.strip()
    if not msg:
        raise BadRequestError("Feedback message cannot be empty.")

    words = msg.split()
    if len(words) > 30:
        raise BadRequestError(
            f"Feedback message exceeds 30 words (current: {len(words)} words)."
        )

    # ── Configuration guard ──────────────────────────────────────────────────
    if not settings.feedback_webhook_url or not settings.feedback_webhook_url.strip():
        logger.warning("Feedback submitted but FEEDBACK_WEBHOOK_URL is not configured.")
        raise AppException(
            "Feedback service is currently unconfigured."
            " Set FEEDBACK_WEBHOOK_URL to enable persistence.",
            code="feedback_destination_unconfigured",
            status_code=503,
        )

    if (
        not settings.feedback_webhook_token
        or not settings.feedback_webhook_token.strip()
    ):
        logger.warning(
            "Feedback submitted but FEEDBACK_WEBHOOK_TOKEN is not configured."
        )
        raise AppException(
            "Feedback service is currently unconfigured."
            " Set FEEDBACK_WEBHOOK_TOKEN to enable persistence.",
            code="feedback_destination_unconfigured",
            status_code=503,
        )

    # ── Build GET params (requests library URL-encodes these automatically) ──
    now = datetime.now(UTC)
    params = {
        "token": settings.feedback_webhook_token,
        "category": category,
        "message": msg,
        "word_count": len(words),
        "workspace_id": request.workspace_id or "",
        "timestamp": now.isoformat(),
    }

    # ── Dispatch to Apps Script doGet() ──────────────────────────────────────
    try:
        resp = requests.get(settings.feedback_webhook_url, params=params, timeout=10)
        resp.raise_for_status()
        body = resp.text.strip()
        if body != "OK":
            logger.error(
                "Feedback webhook returned unexpected body (len=%d). Expected 'OK'.",
                len(body),
            )
            raise AppException(
                "Failed to record feedback due to destination delivery failure.",
                code="feedback_delivery_failed",
                status_code=502,
            )
    except AppException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to deliver feedback to configured destination: %s",
            type(exc).__name__,
        )
        raise AppException(
            "Failed to record feedback due to destination delivery failure.",
            code="feedback_delivery_failed",
            status_code=502,
        ) from None

    return FeedbackResponse(
        status="recorded",
        message="Thanks — your feedback has been recorded.",
        timestamp=now,
    )
