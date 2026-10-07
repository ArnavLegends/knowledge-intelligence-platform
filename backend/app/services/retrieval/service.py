"""Application-facing retrieval service."""

import logging

from fastapi import Depends

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import RetrievalError
from app.core.workspace import get_workspace_id
from app.services.embeddings.models import EmbeddingInput, EmbeddingRequest
from app.services.embeddings.service import EmbeddingService
from app.services.retrieval.models import RetrievalQuery, RetrievedChunk
from app.services.vector_store.service import VectorStoreService

logger = logging.getLogger(__name__)


class RetrievalService:
    """Provides high-level retrieval capabilities scoped to workspaces."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_store_service: VectorStoreService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._embedding_service = embedding_service or EmbeddingService()
        self._vector_store_service = vector_store_service or VectorStoreService()
        self._settings = settings or default_settings

    def search(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        """Perform a semantic search strictly scoped to the query's workspace."""
        if not query.workspace_id or not query.workspace_id.strip():
            raise RetrievalError("workspace_id is required for retrieval operations.")

        if not query.text.strip():
            return []

        # 1. Embed the query text
        try:
            emb_req = EmbeddingRequest(
                inputs=[EmbeddingInput(source_id="query", text=query.text)],
                model=self._settings.embedding_model,
            )
            embeddings = self._embedding_service.embed_texts(emb_req)
        except Exception as e:
            raise RetrievalError(f"Failed to embed query: {e}") from e

        if not embeddings or not embeddings[0].vector:
            raise RetrievalError("Embedding service returned empty vector for query.")

        query_vector = embeddings[0].vector

        # 2. Search the vector store with mandatory workspace filter
        try:
            results = self._vector_store_service.search(
                query_vector=query_vector,
                top_k=query.top_k,
                workspace_id=query.workspace_id,
                threshold=query.threshold,
            )
        except Exception as e:
            raise RetrievalError(f"Vector store search failed: {e}") from e

        # 3. Convert to RetrievedChunk with defensive isolation check
        retrieved_chunks = []
        for res in results:
            # Defensive validation: reject any result not matching workspace_id
            chunk_ws = res.metadata.get("workspace_id")
            if chunk_ws is not None and chunk_ws != query.workspace_id:
                logger.warning(
                    "Security invariant violation: discarded cross-tenant chunk in %s",
                    query.workspace_id[:8],
                )
                continue

            doc_id = res.metadata.get("document_id")
            text = res.metadata.get("text")

            retrieved_chunks.append(
                RetrievedChunk(
                    id=res.id,
                    document_id=doc_id,
                    text=text,
                    score=res.distance,
                    metadata=res.metadata,
                )
            )

        return retrieved_chunks


def get_retrieval_service(
    _workspace_id: str = Depends(get_workspace_id),
) -> "RetrievalService":
    """FastAPI dependency that constructs the retrieval service.

    Depends on get_workspace_id so that workspace validation always runs
    before any external AI provider (embedding, vector store) is instantiated.
    """
    return RetrievalService()
