"""Document ingestion services."""

from app.services.documents.models import Document
from app.services.documents.service import DocumentIngestionService

__all__ = ["Document", "DocumentIngestionService"]
