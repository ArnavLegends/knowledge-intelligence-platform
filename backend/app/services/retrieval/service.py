"""Application-facing retrieval service."""

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import RetrievalError
from app.services.embeddings.models import EmbeddingInput, EmbeddingRequest
from app.services.embeddings.service import EmbeddingService
from app.services.retrieval.models import RetrievalQuery, RetrievedChunk
from app.services.vector_store.service import VectorStoreService


class RetrievalService:
    """Provides high-level retrieval capabilities."""

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
        """Perform a semantic search to retrieve relevant chunks."""

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

        # 2. Search the vector store
        try:
            results = self._vector_store_service.search(
                query_vector=query_vector,
                top_k=query.top_k,
                threshold=query.threshold,
            )
        except Exception as e:
            raise RetrievalError(f"Vector store search failed: {e}") from e

        # 3. Convert to RetrievedChunk
        retrieved_chunks = []
        for res in results:
            doc_id = res.metadata.get("document_id")
            text = res.metadata.get("text")

            # Clean internal metadata keys if desired, but we can just pass it through

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
