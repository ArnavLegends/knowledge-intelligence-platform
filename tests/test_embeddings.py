"""Tests for the embedding subsystem."""

from unittest.mock import Mock, patch

import openai
import pytest
from google.genai.errors import APIError

from app.core.config import Settings
from app.core.exceptions import AppException, EmbeddingProviderError
from app.services.chunking.models import Chunk
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingInput, EmbeddingRequest
from app.services.embeddings.providers.gemini import GeminiEmbeddingProvider
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


def test_gemini_adapter_success():
    """Test Gemini adapter translates request and response correctly with Content objects."""
    mock_client = Mock()

    # Setup mock response
    mock_response = Mock()
    item1 = Mock()
    item1.values = [0.1, 0.2]
    item2 = Mock()
    item2.values = [0.3, 0.4]
    mock_response.embeddings = [item1, item2]
    mock_client.models.embed_content.return_value = mock_response

    provider = GeminiEmbeddingProvider(api_key="fake", client=mock_client)

    req = EmbeddingRequest(
        model="custom-model",
        inputs=[
            EmbeddingInput(source_id="c1", text="text1", metadata={"a": 1}),
            EmbeddingInput(source_id="c2", text="text2", metadata={"b": 2}),
        ],
    )

    embeddings = provider.embed(req)

    # Assert request formatting: each input is its own Content object with Part.from_text
    mock_client.models.embed_content.assert_called_once()
    call_kwargs = mock_client.models.embed_content.call_args[1]
    assert call_kwargs["model"] == "custom-model"
    contents = call_kwargs["contents"]
    assert len(contents) == 2
    assert contents[0].parts[0].text == "text1"
    assert contents[1].parts[0].text == "text2"

    # Assert response formatting and provenance
    assert len(embeddings) == 2
    assert embeddings[0].source_id == "c1"
    assert embeddings[0].vector == [0.1, 0.2]
    assert embeddings[0].dimensions == 2
    assert embeddings[0].metadata == {"a": 1}
    assert embeddings[0].provider == "gemini"
    assert embeddings[0].model == "custom-model"

    assert embeddings[1].source_id == "c2"
    assert embeddings[1].vector == [0.3, 0.4]
    assert embeddings[1].dimensions == 2
    assert embeddings[1].metadata == {"b": 2}


def test_gemini_adapter_single_input():
    """Test Gemini adapter handles a single input (e.g. query embedding)."""
    mock_client = Mock()
    mock_response = Mock()
    item = Mock()
    item.values = [0.11, 0.22, 0.33]
    mock_response.embeddings = [item]
    mock_client.models.embed_content.return_value = mock_response

    provider = GeminiEmbeddingProvider(api_key="fake", client=mock_client)

    req = EmbeddingRequest(
        inputs=[
            EmbeddingInput(source_id="query", text="what is knowledge?", metadata={"type": "query"}),
        ]
    )

    embeddings = provider.embed(req)

    call_kwargs = mock_client.models.embed_content.call_args[1]
    contents = call_kwargs["contents"]
    assert len(contents) == 1
    assert contents[0].parts[0].text == "what is knowledge?"

    assert len(embeddings) == 1
    assert embeddings[0].source_id == "query"
    assert embeddings[0].vector == [0.11, 0.22, 0.33]
    assert embeddings[0].dimensions == 3
    assert embeddings[0].metadata == {"type": "query"}


def test_gemini_adapter_multiple_inputs_ordering_and_provenance():
    """Test multiple inputs produce multiple embeddings with exact ordering and provenance."""
    mock_client = Mock()
    mock_response = Mock()
    item1 = Mock(values=[0.1, 0.2])
    item2 = Mock(values=[0.3, 0.4])
    item3 = Mock(values=[0.5, 0.6])
    mock_response.embeddings = [item1, item2, item3]
    mock_client.models.embed_content.return_value = mock_response

    provider = GeminiEmbeddingProvider(api_key="fake", client=mock_client)

    inputs = [
        EmbeddingInput(source_id="docA-c1", text="Chunk A1", metadata={"doc": "A", "chunk": 0}),
        EmbeddingInput(source_id="docA-c2", text="Chunk A2", metadata={"doc": "A", "chunk": 1}),
        EmbeddingInput(source_id="docB-c1", text="Chunk B1", metadata={"doc": "B", "chunk": 0}),
    ]
    req = EmbeddingRequest(inputs=inputs)

    embeddings = provider.embed(req)

    call_kwargs = mock_client.models.embed_content.call_args[1]
    contents = call_kwargs["contents"]
    assert len(contents) == 3
    for i, inp in enumerate(inputs):
        assert contents[i].parts[0].text == inp.text

    assert len(embeddings) == 3
    for i, emb in enumerate(embeddings):
        assert emb.source_id == inputs[i].source_id
        assert emb.metadata == inputs[i].metadata
        assert emb.provider == "gemini"
    assert embeddings[0].vector == [0.1, 0.2]
    assert embeddings[1].vector == [0.3, 0.4]
    assert embeddings[2].vector == [0.5, 0.6]


def test_gemini_adapter_dimension_validation():
    """Test output dimensionality validation on Gemini embeddings."""
    mock_client = Mock()
    mock_response = Mock()
    # Return vector of length 2 when 768 is configured
    item = Mock(values=[0.1, 0.2])
    mock_response.embeddings = [item]
    mock_client.models.embed_content.return_value = mock_response

    provider = GeminiEmbeddingProvider(
        api_key="fake",
        client=mock_client,
        output_dimensionality=768,
    )
    req = EmbeddingRequest(
        inputs=[EmbeddingInput(source_id="c1", text="hello")]
    )

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed(req)
    assert "dimension mismatch" in str(exc_info.value)
    assert "expected 768, got 2" in str(exc_info.value)


def test_gemini_adapter_count_mismatch():
    """Test that aggregated single embedding response for multi-input raises an error."""
    mock_client = Mock()
    mock_response = Mock()
    # Return only 1 embedding when 3 were requested (the bug behavior)
    mock_response.embeddings = [Mock(values=[0.1, 0.2])]
    mock_client.models.embed_content.return_value = mock_response

    provider = GeminiEmbeddingProvider(api_key="fake", client=mock_client)
    req = EmbeddingRequest(
        inputs=[
            EmbeddingInput(source_id="c1", text="text1"),
            EmbeddingInput(source_id="c2", text="text2"),
            EmbeddingInput(source_id="c3", text="text3"),
        ]
    )

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed(req)
    assert "Expected 3, got 1" in str(exc_info.value)


def test_gemini_adapter_empty_inputs():
    """Test empty inputs returns empty list without calling API."""
    mock_client = Mock()
    provider = GeminiEmbeddingProvider(api_key="fake", client=mock_client)
    req = Mock(inputs=[], model="gemini-embedding-2")
    assert provider.embed(req) == []
    mock_client.models.embed_content.assert_not_called()


def test_gemini_adapter_failure():
    """Test Gemini adapter translates API errors."""
    mock_client = Mock()
    mock_client.models.embed_content.side_effect = APIError(
        "API failed", 500, "INTERNAL"
    )

    provider = GeminiEmbeddingProvider(api_key="fake", client=mock_client)
    req = EmbeddingRequest(inputs=[EmbeddingInput(source_id="c1", text="text")])

    with pytest.raises(EmbeddingProviderError):
        provider.embed(req)

