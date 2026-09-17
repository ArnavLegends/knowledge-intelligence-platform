"""Tests for the embedding subsystem."""

from unittest.mock import Mock, patch

import openai
import pytest

from app.core.config import Settings
from app.core.exceptions import AppException, EmbeddingProviderError
from app.services.chunking.models import Chunk
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingInput, EmbeddingRequest
from app.services.embeddings.providers.openai import OpenAIEmbeddingProvider
from app.services.embeddings.service import EmbeddingService


def test_embedding_input_valid():
    """Test valid EmbeddingInput."""
    inp = EmbeddingInput(source_id="c1", text="test text", metadata={"key": "val"})
    assert inp.source_id == "c1"
    assert inp.text == "test text"
    assert inp.metadata == {"key": "val"}


def test_embedding_input_rejects_empty():
    """Test EmbeddingInput rejects empty text."""
    with pytest.raises(ValueError):
        EmbeddingInput(source_id="c1", text="")


def test_embedding_request_valid():
    """Test valid EmbeddingRequest."""
    req = EmbeddingRequest(
        model="test-model", inputs=[EmbeddingInput(source_id="c1", text="text")]
    )
    assert req.model == "test-model"
    assert len(req.inputs) == 1


def test_embedding_valid():
    """Test valid Embedding."""
    emb = Embedding(
        source_id="c1",
        vector=[0.1, 0.2, 0.3],
        dimensions=3,
        metadata={"a": "b"},
    )
    assert emb.source_id == "c1"
    assert emb.vector == [0.1, 0.2, 0.3]
    assert emb.dimensions == 3


def test_embedding_rejects_empty_vector():
    """Test Embedding rejects empty vector."""
    with pytest.raises(ValueError):
        Embedding(source_id="c1", vector=[], dimensions=0)


def test_embedding_validates_dimensions():
    """Test Embedding dimensions match vector length."""
    with pytest.raises(ValueError):
        Embedding(source_id="c1", vector=[0.1, 0.2], dimensions=3)


def test_manager_selects_openai():
    """Test EmbeddingManager selects configured OpenAI provider."""
    settings = Settings(embedding_provider="openai", llm_api_key="fake")
    manager = EmbeddingManager(settings=settings)
    assert manager.provider_name == "openai"


def test_manager_rejects_unsupported():
    """Test EmbeddingManager rejects unsupported provider."""
    settings = Settings(embedding_provider="fake-provider")
    with pytest.raises(AppException) as exc:
        EmbeddingManager(settings=settings)
    assert exc.value.code == "unsupported_embedding_provider"


@patch("app.services.embeddings.providers.openai.OpenAI")
def test_openai_adapter_success(mock_openai_class):
    """Test OpenAI adapter translates request and response correctly."""
    mock_client = Mock()
    mock_openai_class.return_value = mock_client

    # Setup mock response
    mock_response = Mock()
    item1 = Mock()
    item1.index = 0
    item1.embedding = [0.1, 0.2]
    item2 = Mock()
    item2.index = 1
    item2.embedding = [0.3, 0.4]
    mock_response.data = [item2, item1]  # Intentional out of order
    mock_client.embeddings.create.return_value = mock_response

    provider = OpenAIEmbeddingProvider(api_key="fake", model="default-model")

    req = EmbeddingRequest(
        model="custom-model",
        inputs=[
            EmbeddingInput(source_id="c1", text="text1", metadata={"a": 1}),
            EmbeddingInput(source_id="c2", text="text2", metadata={"b": 2}),
        ],
    )

    embeddings = provider.embed(req)

    # Assert request formatting
    mock_client.embeddings.create.assert_called_once_with(
        input=["text1", "text2"], model="custom-model"
    )

    # Assert response formatting and ordering
    assert len(embeddings) == 2
    assert embeddings[0].source_id == "c1"
    assert embeddings[0].vector == [0.1, 0.2]
    assert embeddings[0].dimensions == 2
    assert embeddings[0].metadata == {"a": 1}
    assert embeddings[0].provider == "openai"
    assert embeddings[0].model == "custom-model"

    assert embeddings[1].source_id == "c2"
    assert embeddings[1].vector == [0.3, 0.4]


@patch("app.services.embeddings.providers.openai.OpenAI")
def test_openai_adapter_failure(mock_openai_class):
    """Test OpenAI adapter translates API errors."""
    mock_client = Mock()
    mock_openai_class.return_value = mock_client
    mock_client.embeddings.create.side_effect = openai.OpenAIError("API failed")

    provider = OpenAIEmbeddingProvider(api_key="fake")
    req = EmbeddingRequest(inputs=[EmbeddingInput(source_id="c1", text="text")])

    with pytest.raises(EmbeddingProviderError):
        provider.embed(req)


def test_embedding_service_flow():
    """Test EmbeddingService orchestrates correctly."""
    mock_manager = Mock()

    emb_result = Embedding(
        source_id="c1", vector=[1.0], dimensions=1, metadata={"m": "1"}
    )
    mock_manager.embed.return_value = [emb_result]

    service = EmbeddingService(manager=mock_manager)

    chunks = [
        Chunk(
            id="c1",
            document_id="d1",
            index=0,
            text="hello",
            character_count=5,
            metadata={"m": "1"},
        )
    ]

    embeddings = service.embed_chunks(chunks)

    assert len(embeddings) == 1
    assert embeddings[0].source_id == "c1"

    # Check that manager was called correctly
    mock_manager.embed.assert_called_once()
    called_request = mock_manager.embed.call_args[0][0]
    assert isinstance(called_request, EmbeddingRequest)
    assert called_request.inputs[0].source_id == "c1"
    assert called_request.inputs[0].text == "hello"


def test_embedding_service_empty():
    """Test EmbeddingService handles empty list."""
    service = EmbeddingService(manager=Mock())
    assert service.embed_chunks([]) == []
