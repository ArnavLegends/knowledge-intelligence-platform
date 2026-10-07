"""Application-facing document indexing service."""

import logging
from typing import Any

from fastapi import Depends

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import AppException
from app.core.workspace import get_workspace_id
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.service import ChunkingService
from app.services.documents.models import Document
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.models import IndexingResult
from app.services.vector_store.service import VectorStoreService

logger = logging.getLogger(__name__)


class DocumentIndexingService:
    """Orchestrates chunking, embedding, and storage of a Document in workspace."""

    def __init__(
        self,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
        vector_store_service: VectorStoreService,
        settings: Settings | None = None,
    ) -> None:
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service
        self._vector_store_service = vector_store_service
        self._settings = settings or default_settings

    def document_exists(self, document_id: str, workspace_id: str = "default") -> bool:
        """Return True if vectors for document_id exist in workspace_id."""
        if not workspace_id or not workspace_id.strip():
            raise AppException(
                "workspace_id is required.",
                code="missing_workspace_id",
                status_code=400,
            )
        return self._vector_store_service.document_exists(document_id, workspace_id)

    def list_documents(self, workspace_id: str = "default") -> list[dict[str, Any]]:
        """Return distinct documents and metadata belonging to workspace_id."""
        if not workspace_id or not workspace_id.strip():
            raise AppException(
                "workspace_id is required.",
                code="missing_workspace_id",
                status_code=400,
            )
        return self._vector_store_service.list_documents(workspace_id)

    def index_document(
        self, document: Document, workspace_id: str = "default"
    ) -> IndexingResult:
        """Process a Document through the workspace-scoped indexing pipeline."""
        if not workspace_id or not workspace_id.strip():
            raise AppException(
                "workspace_id is required for indexing.",
                code="missing_workspace_id",
                status_code=400,
            )

        logger.info(
            "Indexing started: workspace_id=%s document_id=%s filename=%s",
            workspace_id[:8] + "...",
            document.id,
            document.filename,
        )

        # Idempotency check: if already indexed in this workspace, return 0 chunks
        if self._vector_store_service.document_exists(document.id, workspace_id):
            logger.info(
                "Document %s already exists in workspace %s",
                document.id,
                workspace_id[:8] + "...",
            )
            return IndexingResult(document_id=document.id, chunks_indexed=0)

        # Enforce workspace document limit
        current_docs = self._vector_store_service.list_documents(workspace_id)
        if len(current_docs) >= self._settings.max_documents_per_workspace:
            raise AppException(
                f"Workspace document limit of "
                f"{self._settings.max_documents_per_workspace} exceeded.",
                code="workspace_document_limit_exceeded",
                status_code=429,
            )

        # 1. Chunking
        chunks = self._chunking_service.chunk_document(document)
        if not chunks:
            logger.warning("Indexing produced no chunks: document_id=%s", document.id)
            return IndexingResult(document_id=document.id, chunks_indexed=0)

        # Enforce workspace chunk limit
        current_chunks = self._vector_store_service.count(workspace_id)
        if (current_chunks + len(chunks)) > self._settings.max_chunks_per_workspace:
            raise AppException(
                f"Workspace chunk limit of "
                f"{self._settings.max_chunks_per_workspace} exceeded.",
                code="workspace_chunk_limit_exceeded",
                status_code=429,
            )

        logger.debug(
            "Chunking complete: document_id=%s chunks=%d", document.id, len(chunks)
        )

        for chunk in chunks:
            chunk.metadata["workspace_id"] = workspace_id

        # 2. Embedding
        embeddings = self._embedding_service.embed_chunks(chunks)
        for emb in embeddings:
            emb.metadata["workspace_id"] = workspace_id

        logger.debug(
            "Embedding complete: document_id=%s embeddings=%d",
            document.id,
            len(embeddings),
        )

        # 3. Vector Storage with partial failure cleanup
        try:
            self._vector_store_service.store_embeddings(
                embeddings, workspace_id=workspace_id
            )
        except Exception as e:
            logger.error(
                "Failed to store embeddings for document %s in workspace %s. "
                "Cleaning up partial records.",
                document.id,
                workspace_id[:8],
            )
            try:
                self._vector_store_service.delete_document(
                    document.id, workspace_id=workspace_id
                )
            except Exception as cleanup_err:
                logger.error(
                    "Cleanup failed for document %s in workspace %s: %s",
                    document.id,
                    workspace_id[:8],
                    cleanup_err,
                )
            raise e

        logger.info(
            "Indexing complete: document_id=%s chunks_indexed=%d",
            document.id,
            len(chunks),
        )
        return IndexingResult(
            document_id=document.id,
            chunks_indexed=len(chunks),
        )


def get_indexing_service(
    _workspace_id: str = Depends(get_workspace_id),
) -> "DocumentIndexingService":
    """FastAPI dependency that constructs the document indexing service.

    Depends on get_workspace_id so that workspace validation always runs
    before any external AI provider (embedding, vector store) is instantiated.
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
