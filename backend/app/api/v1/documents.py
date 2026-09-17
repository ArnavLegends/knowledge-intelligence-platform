"""HTTP schemas and routes for document ingestion."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from app.services.documents.models import Document
from app.services.documents.service import (
    DocumentIngestionService,
    get_document_ingestion_service,
)

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

    @classmethod
    def from_internal(cls, document: Document) -> "DocumentResponse":
        return cls(
            id=document.id,
            filename=document.filename,
            media_type=document.media_type,
            text=document.text,
            metadata=document.metadata,
            source=document.source,
            ingested_at=document.ingested_at,
        )


@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
    service: Annotated[
        DocumentIngestionService, Depends(get_document_ingestion_service)
    ],
) -> DocumentResponse:
    """Ingest an uploaded file and return a normalized document."""
    content = await file.read()
    document = service.ingest(file.filename, content, file.content_type)
    return DocumentResponse.from_internal(document)
