"""Vector store manager that selects and hides the configured provider."""

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import AppException
from app.services.vector_store.base import VectorStoreProvider
from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider


class VectorStoreManager:
    """Gateway that exposes a provider-agnostic vector store interface."""

    def __init__(
        self,
        settings: Settings | None = None,
        provider: VectorStoreProvider | None = None,
    ) -> None:
        self._settings = settings or default_settings
        self._provider = provider or self._create_provider(self._settings)

    @property
    def provider(self) -> VectorStoreProvider:
        """Access the underlying provider."""
        return self._provider

    @staticmethod
    def _create_provider(settings: Settings) -> VectorStoreProvider:
        provider_name = settings.vector_store_provider.strip().lower()
        if provider_name == "chroma":
            # Append embedding provider to collection name to prevent dimension mismatch
            embed_prov = settings.embedding_provider.strip().lower()
            collection_name = f"{settings.vector_store_collection}_{embed_prov}"
            return ChromaVectorStoreProvider(
                collection_name=collection_name,
                persist_directory=settings.vector_store_persist_directory,
            )
        raise AppException(
            "Unsupported vector store provider.",
            code="unsupported_vector_store_provider",
            status_code=500,
        )
