"""RAG orchestration service."""

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import RAGError
from app.services.llm.models import LLMMessage, LLMRequest
from app.services.llm.service import LLMService
from app.services.rag.context import ContextBuilder
from app.services.rag.models import RAGRequest, RAGResponse
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService


class RAGService:
    """Coordinates retrieval and generation to answer queries."""

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
        """Retrieve relevant context and generate an answer."""
        query_text = request.query.strip()
        if not query_text:
            raise RAGError("RAG query cannot be empty.")

        # 1. Retrieve context
        try:
            retrieval_query = RetrievalQuery(
                text=query_text,
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

        # 2. Build context representation
        context_items = ContextBuilder.build_context_items(retrieved_chunks)

        if not context_items:
            # Handle empty context gracefully
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
                temperature=0.0,  # Deterministic configuration choice
            )
            llm_response = self._llm_service.generate(llm_request)
        except Exception as e:
            raise RAGError(f"LLM generation failed: {e}") from e

        if not llm_response.content:
            raise RAGError("LLM returned an empty response.")

        # 4. Return results with provenance
        return RAGResponse(
            answer=llm_response.content,
            sources=context_items,
        )
