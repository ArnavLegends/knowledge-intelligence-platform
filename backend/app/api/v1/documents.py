"""HTTP schemas and routes for document ingestion and indexing."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

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
    ) -> "DocumentResponse":
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


@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
    ingestion_service: Annotated[
        DocumentIngestionService, Depends(get_document_ingestion_service)
    ],
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "default",
) -> DocumentResponse:
    """Ingest an uploaded file, index it into workspace, and return metadata.

    Requires X-KIP-Workspace-ID header. Operations are scoped to workspace.
    """
    content = await file.read()

    # 1. Parse and normalize (generates deterministic document ID based on content)
    document = ingestion_service.ingest(file.filename, content, file.content_type)

    # 2. Check if already indexed in this specific workspace
    if indexing_service.document_exists(document.id, workspace_id):
        return DocumentResponse.from_internal(document, chunks_indexed=0)

    # 3. Chunk, embed, and store in vector store scoped to workspace
    indexing_result = indexing_service.index_document(document, workspace_id)

    return DocumentResponse.from_internal(
        document, chunks_indexed=indexing_result.chunks_indexed
    )


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
        )
        for d in docs
    ]
