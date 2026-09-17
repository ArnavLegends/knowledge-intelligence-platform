"""Language model manager that selects and hides the configured provider."""

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import AppException
from app.services.llm.base import LLMProvider
from app.services.llm.models import LLMRequest, LLMResponse
from app.services.llm.providers.openai import OpenAIProvider


class LLMManager:
    """Gateway that exposes a provider-agnostic generate() interface."""

    def __init__(
        self,
        settings: Settings | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self._settings = settings or default_settings
        self._provider = provider or self._create_provider(self._settings)

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Invoke the configured provider and return a normalized response."""
        return self._provider.generate(request)

    @staticmethod
    def _create_provider(settings: Settings) -> LLMProvider:
        provider_name = settings.llm_provider.strip().lower()
        if provider_name == "openai":
            return OpenAIProvider(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
            )
        raise AppException(
            "Unsupported LLM provider.",
            code="unsupported_llm_provider",
            status_code=500,
        )
