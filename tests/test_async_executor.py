"""Tests for async_executor and endpoint-level timeout/non-blocking behavior.

Covers:
  - run_blocking() successfully runs sync callables in a thread pool
  - run_blocking() enforces timeouts and raises asyncio.TimeoutError
  - Concurrent calls are served concurrently (event loop not blocked)
  - Retrieval endpoint returns HTTP 504 on timeout
  - RAG endpoint returns HTTP 504 on timeout
  - Thread-pool workers are bounded and re-used (no unbounded leak)

Note: async tests use asyncio.run() directly — no pytest-asyncio dependency.
"""

from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import patch

import pytest

# --- Async executor unit tests -----------------------------------------------

@pytest.fixture(autouse=True)
def reset_executor():
    """Reset the module-level executor singleton between tests."""
    import app.core.async_executor as ae

    original = ae._executor
    ae._executor = None
    yield
    if ae._executor is not None:
        ae._executor.shutdown(wait=False)
    ae._executor = original


def test_run_blocking_returns_value():
    """run_blocking should return the callable's return value."""
    from app.core.async_executor import run_blocking

    result = asyncio.run(run_blocking(lambda: 42))
    assert result == 42


def test_run_blocking_passes_args():
    """run_blocking should forward positional arguments to the callable."""
    from app.core.async_executor import run_blocking

    result = asyncio.run(run_blocking(lambda x, y: x + y, 3, 7))
    assert result == 10


def test_run_blocking_runs_in_thread():
    """run_blocking callable should NOT run on the event-loop thread."""
    import threading

    from app.core.async_executor import run_blocking

    main_thread = threading.current_thread()
    call_thread: list[threading.Thread] = []

    def get_thread() -> threading.Thread:
        call_thread.append(threading.current_thread())
        return threading.current_thread()

    asyncio.run(run_blocking(get_thread))
    assert call_thread[0] is not main_thread


def test_run_blocking_timeout_raises():
    """run_blocking should raise asyncio.TimeoutError when callable exceeds timeout."""
    from app.core.async_executor import run_blocking

    def slow_fn() -> None:
        time.sleep(5)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_blocking(slow_fn, timeout=0.05))


def test_run_blocking_no_timeout_completes():
    """run_blocking without timeout should complete normally."""
    from app.core.async_executor import run_blocking

    def fast_fn() -> str:
        return "done"

    result = asyncio.run(run_blocking(fast_fn, timeout=None))
    assert result == "done"


def test_run_blocking_propagates_exception():
    """run_blocking should re-raise exceptions from the callable."""
    from app.core.async_executor import run_blocking

    def failing_fn() -> None:
        raise ValueError("deliberate error")

    with pytest.raises(ValueError, match="deliberate error"):
        asyncio.run(run_blocking(failing_fn))


def test_concurrent_calls_run_truly_parallel():
    """Concurrent run_blocking calls should execute in parallel, not serially.

    Each task sleeps 0.1 s. If they ran serially total time >= 0.4 s.
    In a thread pool they should complete in ~0.1 s + scheduling overhead.
    """
    from app.core.async_executor import run_blocking

    n = 4
    sleep_s = 0.1

    async def run_parallel() -> float:
        tasks = [run_blocking(time.sleep, sleep_s, max_workers=n) for _ in range(n)]
        t0 = time.perf_counter()
        await asyncio.gather(*tasks)
        return time.perf_counter() - t0

    wall_clock = asyncio.run(run_parallel())

    assert wall_clock < sleep_s * 2.5, (
        f"Expected parallel completion ~{sleep_s:.2f}s, got {wall_clock:.3f}s — "
        "event loop may have been blocked"
    )


def test_set_executor_replaces_pool():
    """set_executor should allow injecting a custom executor."""
    import app.core.async_executor as ae
    from app.core.async_executor import run_blocking, set_executor

    custom_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-pool")
    set_executor(custom_executor)
    assert ae._executor is custom_executor

    result = asyncio.run(run_blocking(lambda: "custom"))
    assert result == "custom"
    custom_executor.shutdown(wait=False)


# --- Endpoint timeout tests ---------------------------------------------------


