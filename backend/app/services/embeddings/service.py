"""Application-facing embedding service."""

from app.services.chunking.models import Chunk
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingInput, EmbeddingRequest


class EmbeddingService:
    """Converts Chunks into Embeddings via the EmbeddingManager."""

    def __init__(self, manager: EmbeddingManager | None = None) -> None:
        self._manager = manager or EmbeddingManager()

    def embed_chunks(self, chunks: list[Chunk]) -> list[Embedding]:
        """Convert a list of Chunks into normalized Embeddings."""
        if not chunks:
            return []

        inputs = []
        for chunk in chunks:
            inputs.append(
                EmbeddingInput(
                    source_id=chunk.id,
                    text=chunk.text,
                    metadata=chunk.metadata.copy(),
                )
            )

        request = EmbeddingRequest(inputs=inputs)
        return self._manager.embed(request)
