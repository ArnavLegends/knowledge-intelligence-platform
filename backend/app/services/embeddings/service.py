"""Application-facing embedding service."""

from collections.abc import Callable

from app.services.chunking.models import Chunk
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingInput, EmbeddingRequest


class EmbeddingService:
    """Converts Chunks into Embeddings via the EmbeddingManager."""

    def __init__(
        self,
        manager: EmbeddingManager | None = None,
        doc_formatter: Callable[[str], str] | None = None,
    ) -> None:
        self._manager = manager or EmbeddingManager()
        self._doc_formatter = doc_formatter

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

            text_to_embed = (
                self._doc_formatter(chunk.text)
                if self._doc_formatter is not None
                else chunk.text
            )
            inputs.append(
                EmbeddingInput(
                    source_id=chunk.id,
                    text=text_to_embed,
                    metadata=meta,
                )
            )

        request = EmbeddingRequest(inputs=inputs)
        return self.embed_texts(request)
