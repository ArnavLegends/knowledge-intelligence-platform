"""Application-facing document indexing service."""

import logging

from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.service import ChunkingService
from app.services.documents.models import Document
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.models import IndexingResult
from app.services.vector_store.service import VectorStoreService

logger = logging.getLogger(__name__)


class DocumentIndexingService:
    """Orchestrates chunking, embedding, and storing of a Document."""

    def __init__(
        self,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
        vector_store_service: VectorStoreService,
    ) -> None:
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service
        self._vector_store_service = vector_store_service

    def index_document(self, document: Document) -> IndexingResult:
        """Process a Document through the indexing pipeline."""
        logger.info(
            "Indexing started: document_id=%s filename=%s",
            document.id,
            document.filename,
        )

        # 1. Chunking
        chunks = self._chunking_service.chunk_document(document)
        if not chunks:
            logger.warning("Indexing produced no chunks: document_id=%s", document.id)
            return IndexingResult(document_id=document.id, chunks_indexed=0)

        logger.debug(
            "Chunking complete: document_id=%s chunks=%d", document.id, len(chunks)
        )

        # 2. Embedding
        embeddings = self._embedding_service.embed_chunks(chunks)
        logger.debug(
            "Embedding complete: document_id=%s embeddings=%d",
            document.id,
            len(embeddings),
        )

        # 3. Vector Storage (upsert behavior preserves idempotency)
        self._vector_store_service.store_embeddings(embeddings)

        logger.info(
            "Indexing complete: document_id=%s chunks_indexed=%d",
            document.id,
            len(chunks),
        )
        return IndexingResult(
            document_id=document.id,
            chunks_indexed=len(chunks),
        )


def get_indexing_service() -> "DocumentIndexingService":
    """FastAPI dependency that constructs the document indexing service.

    Wires together ChunkingService, EmbeddingService, and VectorStoreService
    using application-level defaults from config.
    """
    from app.core.config import settings

    chunking_service = ChunkingService(
        chunker=FixedSizeChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    )
    embedding_service = EmbeddingService()
    vector_store_service = VectorStoreService()

    return DocumentIndexingService(
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        vector_store_service=vector_store_service,
    )
