"""Tests for the KIP evaluation framework."""

import json

from evaluation.models import (
    AnswerMetrics,
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkResult,
    BenchmarkRunConfig,
    CaseResult,
    RetrievalMetrics,
)

# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_benchmark_case_valid():
    case = BenchmarkCase(
        id="test-001",
        question="What is KIP?",
        reference_answer="Knowledge Intelligence Platform",
        expected_keywords=["KIP", "platform"],
    )
    assert case.id == "test-001"
    assert case.expected_keywords == ["KIP", "platform"]


def test_benchmark_case_minimal():
    case = BenchmarkCase(id="x", question="Q?")
    assert case.reference_answer is None
    assert case.expected_document_ids == []
    assert case.expected_keywords == []
    assert case.metadata == {}


def test_benchmark_dataset_valid():
    ds = BenchmarkDataset(
        version="v1",
        description="Test dataset",
        cases=[BenchmarkCase(id="c1", question="Q?")],
    )
    assert ds.version == "v1"
    assert len(ds.cases) == 1


def test_benchmark_dataset_empty_cases():
    ds = BenchmarkDataset(version="v1", cases=[])
    assert ds.cases == []


# ---------------------------------------------------------------------------
# Benchmark dataset loading
# ---------------------------------------------------------------------------


def test_baseline_dataset_loads():
    """The committed baseline dataset must be loadable and well-formed."""
    import pathlib

    path = pathlib.Path("benchmarks/kip_v1_baseline.json")
    assert path.exists(), "Baseline benchmark file must exist"
    data = json.loads(path.read_text())
    ds = BenchmarkDataset(**data)
    assert len(ds.cases) >= 1
    for case in ds.cases:
        assert case.id
        assert case.question


def test_baseline_dataset_case_ids_unique():
    import pathlib

    path = pathlib.Path("benchmarks/kip_v1_baseline.json")
    data = json.loads(path.read_text())
    ds = BenchmarkDataset(**data)
    ids = [c.id for c in ds.cases]
    assert len(ids) == len(set(ids)), "Case IDs must be unique"


# ---------------------------------------------------------------------------
# Retrieval metric computation
# ---------------------------------------------------------------------------


def _make_retrieval_metrics(hit=True, rr=1.0, latency=5.0):
    return RetrievalMetrics(
        case_id="c1",
        hit=hit,
        reciprocal_rank=rr,
        retrieved_count=3,
        expected_count=1,
        retrieved_doc_ids=["doc-a"],
        expected_doc_ids=["doc-a"],
        retrieval_latency_ms=latency,
    )


def _make_answer_metrics(coverage=1.0):
    return AnswerMetrics(
        case_id="c1",
        has_answer=True,
        has_context=True,
        keyword_hits=["KIP"],
        keyword_misses=[],
        keyword_coverage=coverage,
    )


def _make_case_result(case_id="c1", hit=True, rr=1.0, coverage=1.0, total_ms=50.0):
    return CaseResult(
        case_id=case_id,
        question="Q?",
        answer="The answer.",
        sources_count=1,
        retrieval=_make_retrieval_metrics(hit=hit, rr=rr),
        answer_metrics=_make_answer_metrics(coverage=coverage),
        total_latency_ms=total_ms,
    )


def test_benchmark_result_hit_rate():
    config = BenchmarkRunConfig(
        benchmark_version="v1",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )
    results = [
        _make_case_result("c1", hit=True),
        _make_case_result("c2", hit=False),
        _make_case_result("c3", hit=True),
    ]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=config,
        results=results,
    )
    assert run_result.total_cases == 3
    assert abs(run_result.hit_rate - 2 / 3) < 1e-9


def test_benchmark_result_mrr():
    config = BenchmarkRunConfig(
        benchmark_version="v1",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )
    results = [
        _make_case_result("c1", rr=1.0),
        _make_case_result("c2", rr=0.5),
    ]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=config,
        results=results,
    )
    assert abs(run_result.mean_reciprocal_rank - 0.75) < 1e-9


