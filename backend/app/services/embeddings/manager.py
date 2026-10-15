"""Embedding manager that selects and hides the configured provider.

Performance instrumentation
----------------------------
``embed()`` records ``embed_ms`` (wall-clock duration via ``time.perf_counter``)
and logs embedding-cache hit/miss at DEBUG level.  No sensitive data (query
text, vectors) is logged.
"""

import logging
import time

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import AppException
from app.services.cache.embedding_cache import EmbeddingCache
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.models import Embedding, EmbeddingRequest

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """Gateway that exposes a provider-agnostic embed() interface.

    Wraps the configured provider with a bounded in-process LRU cache.
    The cache key is (normalized_text, model, output_dimensionality).
    Only single-input requests (i.e. query embedding) are cached; batch
    requests (document chunk embedding during indexing) bypass the cache
    intentionally — document chunks are unique per upload and would bloat
    the cache without providing query-path benefit.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        provider: EmbeddingProvider | None = None,
        embedding_cache: EmbeddingCache | None = None,
    ) -> None:
        self._settings = settings or default_settings
        self._provider = provider or self._create_provider(self._settings)
        self._cache: EmbeddingCache = embedding_cache or EmbeddingCache(
            capacity=self._settings.embedding_cache_capacity
        )

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def embedding_cache(self) -> EmbeddingCache:
        """Expose cache for stats, testing, and external invalidation."""
        return self._cache

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        """Invoke the configured provider and return normalized embeddings.

        Single-input requests check the embedding cache before hitting the
        provider.  Multi-input requests (batch indexing) always call the
        provider directly.
        """
        t0 = time.perf_counter()

        # Only cache single-input (query) embedding requests
        if len(request.inputs) == 1:
            result = self._embed_single_cached(request, t0)
        else:
            result = self._embed_batch(request, t0)

        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _embed_single_cached(
        self, request: EmbeddingRequest, t0: float
    ) -> list[Embedding]:
        """Embed a single input with cache look-up."""
        inp = request.inputs[0]
        model = request.model or self._settings.embedding_model
        output_dim = self._settings.embedding_dimensions or None

        cached_vector = self._cache.get(inp.text, model, output_dim)
        if cached_vector is not None:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "embedding_cache=hit embed_ms=%.1f model=%s",
                elapsed_ms,
                model,
            )
            # Reconstruct a full Embedding object from the cached vector
            return [
                Embedding(
                    source_id=inp.source_id,
                    vector=cached_vector,
                    dimensions=len(cached_vector),
                    metadata=inp.metadata.copy(),
                    provider=self._provider.name,
                    model=model,
                )
            ]

        # Cache miss — call the provider
        embeddings = self._provider.embed(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "embedding_cache=miss embed_ms=%.1f model=%s",
            elapsed_ms,
            model,
        )

        # Store result in cache if valid
        if embeddings and embeddings[0].vector:
            self._cache.put(inp.text, model, output_dim, embeddings[0].vector)

        return embeddings

    def _embed_batch(self, request: EmbeddingRequest, t0: float) -> list[Embedding]:
        """Embed a batch of inputs, bypassing the cache."""
        embeddings = self._provider.embed(request)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            "embedding_cache=bypass_batch embed_ms=%.1f inputs=%d",
            elapsed_ms,
            len(request.inputs),
        )
        return embeddings

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
                timeout_seconds=settings.embedding_timeout_seconds,
            )
        raise AppException(
            f"Unsupported embedding provider: {provider_name}",
            code="unsupported_embedding_provider",
            status_code=500,
        )
