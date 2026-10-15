"""Focused tests for the KIP in-process caching layer.

Coverage
--------
EmbeddingCache
- Repeated identical query → cache hit, single provider call
- Different query → cache miss
- Different model → cache miss
- Different output_dimensionality → cache miss
- Capacity enforcement and LRU eviction
- Failed embedding not cached
- Empty vector not cached
- Returned vector is a mutable copy (does not alias cache entry)
- stats() and clear() behaviour
- Concurrent access (basic smoke-test)

SearchCache
- Valid cache hit within TTL
- Cache miss for different workspace_id (tenant isolation)
- Cache miss for different top_k
- Cache miss for different threshold
- Cache miss for different query vector
- Cache miss for different collection
- TTL expiry
- Capacity enforcement and LRU eviction
- Failure not cached
- invalidate_workspace() eviction
- Returned results are copies (do not alias cache entry)
- stats() and clear() behaviour

Integration / regression
- RetrievalService uses embedding cache via EmbeddingManager
- RetrievalService uses search cache
- Cache hits do not bypass workspace validation
- Failures propagate normally through caching layer
- invalidate_search_cache_for_workspace() works end-to-end
"""

from __future__ import annotations

import threading
import time
from datetime import UTC
from unittest.mock import MagicMock, create_autospec

import pytest

from app.core.config import Settings
from app.core.exceptions import EmbeddingProviderError, RetrievalError
from app.services.cache.embedding_cache import EmbeddingCache
from app.services.cache.search_cache import SearchCache
from app.services.chunking.service import ChunkingService
from app.services.documents.models import Document
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingInput, EmbeddingRequest
from app.services.indexing.service import DocumentIndexingService
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService
from app.services.vector_store.models import VectorSearchResult
from app.services.vector_store.service import VectorStoreService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIM = 4


def _make_vector(val: float = 0.1) -> list[float]:
    return [val] * _DIM


def _make_embedding(text: str = "q", model: str = "m1") -> Embedding:
    return Embedding(
        source_id="query",
        vector=_make_vector(),
        dimensions=_DIM,
        metadata={},
        provider="fake",
        model=model,
    )


def _make_search_result(workspace_id: str = "ws-a") -> VectorSearchResult:
    return VectorSearchResult(
        id="c1",
        vector=_make_vector(),
        metadata={"workspace_id": workspace_id, "document_id": "d1", "text": "hello"},
        distance=0.1,
    )


def _make_provider_that_returns(vector: list[float]) -> EmbeddingProvider:
    """Return a fake EmbeddingProvider that always returns ``vector``."""
    provider = MagicMock(spec=EmbeddingProvider)
    provider.name = "fake"

    def _embed(request: EmbeddingRequest) -> list[Embedding]:
        return [
            Embedding(
                source_id=inp.source_id,
                vector=list(vector),
                dimensions=len(vector),
                metadata=inp.metadata.copy(),
                provider="fake",
                model=request.model or "fake-model",
            )
            for inp in request.inputs
        ]

    provider.embed.side_effect = _embed
    return provider


# ===========================================================================
# EmbeddingCache unit tests
# ===========================================================================


