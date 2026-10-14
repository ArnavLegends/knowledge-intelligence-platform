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
# Benchmark dataset loading — v1.0 historical dataset
# ---------------------------------------------------------------------------


def test_baseline_dataset_loads():
    """The committed v1.0 baseline dataset must be loadable and well-formed."""
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
# v1.1 benchmark dataset loading and ground-truth validation
# ---------------------------------------------------------------------------


def test_v11_baseline_dataset_loads():
    """The v1.1 baseline dataset must be loadable and well-formed."""
    import pathlib

    path = pathlib.Path("benchmarks/kip_v1_1_baseline.json")
    assert path.exists(), "v1.1 baseline benchmark file must exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    ds = BenchmarkDataset(**data)
    assert ds.version == "v1.1-baseline"
    assert len(ds.cases) >= 1


def test_v11_baseline_all_cases_have_expected_document_ids():
    """All v1.1 cases must have populated expected_document_ids."""
    import pathlib

    path = pathlib.Path("benchmarks/kip_v1_1_baseline.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    ds = BenchmarkDataset(**data)
    for case in ds.cases:
        assert case.expected_document_ids, (
            f"Case {case.id!r} has empty expected_document_ids — "
            "all v1.1 cases must be labelled for retrieval evaluation"
        )


def test_v11_baseline_case_ids_unique():
    """v1.1 case IDs must be unique."""
    import pathlib

    path = pathlib.Path("benchmarks/kip_v1_1_baseline.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    ds = BenchmarkDataset(**data)
    ids = [c.id for c in ds.cases]
    assert len(ids) == len(set(ids)), "v1.1 case IDs must be unique"


def test_v11_baseline_document_ids_match_corpus():
    """Document IDs in v1.1 dataset must match SHA-256 of corpus file bytes."""
    import hashlib
    import pathlib

    corpus_dir = pathlib.Path("benchmarks/corpus")
    dataset_path = pathlib.Path("benchmarks/kip_v1_1_baseline.json")

    # Derive actual IDs from the corpus files
    actual_ids = {
        hashlib.sha256(f.read_bytes()).hexdigest() for f in corpus_dir.glob("*.txt")
    }

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    ds = BenchmarkDataset(**data)

    for case in ds.cases:
        for doc_id in case.expected_document_ids:
            assert doc_id in actual_ids, (
                f"Case {case.id!r} references document_id {doc_id!r} "
                "which does not match any file in benchmarks/corpus/"
            )


def test_corpus_files_have_lf_line_endings_only():
    """Corpus files must use LF line endings to ensure stable SHA-256 IDs."""
    import pathlib

    corpus_dir = pathlib.Path("benchmarks/corpus")
    for txt_file in corpus_dir.glob("*.txt"):
        raw = txt_file.read_bytes()
        assert b"\r" not in raw, (
            f"{txt_file.name} contains CR bytes (CRLF line endings). "
            "This would change the SHA-256 document ID. "
            "Corpus files must use LF line endings only."
        )


# ---------------------------------------------------------------------------
# Retrieval metric computation
# ---------------------------------------------------------------------------


def _make_retrieval_metrics(
    hit=True, rr=1.0, latency=5.0, expected_count=1, retrieval_error=None
):
    return RetrievalMetrics(
        case_id="c1",
        hit=hit,
        reciprocal_rank=rr,
        retrieved_count=3,
        expected_count=expected_count,
        retrieved_doc_ids=["doc-a"],
        expected_doc_ids=["doc-a"],
        retrieval_latency_ms=latency,
        retrieval_error=retrieval_error,
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


def _make_case_result(
    case_id="c1",
    hit=True,
    rr=1.0,
    coverage=1.0,
    total_ms=50.0,
    expected_count=1,
    retrieval_error=None,
):
    return CaseResult(
        case_id=case_id,
        question="Q?",
        answer="The answer.",
        sources_count=1,
        retrieval=_make_retrieval_metrics(
            hit=hit,
            rr=rr,
            expected_count=expected_count,
            retrieval_error=retrieval_error,
        ),
        answer_metrics=_make_answer_metrics(coverage=coverage),
        total_latency_ms=total_ms,
    )


def _make_config():
    return BenchmarkRunConfig(
        benchmark_version="v1",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )


def test_benchmark_result_hit_rate():
    results = [
        _make_case_result("c1", hit=True),
        _make_case_result("c2", hit=False),
        _make_case_result("c3", hit=True),
    ]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=_make_config(),
        results=results,
    )
    assert run_result.total_cases == 3
    assert run_result.labelled_cases == 3
    assert abs(run_result.hit_rate - 2 / 3) < 1e-9


def test_benchmark_result_mrr():
    results = [
        _make_case_result("c1", rr=1.0),
        _make_case_result("c2", rr=0.5),
    ]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=_make_config(),
        results=results,
    )
    assert abs(run_result.mean_reciprocal_rank - 0.75) < 1e-9


def test_benchmark_result_empty():
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=_make_config(),
        results=[],
    )
    assert run_result.total_cases == 0
    assert run_result.hit_rate is None
    assert run_result.mean_reciprocal_rank is None


