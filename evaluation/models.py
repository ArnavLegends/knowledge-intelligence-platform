"""Benchmark case and result schemas for KIP evaluation."""

from typing import Any

from pydantic import BaseModel, Field


class BenchmarkCase(BaseModel):
    """A single evaluation case for the KIP RAG pipeline.

    Fields:
        id: Unique identifier for this case.
        question: The natural-language question to ask the RAG system.
        reference_answer: Optional ground-truth answer for comparison.
        expected_document_ids: IDs of documents whose chunks should be retrieved.
        expected_keywords: Keywords that should appear in the retrieved
            context or answer.
        metadata: Arbitrary per-case metadata (e.g. difficulty, topic).
    """

    id: str
    question: str
    reference_answer: str | None = None
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkDataset(BaseModel):
    """A versioned collection of benchmark cases."""

    version: str
    description: str = ""
    cases: list[BenchmarkCase]


class RetrievalMetrics(BaseModel):
    """Retrieval evaluation metrics for a single benchmark case."""

    case_id: str
    hit: bool  # At least one expected document was in top-k results
    reciprocal_rank: float  # MRR contribution: 1/rank of first relevant hit (0 if none)
    retrieved_count: int
    expected_count: int
    retrieved_doc_ids: list[str]
    expected_doc_ids: list[str]
    retrieval_latency_ms: float


class AnswerMetrics(BaseModel):
    """Answer-level evaluation metrics for a single benchmark case."""

    case_id: str
    has_answer: bool  # Whether the system returned a non-empty answer
    has_context: bool  # Whether context was retrieved (not empty-context path)
    keyword_hits: list[str]  # Expected keywords found in the answer
    keyword_misses: list[str]  # Expected keywords not found in the answer
    keyword_coverage: float  # Fraction of expected keywords present
    # NOTE: exact_match and semantic_similarity require an LLM judge and are
    # not computed by default. They are left as optional fields.
    exact_match: bool | None = None
    llm_faithfulness: float | None = None  # Requires external LLM judge
    generation_latency_ms: float | None = None


class CaseResult(BaseModel):
    """Combined result for one benchmark case."""

    case_id: str
    question: str
    answer: str
    sources_count: int
    retrieval: RetrievalMetrics
    answer_metrics: AnswerMetrics
    total_latency_ms: float


class BenchmarkRunConfig(BaseModel):
    """Records the configuration under which a benchmark run was executed."""

    benchmark_version: str
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    retrieval_top_k: int
    chunk_size: int
    chunk_overlap: int
    live_llm_available: bool = False


class BenchmarkResult(BaseModel):
    """Complete result of a benchmark run."""

    run_id: str
    timestamp: str
    config: BenchmarkRunConfig
    case_results: list[CaseResult]

    # Aggregate metrics
    total_cases: int
    hit_rate: float  # Fraction of cases where at least one expected doc was retrieved
    mean_reciprocal_rank: float
    keyword_coverage: float  # Mean keyword coverage across all cases
    mean_retrieval_latency_ms: float
    mean_total_latency_ms: float

    @classmethod
    def from_case_results(
        cls,
        run_id: str,
        timestamp: str,
        config: BenchmarkRunConfig,
        results: list[CaseResult],
    ) -> "BenchmarkResult":
        n = len(results)
        if n == 0:
            return cls(
                run_id=run_id,
                timestamp=timestamp,
                config=config,
                case_results=[],
                total_cases=0,
                hit_rate=0.0,
                mean_reciprocal_rank=0.0,
                keyword_coverage=0.0,
                mean_retrieval_latency_ms=0.0,
                mean_total_latency_ms=0.0,
            )
        hit_rate = sum(1 for r in results if r.retrieval.hit) / n
        mrr = sum(r.retrieval.reciprocal_rank for r in results) / n
        kw_cov = sum(r.answer_metrics.keyword_coverage for r in results) / n
        mean_ret_lat = sum(r.retrieval.retrieval_latency_ms for r in results) / n
        mean_total_lat = sum(r.total_latency_ms for r in results) / n
        return cls(
            run_id=run_id,
            timestamp=timestamp,
            config=config,
            case_results=results,
            total_cases=n,
            hit_rate=hit_rate,
            mean_reciprocal_rank=mrr,
            keyword_coverage=kw_cov,
            mean_retrieval_latency_ms=mean_ret_lat,
            mean_total_latency_ms=mean_total_lat,
        )