class TestEmbeddingCacheBasic:
    def test_miss_then_hit(self):
        cache = EmbeddingCache(capacity=32)
        assert cache.get("hello", "m1", None) is None
        cache.put("hello", "m1", None, [0.1, 0.2])
        result = cache.get("hello", "m1", None)
        assert result == [0.1, 0.2]

    def test_different_query_is_miss(self):
        cache = EmbeddingCache(capacity=32)
        cache.put("hello", "m1", None, [0.1])
        assert cache.get("world", "m1", None) is None

    def test_different_model_is_miss(self):
        cache = EmbeddingCache(capacity=32)
        cache.put("hello", "m1", None, [0.1])
        assert cache.get("hello", "m2", None) is None

    def test_different_dimensionality_is_miss(self):
        cache = EmbeddingCache(capacity=32)
        cache.put("hello", "m1", 768, [0.1])
        assert cache.get("hello", "m1", 1536) is None
        assert cache.get("hello", "m1", None) is None

    def test_normalisation_strips_whitespace(self):
        """Leading/trailing and internal whitespace runs are collapsed."""
        cache = EmbeddingCache(capacity=32)
        cache.put("  hello   world  ", "m1", None, [0.5])
        assert cache.get("hello world", "m1", None) == [0.5]

    def test_empty_vector_not_cached(self):
        cache = EmbeddingCache(capacity=32)
        cache.put("hello", "m1", None, [])
        assert cache.get("hello", "m1", None) is None

    def test_returned_vector_is_copy(self):
        cache = EmbeddingCache(capacity=32)
        cache.put("hello", "m1", None, [1.0, 2.0])
        v1 = cache.get("hello", "m1", None)
        v1[0] = 999.0
        v2 = cache.get("hello", "m1", None)
        assert v2 == [1.0, 2.0], "Mutation of returned vector must not affect cache"

    def test_capacity_enforced_lru(self):
        cache = EmbeddingCache(capacity=3)
        for i in range(3):
            cache.put(f"q{i}", "m1", None, [float(i)])
        # Access q0 to make it recently used
        cache.get("q0", "m1", None)
        # Insert a 4th entry — q1 (LRU) should be evicted
        cache.put("q3", "m1", None, [3.0])
        assert cache.get("q1", "m1", None) is None
        assert cache.get("q0", "m1", None) is not None
        assert len(cache) == 3

    def test_eviction_counted_in_stats(self):
        cache = EmbeddingCache(capacity=2)
        cache.put("a", "m1", None, [1.0])
        cache.put("b", "m1", None, [2.0])
        cache.put("c", "m1", None, [3.0])  # evicts 'a'
        assert cache.stats().evictions == 1

    def test_stats_hit_miss_counts(self):
        cache = EmbeddingCache(capacity=32)
        cache.put("x", "m1", None, [0.5])
        cache.get("x", "m1", None)  # hit
        cache.get("y", "m1", None)  # miss
        s = cache.stats()
        assert s.hits == 1
        assert s.misses == 1
        assert s.hit_rate == 0.5

    def test_clear_resets_state(self):
        cache = EmbeddingCache(capacity=32)
        cache.put("x", "m1", None, [0.1])
        cache.get("x", "m1", None)
        cache.get("y", "m1", None)
        cache.clear()
        assert len(cache) == 0
        s = cache.stats()
        assert s.hits == 0
        assert s.misses == 0
        assert s.evictions == 0
        assert cache.get("x", "m1", None) is None

    def test_invalid_capacity_raises(self):
        with pytest.raises(ValueError):
            EmbeddingCache(capacity=0)

    def test_concurrent_puts_do_not_corrupt(self):
        """Smoke-test: concurrent writers must not raise or corrupt the cache."""
        cache = EmbeddingCache(capacity=64)
        errors: list[Exception] = []

        def _writer(idx: int) -> None:
            try:
                for _ in range(50):
                    cache.put(f"q{idx}", "m1", None, [float(idx)])
                    cache.get(f"q{idx}", "m1", None)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent access raised: {errors}"


# ===========================================================================
# SearchCache unit tests
# ===========================================================================


