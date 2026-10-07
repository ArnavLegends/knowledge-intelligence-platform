"""RAG API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.workspace import get_workspace_id
from app.services.rag.models import RAGRequest, RAGResponse
from app.services.rag.service import RAGService, get_rag_service

router = APIRouter()


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
    """Generate an answer using retrieved knowledge strictly within the workspace."""
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

    return service.answer(rag_req)