def test_unlabelled_cases_excluded_from_retrieval_metrics():
    """Cases with empty expected_document_ids must not contribute to Hit Rate or MRR."""
    results = [
        _make_case_result("c1", hit=True, rr=1.0, expected_count=1),  # labelled, hit
        _make_case_result("c2", hit=False, rr=0.0, expected_count=0),  # unlabelled
        _make_case_result("c3", hit=False, rr=0.0, expected_count=0),  # unlabelled
    ]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=_make_config(),
        results=results,
    )
    assert run_result.total_cases == 3
    assert run_result.labelled_cases == 1
    # Only 1 labelled case, which is a hit → hit_rate = 1.0
    assert run_result.hit_rate == 1.0
    assert run_result.mean_reciprocal_rank == 1.0


def test_all_unlabelled_produces_none_retrieval_metrics():
    """With zero labelled cases, hit_rate and MRR must be None."""
    results = [
        _make_case_result("c1", expected_count=0),
        _make_case_result("c2", expected_count=0),
    ]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=_make_config(),
        results=results,
    )
    assert run_result.labelled_cases == 0
    assert run_result.hit_rate is None
    assert run_result.mean_reciprocal_rank is None


def test_retrieval_error_is_visible_not_silent_miss():
    """Infrastructure failures must be recorded in retrieval_error,
    not silently zeroed."""
    result = _make_case_result(
        "c1",
        hit=False,
        rr=0.0,
        expected_count=1,
        retrieval_error="RetrievalError: workspace_id is required",
    )
    assert result.retrieval.retrieval_error is not None
    assert "workspace_id" in result.retrieval.retrieval_error


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def test_benchmark_result_serializable():
    results = [_make_case_result()]
    run_result = BenchmarkResult.from_case_results(
        run_id="test-run",
        timestamp="2026-01-01T00:00:00Z",
        config=_make_config(),
        results=results,
    )
    serialized = run_result.model_dump_json()
    parsed = json.loads(serialized)
    assert parsed["total_cases"] == 1
    assert "hit_rate" in parsed
    assert "mean_reciprocal_rank" in parsed
    assert "labelled_cases" in parsed


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

    eval_workspace = "kip-eval-workspace"
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
        evaluation_workspace_id=eval_workspace,
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
    json.loads(result.model_dump_json())


def test_evaluation_runner_workspace_propagated(e2e_pipeline):
    """Runner must pass evaluation_workspace_id to both retrieval and generation."""
    from unittest.mock import MagicMock

    from evaluation.models import BenchmarkRunConfig
    from evaluation.runner import EvaluationRunner

    eval_workspace = "kip-eval-ws-propagation-test"

    mock_retrieval = MagicMock()
    mock_retrieval.search.return_value = []
    mock_rag = MagicMock()
    from app.services.rag.models import RAGResponse

    mock_rag.answer.return_value = RAGResponse(answer="test answer", sources=[])

    config = BenchmarkRunConfig(
        benchmark_version="v1-test",
        evaluation_workspace_id=eval_workspace,
        llm_provider="fake",
        llm_model="fake-model",
        embedding_provider="fake",
        embedding_model="fake-embed",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )

    dataset = BenchmarkDataset(
        version="v1-test",
        cases=[BenchmarkCase(id="p-001", question="Q?")],
    )

    runner = EvaluationRunner(
        rag_service=mock_rag,
        retrieval_service=mock_retrieval,
        config=config,
    )
    runner.evaluate_dataset(dataset)

    # Verify workspace_id was passed to retrieval
    retrieval_call_args = mock_retrieval.search.call_args
    assert retrieval_call_args is not None
    retrieval_query = retrieval_call_args[0][0]
    assert retrieval_query.workspace_id == eval_workspace

    # Verify workspace_id was passed to RAG
    rag_call_args = mock_rag.answer.call_args
    assert rag_call_args is not None
    rag_request = rag_call_args[0][0]
    assert rag_request.workspace_id == eval_workspace