@pytest.fixture
def kip_test_client():
    """Minimal TestClient with dependency overrides for endpoint timeout tests."""
    import hashlib

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.embeddings.base import EmbeddingProvider
    from app.services.embeddings.manager import EmbeddingManager
    from app.services.embeddings.models import Embedding, EmbeddingRequest
    from app.services.embeddings.service import EmbeddingService
    from app.services.llm.base import LLMProvider
    from app.services.llm.manager import LLMManager
    from app.services.llm.models import LLMRequest, LLMResponse
    from app.services.llm.service import LLMService, get_llm_service
    from app.services.rag.service import RAGService, get_rag_service
    from app.services.retrieval.service import RetrievalService, get_retrieval_service
    from app.services.vector_store.manager import VectorStoreManager
    from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
    from app.services.vector_store.service import VectorStoreService

    _DIMS = 8

    def _tv(text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [d[i] / 255.0 for i in range(_DIMS)]

    class FakeEmbedProvider(EmbeddingProvider):
        @property
        def name(self) -> str:
            return "fake"

        def embed(self, request: EmbeddingRequest) -> list[Embedding]:
            return [
                Embedding(
                    source_id=inp.source_id,
                    vector=_tv(inp.text),
                    dimensions=_DIMS,
                    metadata=inp.metadata.copy(),
                    provider="fake",
                    model="fake-v1",
                )
                for inp in request.inputs
            ]

    class FakeLLMProvider(LLMProvider):
        @property
        def name(self) -> str:
            return "fake-llm"

        def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(
                content="Fake answer",
                model="fake-llm-v1",
                provider="fake-llm",
            )

    col = f"to_test_{os.getpid()}"
    emb_svc = EmbeddingService(manager=EmbeddingManager(provider=FakeEmbedProvider()))
    vs_provider = ChromaVectorStoreProvider(collection_name=col, persist_directory=None)
    vs_svc = VectorStoreService(manager=VectorStoreManager(provider=vs_provider))
    retrieval_svc = RetrievalService(
        embedding_service=emb_svc, vector_store_service=vs_svc
    )
    llm_svc = LLMService(manager=LLMManager(provider=FakeLLMProvider()))
    rag_svc = RAGService(retrieval_service=retrieval_svc, llm_service=llm_svc)

    app.dependency_overrides[get_retrieval_service] = lambda: retrieval_svc
    app.dependency_overrides[get_rag_service] = lambda: rag_svc
    app.dependency_overrides[get_llm_service] = lambda: llm_svc

    client = TestClient(
        app,
        headers={"X-KIP-Workspace-ID": "timeout-test-workspace"},
        raise_server_exceptions=False,
    )
    yield client
    app.dependency_overrides.clear()


def test_retrieval_endpoint_timeout_returns_504(kip_test_client):
    """Retrieval endpoint should return HTTP 504 when service call times out."""

    async def raise_timeout(*args: Any, **kwargs: Any) -> None:
        raise TimeoutError

    _patch_target = "app.api.v1.endpoints.retrieval.run_blocking"
    with patch(_patch_target, side_effect=raise_timeout):
        resp = kip_test_client.post(
            "/api/v1/retrieval/search",
            json={"query": "test query"},
        )

    assert resp.status_code == 504
    body = resp.json()
    # FastAPI HTTPException serialises to {"detail": "..."} or the body may be
    # wrapped differently when raise_server_exceptions=False — check both shapes.
    detail_text = (
        body.get("detail") or body.get("message") or str(body)
    ).lower()
    assert "timed out" in detail_text, f"Unexpected body: {body}"


def test_rag_endpoint_timeout_returns_504(kip_test_client):
    """RAG endpoint should return HTTP 504 when service call times out."""

    async def raise_timeout(*args: Any, **kwargs: Any) -> None:
        raise TimeoutError

    with patch("app.api.v1.endpoints.rag.run_blocking", side_effect=raise_timeout):
        resp = kip_test_client.post(
            "/api/v1/rag/answer",
            json={"query": "what is KIP?"},
        )

    assert resp.status_code == 504
    body = resp.json()
    detail_text = (
        body.get("detail") or body.get("message") or str(body)
    ).lower()
    assert "timed out" in detail_text, f"Unexpected body: {body}"


def test_retrieval_endpoint_success_does_not_504(kip_test_client):
    """Retrieval endpoint should return 200 when service completes in time."""
    resp = kip_test_client.post(
        "/api/v1/retrieval/search",
        json={"query": "test query"},
    )
    assert resp.status_code == 200
    assert "results" in resp.json()


def test_rag_endpoint_success_does_not_504(kip_test_client):
    """RAG endpoint should return 200 when service completes in time."""
    resp = kip_test_client.post(
        "/api/v1/rag/answer",
        json={"query": "what is KIP?"},
    )
    assert resp.status_code == 200
    assert "answer" in resp.json()


# --- Timeout configuration tests ---------------------------------------------


def test_timeout_settings_defaults():
    """Settings defaults for timeout and executor are sensible."""
    from app.core.config import Settings

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.embedding_timeout_seconds == 15.0
    assert s.llm_timeout_seconds == 30.0
    assert s.retrieval_executor_workers == 4


def test_timeout_settings_env_override(monkeypatch: pytest.MonkeyPatch):
    """Timeout settings should be overridable via environment variables."""
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "5.0")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "20.0")
    monkeypatch.setenv("RETRIEVAL_EXECUTOR_WORKERS", "8")

    from app.core.config import Settings

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.embedding_timeout_seconds == 5.0
    assert s.llm_timeout_seconds == 20.0
    assert s.retrieval_executor_workers == 8


def test_shutdown_executor():
    """shutdown_executor should cleanly terminate the process-level pool."""
    import app.core.async_executor as ae
    from app.core.async_executor import _get_executor, shutdown_executor

    executor = _get_executor(max_workers=2)
    assert ae._executor is not None
    assert not executor._shutdown

    shutdown_executor(wait=False)
    assert ae._executor is None
    assert executor._shutdown
