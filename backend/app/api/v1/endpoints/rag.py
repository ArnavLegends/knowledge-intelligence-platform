"""RAG API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services.rag.models import RAGRequest, RAGResponse
from app.services.rag.service import RAGService

router = APIRouter()


class RAGAPIRequest(BaseModel):
    """API payload for asking a question over the knowledge base."""

    query: str
    top_k: int | None = None
    threshold: float | None = None


def get_rag_service() -> RAGService:
    """Dependency injection for the RAG service."""
    return RAGService()


@router.post("/answer", response_model=RAGResponse)
async def answer(
    request: RAGAPIRequest,
    service: RAGService = Depends(get_rag_service),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> RAGResponse:
    """Generate an answer using retrieved knowledge."""
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
        top_k=top_k,
        threshold=threshold,
    )

    return service.answer(rag_req)
