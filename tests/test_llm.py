"""LLM gateway unit tests. Provider HTTP calls are mocked."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppException, LLMProviderError
from app.services.llm.base import LLMProvider
from app.services.llm.manager import LLMManager
from app.services.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMUsage
from app.services.llm.providers.openai import OpenAIProvider


class FakeProvider(LLMProvider):
    def __init__(self, name: str = "fake") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=request.messages[-1].content,
            model="fake-model",
            provider=self._name,
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )


def _request() -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role="user", content="hello")])


def test_settings_load_llm_provider_and_model(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-real")

    settings = Settings()

    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-4o"
    assert settings.llm_api_key == "sk-test-not-real"


def test_manager_selects_configured_openai_provider() -> None:
    settings = Settings(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_api_key="sk-test",
    )
    manager = LLMManager(settings=settings)

    assert manager.provider_name == "openai"


def test_manager_rejects_unsupported_provider() -> None:
    settings = Settings(llm_provider="anthropic", llm_api_key="sk-test")

    with pytest.raises(AppException) as exc_info:
        LLMManager(settings=settings)

    assert exc_info.value.code == "unsupported_llm_provider"
    assert exc_info.value.status_code == 500


def test_normalized_request_response_contract() -> None:
    manager = LLMManager(
        settings=Settings(llm_provider="openai", llm_api_key="unused"),
        provider=FakeProvider(),
    )

    response = manager.generate(_request())

    assert isinstance(response, LLMResponse)
    assert response.content == "hello"
    assert response.provider == "fake"
    assert response.model == "fake-model"
    assert response.usage is not None
    assert response.usage.total_tokens == 3
    assert not hasattr(response, "choices")


def test_message_roles_are_system_user_assistant() -> None:
    system = LLMMessage(role="system", content="You are helpful.")
    user = LLMMessage(role="user", content="Hello")
    assistant = LLMMessage(role="assistant", content="Hi")

    assert system.role == "system"
    assert user.role == "user"
    assert assistant.role == "assistant"


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role="tool", content="not allowed")  # type: ignore[arg-type]


def test_message_rejects_blank_content() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role="user", content="   ")


def test_message_order_is_preserved() -> None:
    request = LLMRequest(
        messages=[
            LLMMessage(role="system", content="Be brief."),
            LLMMessage(role="user", content="First"),
            LLMMessage(role="assistant", content="Second"),
            LLMMessage(role="user", content="Third"),
        ]
    )

    assert [message.role for message in request.messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert [message.content for message in request.messages] == [
        "Be brief.",
        "First",
        "Second",
        "Third",
    ]


def test_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(messages=[])


def test_request_validates_generation_parameters() -> None:
    request = LLMRequest(
        messages=[LLMMessage(role="user", content="hello")],
        model="gpt-4o-mini",
        temperature=0.2,
        max_output_tokens=128,
    )
    assert request.temperature == 0.2
    assert request.max_output_tokens == 128

    with pytest.raises(ValidationError):
        LLMRequest(
            messages=[LLMMessage(role="user", content="hello")],
            temperature=3.0,
        )
    with pytest.raises(ValidationError):
        LLMRequest(
            messages=[LLMMessage(role="user", content="hello")],
            max_output_tokens=0,
        )


def test_openai_adapter_translates_internal_request() -> None:
    provider = OpenAIProvider(
        api_key="sk-test",
        model="gpt-4o-mini",
        client=MagicMock(),
    )
    request = LLMRequest(
        messages=[
            LLMMessage(role="system", content="Be brief."),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi"),
            LLMMessage(role="user", content="Continue"),
        ],
        model="gpt-4o",
        temperature=0.4,
        max_output_tokens=64,
    )

    payload = provider._to_openai_payload(request)

    assert payload["model"] == "gpt-4o"
    assert payload["temperature"] == 0.4
    assert payload["max_tokens"] == 64
    assert payload["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Continue"},
    ]


def test_openai_adapter_returns_normalized_response() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        model="gpt-4o-mini",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5, total_tokens=9),
    )
    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini", client=client)

    response = provider.generate(_request())

    assert isinstance(response, LLMResponse)
    assert response.content == "ok"
    assert response.provider == "openai"
    assert response.model == "gpt-4o-mini"
    assert response.usage == LLMUsage(
        prompt_tokens=4, completion_tokens=5, total_tokens=9
    )
    assert response.finish_reason == "stop"
    client.chat.completions.create.assert_called_once()
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["messages"] == [{"role": "user", "content": "hello"}]
    assert "temperature" not in call_kwargs
    assert "max_tokens" not in call_kwargs


def test_openai_adapter_maps_provider_failures() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError(
        "openai.RateLimitError: secret"
    )
    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini", client=client)

    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate(_request())

    assert type(exc_info.value) is LLMProviderError
    assert exc_info.value.code == "llm_provider_error"
    assert exc_info.value.status_code == 503
    assert "secret" not in exc_info.value.message
    assert "RateLimit" not in exc_info.value.message
    assert "openai" not in exc_info.value.message
    assert exc_info.value.__cause__ is None


def test_openai_adapter_requires_api_key() -> None:
    with pytest.raises(LLMProviderError):
        OpenAIProvider(api_key="", model="gpt-4o-mini")


def test_application_depends_on_normalized_types_not_sdk() -> None:
    manager = LLMManager(provider=FakeProvider("openai"))
    response = manager.generate(_request())

    assert type(response).__module__ == "app.services.llm.models"
    assert "openai" not in type(response).__module__
