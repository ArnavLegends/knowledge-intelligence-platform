"""Bounded in-process Qdrant search-result cache with TTL.

Design decisions
----------------
- Separate from the embedding cache: search results depend on the live
  state of the Qdrant index (uploads, deletions), so they need a TTL.
  Embedding vectors are deterministic given the input; they have no TTL.

- Cache key: (workspace_id, collection, embedding_hash, top_k,
  threshold, document_id, normalized_filters).
  ``workspace_id`` is mandatory and isolates tenants structurally.
  ``collection`` isolates results if the Qdrant collection is changed.
  ``embedding_hash`` is a SHA-256 hex digest of the query vector bytes,
  giving collision resistance without storing the full vector in the key.
  ``top_k`` and ``threshold`` are included because they affect candidate selection.
  ``document_id`` is included so unrestricted and document-restricted searches
  never collide, and different document scopes remain strictly isolated.
  ``normalized_filters`` is a sorted, deterministic tuple of (key, value) pairs
  so additional payload filters are collision-resistant.

- TTL: 60 s default.  Entries older than the TTL are treated as misses
  and lazily evicted on the next access.  A background sweep is NOT used
  to avoid complexity; lazy eviction is safe and sufficient for this scale.

- Capacity: 256 entries.  When the store is full the LRU entry is evicted
  regardless of TTL.

- Thread safety: same lock-around-dict pattern as EmbeddingCache.
  The lock is NOT held while the caller makes its Qdrant search call.

- Immutability: each cached value is a tuple of ``VectorSearchResult``
  Pydantic model instances.  Pydantic models are mutable, so callers
  receive a fresh list of model copies (via ``model_copy()``) to prevent
  accidental mutation of cached state.

- Invalidation: ``invalidate_workspace(workspace_id)`` evicts all entries
  for a workspace.  ``invalidate_document(workspace_id, document_id)`` evicts
  entries scoped to that document.  ``clear()`` evicts everything.

- Failures are never cached.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from app.services.vector_store.models import VectorSearchResult

logger = logging.getLogger(__name__)

_DEFAULT_CAPACITY = 256
_DEFAULT_TTL_SECONDS = 60.0


@dataclass
class SearchCacheStats:
    """Snapshot of search-cache statistics at a point in time."""

    hits: int = 0
    misses: int = 0
    size: int = 0
    capacity: int = 0
    evictions: int = 0
    ttl_seconds: float = _DEFAULT_TTL_SECONDS

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class _Entry:
    """Internal cache entry."""

    results: tuple[VectorSearchResult, ...]
    stored_at: float  # monotonic time


class SearchCache:
    """Thread-safe bounded LRU cache for Qdrant vector-search results.

    Parameters
    ----------
    capacity:
        Maximum number of entries.  Oldest-used entry is evicted when full.
    ttl_seconds:
        Entries older than this (wall-clock seconds) are treated as misses.
    """

    def __init__(
        self,
        capacity: int = _DEFAULT_CAPACITY,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    ) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._store: OrderedDict[tuple, _Entry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        workspace_id: str,
        collection: str,
        query_vector: list[float],
        top_k: int,
        threshold: float | None = None,
        document_id: str | None = None,
        filters: Any = None,
    ) -> list[VectorSearchResult] | None:
        """Return cached search results or ``None`` on a miss or expiry.

        Returns fresh copies of the stored ``VectorSearchResult`` objects.
        """
        key = self._make_key(
            workspace_id,
            collection,
            query_vector,
            top_k,
            threshold,
            document_id,
            filters,
        )
        now = time.monotonic()

        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            # TTL check
            if now - entry.stored_at > self._ttl:
                del self._store[key]
                self._misses += 1
                return None

            self._store.move_to_end(key)
            self._hits += 1
            # Return deep copies to prevent callers from mutating cached metadata dicts
            return [r.model_copy(deep=True) for r in entry.results]

    def put(
        self,
        workspace_id: str,
        collection: str,
        query_vector: list[float],
        top_k: int,
        threshold: float | None = None,
        results: list[VectorSearchResult] | None = None,
        document_id: str | None = None,
        filters: Any = None,
    ) -> None:
        """Store search results.  Silently ignores if results is None."""
        if results is None:
            return

        key = self._make_key(
            workspace_id,
            collection,
            query_vector,
            top_k,
            threshold,
            document_id,
            filters,
        )
        entry = _Entry(results=tuple(results), stored_at=time.monotonic())

        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = entry
                return

            self._store[key] = entry
            if len(self._store) > self._capacity:
                self._store.popitem(last=False)  # evict LRU
                self._evictions += 1

    def invalidate_workspace(self, workspace_id: str) -> int:
        """Evict all entries belonging to ``workspace_id``.

        Removes entries regardless of scope or filters.
        Returns the number of entries removed.
        """
        with self._lock:
            to_delete = [k for k in self._store if k[0] == workspace_id]
            for k in to_delete:
                self._store.pop(k, None)
        return len(to_delete)

    def invalidate_document(self, workspace_id: str, document_id: str) -> int:
        """Evict all entries belonging to ``workspace_id`` with ``document_id`` scope.

        Returns the number of entries removed.
        """
        if not document_id:
            return 0
        norm_doc = document_id.strip()
        with self._lock:
            to_delete = [
                k for k in self._store if k[0] == workspace_id and k[5] == norm_doc
            ]
            for k in to_delete:
                self._store.pop(k, None)
        return len(to_delete)

    def clear(self) -> None:
        """Remove all entries and reset statistics."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def stats(self) -> SearchCacheStats:
        """Return a snapshot of current cache statistics."""
        with self._lock:
            return SearchCacheStats(
                hits=self._hits,
                misses=self._misses,
                size=len(self._store),
                capacity=self._capacity,
                evictions=self._evictions,
                ttl_seconds=self._ttl,
            )

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_vector(vector: list[float]) -> str:
        """Return a collision-resistant hex digest of a float vector."""
        raw = struct.pack(f"<{len(vector)}d", *vector)
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _normalize_filters(
        filters: Any,
    ) -> tuple[tuple[str, str], ...] | None:
        """Deterministic, sorted, hashable representation of payload filters."""
        if not filters:
            return None
        if isinstance(filters, dict):
            items = filters.items()
        elif isinstance(filters, (list, tuple, set)):
            items = filters
        else:
            return ((str(filters), ""),)
        return tuple(sorted((str(k), "" if v is None else str(v)) for k, v in items))

    @classmethod
    def _make_key(
        cls,
        workspace_id: str,
        collection: str,
        query_vector: list[float],
        top_k: int,
        threshold: float | None = None,
        document_id: str | None = None,
        filters: Any = None,
    ) -> tuple[
        str,
        str,
        str,
        int,
        float | None,
        str | None,
        tuple[tuple[str, str], ...] | None,
    ]:
        norm_doc = document_id.strip() if document_id and document_id.strip() else None
        return (
            workspace_id,
            collection,
            cls._hash_vector(query_vector),
            top_k,
            threshold,
            norm_doc,
            cls._normalize_filters(filters),
        )


_default_search_cache: SearchCache | None = None


def get_default_search_cache() -> SearchCache:
    """Return the application-wide default SearchCache instance."""
    global _default_search_cache
    if _default_search_cache is None:
        from app.core.config import settings

        _default_search_cache = SearchCache(
            capacity=settings.search_cache_capacity,
            ttl_seconds=settings.search_cache_ttl_seconds,
        )
    return _default_search_cache


def reset_default_search_cache() -> None:
    """Reset the application-wide default SearchCache (primarily for tests)."""
    global _default_search_cache
    if _default_search_cache is not None:
        _default_search_cache.clear()
    _default_search_cache = None