def test_evaluation_runner_retrieval_failure_recorded():
    """Retrieval infrastructure failures must be recorded, not silently zeroed."""
    from unittest.mock import MagicMock

    from evaluation.models import BenchmarkRunConfig
    from evaluation.runner import EvaluationRunner

    mock_retrieval = MagicMock()
    mock_retrieval.search.side_effect = Exception("embedding service unavailable")
    mock_rag = MagicMock()
    from app.services.rag.models import RAGResponse

    mock_rag.answer.return_value = RAGResponse(answer="fallback answer", sources=[])

    config = BenchmarkRunConfig(
        benchmark_version="v1",
        evaluation_workspace_id="kip-eval-workspace",
        llm_provider="fake",
        llm_model="fake-model",
        embedding_provider="fake",
        embedding_model="fake-embed",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )
    dataset = BenchmarkDataset(
        version="v1",
        cases=[
            BenchmarkCase(
                id="e-001",
                question="Q?",
                expected_document_ids=["abc123"],
            )
        ],
    )
    runner = EvaluationRunner(
        rag_service=mock_rag,
        retrieval_service=mock_retrieval,
        config=config,
    )
    result = runner.evaluate_dataset(dataset)

    case = result.case_results[0]
    # retrieval_error must be set — failure is not a silent miss
    assert case.retrieval.retrieval_error is not None
    assert "embedding service unavailable" in case.retrieval.retrieval_error
    # hit must be False (not True from the old degenerate logic)
    assert case.retrieval.hit is False


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
        evaluation_workspace_id="kip-eval-workspace",
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


def test_evaluation_runner_end_to_end_with_indexed_corpus(e2e_pipeline):
    """Runner correctly retrieves from indexed corpus using fake embedding provider."""
    import hashlib
    import uuid

    from evaluation.models import BenchmarkRunConfig
    from evaluation.runner import EvaluationRunner

    from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
    from app.services.chunking.service import ChunkingService
    from app.services.documents.models import Document
    from app.services.embeddings.manager import EmbeddingManager
    from app.services.embeddings.service import EmbeddingService
    from app.services.indexing.service import DocumentIndexingService
    from app.services.llm.manager import LLMManager
    from app.services.llm.service import LLMService
    from app.services.rag.service import RAGService
    from app.services.retrieval.service import RetrievalService
    from app.services.vector_store.manager import VectorStoreManager
    from app.services.vector_store.providers.chroma import ChromaVectorStoreProvider
    from app.services.vector_store.service import VectorStoreService
    from conftest import DeterministicEmbeddingProvider, DeterministicLLMProvider

    eval_workspace = f"kip-eval-e2e-{uuid.uuid4().hex[:8]}"
    collection_name = f"eval_e2e_{uuid.uuid4().hex[:12]}"

    emb_provider = DeterministicEmbeddingProvider()
    emb_service = EmbeddingService(manager=EmbeddingManager(provider=emb_provider))
    vs_provider = ChromaVectorStoreProvider(
        collection_name=collection_name, persist_directory=None
    )
    vs_service = VectorStoreService(manager=VectorStoreManager(provider=vs_provider))
    indexing_service = DocumentIndexingService(
        chunking_service=ChunkingService(
            chunker=FixedSizeChunker(chunk_size=500, chunk_overlap=50)
        ),
        embedding_service=emb_service,
        vector_store_service=vs_service,
    )

    # Index a document whose content matches a known keyword
    doc_content = b"The default chunk size in KIP is 1000 characters with 200 overlap."
    doc_id = hashlib.sha256(doc_content).hexdigest()
    document = Document.create(
        document_id=doc_id,
        filename="test_corpus.txt",
        media_type="text/plain",
        text=doc_content.decode("utf-8"),
    )
    indexing_service.index_document(document, workspace_id=eval_workspace)

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
        benchmark_version="v1-e2e-test",
        evaluation_workspace_id=eval_workspace,
        llm_provider="fake",
        llm_model="fake-model",
        embedding_provider="fake",
        embedding_model="fake-embed",
        retrieval_top_k=3,
        chunk_size=500,
        chunk_overlap=50,
    )
    dataset = BenchmarkDataset(
        version="v1-e2e",
        cases=[
            BenchmarkCase(
                id="e2e-001",
                question="What is the default chunk size?",
                expected_document_ids=[doc_id],
                expected_keywords=["1000"],
            )
        ],
    )

    runner = EvaluationRunner(
        rag_service=rag_service,
        retrieval_service=retrieval_service,
        config=config,
    )
    result = runner.evaluate_dataset(dataset)

    assert result.total_cases == 1
    assert result.labelled_cases == 1
    # The document was indexed and should be retrieved (fake embeddings are
    # deterministic; same text → same vector → cosine similarity = 1.0)
    assert result.hit_rate == 1.0
    assert result.mean_reciprocal_rank == 1.0


