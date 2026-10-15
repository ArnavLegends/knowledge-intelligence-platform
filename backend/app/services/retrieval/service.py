"""Application-facing retrieval service.

Performance instrumentation
----------------------------
``search()`` records per-stage wall-clock durations via ``time.perf_counter``:

- ``embed_ms``    — time to embed the query (includes cache hit time)
- ``search_ms``   — time for the Qdrant vector search (includes cache hit time)
- ``total_ms``    — end-to-end duration of the search() call

Cache behaviour is also logged at DEBUG level (``embedding_cache``,
``search_cache`` fields).  No user query text or document content is logged.

Search-cache invalidation
--------------------------
``invalidate_search_cache_for_workspace(workspace_id)`` is provided so that
callers (e.g. an indexing completion hook or document deletion handler) can
evict stale entries when the workspace index changes.  The short default TTL
(60 s) acts as a safety net for mutation paths that do not call invalidate.
"""

import logging
import time
from collections.abc import Callable

from fastapi import Depends

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.exceptions import RetrievalError
from app.core.workspace import get_workspace_id
from app.services.cache.search_cache import SearchCache, get_default_search_cache
from app.services.embeddings.models import EmbeddingInput, EmbeddingRequest
from app.services.embeddings.service import EmbeddingService
from app.services.retrieval.models import RetrievalQuery, RetrievedChunk
from app.services.vector_store.service import VectorStoreService

logger = logging.getLogger(__name__)


class RetrievalService:
    """Provides high-level retrieval capabilities scoped to workspaces."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_store_service: VectorStoreService | None = None,
        settings: Settings | None = None,
        query_formatter: Callable[[str], str] | None = None,
        search_cache: SearchCache | None = None,
    ) -> None:
        self._embedding_service = embedding_service or EmbeddingService()
        self._vector_store_service = vector_store_service or VectorStoreService()
        self._settings = settings or default_settings
        self._query_formatter = query_formatter
        self._search_cache: SearchCache = (
            search_cache if search_cache is not None else get_default_search_cache()
        )

    @property
    def search_cache(self) -> SearchCache:
        """Expose cache for stats, testing, and external invalidation."""
        return self._search_cache

    def search(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        """Perform a semantic search strictly scoped to the query's workspace."""
        if not query.workspace_id or not query.workspace_id.strip():
            raise RetrievalError("workspace_id is required for retrieval operations.")

        if not query.text.strip():
            return []

        t_total = time.perf_counter()

        # 1. Embed the query text
        t_embed = time.perf_counter()
        try:
            query_text_to_embed = (
                self._query_formatter(query.text)
                if self._query_formatter is not None
                else query.text
            )
            emb_req = EmbeddingRequest(
                inputs=[EmbeddingInput(source_id="query", text=query_text_to_embed)],
                model=self._settings.embedding_model,
            )
            embeddings = self._embedding_service.embed_texts(emb_req)
        except Exception as e:
            raise RetrievalError(f"Failed to embed query: {e}") from e
        embed_ms = (time.perf_counter() - t_embed) * 1000

        if not embeddings or not embeddings[0].vector:
            raise RetrievalError("Embedding service returned empty vector for query.")

        query_vector = embeddings[0].vector

        # 2. Search the vector store with mandatory workspace filter
        #    Check search cache first.
        t_search = time.perf_counter()
        collection = self._settings.qdrant_collection

        cached_results = self._search_cache.get(
            workspace_id=query.workspace_id,
            collection=collection,
            query_vector=query_vector,
            top_k=query.top_k,
            threshold=query.threshold,
            document_id=query.document_id,
            filters=query.filters,
        )

        if cached_results is not None:
            search_ms = (time.perf_counter() - t_search) * 1000
            total_ms = (time.perf_counter() - t_total) * 1000
            logger.info(
                "search_cache=hit embed_ms=%.1f search_ms=%.1f total_ms=%.1f "
                "workspace=%s top_k=%d doc_scope=%s",
                embed_ms,
                search_ms,
                total_ms,
                query.workspace_id[:8],
                query.top_k,
                query.document_id,
            )
            return self._to_retrieved_chunks(cached_results, query.workspace_id)

        try:
            raw_results = self._vector_store_service.search(
                query_vector=query_vector,
                top_k=query.top_k,
                workspace_id=query.workspace_id,
                threshold=query.threshold,
                document_id=query.document_id,
                filters=query.filters,
            )
        except Exception as e:
            raise RetrievalError(f"Vector store search failed: {e}") from e

        search_ms = (time.perf_counter() - t_search) * 1000

        # Store in cache (only on success)
        self._search_cache.put(
            workspace_id=query.workspace_id,
            collection=collection,
            query_vector=query_vector,
            top_k=query.top_k,
            threshold=query.threshold,
            results=raw_results,
            document_id=query.document_id,
            filters=query.filters,
        )

        total_ms = (time.perf_counter() - t_total) * 1000
        logger.info(
            "search_cache=miss embed_ms=%.1f search_ms=%.1f total_ms=%.1f "
            "workspace=%s top_k=%d results=%d doc_scope=%s",
            embed_ms,
            search_ms,
            total_ms,
            query.workspace_id[:8],
            query.top_k,
            len(raw_results),
            query.document_id,
        )

        return self._to_retrieved_chunks(raw_results, query.workspace_id)

    def invalidate_search_cache_for_workspace(self, workspace_id: str) -> int:
        """Evict all search-cache entries for ``workspace_id``.

        Should be called after document upload, re-indexing, or deletion to
        prevent stale results from being served within the TTL window.
        Returns the number of evicted entries.
        """
        removed = self._search_cache.invalidate_workspace(workspace_id)
        if removed:
            logger.info(
                "search_cache invalidated workspace=%s entries_removed=%d",
                workspace_id[:8],
                removed,
            )
        return removed

    def invalidate_search_cache_for_document(
        self, workspace_id: str, document_id: str
    ) -> int:
        """Evict all search-cache entries for ``document_id`` in ``workspace_id``.

        Returns the number of evicted entries.
        """
        removed = self._search_cache.invalidate_document(workspace_id, document_id)
        if removed:
            logger.info(
                "search_cache invalidated workspace=%s document=%s entries_removed=%d",
                workspace_id[:8],
                document_id[:8],
                removed,
            )
        return removed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _to_retrieved_chunks(
        results: list,
        workspace_id: str,
    ) -> list[RetrievedChunk]:
        """Convert VectorSearchResult list to RetrievedChunk list.

        Applies defensive workspace-isolation check: any result whose
        metadata workspace_id does not match is silently discarded and
        logged at WARNING.
        """
        retrieved_chunks = []
        for res in results:
            chunk_ws = res.metadata.get("workspace_id")
            if chunk_ws is not None and chunk_ws != workspace_id:
                logger.warning(
                    "Security invariant violation: discarded cross-tenant chunk in %s",
                    workspace_id[:8],
                )
                continue

            doc_id = res.metadata.get("document_id")
            text = res.metadata.get("text")

            retrieved_chunks.append(
                RetrievedChunk(
                    id=res.id,
                    document_id=doc_id,
                    text=text,
                    score=res.distance,
                    metadata=res.metadata,
                )
            )

        return retrieved_chunks


def get_retrieval_service(
    _workspace_id: str = Depends(get_workspace_id),
) -> "RetrievalService":
    """FastAPI dependency that constructs the retrieval service.

    Depends on get_workspace_id so that workspace validation always runs
    before any external AI provider (embedding, vector store) is instantiated.
    """
    return RetrievalService(search_cache=get_default_search_cache())
