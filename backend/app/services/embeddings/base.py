"""Provider-agnostic embedding interface."""

from abc import ABC, abstractmethod

from app.services.embeddings.models import Embedding, EmbeddingRequest


class EmbeddingProvider(ABC):
    """Contract that every embedding model adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier used for configuration and responses."""

    @abstractmethod
    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        """Convert a batch of inputs into normalized embeddings."""
