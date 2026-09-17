"""Application-facing vector store service."""

from collections.abc import Sequence

from app.services.embeddings.models import Embedding
from app.services.vector_store.manager import VectorStoreManager
from app.services.vector_store.models import StoredVector


class VectorStoreService:
    """Provides high-level vector storage operations."""

    def __init__(self, manager: VectorStoreManager | None = None) -> None:
        self._manager = manager or VectorStoreManager()

    def store_embeddings(self, embeddings: Sequence[Embedding]) -> None:
        """Convert Embeddings to StoredVectors and upsert them to the store."""
        if not embeddings:
            return

        records = []
        for emb in embeddings:
            records.append(
                StoredVector(
                    id=emb.source_id,  # Preserve source chunk ID as record ID
                    vector=emb.vector,
                    metadata=emb.metadata.copy(),
                )
            )

        self._manager.provider.upsert(records)

    def retrieve(self, ids: Sequence[str]) -> list[StoredVector]:
        """Retrieve stored vectors by their identifiers."""
        return self._manager.provider.retrieve(ids)

    def delete(self, ids: Sequence[str]) -> None:
        """Delete stored vectors by their identifiers."""
        self._manager.provider.delete(ids)

    def count(self) -> int:
        """Return the total number of vectors in the collection."""
        return self._manager.provider.count()