# ---------------------------------------------------------------------------
# Runner preflight validation tests
# ---------------------------------------------------------------------------


def test_preflight_check_valid():
    """preflight_check succeeds with the real corpus and v1.1 dataset."""
    import pathlib

    from evaluation.run_v1_1_baseline import preflight_check

    corpus_dir = pathlib.Path("benchmarks/corpus")
    dataset_path = pathlib.Path("benchmarks/kip_v1_1_baseline.json")
    corpus_ids, dataset = preflight_check(corpus_dir, dataset_path, "test_api_key")

    assert len(corpus_ids) == 3
    assert len(dataset["cases"]) == 7


def test_preflight_check_missing_api_key():
    """preflight_check raises ValueError when api_key is missing."""
    import pathlib

    import pytest
    from evaluation.run_v1_1_baseline import preflight_check

    corpus_dir = pathlib.Path("benchmarks/corpus")
    dataset_path = pathlib.Path("benchmarks/kip_v1_1_baseline.json")
    with pytest.raises(ValueError, match="LLM_API_KEY is not configured"):
        preflight_check(corpus_dir, dataset_path, "")


def test_preflight_check_missing_corpus(tmp_path):
    """preflight_check raises ValueError when corpus dir does not exist."""
    import pathlib

    import pytest
    from evaluation.run_v1_1_baseline import preflight_check

    non_existent = tmp_path / "missing_corpus"
    dataset_path = pathlib.Path("benchmarks/kip_v1_1_baseline.json")
    with pytest.raises(ValueError, match="Corpus directory not found"):
        preflight_check(non_existent, dataset_path, "dummy_key")


