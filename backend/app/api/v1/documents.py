"""HTTP schemas and routes for document ingestion, persistence, lifecycle,
and indexing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from app.core.exceptions import NotFoundError
from app.core.workspace import get_workspace_id
from app.services.documents.models import Document
from app.services.documents.service import (
    DocumentIngestionService,
    get_document_ingestion_service,
)
from app.services.indexing.service import DocumentIndexingService, get_indexing_service

router = APIRouter(tags=["documents"])


class DocumentResponse(BaseModel):
    """Application response body for POST /api/v1/documents."""

    id: str
    filename: str
    media_type: str
    text: str
    metadata: dict[str, Any]
    source: str
    ingested_at: datetime
    chunks_indexed: int = 0

    @classmethod
    def from_internal(
        cls, document: Document, chunks_indexed: int = 0
    ) -> DocumentResponse:
        return cls(
            id=document.id,
            filename=document.filename,
            media_type=document.media_type,
            text=document.text,
            metadata=document.metadata,
            source=document.source,
            ingested_at=document.ingested_at,
            chunks_indexed=chunks_indexed,
        )


class WorkspaceDocumentItem(BaseModel):
    """Metadata for a document indexed within a workspace."""

    document_id: str
    filename: str
    chunks_indexed: int
    media_type: str = "application/octet-stream"
    size_bytes: int = 0
    parser: str = ""
    status: str = "indexed"
    indexed_at: str | None = None


class DocumentVersionItem(BaseModel):
    """Metadata for a historical version of an indexed document."""

    version_id: str
    document_id: str
    workspace_id: str
    version_number: int
    content_hash: str
    filename: str
    media_type: str
    size_bytes: int
    chunks_indexed: int
    status: str
    created_at: str


class DocumentDeleteResponse(BaseModel):
    """Response body for DELETE /api/v1/documents/{document_id}."""

    document_id: str
    deleted: bool
    workspace_id: str
    message: str


class WorkspaceReindexResponse(BaseModel):
    """Response summary returned upon workspace-wide reindexing."""

    workspace_id: str
    total_documents: int
    reindexed: int
    skipped_legacy: int
    failed: int


@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
    ingestion_service: Annotated[
        DocumentIngestionService, Depends(get_document_ingestion_service)
    ],
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "default",
) -> DocumentResponse:
    """Ingest uploaded file, persist bytes, index into workspace, return metadata."""
    content = await file.read()

    # 1. Parse and normalize
    document = ingestion_service.ingest(file.filename, content, file.content_type)

    # 2. Check if already indexed in this specific workspace
    if indexing_service.document_exists(document.id, workspace_id):
        # Still record in metadata store and persist file if needed
        indexing_result = indexing_service.index_document(
            document, workspace_id, raw_content=content
        )
        return DocumentResponse.from_internal(
            document, chunks_indexed=indexing_result.chunks_indexed
        )

    # 3. Chunk, embed, store vectors, persist raw source, and update metadata store
    indexing_result = indexing_service.index_document(
        document, workspace_id, raw_content=content
    )

    return DocumentResponse.from_internal(
        document, chunks_indexed=indexing_result.chunks_indexed
    )


@router.post("/documents/{document_id}/replace", response_model=DocumentResponse)
async def replace_document(
    document_id: str,
    file: Annotated[UploadFile, File()],
    ingestion_service: Annotated[
        DocumentIngestionService, Depends(get_document_ingestion_service)
    ],
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "default",
) -> DocumentResponse:
    """Replace an existing document with an updated version.

    Purges old vectors, updates the local source file, increments the active version,
    and invalidates the workspace search cache.
    """
    content = await file.read()
    new_doc = ingestion_service.ingest(file.filename, content, file.content_type)
    res = indexing_service.replace_document(
        document_id=document_id,
        new_document=new_doc,
        raw_content=content,
        workspace_id=workspace_id,
    )
    return DocumentResponse.from_internal(new_doc, chunks_indexed=res.chunks_indexed)


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[DocumentVersionItem],
)
async def list_document_versions(
    document_id: str,
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "default",
) -> list[DocumentVersionItem]:
    """Retrieve full version history for a document."""
    versions = indexing_service.list_document_versions(document_id, workspace_id)
    return [
        DocumentVersionItem(
            version_id=v["version_id"],
            document_id=v["document_id"],
            workspace_id=v["workspace_id"],
            version_number=v["version_number"],
            content_hash=v["content_hash"],
            filename=v["filename"],
            media_type=v["media_type"],
            size_bytes=v["size_bytes"],
            chunks_indexed=v["chunks_indexed"],
            status=v["status"],
            created_at=v["created_at"],
        )
        for v in versions
    ]


@router.post("/documents/{document_id}/reindex", response_model=DocumentResponse)
async def reindex_document(
    document_id: str,
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "default",
) -> DocumentResponse:
    """Reindex an existing document from its retained raw source file on disk."""
    res = indexing_service.reindex_document(document_id, workspace_id)
    docs = indexing_service.list_documents(workspace_id)
    doc_meta = next((d for d in docs if d["document_id"] == document_id), None)
    return DocumentResponse(
        id=document_id,
        filename=doc_meta["filename"] if doc_meta else "reindexed",
        media_type=doc_meta.get("media_type", "application/octet-stream")
        if doc_meta
        else "application/octet-stream",
        text="",
        metadata={},
        source="reindexed",
        ingested_at=datetime.utcnow(),
        chunks_indexed=res.chunks_indexed,
    )


@router.post(
    "/workspaces/{workspace_id}/reindex",
    response_model=WorkspaceReindexResponse,
)
async def reindex_workspace(
    workspace_id: str,
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
) -> WorkspaceReindexResponse:
    """Reindex all active documents with retained source files in workspace."""
    summary = indexing_service.reindex_workspace(workspace_id)
    return WorkspaceReindexResponse(**summary)


@router.get("/documents", response_model=list[WorkspaceDocumentItem])
async def list_workspace_documents(
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "default",
) -> list[WorkspaceDocumentItem]:
    """List documents and metadata belonging strictly to the requested workspace."""
    docs = indexing_service.list_documents(workspace_id)
    return [
        WorkspaceDocumentItem(
            document_id=d.get("document_id", d.get("id", "")),
            filename=d.get("filename", "unknown"),
            chunks_indexed=d.get("chunks_indexed", 0),
            media_type=d.get("media_type", "application/octet-stream"),
            size_bytes=d.get("size_bytes", 0),
            parser=d.get("parser", ""),
            status=d.get("status", "indexed"),
            indexed_at=(
                d.get("indexed_at") or d.get("updated_at") or d.get("created_at")
            ),
        )
        for d in docs
    ]


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "default",
) -> DocumentDeleteResponse:
    """Delete document, its raw retained file, and vectors within workspace."""
    if not indexing_service.document_exists(document_id, workspace_id):
        raise NotFoundError(f"Document '{document_id}' not found in workspace.")

    deleted = indexing_service.delete_document(document_id, workspace_id)
    if not deleted:
        raise NotFoundError(f"Document '{document_id}' not found in workspace.")

    return DocumentDeleteResponse(
        document_id=document_id,
        deleted=True,
        workspace_id=workspace_id,
        message=f"Document '{document_id}' deleted successfully from workspace.",
    )
