"""HTTP schemas and routes for document ingestion and indexing."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

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


@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
    ingestion_service: Annotated[
        DocumentIngestionService, Depends(get_document_ingestion_service)
    ],
    indexing_service: Annotated[DocumentIndexingService, Depends(get_indexing_service)],
) -> DocumentResponse:
    """Ingest an uploaded file, index it into the knowledge base, and return metadata.

    The document is both ingested (parsed/normalized) and indexed (chunked,
    embedded, stored in the vector store) within the same request. A successful
    response means the content is immediately queryable via the RAG endpoint.
    """
    content = await file.read()

    # 1. Parse and normalize (generates deterministic document ID based on content)
    document = ingestion_service.ingest(file.filename, content, file.content_type)

    # 2. Check if already indexed (via the same vector store the indexing service uses)
    if indexing_service.document_exists(document.id):
        return DocumentResponse.from_internal(document, chunks_indexed=0)

    # 3. Chunk, embed, and store in vector store
    indexing_result = indexing_service.index_document(document)

    return DocumentResponse.from_internal(
        document, chunks_indexed=indexing_result.chunks_indexed
    )
