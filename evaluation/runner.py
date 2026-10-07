"""Evaluation runner for the KIP RAG pipeline.

This module executes a BenchmarkDataset against the KIP pipeline and produces
a BenchmarkResult with deterministic, reproducible metrics.

IMPORTANT: This evaluator measures mechanical properties of the system:
- Whether expected documents were retrieved (hit rate, MRR)
- Whether expected keywords appear in retrieved context or the answer
- Latency of retrieval and generation stages

It does NOT perform:
- LLM-as-judge evaluation (faithfulness, semantic similarity)
- Scientific accuracy claims
- Claims about retrieval quality without ground-truth evaluation data

LLM-as-judge evaluation is marked as optional and is only performed when
explicitly configured with available credentials.
"""

import time
from datetime import UTC, datetime
from uuid import uuid4

from evaluation.models import (
    AnswerMetrics,
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkResult,
    BenchmarkRunConfig,
    CaseResult,
    RetrievalMetrics,
)


class EvaluationRunner:
    """Runs a benchmark dataset against the KIP RAG pipeline.

    The runner calls the KIP services directly (not via HTTP) for speed
    and to isolate evaluation from networking concerns. It is designed to
    work with the same dependency injection used in the rest of the system.
    """

    def __init__(
        self, rag_service, retrieval_service, config: BenchmarkRunConfig
    ) -> None:
        self._rag_service = rag_service
        self._retrieval_service = retrieval_service
        self._config = config

    def evaluate_dataset(self, dataset: BenchmarkDataset) -> BenchmarkResult:
        """Run all cases in the dataset and return a full BenchmarkResult."""
        run_id = uuid4().hex
        timestamp = datetime.now(UTC).isoformat()

        case_results = []
        for case in dataset.cases:
            result = self._evaluate_case(case)
            case_results.append(result)

        return BenchmarkResult.from_case_results(
            run_id=run_id,
            timestamp=timestamp,
            config=self._config,
            results=case_results,
        )

    def _evaluate_case(self, case: BenchmarkCase) -> CaseResult:
        """Evaluate a single benchmark case."""
        from app.services.rag.models import RAGRequest
        from app.services.retrieval.models import RetrievalQuery

        t_start = time.perf_counter()

        # --- Retrieval phase ---
        t_ret_start = time.perf_counter()
        try:
            retrieval_query = RetrievalQuery(
                text=case.question,
                top_k=self._config.retrieval_top_k,
            )
            chunks = self._retrieval_service.search(retrieval_query)
            retrieved_doc_ids = list({c.document_id for c in chunks if c.document_id})
        except Exception:
            chunks = []
            retrieved_doc_ids = []
        t_ret_end = time.perf_counter()
        retrieval_latency_ms = (t_ret_end - t_ret_start) * 1000

        # Compute retrieval metrics
        hit = bool(
            case.expected_document_ids
            and any(d in retrieved_doc_ids for d in case.expected_document_ids)
        )
        if not case.expected_document_ids:
            hit = True  # No expectation = not a miss

        reciprocal_rank = 0.0
        if case.expected_document_ids and chunks:
            for rank, chunk in enumerate(chunks, start=1):
                if chunk.document_id in case.expected_document_ids:
                    reciprocal_rank = 1.0 / rank
                    break

        retrieval_metrics = RetrievalMetrics(
            case_id=case.id,
            hit=hit,
            reciprocal_rank=reciprocal_rank,
            retrieved_count=len(chunks),
            expected_count=len(case.expected_document_ids),
            retrieved_doc_ids=retrieved_doc_ids,
            expected_doc_ids=list(case.expected_document_ids),
            retrieval_latency_ms=retrieval_latency_ms,
        )

        # --- Generation phase ---
        t_gen_start = time.perf_counter()
        try:
            rag_request = RAGRequest(
                query=case.question,
                top_k=self._config.retrieval_top_k,
            )
            rag_response = self._rag_service.answer(rag_request)
            answer = rag_response.answer
            sources_count = len(rag_response.sources)
            has_context = sources_count > 0
        except Exception as e:
            answer = f"[Evaluation Error: {e}]"
            sources_count = 0
            has_context = False
        t_gen_end = time.perf_counter()
        generation_latency_ms = (t_gen_end - t_gen_start) * 1000

        # Keyword coverage
        answer_lower = answer.lower()
        keyword_hits = [
            kw for kw in case.expected_keywords if kw.lower() in answer_lower
        ]
        keyword_misses = [
            kw for kw in case.expected_keywords if kw.lower() not in answer_lower
        ]
        keyword_coverage = (
            len(keyword_hits) / len(case.expected_keywords)
            if case.expected_keywords
            else 1.0
        )

        answer_metrics = AnswerMetrics(
            case_id=case.id,
            has_answer=bool(answer.strip()),
            has_context=has_context,
            keyword_hits=keyword_hits,
            keyword_misses=keyword_misses,
            keyword_coverage=keyword_coverage,
            generation_latency_ms=generation_latency_ms,
        )

        t_end = time.perf_counter()
        total_latency_ms = (t_end - t_start) * 1000

        return CaseResult(
            case_id=case.id,
            question=case.question,
            answer=answer,
            sources_count=sources_count,
            retrieval=retrieval_metrics,
            answer_metrics=answer_metrics,
            total_latency_ms=total_latency_ms,
        )
