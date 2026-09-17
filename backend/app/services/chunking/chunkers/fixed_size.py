"""Deterministic fixed-size character chunking."""

from app.core.exceptions import ChunkingError
from app.services.chunking.chunkers.base import DocumentChunker


class FixedSizeChunker(DocumentChunker):
    """Chunks text into fixed size segments with a specified overlap."""

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        if chunk_size <= 0:
            raise ChunkingError("chunk_size must be strictly greater than 0")
        if chunk_overlap < 0:
            raise ChunkingError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ChunkingError("chunk_overlap must be strictly less than chunk_size")

        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._step = chunk_size - chunk_overlap

    def chunk(self, text: str) -> list[str]:
        """Convert a source string into ordered chunk strings."""
        if not text:
            return []

        if len(text) <= self._chunk_size:
            return [text]

        chunks = []
        # The loop condition ensures we get all text.
        # i goes from 0 up to len(text), stepping by self._step
        # We ensure we don't return tiny chunks at the very end if they
        # duplicate text excessively.
        for i in range(0, len(text), self._step):
            chunk_text = text[i : i + self._chunk_size]
            chunks.append(chunk_text)
            # If the current chunk reaches the end of the text,
            # break to prevent redundant smaller chunks
            if i + self._chunk_size >= len(text):
                break

        return chunks
