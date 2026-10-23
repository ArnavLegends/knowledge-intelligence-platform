"""HTTP tests for POST /api/v1/llm/generate."""

from fastapi.testclient import TestClient

from app.core.exceptions import LLMProviderError
from app.main import app
from app.services.llm.base import LLMProvider
from app.services.llm.manager import LLMManager
from app.services.llm.models import LLMRequest, LLMResponse, LLMUsage
from app.services.llm.service import LLMService, get_llm_service

GENERATE_URL = "/api/v1/llm/generate"


class FakeProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "fake"

    def generate(self, request: LLMRequest) -> LLMResponse:
        last_message = request.messages[-1].content
        return LLMResponse(
            content=f"echo:{last_message}",
            model=request.model or "fake-model",
            provider=self.name,
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            finish_reason="stop",
        )


class FailingProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "failing"

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderError("Language model provider request failed.")


def _override_service(
    provider: LLMProvider,
    enable_endpoint: bool = True,
    admin_key: str = "test-admin-secret",
) -> None:
    service = LLMService(manager=LLMManager(provider=provider))
    app.dependency_overrides[get_llm_service] = lambda: service
    from app.core.config import Settings, get_settings

    override_settings = Settings(
        enable_direct_llm_endpoint=enable_endpoint,
        admin_api_key=admin_key,
        llm_api_key="fake",
    )
    app.dependency_overrides[get_settings] = lambda: override_settings


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_generate_endpoint_disabled_by_default_returns_403() -> None:
    """When enable_direct_llm_endpoint is False, calls are rejected with 403."""
    _override_service(FakeProvider(), enable_endpoint=False)
    client = _client()

    response = client.post(
        GENERATE_URL,
        headers={"X-KIP-Admin-Key": "test-admin-secret"},
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 403
    err_body = response.json()
    msg = err_body.get("detail") or err_body.get("error", {}).get("message", "")
    assert "disabled by policy" in msg


def test_generate_endpoint_requires_admin_key_when_enabled() -> None:
    """When enabled, calls without valid admin key are rejected with 403."""
    _override_service(FakeProvider(), enable_endpoint=True, admin_key="secret-key")
    client = _client()

    no_auth = client.post(
        GENERATE_URL,
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert no_auth.status_code == 403

    wrong_auth = client.post(
        GENERATE_URL,
        headers={"X-KIP-Admin-Key": "wrong-key"},
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert wrong_auth.status_code == 403


def test_generate_endpoint_returns_normalized_response() -> None:
    _override_service(FakeProvider(), enable_endpoint=True)
    client = _client()

    response = client.post(
        GENERATE_URL,
        headers={"X-KIP-Admin-Key": "test-admin-secret"},
        json={
            "messages": [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "Hello"},
            ],
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "max_output_tokens": 64,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "content": "echo:Hello",
        "model": "gpt-4o-mini",
        "provider": "fake",
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
        },
        "finish_reason": "stop",
    }
    assert "choices" not in body
    assert "id" not in body


def test_generate_endpoint_rejects_invalid_payload() -> None:
    _override_service(FakeProvider())
    client = _client()
    headers = {"X-KIP-Admin-Key": "test-admin-secret"}

    missing_messages = client.post(
        GENERATE_URL, headers=headers, json={"temperature": 0.5}
    )
    assert missing_messages.status_code == 422

    invalid_role = client.post(
        GENERATE_URL,
        headers=headers,
        json={"messages": [{"role": "tool", "content": "nope"}]},
    )
    assert invalid_role.status_code == 422

    empty_content = client.post(
        GENERATE_URL,
        headers=headers,
        json={"messages": [{"role": "user", "content": "   "}]},
    )
    assert empty_content.status_code == 422

    invalid_temperature = client.post(
        GENERATE_URL,
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 3.0,
        },
    )
    assert invalid_temperature.status_code == 422

    invalid_max_tokens = client.post(
        GENERATE_URL,
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "max_output_tokens": 0,
        },
    )
    assert invalid_max_tokens.status_code == 422


def test_generate_endpoint_maps_provider_failure() -> None:
    _override_service(FailingProvider())
    client = _client()
    headers = {"X-KIP-Admin-Key": "test-admin-secret"}

    response = client.post(
        GENERATE_URL,
        headers=headers,
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "llm_provider_error",
            "message": "Language model provider request failed.",
        }
    }
    assert "traceback" not in response.text.lower()
    assert "openai" not in response.text.lower()
