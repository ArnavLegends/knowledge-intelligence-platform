"""Application LLM service tests. Provider HTTP calls are mocked."""

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import LLMProviderError
from app.services.llm.base import LLMProvider
from app.services.llm.manager import LLMManager
from app.services.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMUsage
from app.services.llm.service import LLMService


class FakeProvider(LLMProvider):
    def __init__(self, name: str = "fake") -> None:
        self._name = name
        self.calls: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return self._name

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            content="generated",
            model=request.model or "fake-model",
            provider=self._name,
            usage=LLMUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
            finish_reason="stop",
        )


class FailingProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "failing"

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderError("Language model provider request failed.")


def test_service_calls_manager_and_returns_normalized_response() -> None:
    provider = FakeProvider()
    service = LLMService(manager=LLMManager(provider=provider))
    request = LLMRequest(messages=[LLMMessage(role="user", content="hello")])

    response = service.generate(request)

    assert len(provider.calls) == 1
    assert provider.calls[0] is request
    assert isinstance(response, LLMResponse)
    assert response.content == "generated"
    assert response.model == "fake-model"
    assert response.provider == "fake"
    assert response.usage is not None
    assert response.usage.total_tokens == 5
    assert response.finish_reason == "stop"
    assert "openai" not in type(response).__module__


def test_service_propagates_provider_failures() -> None:
    service = LLMService(manager=LLMManager(provider=FailingProvider()))
    request = LLMRequest(messages=[LLMMessage(role="user", content="hello")])

    with pytest.raises(LLMProviderError) as exc_info:
        service.generate(request)

    assert exc_info.value.code == "llm_provider_error"
    assert exc_info.value.status_code == 503


def test_service_does_not_import_openai_types() -> None:
    manager = MagicMock()
    manager.generate.return_value = LLMResponse(
        content="ok",
        model="test-model",
        provider="fake",
    )
    service = LLMService(manager=manager)

    response = service.generate(
        LLMRequest(messages=[LLMMessage(role="user", content="hello")])
    )

    manager.generate.assert_called_once()
    assert type(response).__module__ == "app.services.llm.models"
