"""Embedding manager that selects and hides the configured provider."""

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import AppException
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.models import Embedding, EmbeddingRequest


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
            from app.services.embeddings.providers.openai import OpenAIEmbeddingProvider

            return OpenAIEmbeddingProvider(
                api_key=settings.llm_api_key,
                model=settings.embedding_model,
            )
        elif provider_name == "gemini":
            from app.services.embeddings.providers.gemini import GeminiEmbeddingProvider

            return GeminiEmbeddingProvider(
                api_key=settings.llm_api_key,
                model=settings.embedding_model,
                output_dimensionality=settings.embedding_dimensions,
            )
        raise AppException(
            f"Unsupported embedding provider: {provider_name}",
            code="unsupported_embedding_provider",
            status_code=500,
        )