def test_benchmark_result_empty():
    config = BenchmarkRunConfig(
        benchmark_version="v1",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=config,
        results=[],
    )
    assert run_result.total_cases == 0
    assert run_result.hit_rate == 0.0


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def test_benchmark_result_serializable():
    config = BenchmarkRunConfig(
        benchmark_version="v1",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )
    results = [_make_case_result()]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=config,
        results=results,
    )
    serialized = run_result.model_dump_json()
    parsed = json.loads(serialized)
    assert parsed["total_cases"] == 1
    assert "hit_rate" in parsed
    assert "mean_reciprocal_rank" in parsed


# ---------------------------------------------------------------------------
# Deterministic evaluation runner (no external services)
# ---------------------------------------------------------------------------


def test_evaluation_runner_deterministic(e2e_pipeline):
    """EvaluationRunner produces consistent results with deterministic services."""
    import uuid

    from evaluation.models import BenchmarkRunConfig
    from evaluation.runner import EvaluationRunner

    from app.services.embeddings.manager import EmbeddingManager
    from app.services.embeddings.service import EmbeddingService
    from app.services.llm.manager import LLMManager
    from app.services.llm.service import LLMService
    from app.services.rag.service import RAGService
    from app.services.retrieval.service import RetrievalService
    from app.services.vector_store.manager import VectorStoreManager
    from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
    from app.services.vector_store.service import VectorStoreService

    # Build an isolated pipeline using the same deterministic fakes as conftest.
    from conftest import DeterministicEmbeddingProvider, DeterministicLLMProvider

    collection_name = f"eval_test_{uuid.uuid4().hex[:12]}"
    emb_provider = DeterministicEmbeddingProvider()
    emb_service = EmbeddingService(manager=EmbeddingManager(provider=emb_provider))
    vs_provider = ChromaVectorStoreProvider(
        collection_name=collection_name, persist_directory=None
    )
    vs_service = VectorStoreService(manager=VectorStoreManager(provider=vs_provider))
    retrieval_service = RetrievalService(
        embedding_service=emb_service,
        vector_store_service=vs_service,
    )
    llm_service = LLMService(manager=LLMManager(provider=DeterministicLLMProvider()))
    rag_service = RAGService(
        retrieval_service=retrieval_service,
        llm_service=llm_service,
    )

    config = BenchmarkRunConfig(
        benchmark_version="v1-test",
        llm_provider="fake",
        llm_model="fake-model",
        embedding_provider="fake",
        embedding_model="fake-embed",
        retrieval_top_k=3,
        chunk_size=1000,
        chunk_overlap=200,
        live_llm_available=False,
    )

    dataset = BenchmarkDataset(
        version="v1-test",
        cases=[
            BenchmarkCase(
                id="t-001",
                question="What does KIP stand for?",
                expected_keywords=["KIP"],
            ),
        ],
    )

    runner = EvaluationRunner(
        rag_service=rag_service,
        retrieval_service=retrieval_service,
        config=config,
    )
    result = runner.evaluate_dataset(dataset)

    assert result.total_cases == 1
    assert result.run_id
    assert result.timestamp
    # Results must be JSON-serializable
    import json

    json.loads(result.model_dump_json())


def test_evaluation_runner_no_llm_credentials():
    """Runner handles missing LLM credentials gracefully without crashing."""
    from unittest.mock import MagicMock

    from evaluation.models import BenchmarkRunConfig
    from evaluation.runner import EvaluationRunner

    mock_rag = MagicMock()
    mock_rag.answer.side_effect = Exception("No API key configured")
    mock_retrieval = MagicMock()
    mock_retrieval.search.return_value = []

    config = BenchmarkRunConfig(
        benchmark_version="v1",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
        live_llm_available=False,
    )
    dataset = BenchmarkDataset(
        version="v1",
        cases=[BenchmarkCase(id="c1", question="Q?")],
    )
    runner = EvaluationRunner(
        rag_service=mock_rag,
        retrieval_service=mock_retrieval,
        config=config,
    )
    result = runner.evaluate_dataset(dataset)
    assert result.total_cases == 1
    # Answer should contain error note, not crash
    assert "Evaluation Error" in result.case_results[0].answer
