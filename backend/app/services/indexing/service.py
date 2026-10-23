"""Application-facing document indexing and lifecycle orchestration service."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import AppException, NotFoundError
from app.core.workspace import get_workspace_id
from app.services.cache.search_cache import SearchCache, get_default_search_cache
from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
from app.services.chunking.service import ChunkingService
from app.services.documents.metadata_store import (
    DocumentMetadataStore,
    get_document_metadata_store,
)
from app.services.documents.models import Document
from app.services.documents.service import DocumentIngestionService
from app.services.documents.storage import LocalDocumentStorage, get_document_storage
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.models import IndexingResult
from app.services.vector_store.service import VectorStoreService

logger = logging.getLogger(__name__)


class DocumentIndexingService:
    """Orchestrates chunking, embedding, vector storage, and persistent lifecycle."""

    def __init__(
        self,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
        vector_store_service: VectorStoreService,
        settings: Settings | None = None,
        search_cache: SearchCache | None = None,
        metadata_store: DocumentMetadataStore | None = None,
        storage: LocalDocumentStorage | None = None,
    ) -> None:
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service
        self._vector_store_service = vector_store_service
        self._settings = settings or default_settings
        self._search_cache = (
            search_cache if search_cache is not None else get_default_search_cache()
        )
        self._metadata_store = metadata_store or get_document_metadata_store()
        self._storage = storage or get_document_storage()

    def document_exists(self, document_id: str, workspace_id: str = "default") -> bool:
        """Return True if vectors for document exist in workspace or metadata store."""
        if not workspace_id or not workspace_id.strip():
            raise AppException(
                "workspace_id is required.",
                code="missing_workspace_id",
                status_code=400,
            )
        # Check authoritative metadata store first
        doc = self._metadata_store.get_document(document_id, workspace_id)
        if doc and doc["status"] == "active":
            return True
        # Check vector store
        return self._vector_store_service.document_exists(document_id, workspace_id)

    def list_documents(self, workspace_id: str = "default") -> list[dict[str, Any]]:
        """Return distinct documents and metadata belonging to workspace_id."""
        if not workspace_id or not workspace_id.strip():
            raise AppException(
                "workspace_id is required.",
                code="missing_workspace_id",
                status_code=400,
            )

        stored = self._metadata_store.list_documents(workspace_id, status="active")
        if stored:
            return stored

        # Fallback to vector store for legacy documents prior to metadata store
        return self._vector_store_service.list_documents(workspace_id)

    def list_document_versions(
        self, document_id: str, workspace_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Return version history for a specific document."""
        return self._metadata_store.list_versions(document_id, workspace_id)

    def delete_document(self, document_id: str, workspace_id: str = "default") -> bool:
        """Delete vectors and persistent files for document strictly in workspace."""
        if not workspace_id or not workspace_id.strip():
            raise AppException(
                "workspace_id is required.",
                code="missing_workspace_id",
                status_code=400,
            )
        if not document_id or not document_id.strip():
            raise AppException(
                "document_id is required.",
                code="missing_document_id",
                status_code=400,
            )

        exists_in_meta = (
            self._metadata_store.get_document(document_id, workspace_id) is not None
        )
        exists_in_vs = self._vector_store_service.document_exists(
            document_id, workspace_id
        )

        if not exists_in_meta and not exists_in_vs:
            return False

        # 1. Transition state to 'deleting' in metadata store to block new queries
        self._metadata_store.set_status(document_id, workspace_id, "deleting")

        # 2. Evict vectors from vector store
        if exists_in_vs:
            self._vector_store_service.delete_document(
                document_id, workspace_id=workspace_id
            )

        # 3. Prune retained raw files if present
        meta = self._metadata_store.get_document(document_id, workspace_id)
        if meta and meta.get("filename"):
            self._storage.delete_file(workspace_id, document_id, meta["filename"])

        # 4. Finalize state in metadata store
        self._metadata_store.delete_document(document_id, workspace_id)

        # 5. Invalidate search cache
        if self._search_cache is not None:
            self._search_cache.invalidate_workspace(workspace_id)

        return True

    def index_document(
        self,
        document: Document,
        workspace_id: str = "default",
        raw_content: bytes | None = None,
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
            # Ensure metadata store record exists
            if not self._metadata_store.get_document(document.id, workspace_id):
                file_rel_path = None
                if raw_content:
                    file_rel_path = self._storage.save_file(
                        workspace_id, document.id, document.filename, raw_content
                    )
                self._metadata_store.record_document(
                    document_id=document.id,
                    workspace_id=workspace_id,
                    filename=document.filename,
                    content_hash=document.id,
                    media_type=document.media_type,
                    size_bytes=len(raw_content) if raw_content else 0,
                    chunks_indexed=0,
                    file_path=file_rel_path,
                )
            return IndexingResult(document_id=document.id, chunks_indexed=0)

        # Enforce workspace document limit
        current_docs = self.list_documents(workspace_id)
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
            "Chunking complete: document_id=%s chunks=%d",
            document.id,
            len(chunks),
        )

        indexed_at_iso = document.ingested_at.isoformat()
        for chunk in chunks:
            chunk.metadata["workspace_id"] = workspace_id
            chunk.metadata["indexed_at"] = indexed_at_iso
            chunk.metadata["chunk_index"] = chunk.index
            chunk.metadata["media_type"] = document.media_type

        # 2. Embedding
        embeddings = self._embedding_service.embed_chunks(chunks)
        for emb in embeddings:
            emb.metadata["workspace_id"] = workspace_id

        # 3. Vector Storage with partial failure cleanup
        try:
            self._vector_store_service.store_embeddings(
                embeddings, workspace_id=workspace_id
            )
        except Exception as e:
            logger.error(
                "Failed to store embeddings for document %s in workspace %s.",
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

        # 4. Persistent raw file and metadata storage
        file_rel_path = None
        if raw_content:
            try:
                file_rel_path = self._storage.save_file(
                    workspace_id, document.id, document.filename, raw_content
                )
            except Exception as err:
                logger.error("Failed to persist source document to disk: %s", err)

        self._metadata_store.record_document(
            document_id=document.id,
            workspace_id=workspace_id,
            filename=document.filename,
            content_hash=document.id,
            media_type=document.media_type,
            size_bytes=len(raw_content) if raw_content else 0,
            chunks_indexed=len(chunks),
            file_path=file_rel_path,
            status="active",
        )

        # Invalidate search cache for this workspace on successful index mutation
        if self._search_cache is not None:
            self._search_cache.invalidate_workspace(workspace_id)

        logger.info(
            "Indexing complete: document_id=%s chunks_indexed=%d",
            document.id,
            len(chunks),
        )
        return IndexingResult(
            document_id=document.id,
            chunks_indexed=len(chunks),
        )

    def replace_document(
        self,
        document_id: str,
        new_document: Document,
        raw_content: bytes,
        workspace_id: str = "default",
    ) -> IndexingResult:
        """Replace an existing document with a new version, purging obsolete vectors."""
        if not self.document_exists(document_id, workspace_id):
            raise NotFoundError(
                f"Document '{document_id}' not found in workspace '{workspace_id}'."
            )

        # 1. Chunk and embed new document
        chunks = self._chunking_service.chunk_document(new_document)
        if not chunks:
            raise AppException(
                "Replacement document produced no indexable chunks.",
                code="empty_document",
                status_code=400,
            )

        indexed_at_iso = new_document.ingested_at.isoformat()
        for chunk in chunks:
            chunk.metadata["workspace_id"] = workspace_id
            chunk.metadata["document_id"] = document_id  # Maintain stable ID
            chunk.metadata["indexed_at"] = indexed_at_iso
            chunk.metadata["chunk_index"] = chunk.index
            chunk.metadata["media_type"] = new_document.media_type

        embeddings = self._embedding_service.embed_chunks(chunks)
        for emb in embeddings:
            emb.metadata["workspace_id"] = workspace_id
            emb.metadata["document_id"] = document_id

        # 2. Atomic replacement in vector store: delete old vectors, insert new
        self._vector_store_service.delete_document(
            document_id, workspace_id=workspace_id
        )
        self._vector_store_service.store_embeddings(
            embeddings, workspace_id=workspace_id
        )

        # 3. Persist new raw file to storage
        file_rel_path = self._storage.save_file(
            workspace_id, document_id, new_document.filename, raw_content
        )

        # 4. Create new version in metadata store
        self._metadata_store.create_replacement_version(
            document_id=document_id,
            workspace_id=workspace_id,
            filename=new_document.filename,
            content_hash=new_document.id,
            media_type=new_document.media_type,
            size_bytes=len(raw_content),
            chunks_indexed=len(chunks),
            file_path=file_rel_path,
        )

        # 5. Invalidate search cache
        if self._search_cache is not None:
            self._search_cache.invalidate_workspace(workspace_id)

        return IndexingResult(document_id=document_id, chunks_indexed=len(chunks))

    def reindex_document(
        self, document_id: str, workspace_id: str = "default"
    ) -> IndexingResult:
        """Reindex an existing document from its retained raw source file on disk."""
        meta = self._metadata_store.get_document(document_id, workspace_id)
        if not meta or not meta.get("filename"):
            raise NotFoundError(
                f"Document '{document_id}' not found in workspace '{workspace_id}'."
            )

        filename = meta["filename"]
        if not self._storage.file_exists(workspace_id, document_id, filename):
            raise AppException(
                f"Raw source file for document '{document_id}' is unavailable on disk. "
                "This document was ingested under legacy storage and requires "
                "re-uploading.",
                code="source_file_unavailable",
                status_code=400,
            )

        raw_bytes = self._storage.read_file(workspace_id, document_id, filename)
        ingestion_service = DocumentIngestionService()
        doc = ingestion_service.ingest(filename, raw_bytes, meta.get("media_type"))

        # Re-chunk and re-embed
        chunks = self._chunking_service.chunk_document(doc)
        if not chunks:
            raise AppException(
                "Reindexing produced no chunks from source document.",
                code="reindex_failed_empty",
                status_code=500,
            )

        indexed_at_iso = doc.ingested_at.isoformat()
        for chunk in chunks:
            chunk.metadata["workspace_id"] = workspace_id
            chunk.metadata["document_id"] = document_id
            chunk.metadata["indexed_at"] = indexed_at_iso
            chunk.metadata["chunk_index"] = chunk.index

        embeddings = self._embedding_service.embed_chunks(chunks)
        for emb in embeddings:
            emb.metadata["workspace_id"] = workspace_id
            emb.metadata["document_id"] = document_id

        # Replace vectors
        self._vector_store_service.delete_document(
            document_id, workspace_id=workspace_id
        )
        self._vector_store_service.store_embeddings(
            embeddings, workspace_id=workspace_id
        )

        # Update metadata store chunk count
        self._metadata_store.record_document(
            document_id=document_id,
            workspace_id=workspace_id,
            filename=filename,
            content_hash=doc.id,
            media_type=meta.get("media_type", "application/octet-stream"),
            size_bytes=len(raw_bytes),
            chunks_indexed=len(chunks),
            file_path=meta.get("file_path"),
            status="active",
        )

        if self._search_cache is not None:
            self._search_cache.invalidate_workspace(workspace_id)

        return IndexingResult(document_id=document_id, chunks_indexed=len(chunks))

    def reindex_workspace(self, workspace_id: str = "default") -> dict[str, Any]:
        """Reindex all active documents with retained source files in a workspace."""
        active_docs = self._metadata_store.list_documents(workspace_id, status="active")
        total = len(active_docs)
        reindexed = 0
        skipped_legacy = 0
        failed = 0

        for doc in active_docs:
            doc_id = doc["document_id"]
            try:
                self.reindex_document(doc_id, workspace_id)
                reindexed += 1
            except AppException as exc:
                if exc.code == "source_file_unavailable":
                    skipped_legacy += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return {
            "workspace_id": workspace_id,
            "total_documents": total,
            "reindexed": reindexed,
            "skipped_legacy": skipped_legacy,
            "failed": failed,
        }


def get_indexing_service(
    _workspace_id: str = Depends(get_workspace_id),
) -> DocumentIndexingService:
    """FastAPI dependency that constructs the document indexing service."""
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
        search_cache=get_default_search_cache(),
        metadata_store=get_document_metadata_store(),
        storage=get_document_storage(),
    )
