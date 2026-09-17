"""Tests for the indexing subsystem."""

from datetime import UTC
from unittest.mock import create_autospec

from app.services.chunking.models import Chunk
from app.services.chunking.service import ChunkingService
from app.services.documents.models import Document
from app.services.embeddings.models import Embedding
from app.services.embeddings.service import EmbeddingService
from app.services.indexing.service import DocumentIndexingService
from app.services.vector_store.service import VectorStoreService


def test_indexing_service_flow():
    """Test the complete document indexing orchestration."""
    mock_chunking = create_autospec(ChunkingService)
    mock_embedding = create_autospec(EmbeddingService)
    mock_vs = create_autospec(VectorStoreService)

    # Setup mocks
    mock_chunk = Chunk(
        id="c1", document_id="d1", index=0, text="text1", character_count=5
    )
    mock_chunking.chunk_document.return_value = [mock_chunk]

    mock_emb = Embedding(source_id="c1", vector=[0.1], dimensions=1)
    mock_embedding.embed_chunks.return_value = [mock_emb]

    service = DocumentIndexingService(
        chunking_service=mock_chunking,
        embedding_service=mock_embedding,
        vector_store_service=mock_vs,
    )

    from datetime import datetime

    doc = Document(
        id="d1",
        filename="test.txt",
        media_type="text/plain",
        text="text1",
        source="test",
        ingested_at=datetime.now(UTC),
    )
    result = service.index_document(doc)

    assert result.document_id == "d1"
    assert result.chunks_indexed == 1

    mock_chunking.chunk_document.assert_called_once_with(doc)
    mock_embedding.embed_chunks.assert_called_once_with([mock_chunk])
    mock_vs.store_embeddings.assert_called_once_with([mock_emb])


def test_indexing_service_empty_document():
    """Test indexing service handles empty chunking results."""
    mock_chunking = create_autospec(ChunkingService)
    mock_embedding = create_autospec(EmbeddingService)
    mock_vs = create_autospec(VectorStoreService)

    mock_chunking.chunk_document.return_value = []

    service = DocumentIndexingService(
        chunking_service=mock_chunking,
        embedding_service=mock_embedding,
        vector_store_service=mock_vs,
    )

    from datetime import datetime

    doc = Document(
        id="d1",
        filename="test.txt",
        media_type="text/plain",
        text="",
        source="test",
        ingested_at=datetime.now(UTC),
    )
    result = service.index_document(doc)

    assert result.chunks_indexed == 0
    mock_embedding.embed_chunks.assert_not_called()
    mock_vs.store_embeddings.assert_not_called()
