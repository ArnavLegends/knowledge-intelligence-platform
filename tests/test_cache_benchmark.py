"""Controlled performance benchmark for KIP caching layer.

Methodology
-----------
- All providers are deterministic mocks (no real Gemini or Qdrant calls).
- Latency figures measure Python call overhead only; they are NOT production
  latency estimates.
- The benchmark's purpose is to verify that:
  (a) provider call counts drop to zero on repeated cache-hit workloads, and
  (b) the per-call overhead of a cache hit is measurably smaller than a mock
      provider call (which sleeps for a fixed duration to simulate network I/O).
- Results are printed to stdout and asserted on call-count reductions.
  No latency assertions are made, to avoid flaky timing-dependent CI failures.

Sample sizes
------------
WARMUP_QUERIES = 10  (establish cache entries)
REPEAT_QUERIES = 100  (measure hit-path performance)
UNIQUE_QUERIES = 50   (measure miss-path comparison)
"""

from __future__ import annotations

import statistics
import time
from unittest.mock import MagicMock

from app.core.config import Settings
from app.services.cache.embedding_cache import EmbeddingCache
from app.services.cache.search_cache import SearchCache
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.manager import EmbeddingManager
from app.services.embeddings.models import Embedding, EmbeddingInput, EmbeddingRequest
from app.services.retrieval.models import RetrievalQuery
from app.services.retrieval.service import RetrievalService
from app.services.vector_store.models import VectorSearchResult
from app.services.vector_store.service import VectorStoreService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DIM = 8
_FAKE_PROVIDER_SLEEP_S = 0.001  # 1 ms simulated network latency
_WARMUP_QUERIES = 10
_REPEAT_QUERIES = 100
_UNIQUE_QUERIES = 50


# ---------------------------------------------------------------------------
# Fake providers with simulated latency
# ---------------------------------------------------------------------------


class SlowFakeEmbeddingProvider(EmbeddingProvider):
    """Fake provider that sleeps _FAKE_PROVIDER_SLEEP_S to simulate I/O."""

    def __init__(self) -> None:
        self._call_count = 0

    @property
    def name(self) -> str:
        return "slow-fake"

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        time.sleep(_FAKE_PROVIDER_SLEEP_S)
        self._call_count += 1
        return [
            Embedding(
                source_id=inp.source_id,
                vector=[0.1] * _DIM,
                dimensions=_DIM,
                metadata=inp.metadata.copy(),
                provider="slow-fake",
                model=request.model or "slow-fake-v1",
            )
            for inp in request.inputs
        ]

    @property
    def call_count(self) -> int:
        return self._call_count


def _make_search_result(ws: str = "ws-bench") -> list[VectorSearchResult]:
    return [
        VectorSearchResult(
            id="c1",
            vector=[0.1] * _DIM,
            metadata={"workspace_id": ws, "document_id": "d1", "text": "bench text"},
            distance=0.05,
        )
    ]


# ---------------------------------------------------------------------------
# Benchmark: embedding cache
# ---------------------------------------------------------------------------


class TestEmbeddingCacheBenchmark:
    """Verify provider-call reduction for repeated single-query workloads."""

    def _setup(self) -> tuple[EmbeddingManager, SlowFakeEmbeddingProvider]:
        provider = SlowFakeEmbeddingProvider()
        cache = EmbeddingCache(capacity=_WARMUP_QUERIES + 10)
        settings = Settings(
            embedding_provider="gemini",
            embedding_model="bench-model",
            embedding_dimensions=_DIM,
        )
        manager = EmbeddingManager(
            settings=settings, provider=provider, embedding_cache=cache
        )
        return manager, provider

    def _single_req(self, text: str) -> EmbeddingRequest:
        return EmbeddingRequest(
            inputs=[EmbeddingInput(source_id="query", text=text)],
            model="bench-model",
        )

    def test_provider_calls_reduced_on_repeated_queries(self):
        manager, provider = self._setup()

        # --- Warmup: embed unique queries, populating the cache ---
        queries = [f"benchmark query number {i}" for i in range(_WARMUP_QUERIES)]
        for q in queries:
            manager.embed(self._single_req(q))

        calls_after_warmup = provider.call_count
        assert calls_after_warmup == _WARMUP_QUERIES, (
            f"Expected {_WARMUP_QUERIES} provider calls during warmup, "
            f"got {calls_after_warmup}"
        )

        # --- Repeated phase: re-embed the same queries (cache hits) ---
        hit_times: list[float] = []
        for _ in range(_REPEAT_QUERIES):
            q = queries[_ % _WARMUP_QUERIES]
            t0 = time.perf_counter()
            manager.embed(self._single_req(q))
            hit_times.append((time.perf_counter() - t0) * 1000)

        calls_after_hits = provider.call_count
        assert calls_after_hits == _WARMUP_QUERIES, (
            f"Provider must not be called during cache-hit phase. "
            f"Expected {_WARMUP_QUERIES}, got {calls_after_hits}"
        )

        s = manager.embedding_cache.stats()
        assert s.hits == _REPEAT_QUERIES
        assert s.misses == _WARMUP_QUERIES

        # --- Miss phase: embed unique queries not in cache ---
        miss_times: list[float] = []
        for i in range(_UNIQUE_QUERIES):
            t0 = time.perf_counter()
            manager.embed(self._single_req(f"unseen query {i}"))
            miss_times.append((time.perf_counter() - t0) * 1000)

        calls_after_misses = provider.call_count
        assert calls_after_misses == _WARMUP_QUERIES + _UNIQUE_QUERIES

        # Report (not asserted — avoids flaky CI)
        hit_p95 = sorted(hit_times)[int(len(hit_times) * 0.95)]
        miss_p95 = sorted(miss_times)[int(len(miss_times) * 0.95)]
        print(
            f"\n[EmbeddingCache Benchmark]\n"
            f"  Warmup calls (misses):   {_WARMUP_QUERIES}\n"
            f"  Repeat calls (hits):     {_REPEAT_QUERIES}\n"
            f"  Unique miss calls:       {_UNIQUE_QUERIES}\n"
            f"  Provider calls (warmup): {calls_after_warmup}\n"
            f"  Provider calls (hits):   0 (confirmed)\n"
            f"  Provider calls (misses): {_UNIQUE_QUERIES}\n"
            f"  Hit p50 latency:         {statistics.median(hit_times):.2f} ms\n"
            f"  Hit p95 latency:         {hit_p95:.2f} ms\n"
            f"  Miss p50 latency:        {statistics.median(miss_times):.2f} ms\n"
            f"  Miss p95 latency:        {miss_p95:.2f} ms\n"
            f"  Cache stats:             {s}\n"
        )

        # Hit path must be faster than miss path on average (mock sleep dominates)
        assert statistics.mean(hit_times) < statistics.mean(miss_times), (
            "Cache hit path should be faster than the mock provider path"
        )


