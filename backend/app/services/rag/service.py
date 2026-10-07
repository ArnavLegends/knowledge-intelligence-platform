"""RAG orchestration service."""

import logging

from fastapi import Depends

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import RAGError
from app.core.workspace import get_workspace_id
from app.services.llm.models import LLMMessage, LLMRequest
from app.services.llm.service import LLMService
from app.services.rag.context import ContextBuilder
from app.services.rag.models import RAGRequest, RAGResponse
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)


class RAGService:
    """Coordinates retrieval and generation to answer queries within a workspace."""

    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        llm_service: LLMService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service or RetrievalService()
        self._llm_service = llm_service or LLMService()
        self._settings = settings or default_settings

    def answer(self, request: RAGRequest) -> RAGResponse:
        """Retrieve relevant context and generate an answer scoped to workspace."""
        if not request.workspace_id or not request.workspace_id.strip():
            raise RAGError("workspace_id is required for RAG operations.")

        query_text = request.query.strip()
        if not query_text:
            raise RAGError("RAG query cannot be empty.")

        logger.info(
            "RAG query received: workspace_id=%s top_k=%s",
            request.workspace_id[:8] + "...",
            request.top_k,
        )

        # 1. Retrieve context scoped strictly to workspace_id
        try:
            retrieval_query = RetrievalQuery(
                text=query_text,
                workspace_id=request.workspace_id,
                top_k=(
                    request.top_k
                    if request.top_k is not None
                    else self._settings.retrieval_default_top_k
                ),
                threshold=(
                    request.threshold
                    if request.threshold is not None
                    else self._settings.retrieval_default_threshold
                ),
            )
            retrieved_chunks = self._retrieval_service.search(retrieval_query)
        except Exception as e:
            raise RAGError(f"Retrieval step failed: {e}") from e

        # Defensive check: ensure no cross-tenant contamination in retrieved chunks
        filtered_chunks = []
        for chunk in retrieved_chunks:
            chunk_ws = chunk.metadata.get("workspace_id")
            if chunk_ws is not None and chunk_ws != request.workspace_id:
                logger.warning(
                    "Security violation: cross-workspace chunk filtered in RAG: %s",
                    request.workspace_id[:8],
                )
                continue
            filtered_chunks.append(chunk)

        logger.debug("Retrieval complete: chunks=%d", len(filtered_chunks))

        # 2. Build context representation
        context_items = ContextBuilder.build_context_items(filtered_chunks)

        if not context_items:
            logger.info("No relevant context found — returning empty-context response")
            return RAGResponse(
                answer=self._settings.rag_empty_context_message,
                sources=[],
            )

        context_string = ContextBuilder.build_context_string(context_items)

        # 3. Construct the prompt
        system_prompt = (
            "You are a helpful knowledge assistant.\n"
            "Answer the user's question using ONLY the provided context.\n"
            "If the answer cannot be found in the context, do not guess or invent "
            "information. Instead, state that you cannot answer based on the provided "
            "context."
        )

        user_content = (
            f"Context Information:\n{context_string}\nUser Question: {query_text}"
        )

        try:
            llm_request = LLMRequest(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_content),
                ],
                model=self._settings.llm_model,
                temperature=0.0,
            )
            llm_response = self._llm_service.generate(llm_request)
        except Exception as e:
            raise RAGError(f"LLM generation failed: {e}") from e

        if not llm_response.content:
            raise RAGError("LLM returned an empty response.")

        return RAGResponse(
            answer=llm_response.content,
            sources=context_items,
        )


def get_rag_service(
    _workspace_id: str = Depends(get_workspace_id),
) -> "RAGService":
    """FastAPI dependency that constructs the RAG service.

    Depends on get_workspace_id so that workspace validation always runs
    before any external AI provider (LLM, retrieval) is instantiated.
    """
    return RAGService()
