"""Application-facing embedding service."""

from app.services.chunking.models import Chunk
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingInput, EmbeddingRequest


class EmbeddingService:
    """Converts Chunks into Embeddings via the EmbeddingManager."""

    def __init__(self, manager: EmbeddingManager | None = None) -> None:
        self._manager = manager or EmbeddingManager()

    def embed_texts(self, request: EmbeddingRequest) -> list[Embedding]:
        """Convert an EmbeddingRequest into Embeddings via the manager."""
        return self._manager.embed(request)

    def embed_chunks(self, chunks: list[Chunk]) -> list[Embedding]:
        """Convert a list of Chunks to normalized Embeddings, keeping provenance."""
        if not chunks:
            return []

        inputs = []
        for chunk in chunks:
            # Preserve provenance in metadata
            meta = chunk.metadata.copy()
            meta["document_id"] = chunk.document_id
            meta["text"] = chunk.text

            inputs.append(
                EmbeddingInput(
                    source_id=chunk.id,
                    text=chunk.text,
                    metadata=meta,
                )
            )

        request = EmbeddingRequest(inputs=inputs)
        return self.embed_texts(request)
