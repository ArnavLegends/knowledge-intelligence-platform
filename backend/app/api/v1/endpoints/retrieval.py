"""Retrieval API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services.retrieval.models import RetrievalQuery, RetrievedChunk
from app.services.retrieval.service import RetrievalService

router = APIRouter()


class RetrievalRequest(BaseModel):
    """API payload for semantic search."""

    query: str
    top_k: int | None = None
    threshold: float | None = None


class RetrievalResponse(BaseModel):
    """API response containing retrieved chunks."""

    results: list[RetrievedChunk]


def get_retrieval_service() -> RetrievalService:
    """Dependency injection for the retrieval service."""
    return RetrievalService()


@router.post("/search", response_model=RetrievalResponse)
async def search(
    request: RetrievalRequest,
    service: RetrievalService = Depends(get_retrieval_service),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> RetrievalResponse:
    """Perform a semantic similarity search."""

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
        top_k=top_k,
        threshold=threshold,
    )

    results = service.search(query)
    return RetrievalResponse(results=results)