# ---------------------------------------------------------------------------
# Benchmark: search cache
# ---------------------------------------------------------------------------


class TestSearchCacheBenchmark:
    """Verify Qdrant call reduction for repeated equivalent searches."""

    def _setup(self) -> tuple[RetrievalService, MagicMock]:
        from app.services.embeddings.service import EmbeddingService

        mock_emb_svc = MagicMock(spec=EmbeddingService)
        mock_emb_svc.embed_texts.return_value = [
            Embedding(
                source_id="query",
                vector=[0.1] * _DIM,
                dimensions=_DIM,
                metadata={},
            )
        ]

        mock_vs = MagicMock(spec=VectorStoreService)

        # Simulate Qdrant latency on real calls
        def _slow_search(**kwargs):
            time.sleep(_FAKE_PROVIDER_SLEEP_S)
            return _make_search_result("ws-bench")

        mock_vs.search.side_effect = _slow_search

        cache = SearchCache(capacity=_WARMUP_QUERIES + 10, ttl_seconds=60.0)
        settings = Settings(
            qdrant_collection="bench-col",
            search_cache_capacity=_WARMUP_QUERIES + 10,
            search_cache_ttl_seconds=60.0,
        )
        svc = RetrievalService(
            embedding_service=mock_emb_svc,
            vector_store_service=mock_vs,
            settings=settings,
            search_cache=cache,
        )
        return svc, mock_vs

    def test_vector_store_calls_reduced_on_repeated_searches(self):
        svc, mock_vs = self._setup()

        # Warmup: unique queries
        # (embedding mock always returns same vector, so these differ only by text
        #  normalization — but since embed_texts mock always returns [0.1]*_DIM,
        #  all searches have the same cache key.  We test with top_k variation.)
        warmup_top_ks = list(range(1, _WARMUP_QUERIES + 1))
        for k in warmup_top_ks:
            svc.search(
                RetrievalQuery(text="bench query", workspace_id="ws-bench", top_k=k)
            )

        calls_after_warmup = mock_vs.search.call_count
        assert calls_after_warmup == _WARMUP_QUERIES

        # Repeat: same top_k values → cache hits → zero new VS calls
        hit_times: list[float] = []
        for i in range(_REPEAT_QUERIES):
            k = warmup_top_ks[i % _WARMUP_QUERIES]
            t0 = time.perf_counter()
            svc.search(
                RetrievalQuery(text="bench query", workspace_id="ws-bench", top_k=k)
            )
            hit_times.append((time.perf_counter() - t0) * 1000)

        calls_after_hits = mock_vs.search.call_count
        assert calls_after_hits == _WARMUP_QUERIES, (
            f"VS must not be called during hit phase; got {calls_after_hits}"
        )

        s = svc.search_cache.stats()
        assert s.hits == _REPEAT_QUERIES
        assert s.misses == _WARMUP_QUERIES

        hit_p95 = sorted(hit_times)[int(len(hit_times) * 0.95)]
        print(
            f"\n[SearchCache Benchmark]\n"
            f"  Warmup calls (misses):      {_WARMUP_QUERIES}\n"
            f"  Repeat calls (hits):        {_REPEAT_QUERIES}\n"
            f"  VS calls (warmup):          {calls_after_warmup}\n"
            f"  VS calls (hits):            0 (confirmed)\n"
            f"  Hit p50 latency:            {statistics.median(hit_times):.2f} ms\n"
            f"  Hit p95 latency:            {hit_p95:.2f} ms\n"
            f"  Cache stats:                {s}\n"
        )
