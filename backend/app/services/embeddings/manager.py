"""Embedding manager that selects and hides the configured provider."""

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import AppException
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.models import Embedding, EmbeddingRequest
from app.services.embeddings.providers.openai import OpenAIEmbeddingProvider


class EmbeddingManager:
    """Gateway that exposes a provider-agnostic embed() interface."""

    def __init__(
        self,
        settings: Settings | None = None,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self._settings = settings or default_settings
        self._provider = provider or self._create_provider(self._settings)

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        """Invoke the configured provider and return normalized embeddings."""
        return self._provider.embed(request)

    @staticmethod
    def _create_provider(settings: Settings) -> EmbeddingProvider:
        provider_name = settings.embedding_provider.strip().lower()
        if provider_name == "openai":
            return OpenAIEmbeddingProvider(
                api_key=settings.llm_api_key,
                model=settings.embedding_model,
            )
        raise AppException(
            "Unsupported embedding provider.",
            code="unsupported_embedding_provider",
            status_code=500,
        )