class TestSearchCacheBasic:
    _VEC = [0.1, 0.2, 0.3, 0.4]

    def _make_result(self, ws: str = "ws-a") -> list[VectorSearchResult]:
        return [_make_search_result(workspace_id=ws)]

    def test_miss_then_hit(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        assert cache.get("ws-a", "col", self._VEC, 5, None) is None
        cache.put("ws-a", "col", self._VEC, 5, None, self._make_result())
        hits = cache.get("ws-a", "col", self._VEC, 5, None)
        assert hits is not None
        assert len(hits) == 1

    def test_different_workspace_is_miss(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws-a", "col", self._VEC, 5, None, self._make_result("ws-a"))
        assert cache.get("ws-b", "col", self._VEC, 5, None) is None

    def test_different_top_k_is_miss(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws-a", "col", self._VEC, 5, None, self._make_result())
        assert cache.get("ws-a", "col", self._VEC, 10, None) is None

    def test_different_threshold_is_miss(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws-a", "col", self._VEC, 5, None, self._make_result())
        assert cache.get("ws-a", "col", self._VEC, 5, 0.5) is None

    def test_different_vector_is_miss(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws-a", "col", self._VEC, 5, None, self._make_result())
        other_vec = [0.9, 0.8, 0.7, 0.6]
        assert cache.get("ws-a", "col", other_vec, 5, None) is None

    def test_different_collection_is_miss(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws-a", "col-A", self._VEC, 5, None, self._make_result())
        assert cache.get("ws-a", "col-B", self._VEC, 5, None) is None

    def test_ttl_expiry(self):
        cache = SearchCache(capacity=32, ttl_seconds=0.05)
        cache.put("ws-a", "col", self._VEC, 5, None, self._make_result())
        time.sleep(0.1)
        assert cache.get("ws-a", "col", self._VEC, 5, None) is None

    def test_capacity_enforced(self):
        cache = SearchCache(capacity=3, ttl_seconds=60)
        for i in range(3):
            vec = [float(i)] * 4
            cache.put("ws", "col", vec, 5, None, self._make_result())
        # Access entry 0 to make it recently used
        cache.get("ws", "col", [0.0] * 4, 5, None)
        # Insert 4th — entry 1 (LRU) should be evicted
        cache.put("ws", "col", [3.0] * 4, 5, None, self._make_result())
        assert cache.get("ws", "col", [1.0] * 4, 5, None) is None
        assert len(cache) == 3

    def test_evictions_counted(self):
        cache = SearchCache(capacity=2, ttl_seconds=60)
        cache.put("ws", "col", [0.0] * 4, 5, None, self._make_result())
        cache.put("ws", "col", [1.0] * 4, 5, None, self._make_result())
        cache.put("ws", "col", [2.0] * 4, 5, None, self._make_result())
        assert cache.stats().evictions == 1

    def test_returned_results_are_copies(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        original = self._make_result()
        cache.put("ws-a", "col", self._VEC, 5, None, original)
        hits = cache.get("ws-a", "col", self._VEC, 5, None)
        assert hits is not None
        hits[0].metadata["injected"] = True
        # The cache entry should not be mutated
        hits2 = cache.get("ws-a", "col", self._VEC, 5, None)
        assert hits2 is not None
        assert "injected" not in hits2[0].metadata

    def test_failure_not_cached(self):
        """Putting None (simulating a failure path) must be a no-op."""
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws-a", "col", self._VEC, 5, None, None)  # type: ignore[arg-type]
        assert cache.get("ws-a", "col", self._VEC, 5, None) is None

    def test_invalidate_workspace_removes_entries(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws-a", "col", [0.0] * 4, 5, None, self._make_result("ws-a"))
        cache.put("ws-a", "col", [1.0] * 4, 5, None, self._make_result("ws-a"))
        cache.put("ws-b", "col", [0.0] * 4, 5, None, self._make_result("ws-b"))
        removed = cache.invalidate_workspace("ws-a")
        assert removed == 2
        assert cache.get("ws-a", "col", [0.0] * 4, 5, None) is None
        # ws-b entry must be unaffected
        assert cache.get("ws-b", "col", [0.0] * 4, 5, None) is not None

    def test_stats_and_clear(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put("ws", "col", self._VEC, 5, None, self._make_result())
        cache.get("ws", "col", self._VEC, 5, None)  # hit
        cache.get("ws", "col", [9.9] * 4, 5, None)  # miss
        s = cache.stats()
        assert s.hits == 1
        assert s.misses == 1
        cache.clear()
        s2 = cache.stats()
        assert s2.hits == 0
        assert s2.misses == 0
        assert s2.size == 0

    def test_invalid_capacity_raises(self):
        with pytest.raises(ValueError):
            SearchCache(capacity=0)

    def test_invalid_ttl_raises(self):
        with pytest.raises(ValueError):
            SearchCache(ttl_seconds=0)

    def test_different_document_scope_is_miss(self):
        """Searches scoped to different document IDs must not share cache."""
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put(
            "ws-a",
            "col",
            self._VEC,
            5,
            None,
            self._make_result(),
            document_id="doc-1",
        )
        assert (
            cache.get(
                "ws-a",
                "col",
                self._VEC,
                5,
                None,
                document_id="doc-2",
            )
            is None
        )
        hit = cache.get(
            "ws-a",
            "col",
            self._VEC,
            5,
            None,
            document_id="doc-1",
        )
        assert hit is not None

    def test_unrestricted_and_document_restricted_cannot_collide(self):
        """Unrestricted and restricted searches must not collide."""
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put(
            "ws-a",
            "col",
            self._VEC,
            5,
            None,
            self._make_result(),
            document_id=None,
        )
        assert (
            cache.get(
                "ws-a",
                "col",
                self._VEC,
                5,
                None,
                document_id="doc-1",
            )
            is None
        )

        # Reverse check: restricted search does not answer unrestricted query
        cache.clear()
        cache.put(
            "ws-a",
            "col",
            self._VEC,
            5,
            None,
            self._make_result(),
            document_id="doc-1",
        )
        assert (
            cache.get(
                "ws-a",
                "col",
                self._VEC,
                5,
                None,
                document_id=None,
            )
            is None
        )

    def test_different_payload_filters_is_miss(self):
        """Different payload filter dictionaries must not share cache."""
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put(
            "ws-a",
            "col",
            self._VEC,
            5,
            None,
            self._make_result(),
            filters={"tag": "v1"},
        )
        # Different filter value
        assert (
            cache.get(
                "ws-a",
                "col",
                self._VEC,
                5,
                None,
                filters={"tag": "v2"},
            )
            is None
        )
        # Unfiltered query
        assert (
            cache.get(
                "ws-a",
                "col",
                self._VEC,
                5,
                None,
                filters=None,
            )
            is None
        )
        # Same filter matches
        assert (
            cache.get(
                "ws-a",
                "col",
                self._VEC,
                5,
                None,
                filters={"tag": "v1"},
            )
            is not None
        )

    def test_invalidate_document_evicts_only_scoped_entries(self):
        """invalidate_document should evict entries for that document only."""
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put(
            "ws-a",
            "col",
            [0.1] * 4,
            5,
            None,
            self._make_result("ws-a"),
            document_id="doc-A",
        )
        cache.put(
            "ws-a",
            "col",
            [0.2] * 4,
            5,
            None,
            self._make_result("ws-a"),
            document_id="doc-B",
        )
        cache.put(
            "ws-a",
            "col",
            [0.3] * 4,
            5,
            None,
            self._make_result("ws-a"),
            document_id=None,
        )

        removed = cache.invalidate_document("ws-a", "doc-A")
        assert removed == 1
        assert cache.get("ws-a", "col", [0.1] * 4, 5, None, document_id="doc-A") is None
        assert (
            cache.get("ws-a", "col", [0.2] * 4, 5, None, document_id="doc-B")
            is not None
        )
        assert (
            cache.get("ws-a", "col", [0.3] * 4, 5, None, document_id=None) is not None
        )

    def test_concurrent_puts_do_not_corrupt(self):
        cache = SearchCache(capacity=64, ttl_seconds=60)
        errors: list[Exception] = []

        def _worker(idx: int) -> None:
            try:
                vec = [float(idx)] * 4
                for _ in range(50):
                    cache.put(f"ws-{idx}", "col", vec, 5, None, self._make_result())
                    cache.get(f"ws-{idx}", "col", vec, 5, None)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent access raised: {errors}"


# ===========================================================================
# EmbeddingManager integration tests (cache wired into manager)
# ===========================================================================


class TestEmbeddingManagerCache:
    def _make_manager(self, capacity: int = 32) -> tuple[EmbeddingManager, MagicMock]:
        provider = _make_provider_that_returns(_make_vector())
        cache = EmbeddingCache(capacity=capacity)
        settings = Settings(
            embedding_provider="gemini",  # value doesn't matter; provider injected
            embedding_model="test-model",
            embedding_dimensions=_DIM,
        )
        manager = EmbeddingManager(
            settings=settings, provider=provider, embedding_cache=cache
        )
        return manager, provider

    def _single_request(
        self, text: str = "hello", model: str = "test-model"
    ) -> EmbeddingRequest:
        return EmbeddingRequest(
            inputs=[EmbeddingInput(source_id="query", text=text)],
            model=model,
        )

    def test_second_call_uses_cache(self):
        manager, provider = self._make_manager()
        req = self._single_request("hello")
        manager.embed(req)
        manager.embed(req)
        # Provider called exactly once
        assert provider.embed.call_count == 1

    def test_different_text_causes_miss(self):
        manager, provider = self._make_manager()
        manager.embed(self._single_request("hello"))
        manager.embed(self._single_request("world"))
        assert provider.embed.call_count == 2

    def test_batch_bypasses_cache(self):
        manager, provider = self._make_manager()
        req = EmbeddingRequest(
            inputs=[
                EmbeddingInput(source_id="c1", text="chunk one"),
                EmbeddingInput(source_id="c2", text="chunk two"),
            ],
        )
        manager.embed(req)
        manager.embed(req)
        # Batch always calls provider
        assert provider.embed.call_count == 2

    def test_failed_embedding_not_cached(self):
        provider = MagicMock(spec=EmbeddingProvider)
        provider.name = "fake"
        provider.embed.side_effect = EmbeddingProviderError("API down")
        cache = EmbeddingCache(capacity=32)
        settings = Settings(
            embedding_provider="gemini",
            embedding_model="test-model",
            embedding_dimensions=_DIM,
        )
        manager = EmbeddingManager(
            settings=settings, provider=provider, embedding_cache=cache
        )
        with pytest.raises(EmbeddingProviderError):
            manager.embed(self._single_request("hello"))
        # Cache must still be empty
        assert len(manager.embedding_cache) == 0

    def test_cache_hit_reconstructs_correct_source_id(self):
        """A cache hit must preserve the source_id from the request, not the
        source_id that was used when the entry was originally inserted."""
        manager, _ = self._make_manager()
        req1 = EmbeddingRequest(
            inputs=[EmbeddingInput(source_id="first-call", text="hello")]
        )
        req2 = EmbeddingRequest(
            inputs=[EmbeddingInput(source_id="second-call", text="hello")]
        )
        manager.embed(req1)
        result = manager.embed(req2)
        assert result[0].source_id == "second-call"

    def test_cache_stats_exposed(self):
        manager, _ = self._make_manager()
        req = self._single_request("hello")
        manager.embed(req)
        manager.embed(req)
        s = manager.embedding_cache.stats()
        assert s.hits >= 1
        assert s.misses >= 1


# ===========================================================================
# RetrievalService integration tests (search cache wired in)
# ===========================================================================


class TestRetrievalServiceCache:
    def _make_service(
        self,
        search_results: list[VectorSearchResult] | None = None,
        search_ttl: float = 60.0,
    ) -> tuple[RetrievalService, MagicMock, MagicMock]:
        if search_results is None:
            search_results = [_make_search_result()]

        from app.services.embeddings.service import EmbeddingService

        mock_emb_svc = create_autospec(EmbeddingService)
        mock_emb_svc.embed_texts.return_value = [
            Embedding(
                source_id="query",
                vector=_make_vector(),
                dimensions=_DIM,
                metadata={},
            )
        ]

        mock_vs = create_autospec(VectorStoreService)
        mock_vs.search.return_value = search_results

        cache = SearchCache(capacity=32, ttl_seconds=search_ttl)
        settings = Settings(
            qdrant_collection="test-col",
            search_cache_capacity=32,
            search_cache_ttl_seconds=search_ttl,
        )
        svc = RetrievalService(
            embedding_service=mock_emb_svc,
            vector_store_service=mock_vs,
            settings=settings,
            search_cache=cache,
        )
        return svc, mock_emb_svc, mock_vs

    def _query(self, workspace: str = "ws-a") -> RetrievalQuery:
        return RetrievalQuery(text="what is KIP?", workspace_id=workspace, top_k=5)

    def test_second_search_uses_cache(self):
        svc, mock_emb, mock_vs = self._make_service()
        q = self._query()
        svc.search(q)
        svc.search(q)
        mock_vs.search.assert_called_once()

    def test_different_workspace_causes_miss(self):
        svc, mock_emb, mock_vs = self._make_service()
        mock_vs.search.return_value = [_make_search_result("ws-a")]
        svc.search(self._query("ws-a"))
        mock_vs.search.return_value = [_make_search_result("ws-b")]
        svc.search(self._query("ws-b"))
        assert mock_vs.search.call_count == 2

    def test_different_top_k_causes_miss(self):
        svc, _, mock_vs = self._make_service()
        svc.search(RetrievalQuery(text="q", workspace_id="ws-a", top_k=5))
        svc.search(RetrievalQuery(text="q", workspace_id="ws-a", top_k=10))
        assert mock_vs.search.call_count == 2

    def test_ttl_expiry_causes_miss(self):
        svc, _, mock_vs = self._make_service(search_ttl=0.05)
        q = self._query()
        svc.search(q)
        time.sleep(0.1)
        svc.search(q)
        assert mock_vs.search.call_count == 2

    def test_vector_store_failure_not_cached(self):
        _, mock_emb_svc, mock_vs = self._make_service()
        mock_vs.search.side_effect = Exception("DB error")
        cache = SearchCache(capacity=32, ttl_seconds=60)
        settings = Settings(qdrant_collection="test-col")
        svc = RetrievalService(
            embedding_service=mock_emb_svc,
            vector_store_service=mock_vs,
            settings=settings,
            search_cache=cache,
        )
        with pytest.raises(RetrievalError):
            svc.search(self._query())
        assert len(cache) == 0

    def test_invalidate_search_cache_for_workspace(self):
        svc, _, mock_vs = self._make_service()
        svc.search(self._query("ws-a"))
        svc.search(self._query("ws-a"))
        mock_vs.search.assert_called_once()

        removed = svc.invalidate_search_cache_for_workspace("ws-a")
        assert removed == 1
        svc.search(self._query("ws-a"))
        assert mock_vs.search.call_count == 2

    def test_cache_hit_preserves_workspace_isolation(self):
        """A cache hit for ws-a must not be returned for ws-b."""
        svc, _, mock_vs = self._make_service()
        svc.search(self._query("ws-a"))
        mock_vs.search.return_value = []
        svc.search(self._query("ws-b"))
        # ws-b has no data; its own search was called separately
        assert mock_vs.search.call_count == 2

    def test_search_cache_stats_exposed(self):
        svc, _, _ = self._make_service()
        svc.search(self._query())
        svc.search(self._query())
        s = svc.search_cache.stats()
        assert s.hits >= 1
        assert s.misses >= 1

    def test_empty_workspace_raises_without_cache_interaction(self):
        """workspace_id validation must short-circuit before any cache access."""
        svc, _, _ = self._make_service()
        with pytest.raises(RetrievalError):
            svc.search(RetrievalQuery(text="q", workspace_id="", top_k=5))

    def test_cache_hit_returns_correct_chunk_data(self):
        result_doc = VectorSearchResult(
            id="chunk-42",
            vector=_make_vector(),
            metadata={
                "workspace_id": "ws-a",
                "document_id": "doc-XYZ",
                "text": "cached text",
            },
            distance=0.05,
        )
        svc, _, _ = self._make_service(search_results=[result_doc])
        q = self._query("ws-a")
        first = svc.search(q)
        second = svc.search(q)
        assert second[0].id == "chunk-42"
        assert second[0].text == "cached text"
        assert second[0].document_id == "doc-XYZ"
        assert first == second

    def test_document_scope_isolation_and_hit(self):
        """Document scopes must hit when identical and isolate different scopes."""
        svc, _, mock_vs = self._make_service()
        q_doc_a = RetrievalQuery(
            text="what is KIP?",
            workspace_id="ws-a",
            top_k=5,
            document_id="doc-A",
        )
        q_doc_b = RetrievalQuery(
            text="what is KIP?",
            workspace_id="ws-a",
            top_k=5,
            document_id="doc-B",
        )
        q_unrestricted = RetrievalQuery(
            text="what is KIP?",
            workspace_id="ws-a",
            top_k=5,
            document_id=None,
        )

        # 1. Search doc-A (miss -> calls vector store)
        svc.search(q_doc_a)
        assert mock_vs.search.call_count == 1
        assert mock_vs.search.call_args[1].get("document_id") == "doc-A"

        # 2. Search doc-A again (hit -> does not call vector store)
        svc.search(q_doc_a)
        assert mock_vs.search.call_count == 1

        # 3. Search doc-B (miss -> calls vector store)
        svc.search(q_doc_b)
        assert mock_vs.search.call_count == 2
        assert mock_vs.search.call_args[1].get("document_id") == "doc-B"

        # 4. Search unrestricted (miss -> calls vector store)
        svc.search(q_unrestricted)
        assert mock_vs.search.call_count == 3
        assert mock_vs.search.call_args[1].get("document_id") is None

        # 5. Search unrestricted again (hit -> does not call vector store)
        svc.search(q_unrestricted)
        assert mock_vs.search.call_count == 3

    def test_payload_filter_isolation_and_hit(self):
        """Different payload filters must isolate cache; identical filters hit."""
        svc, _, mock_vs = self._make_service()
        q_filter_1 = RetrievalQuery(
            text="what is KIP?",
            workspace_id="ws-a",
            top_k=5,
            filters={"category": "ai"},
        )
        q_filter_2 = RetrievalQuery(
            text="what is KIP?",
            workspace_id="ws-a",
            top_k=5,
            filters={"category": "finance"},
        )

        svc.search(q_filter_1)
        assert mock_vs.search.call_count == 1

        # Identical filter hits cache
        svc.search(q_filter_1)
        assert mock_vs.search.call_count == 1

        # Different filter misses cache
        svc.search(q_filter_2)
        assert mock_vs.search.call_count == 2

    def test_cache_hit_preserves_ordering_and_filters(self):
        """Cache hit must return chunks in exact original rank order."""
        c1 = VectorSearchResult(
            id="c1",
            vector=_make_vector(),
            metadata={"workspace_id": "ws-a", "document_id": "doc-1", "text": "rank 1"},
            distance=0.01,
        )
        c2 = VectorSearchResult(
            id="c2",
            vector=_make_vector(),
            metadata={"workspace_id": "ws-a", "document_id": "doc-1", "text": "rank 2"},
            distance=0.05,
        )
        c3 = VectorSearchResult(
            id="c3",
            vector=_make_vector(),
            metadata={"workspace_id": "ws-a", "document_id": "doc-1", "text": "rank 3"},
            distance=0.10,
        )

        svc, _, _ = self._make_service(search_results=[c1, c2, c3])
        q = RetrievalQuery(
            text="query",
            workspace_id="ws-a",
            top_k=3,
            document_id="doc-1",
        )

        miss_results = svc.search(q)
        hit_results = svc.search(q)

        assert len(hit_results) == 3
        assert [r.id for r in hit_results] == ["c1", "c2", "c3"]
        assert [r.score for r in hit_results] == [0.01, 0.05, 0.10]
        assert [r.text for r in hit_results] == ["rank 1", "rank 2", "rank 3"]
        assert miss_results == hit_results


# ===========================================================================
# Invalidation integration tests (mutation lifecycle wiring)
# ===========================================================================


class TestCacheInvalidationIntegration:
    """Verifies that indexing and deletion invalidate the search cache."""

    def test_indexing_invalidates_workspace_search_cache(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put(
            "ws-test",
            "test-col",
            _make_vector(),
            5,
            None,
            [_make_search_result("ws-test")],
        )
        assert len(cache) == 1

        mock_chunker = create_autospec(ChunkingService)
        from app.services.chunking.models import Chunk

        mock_chunker.chunk_document.return_value = [
            Chunk(
                id="c1",
                document_id="doc-new",
                text="new text",
                index=0,
                character_count=8,
            )
        ]

        from app.services.embeddings.service import EmbeddingService

        mock_emb_svc = create_autospec(EmbeddingService)
        mock_emb_svc.embed_chunks.return_value = [
            Embedding(
                source_id="c1",
                vector=_make_vector(),
                dimensions=_DIM,
                metadata={},
            )
        ]

        mock_vs = create_autospec(VectorStoreService)
        mock_vs.document_exists.return_value = False
        mock_vs.list_documents.return_value = []
        mock_vs.count.return_value = 0

        indexing_service = DocumentIndexingService(
            chunking_service=mock_chunker,
            embedding_service=mock_emb_svc,
            vector_store_service=mock_vs,
            search_cache=cache,
        )

        from datetime import datetime

        doc = Document(
            id="doc-new",
            filename="test.txt",
            media_type="text/plain",
            text="new text",
            metadata={},
            ingested_at=datetime.now(UTC),
        )

        result = indexing_service.index_document(doc, workspace_id="ws-test")
        assert result.chunks_indexed == 1
        # Search cache for ws-test must have been invalidated
        assert len(cache) == 0

    def test_indexing_does_not_invalidate_other_workspace(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put(
            "ws-a",
            "test-col",
            _make_vector(),
            5,
            None,
            [_make_search_result("ws-a")],
        )
        cache.put(
            "ws-b",
            "test-col",
            _make_vector(),
            5,
            None,
            [_make_search_result("ws-b")],
        )
        assert len(cache) == 2

        mock_chunker = create_autospec(ChunkingService)
        from app.services.chunking.models import Chunk

        mock_chunker.chunk_document.return_value = [
            Chunk(
                id="c1",
                document_id="doc-new",
                text="new text",
                index=0,
                character_count=8,
            )
        ]

        from app.services.embeddings.service import EmbeddingService

        mock_emb_svc = create_autospec(EmbeddingService)
        mock_emb_svc.embed_chunks.return_value = [
            Embedding(
                source_id="c1",
                vector=_make_vector(),
                dimensions=_DIM,
                metadata={},
            )
        ]

        mock_vs = create_autospec(VectorStoreService)
        mock_vs.document_exists.return_value = False
        mock_vs.list_documents.return_value = []
        mock_vs.count.return_value = 0

        indexing_service = DocumentIndexingService(
            chunking_service=mock_chunker,
            embedding_service=mock_emb_svc,
            vector_store_service=mock_vs,
            search_cache=cache,
        )

        from datetime import datetime

        doc = Document(
            id="doc-new",
            filename="test.txt",
            media_type="text/plain",
            text="new text",
            metadata={},
            ingested_at=datetime.now(UTC),
        )

        indexing_service.index_document(doc, workspace_id="ws-a")

        # ws-a was evicted, but ws-b remains cached
        assert cache.get("ws-a", "test-col", _make_vector(), 5, None) is None
        assert cache.get("ws-b", "test-col", _make_vector(), 5, None) is not None

    def test_vector_store_deletion_invalidates_workspace_search_cache(self):
        cache = SearchCache(capacity=32, ttl_seconds=60)
        cache.put(
            "ws-del",
            "test-col",
            _make_vector(),
            5,
            None,
            [_make_search_result("ws-del")],
        )
        assert len(cache) == 1

        mock_manager = MagicMock()
        vs_svc = VectorStoreService(manager=mock_manager, search_cache=cache)
        vs_svc.delete_document("doc-del", workspace_id="ws-del")

        mock_manager.provider.delete_document.assert_called_once_with(
            document_id="doc-del", workspace_id="ws-del"
        )
        # Cache for ws-del must be evicted
        assert len(cache) == 0
