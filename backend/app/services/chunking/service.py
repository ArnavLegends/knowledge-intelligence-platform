"""Application-facing chunking service."""

import hashlib

from app.services.chunking.chunkers.base import DocumentChunker
from app.services.chunking.models import Chunk
from app.services.documents.models import Document


class ChunkingService:
    """Chunks a normalized Document into ordered Chunk objects."""

    def __init__(self, chunker: DocumentChunker) -> None:
        self._chunker = chunker

    def chunk_document(self, document: Document) -> list[Chunk]:
        """Process a Document and return a list of Chunks."""
        text_segments = self._chunker.chunk(document.text)

        chunks = []
        for index, text in enumerate(text_segments):
            # Generate deterministic ID based on document ID and chunk index
            # This ensures re-indexing the same document produces the same chunk IDs
            chunk_hash_input = f"{document.id}:{index}".encode()
            deterministic_id = hashlib.sha256(chunk_hash_input).hexdigest()

            chunk = Chunk(
                id=deterministic_id,
                document_id=document.id,
                index=index,
                text=text,
                character_count=len(text),
                metadata=document.metadata.copy(),
            )
            chunks.append(chunk)

        return chunks
