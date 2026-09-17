"""Provider-agnostic vector store interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.services.vector_store.models import StoredVector


class VectorStoreProvider(ABC):
    """Contract that every vector database adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier used for configuration."""

    @abstractmethod
    def upsert(self, records: Sequence[StoredVector]) -> None:
        """Store or update normalized vectors in the database."""

    @abstractmethod
    def retrieve(self, ids: Sequence[str]) -> list[StoredVector]:
        """Retrieve stored vectors by their identifiers."""

    @abstractmethod
    def delete(self, ids: Sequence[str]) -> None:
        """Delete stored vectors by their identifiers."""

    @abstractmethod
    def count(self) -> int:
        """Return the total number of vectors in the collection."""
