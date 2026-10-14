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
            An empty list means the case is unlabelled for retrieval and is
            excluded from Hit Rate and MRR aggregation.
        expected_keywords: Keywords that should appear in the retrieved
            context or answer.
        metadata: Arbitrary per-case metadata (e.g. difficulty, topic).
    """

    id: str
    question: str
    reference_answer: str | None = None
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
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
    # Set when a retrieval infrastructure failure occurred (not a genuine miss).
    # When non-None the hit/reciprocal_rank values are 0 due to the failure,
    # not because retrieval returned no results.
    retrieval_error: str | None = None
    hit_at_1: bool = False
    hit_at_3: bool = False
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    # Stage A candidate retrieval and Stage B reranking metrics (optional)
    candidate_hit_at_20: bool | None = None
    candidate_count: int | None = None
    candidate_doc_ids: list[str] = Field(default_factory=list)
    candidate_chunk_ids: list[str] = Field(default_factory=list)
    reranking_latency_ms: float | None = None
    dense_scores: list[float] = Field(default_factory=list)
    rerank_scores: list[float] = Field(default_factory=list)
    # Hybrid sparse/dense retrieval metrics (optional)
    dense_latency_ms: float | None = None
    sparse_latency_ms: float | None = None
    fusion_latency_ms: float | None = None
    sparse_scores: list[float] = Field(default_factory=list)
    rrf_scores: list[float] = Field(default_factory=list)
    dense_hit_at_depth: bool | None = None
    sparse_hit_at_depth: bool | None = None


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
    evaluation_workspace_id: str = "kip-eval-workspace"
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    retrieval_top_k: int
    chunk_size: int
    chunk_overlap: int
    live_llm_available: bool = False
    inter_case_delay_seconds: float = 0.0


class BenchmarkResult(BaseModel):
    """Complete result of a benchmark run."""

    run_id: str
    timestamp: str
    config: BenchmarkRunConfig
    case_results: list[CaseResult]

    # Case counts
    total_cases: int
    # Cases with expected_document_ids populated (scored for retrieval)
    labelled_cases: int

    # Retrieval metrics — computed only over labelled cases.
    # None when no labelled cases exist.
    # Fraction of labelled cases with at least one expected doc retrieved.
    hit_rate: float | None
    mean_reciprocal_rank: float | None
    hit_rate_at_1: float | None = None
    hit_rate_at_3: float | None = None
    hit_rate_at_5: float | None = None
    candidate_hit_rate_at_20: float | None = None

    # Answer metrics — computed over all cases.
    keyword_coverage: float  # Mean keyword coverage across all cases
    mean_retrieval_latency_ms: float
    mean_reranking_latency_ms: float | None = None
    mean_dense_latency_ms: float | None = None
    mean_sparse_latency_ms: float | None = None
    mean_fusion_latency_ms: float | None = None
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
                labelled_cases=0,
                hit_rate=None,
                mean_reciprocal_rank=None,
                keyword_coverage=0.0,
                mean_retrieval_latency_ms=0.0,
                mean_total_latency_ms=0.0,
            )

        # Retrieval metrics: only cases with populated expected_document_ids.
        # Cases without ground-truth labels are excluded so that unlabelled
        # cases cannot inflate Hit Rate to 1.0.
        labelled = [r for r in results if r.retrieval.expected_count > 0]
        n_labelled = len(labelled)

        if n_labelled > 0:
            hit_rate: float | None = (
                sum(1 for r in labelled if r.retrieval.hit) / n_labelled
            )
            hit_rate_at_1: float | None = (
                sum(1 for r in labelled if r.retrieval.hit_at_1) / n_labelled
            )
            hit_rate_at_3: float | None = (
                sum(1 for r in labelled if r.retrieval.hit_at_3) / n_labelled
            )
            hit_rate_at_5: float | None = hit_rate
            mrr: float | None = (
                sum(r.retrieval.reciprocal_rank for r in labelled) / n_labelled
            )
        else:
            hit_rate = None
            hit_rate_at_1 = None
            hit_rate_at_3 = None
            hit_rate_at_5 = None
            mrr = None

        # Candidate hit rate @ 20 across labelled cases
        cand_labelled = [
            r for r in labelled if r.retrieval.candidate_hit_at_20 is not None
        ]
        if cand_labelled:
            candidate_hit_rate_at_20: float | None = (
                sum(1 for r in cand_labelled if r.retrieval.candidate_hit_at_20)
                / len(cand_labelled)
            )
        else:
            candidate_hit_rate_at_20 = None

        has_rerank_lat = [
            r for r in results if r.retrieval.reranking_latency_ms is not None
        ]
        if has_rerank_lat:
            mean_rerank_lat: float | None = (
                sum(r.retrieval.reranking_latency_ms or 0.0 for r in has_rerank_lat)
                / len(has_rerank_lat)
            )
        else:
            mean_rerank_lat = None

        has_dense_lat = [
            r for r in results if r.retrieval.dense_latency_ms is not None
        ]
        mean_dense_lat = (
            sum(r.retrieval.dense_latency_ms or 0.0 for r in has_dense_lat)
            / len(has_dense_lat)
            if has_dense_lat
            else None
        )

        has_sparse_lat = [
            r for r in results if r.retrieval.sparse_latency_ms is not None
        ]
        mean_sparse_lat = (
            sum(r.retrieval.sparse_latency_ms or 0.0 for r in has_sparse_lat)
            / len(has_sparse_lat)
            if has_sparse_lat
            else None
        )

        has_fusion_lat = [
            r for r in results if r.retrieval.fusion_latency_ms is not None
        ]
        mean_fusion_lat = (
            sum(r.retrieval.fusion_latency_ms or 0.0 for r in has_fusion_lat)
            / len(has_fusion_lat)
            if has_fusion_lat
            else None
        )

        kw_cov = sum(r.answer_metrics.keyword_coverage for r in results) / n
        mean_ret_lat = sum(r.retrieval.retrieval_latency_ms for r in results) / n
        mean_total_lat = sum(r.total_latency_ms for r in results) / n

        return cls(
            run_id=run_id,
            timestamp=timestamp,
            config=config,
            case_results=results,
            total_cases=n,
            labelled_cases=n_labelled,
            hit_rate=hit_rate,
            mean_reciprocal_rank=mrr,
            hit_rate_at_1=hit_rate_at_1,
            hit_rate_at_3=hit_rate_at_3,
            hit_rate_at_5=hit_rate_at_5,
            candidate_hit_rate_at_20=candidate_hit_rate_at_20,
            keyword_coverage=kw_cov,
            mean_retrieval_latency_ms=mean_ret_lat,
            mean_reranking_latency_ms=mean_rerank_lat,
            mean_dense_latency_ms=mean_dense_lat,
            mean_sparse_latency_ms=mean_sparse_lat,
            mean_fusion_latency_ms=mean_fusion_lat,
            mean_total_latency_ms=mean_total_lat,
        )
