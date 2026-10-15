"""Retrieval API endpoints."""

import functools
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.async_executor import run_blocking
from app.core.config import Settings, get_settings
from app.core.workspace import get_workspace_id
from app.services.retrieval.models import RetrievalQuery, RetrievedChunk
from app.services.retrieval.service import (
    RetrievalService,
    get_retrieval_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class RetrievalRequest(BaseModel):
    """API payload for semantic search."""

    query: str
    top_k: int | None = None
    threshold: float | None = None
    document_id: str | None = None
    filters: dict[str, Any] | None = None


class RetrievalResponse(BaseModel):
    """API response containing retrieved chunks."""

    results: list[RetrievedChunk]


@router.post("/search", response_model=RetrievalResponse)
async def search(
    request: RetrievalRequest,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    service: RetrievalService = Depends(get_retrieval_service),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> RetrievalResponse:
    """Perform a semantic similarity search scoped strictly to the workspace.

    The blocking embedding + vector-store calls are offloaded to a bounded
    thread-pool so the async event loop remains responsive under concurrent load.
    An overall wall-clock timeout (``embedding_timeout_seconds`` +
    ``qdrant_timeout_seconds`` + margin) guards against hung upstream calls.
    """
    top_k = (
        request.top_k if request.top_k is not None else settings.retrieval_default_top_k
    )
    threshold = (
        request.threshold
        if request.threshold is not None
        else settings.retrieval_default_threshold
    )

    query = RetrievalQuery(
        text=request.query,
        workspace_id=workspace_id,
        top_k=top_k,
        threshold=threshold,
        document_id=request.document_id,
        filters=request.filters,
    )

    # Total timeout: embedding + search budgets with a small scheduling margin
    total_timeout = (
        settings.embedding_timeout_seconds
        + settings.qdrant_timeout_seconds
        + 2.0
    )

    try:
        results: list[RetrievedChunk] = await run_blocking(
            functools.partial(service.search, query),
            timeout=total_timeout,
            max_workers=settings.retrieval_executor_workers,
        )
    except TimeoutError:
        logger.warning(
            "Retrieval timed out after %.1fs for workspace=%s",
            total_timeout,
            workspace_id[:8],
        )
        raise HTTPException(
            status_code=504,
            detail="Retrieval timed out. Please try again later.",
        ) from None

    return RetrievalResponse(results=results)
