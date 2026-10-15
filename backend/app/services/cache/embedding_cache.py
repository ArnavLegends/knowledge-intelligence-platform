"""Bounded in-process query-embedding cache.

Design decisions
----------------
- ``functools.lru_cache`` is NOT used here. It is a module-level decorator that
  tightly couples cache lifetime to the function object; it cannot be cleared
  per-instance, its statistics are shared globally, and it cannot be swapped
  easily in tests.  An explicit ``OrderedDict``-based LRU gives full control
  over capacity, stats, and clearing without third-party dependencies.

- Cache key: (normalized_text, model_name, output_dimensionality).
  ``normalized_text`` = strip + collapse internal whitespace runs.
  This is the minimal normalization that cannot change semantic meaning.
  More aggressive normalization (lower-casing, stemming) is intentionally
  excluded to preserve query semantics.

- Thread safety: a ``threading.Lock`` guards the OrderedDict so that
  concurrent reads and writes do not corrupt the internal structure.
  The lock is NOT held while the caller makes its external embedding
  API call; duplicate-miss races can therefore occur (two threads embed
  the same query simultaneously), but the second writer simply overwrites
  the first with an identical result. Request coalescing is deliberately
  omitted — the added synchronization complexity is not justified at
  free-tier single-worker scale.

- Immutability: cached vectors are stored as ``tuple[float, ...]`` and
  returned as a fresh ``list[float]`` copy to prevent callers from
  accidentally mutating the stored value.

- Only successful, non-empty results are stored (validated before insert).
- Exceptions are never cached.
"""

from __future__ import annotations

import logging
import threading
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DEFAULT_CAPACITY = 256


@dataclass
class EmbeddingCacheStats:
    """Snapshot of cache statistics at a point in time."""

    hits: int = 0
    misses: int = 0
    size: int = 0
    capacity: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class _Entry:
    """Internal cache entry."""

    vector: tuple[float, ...]  # immutable storage


class EmbeddingCache:
    """Thread-safe bounded LRU cache for query embedding vectors.

    Parameters
    ----------
    capacity:
        Maximum number of entries to retain.  When the cache is full the
        least-recently-used entry is evicted.
    """

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self._capacity = capacity
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
        text: str,
        model: str,
        output_dimensionality: int | None,
    ) -> list[float] | None:
        """Return a cached embedding vector or ``None`` on a miss.

        Returns a *copy* of the stored vector; callers may mutate it
        freely without affecting the cache.
        """
        key = self._make_key(text, model, output_dimensionality)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            # Move to end (most-recently-used)
            self._store.move_to_end(key)
            self._hits += 1
            return list(entry.vector)  # defensive copy

    def put(
        self,
        text: str,
        model: str,
        output_dimensionality: int | None,
        vector: list[float],
    ) -> None:
        """Store ``vector`` under the given key.

        Validates that ``vector`` is non-empty before storing.
        Silently ignores invalid (empty) vectors — they are never cached.
        """
        if not vector:
            return

        key = self._make_key(text, model, output_dimensionality)
        # Store as tuple for immutability in the cache
        stored = tuple(vector)

        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = _Entry(vector=stored)
                return

            self._store[key] = _Entry(vector=stored)
            if len(self._store) > self._capacity:
                self._store.popitem(last=False)  # evict LRU
                self._evictions += 1

    def invalidate(
        self,
        text: str,
        model: str,
        output_dimensionality: int | None,
    ) -> bool:
        """Remove a specific entry. Returns True if the entry existed."""
        key = self._make_key(text, model, output_dimensionality)
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> None:
        """Remove all entries and reset statistics."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def stats(self) -> EmbeddingCacheStats:
        """Return a snapshot of current cache statistics."""
        with self._lock:
            return EmbeddingCacheStats(
                hits=self._hits,
                misses=self._misses,
                size=len(self._store),
                capacity=self._capacity,
                evictions=self._evictions,
            )

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip leading/trailing whitespace and collapse internal runs."""
        # NFC normalisation ensures the same Unicode scalar values for
        # canonically equivalent strings (e.g. composed vs. decomposed accents).
        normalized = unicodedata.normalize("NFC", text)
        # Collapse internal whitespace runs to a single space
        return " ".join(normalized.split())

    @classmethod
    def _make_key(
        cls,
        text: str,
        model: str,
        output_dimensionality: int | None,
    ) -> tuple[str, str, int | None]:
        return (cls._normalize(text), model.strip(), output_dimensionality)
