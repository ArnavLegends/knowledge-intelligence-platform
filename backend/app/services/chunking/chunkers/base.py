"""Abstract chunker interface."""

import abc


class DocumentChunker(abc.ABC):
    """Base interface for all chunking strategies."""

    @abc.abstractmethod
    def chunk(self, text: str) -> list[str]:
        """Convert a source string into ordered chunk strings."""
        pass
