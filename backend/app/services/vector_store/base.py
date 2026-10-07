"""Provider-agnostic vector store interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from app.services.vector_store.models import StoredVector, VectorSearchResult


class VectorStoreProvider(ABC):
    """Contract that every vector database adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier used for configuration."""

    @abstractmethod
    def upsert(
        self, records: Sequence[StoredVector], workspace_id: str = "default"
    ) -> None:
        """Store or update normalized vectors in the database for a workspace."""

    @abstractmethod
    def retrieve(
        self, ids: Sequence[str], workspace_id: str = "default"
    ) -> list[StoredVector]:
        """Retrieve stored vectors by their identifiers within a workspace."""

    @abstractmethod
    def delete(self, ids: Sequence[str], workspace_id: str = "default") -> None:
        """Delete stored vectors by their identifiers within a workspace."""

    @abstractmethod
    def count(self, workspace_id: str | None = None) -> int:
        """Return the number of vectors, optionally scoped to a workspace."""

    @abstractmethod
    def document_exists(self, document_id: str, workspace_id: str = "default") -> bool:
        """Check if any vectors exist for the given document_id in the workspace."""

    @abstractmethod
    def delete_document(self, document_id: str, workspace_id: str = "default") -> None:
        """Delete all stored vectors belonging to document_id within workspace_id."""

    @abstractmethod
    def list_documents(self, workspace_id: str = "default") -> list[dict[str, Any]]:
        """List documents and metadata belonging to workspace_id."""

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        top_k: int,
        workspace_id: str = "default",
        threshold: float | None = None,
    ) -> list[VectorSearchResult]:
        """Perform similarity search scoped strictly to workspace_id."""
