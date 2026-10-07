"""Application-facing vector store service."""

from collections.abc import Sequence
from typing import Any

from app.services.embeddings.models import Embedding
from app.services.vector_store.manager import VectorStoreManager
from app.services.vector_store.models import StoredVector, VectorSearchResult


class VectorStoreService:
    """Provides high-level vector storage operations scoped to workspaces."""

    def __init__(self, manager: VectorStoreManager | None = None) -> None:
        self._manager = manager or VectorStoreManager()

    def store_embeddings(
        self, embeddings: Sequence[Embedding], workspace_id: str = "default"
    ) -> None:
        """Convert Embeddings to StoredVectors and upsert them for workspace."""
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

        self._manager.provider.upsert(records, workspace_id=workspace_id)

    def retrieve(
        self, ids: Sequence[str], workspace_id: str = "default"
    ) -> list[StoredVector]:
        """Retrieve stored vectors by their identifiers within a workspace."""
        return self._manager.provider.retrieve(ids, workspace_id=workspace_id)

    def delete(self, ids: Sequence[str], workspace_id: str = "default") -> None:
        """Delete stored vectors by their identifiers within a workspace."""
        self._manager.provider.delete(ids, workspace_id=workspace_id)

    def count(self, workspace_id: str | None = None) -> int:
        """Return vector count in collection, optionally scoped to workspace."""
        return self._manager.provider.count(workspace_id=workspace_id)

    def document_exists(self, document_id: str, workspace_id: str = "default") -> bool:
        """Check if any vectors exist for the given document_id in the workspace."""
        return self._manager.provider.document_exists(
            document_id=document_id, workspace_id=workspace_id
        )

    def delete_document(self, document_id: str, workspace_id: str = "default") -> None:
        """Delete all vectors belonging to document_id within workspace_id."""
        self._manager.provider.delete_document(
            document_id=document_id, workspace_id=workspace_id
        )

    def list_documents(self, workspace_id: str = "default") -> list[dict[str, Any]]:
        """List documents and metadata belonging to workspace_id."""
        return self._manager.provider.list_documents(workspace_id=workspace_id)

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        workspace_id: str = "default",
        threshold: float | None = None,
    ) -> list[VectorSearchResult]:
        """Perform a similarity search scoped to workspace_id."""
        return self._manager.provider.search(
            query_vector=query_vector,
            top_k=top_k,
            workspace_id=workspace_id,
            threshold=threshold,
        )