def test_preflight_check_mismatched_doc_id(tmp_path):
    """preflight_check raises ValueError if a dataset case expects an unindexed ID."""
    import pytest
    from evaluation.run_v1_1_baseline import preflight_check

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "doc1.txt").write_bytes(b"Sample document text\n")

    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            {
                "version": "v1.1",
                "cases": [
                    {
                        "id": "c1",
                        "question": "Q?",
                        "expected_document_ids": ["unknown_hash_12345"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="which does not match any indexed corpus"):
        preflight_check(corpus_dir, dataset_path, "dummy_key")


def test_baseline_result_file_integrity():
    """Verify that the genuine v1.1 baseline result file is valid and complete."""
    import pathlib

    result_path = pathlib.Path("benchmarks/kip_v1_1_baseline_result.json")
    assert result_path.exists(), "v1.1 baseline result file must exist"

    raw_data = json.loads(result_path.read_text(encoding="utf-8"))
    res = BenchmarkResult(**raw_data)

    assert res.total_cases == 7
    assert res.labelled_cases == 7
    assert res.hit_rate == 1.0
    assert res.mean_reciprocal_rank is not None and res.mean_reciprocal_rank > 0.0
    assert res.config.benchmark_version == "v1.1-baseline"
    assert res.config.embedding_provider == "gemini"
    assert res.config.embedding_model == "gemini-embedding-2"
    assert res.config.llm_provider == "gemini"
    assert res.config.llm_model == "gemini-2.5-flash"
    assert res.config.evaluation_workspace_id == "kip-eval-workspace"

    for cr in res.case_results:
        assert cr.retrieval.retrieval_error is None
        assert cr.retrieval.hit is True
        assert len(cr.retrieval.retrieved_doc_ids) > 0


# ---------------------------------------------------------------------------
# v1.2 input formatting and expanded benchmark tests
# ---------------------------------------------------------------------------


def test_v12_benchmark_dataset_loads():
    """The v1.2 benchmark dataset must load cleanly with 25 labelled cases."""
    import pathlib

    path = pathlib.Path("benchmarks/kip_v1_2_benchmark.json")
    assert path.exists(), "v1.2 benchmark file must exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    ds = BenchmarkDataset(**data)
    assert ds.version == "v1.2-benchmark"
    assert len(ds.cases) == 25
    for case in ds.cases:
        assert case.id
        assert case.question
        assert len(case.expected_document_ids) >= 1
        assert len(case.expected_chunk_ids) >= 1


def test_v12_benchmark_document_ids_match_corpus():
    """Every expected document ID in v1.2 benchmark must match corpus_v1_2."""
    import hashlib
    import pathlib

    corpus_dir = pathlib.Path("benchmarks/corpus_v1_2")
    dataset_path = pathlib.Path("benchmarks/kip_v1_2_benchmark.json")
    actual_ids = {
        hashlib.sha256(f.read_bytes()).hexdigest() for f in corpus_dir.glob("*.txt")
    }
    assert len(actual_ids) == 18

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    ds = BenchmarkDataset(**data)
    for case in ds.cases:
        for doc_id in case.expected_document_ids:
            assert doc_id in actual_ids, f"Unknown document_id {doc_id} in {case.id}"


def test_doc_formatter_hook_in_embedding_service():
    """EmbeddingService applies doc_formatter while preserving raw text."""
    from unittest.mock import MagicMock

    from app.services.chunking.models import Chunk
    from app.services.embeddings.service import EmbeddingService

    mock_manager = MagicMock()
    mock_manager.embed.return_value = []

    def custom_doc_formatter(text: str) -> str:
        return f"title: none | text: {text}"

    service = EmbeddingService(manager=mock_manager, doc_formatter=custom_doc_formatter)
    chunk = Chunk(
        id="chunk-123",
        document_id="doc-456",
        text="raw chunk content",
        character_count=len("raw chunk content"),
        index=0,
        metadata={"custom": "val"},
    )
    service.embed_chunks([chunk])

    mock_manager.embed.assert_called_once()
    req = mock_manager.embed.call_args[0][0]
    assert len(req.inputs) == 1
    assert req.inputs[0].text == "title: none | text: raw chunk content"
    assert req.inputs[0].metadata["text"] == "raw chunk content"
    assert req.inputs[0].metadata["document_id"] == "doc-456"


def test_query_formatter_hook_in_retrieval_service():
    """RetrievalService applies query_formatter to query text when embedding."""
    from unittest.mock import MagicMock

    from app.services.retrieval.models import RetrievalQuery
    from app.services.retrieval.service import RetrievalService

    mock_emb = MagicMock()
    mock_emb.embed_texts.return_value = [MagicMock(vector=[0.1, 0.2])]
    mock_vs = MagicMock()
    mock_vs.search.return_value = []

    def custom_query_formatter(text: str) -> str:
        return f"task: question answering | query: {text}"

    service = RetrievalService(
        embedding_service=mock_emb,
        vector_store_service=mock_vs,
        query_formatter=custom_query_formatter,
    )
    query = RetrievalQuery(text="what is kip?", top_k=5, workspace_id="test-ws")
    service.search(query)

    mock_emb.embed_texts.assert_called_once()
    req = mock_emb.embed_texts.call_args[0][0]
    assert len(req.inputs) == 1
    assert req.inputs[0].text == "task: question answering | query: what is kip?"


def test_evaluation_runner_retrieval_only_and_fine_grained_hits():
    """EvaluationRunner works with rag_service=None and computes hit_at_1/3/5."""
    from unittest.mock import MagicMock

    from evaluation.runner import EvaluationRunner

    from app.services.retrieval.models import RetrievedChunk

    mock_retrieval = MagicMock()
    # Mock search returns 3 chunks: first is wrong doc, second is right doc
    mock_retrieval.search.return_value = [
        RetrievedChunk(id="c0", document_id="doc_wrong", text="chunk 0", score=0.9),
        RetrievedChunk(id="c1", document_id="doc_target", text="chunk 1", score=0.8),
    ]

    config = BenchmarkRunConfig(
        benchmark_version="v1.2-test",
        evaluation_workspace_id="test-ws",
        llm_provider="none",
        llm_model="none",
        embedding_provider="fake",
        embedding_model="fake-embed",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
        live_llm_available=False,
    )
    dataset = BenchmarkDataset(
        version="v1.2-test",
        cases=[
            BenchmarkCase(
                id="t1",
                question="query text",
                expected_document_ids=["doc_target"],
                expected_chunk_ids=["c1"],
            )
        ],
    )

    runner = EvaluationRunner(
        rag_service=None, retrieval_service=mock_retrieval, config=config
    )
    result = runner.evaluate_dataset(dataset)

    assert result.total_cases == 1
    assert result.labelled_cases == 1
    # Matched at rank 2: hit=True, hit_at_1=False, hit_at_3=True, MRR=0.5
    assert result.hit_rate == 1.0
    assert result.hit_rate_at_1 == 0.0
    assert result.hit_rate_at_3 == 1.0
    assert result.hit_rate_at_5 == 1.0
    assert result.mean_reciprocal_rank == 0.5
    assert result.case_results[0].answer == ""


def test_v12_preflight_check_valid():
    """v1.2 preflight_check succeeds with the real corpus_v1_2 and v1.2 dataset."""
    import pathlib

    from evaluation.run_v1_2_formatting_experiment import preflight_check

    corpus_dir = pathlib.Path("benchmarks/corpus_v1_2")
    dataset_path = pathlib.Path("benchmarks/kip_v1_2_benchmark.json")
    corpus_ids, dataset = preflight_check(corpus_dir, dataset_path, "test_api_key")

    assert len(corpus_ids) == 18
    assert len(dataset["cases"]) == 25


# ---------------------------------------------------------------------------
# v1.2 expanded benchmark — 50-document, 80-case dataset validation
# ---------------------------------------------------------------------------


def test_v12_expanded_benchmark_loads():
    """The expanded benchmark must be loadable and well-formed."""
    import pathlib

    path = pathlib.Path("benchmarks/kip_v1_2_expanded_benchmark.json")
    assert path.exists(), "Expanded benchmark file must exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    ds = BenchmarkDataset(**data)
    assert ds.version == "v1.2-expanded-benchmark"
    assert len(ds.cases) == 80


def test_v12_expanded_benchmark_case_ids_unique():
    """All 80 expanded case IDs must be unique."""
    import pathlib

    data = json.loads(
        pathlib.Path("benchmarks/kip_v1_2_expanded_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    ds = BenchmarkDataset(**data)
    ids = [c.id for c in ds.cases]
    assert len(ids) == len(set(ids)), "Expanded benchmark case IDs must be unique"


def test_v12_expanded_benchmark_all_cases_labelled():
    """Every expanded case must have at least one expected_document_id."""
    import pathlib

    data = json.loads(
        pathlib.Path("benchmarks/kip_v1_2_expanded_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    ds = BenchmarkDataset(**data)
    for case in ds.cases:
        assert case.expected_document_ids, (
            f"Case {case.id!r} has no expected_document_ids — "
            "all expanded cases must be fully labelled"
        )


def test_v12_expanded_benchmark_category_counts():
    """Category distribution must match the design spec: 16/16/16/16/8/8."""
    import pathlib

    data = json.loads(
        pathlib.Path("benchmarks/kip_v1_2_expanded_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    ds = BenchmarkDataset(**data)
    counts: dict[str, int] = {}
    for case in ds.cases:
        cat = case.metadata.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1

    assert counts.get("exact_terminology") == 16
    assert counts.get("paraphrase") == 16
    assert counts.get("multi_concept") == 16
    assert counts.get("hard_negative") == 16
    assert counts.get("cross_document") == 8
    assert counts.get("boundary_handling") == 8


def test_v12_expanded_benchmark_document_ids_match_corpus():
    """All expected doc IDs must match SHA-256 of files in corpus_v1_2_expanded."""
    import hashlib
    import pathlib

    corpus_dir = pathlib.Path("benchmarks/corpus_v1_2_expanded")
    actual_ids = {
        hashlib.sha256(f.read_bytes()).hexdigest()
        for f in corpus_dir.glob("*.txt")
    }
    data = json.loads(
        pathlib.Path("benchmarks/kip_v1_2_expanded_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    ds = BenchmarkDataset(**data)
    for case in ds.cases:
        for doc_id in case.expected_document_ids:
            assert doc_id in actual_ids, (
                f"Case {case.id!r} references document_id {doc_id!r} "
                "which does not match any file in benchmarks/corpus_v1_2_expanded/"
            )


def test_v12_expanded_corpus_lf_line_endings():
    """Expanded corpus files must use LF-only line endings for stable SHA-256 IDs."""
    import pathlib

    corpus_dir = pathlib.Path("benchmarks/corpus_v1_2_expanded")
    for txt_file in corpus_dir.glob("*.txt"):
        raw = txt_file.read_bytes()
        assert b"\r" not in raw, (
            f"{txt_file.name} contains CR bytes (CRLF line endings). "
            "This would change the SHA-256 document ID. "
            "Corpus files must use LF line endings only."
        )


def test_v12_expanded_benchmark_chunk_ids_format():
    """All expected_chunk_ids must be 64-char lowercase hex strings."""
    import pathlib
    import re

    hex64 = re.compile(r"^[0-9a-f]{64}$")
    data = json.loads(
        pathlib.Path("benchmarks/kip_v1_2_expanded_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    ds = BenchmarkDataset(**data)
    for case in ds.cases:
        for chunk_id in case.expected_chunk_ids:
            assert hex64.match(chunk_id), (
                f"Case {case.id!r} has malformed chunk_id {chunk_id!r}"
            )


def test_v12_expanded_benchmark_corpus_size():
    """Expanded corpus must contain exactly 50 source documents."""
    import pathlib

    corpus_dir = pathlib.Path("benchmarks/corpus_v1_2_expanded")
    txt_files = list(corpus_dir.glob("*.txt"))
    assert len(txt_files) == 50, (
        f"Expected 50 corpus documents, found {len(txt_files)}"
    )


def test_v12_expanded_ids_json_consistency():
    """corpus_v1_2_expanded_ids.json must cover all 50 corpus files with valid SHA-256 doc IDs."""
    import hashlib
    import pathlib

    corpus_dir = pathlib.Path("benchmarks/corpus_v1_2_expanded")
    mapping_path = pathlib.Path("benchmarks/corpus_v1_2_expanded_ids.json")
    assert mapping_path.exists(), "ID mapping file must exist"

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    doc_ids = mapping["doc_ids"]
    chunk_ids = mapping["chunk_ids"]

    assert len(doc_ids) == 50
    assert len(chunk_ids) == 50
    assert set(doc_ids.keys()) == set(chunk_ids.keys()), (
        "doc_ids and chunk_ids must cover the same set of filenames"
    )

    # Verify every doc ID matches actual corpus file bytes
    for filename, doc_id in doc_ids.items():
        corpus_file = corpus_dir / filename
        assert corpus_file.exists(), f"Corpus file {filename} missing"
        expected_id = hashlib.sha256(corpus_file.read_bytes()).hexdigest()
        assert doc_id == expected_id, (
            f"doc_id mismatch for {filename}: "
            f"mapping has {doc_id!r}, derived {expected_id!r}"
        )
