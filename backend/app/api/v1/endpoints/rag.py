"""RAG API endpoints."""

import functools
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.async_executor import run_blocking
from app.core.config import Settings, get_settings
from app.core.workspace import get_workspace_id
from app.services.rag.models import RAGRequest, RAGResponse
from app.services.rag.service import RAGService, get_rag_service

router = APIRouter()
logger = logging.getLogger(__name__)


class RAGAPIRequest(BaseModel):
    """API payload for asking a question over the knowledge base."""

    query: str
    top_k: int | None = None
    threshold: float | None = None


@router.post("/answer", response_model=RAGResponse)
async def answer(
    request: RAGAPIRequest,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    service: Annotated[RAGService, Depends(get_rag_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RAGResponse:
    """Generate an answer using retrieved knowledge strictly within the workspace.

    The blocking retrieval + LLM generation calls are offloaded to a bounded
    thread-pool so the async event loop remains responsive under concurrent load.
    An overall wall-clock timeout (embedding + search + generation budgets) guards
    against hung upstream calls.
    """
    top_k = (
        request.top_k if request.top_k is not None else settings.retrieval_default_top_k
    )
    threshold = (
        request.threshold
        if request.threshold is not None
        else settings.retrieval_default_threshold
    )

    rag_req = RAGRequest(
        query=request.query,
        workspace_id=workspace_id,
        top_k=top_k,
        threshold=threshold,
    )

    # Total timeout: embedding + vector search + LLM generation + scheduling margin
    total_timeout = (
        settings.embedding_timeout_seconds
        + settings.qdrant_timeout_seconds
        + settings.llm_timeout_seconds
        + 3.0
    )

    try:
        response: RAGResponse = await run_blocking(
            functools.partial(service.answer, rag_req),
            timeout=total_timeout,
            max_workers=settings.retrieval_executor_workers,
        )
    except TimeoutError:
        logger.warning(
            "RAG answer timed out after %.1fs for workspace=%s",
            total_timeout,
            workspace_id[:8],
        )
        raise HTTPException(
            status_code=504,
            detail="RAG generation timed out. Please try again later.",
        ) from None

    return response
