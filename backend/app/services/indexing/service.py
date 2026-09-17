"""Application-facing document indexing service."""

from app.services.chunking.service import ChunkingService
from app.services.documents.models import Document
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.models import IndexingResult
from app.services.vector_store.service import VectorStoreService


class DocumentIndexingService:
    """Orchestrates chunking, embedding, and storing of a Document."""

    def __init__(
        self,
        chunking_service: ChunkingService | None = None,
        embedding_service: EmbeddingService | None = None,
        vector_store_service: VectorStoreService | None = None,
    ) -> None:
        self._chunking_service = chunking_service or ChunkingService()
        self._embedding_service = embedding_service or EmbeddingService()
        self._vector_store_service = vector_store_service or VectorStoreService()

    def index_document(self, document: Document) -> IndexingResult:
        """Process a Document through the indexing pipeline."""

        # 1. Chunking
        chunks = self._chunking_service.chunk_document(document)
        if not chunks:
            return IndexingResult(document_id=document.id, chunks_indexed=0)

        # 2. Embedding
        embeddings = self._embedding_service.embed_chunks(chunks)

        # 3. Vector Storage
        self._vector_store_service.store_embeddings(embeddings)

        return IndexingResult(
            document_id=document.id,
            chunks_indexed=len(chunks),
        )
