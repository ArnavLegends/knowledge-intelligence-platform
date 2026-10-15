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

Retrieval metrics (Hit Rate, MRR) are computed ONLY over cases that have
populated expected_document_ids. Cases with empty expected_document_ids are
labelled as unlabelled and are excluded from retrieval metric aggregation.
This prevents empty ground-truth lists from silently inflating Hit Rate to 1.0.

Infrastructure failures (e.g. missing workspace, embedding errors) are
recorded in RetrievalMetrics.retrieval_error and are distinguishable from
genuine retrieval misses.
"""

import logging
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

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Runs a benchmark dataset against the KIP RAG pipeline.

    The runner calls the KIP services directly (not via HTTP) for speed
    and to isolate evaluation from networking concerns. It is designed to
    work with the same dependency injection used in the rest of the system.

    Args:
        rag_service: A configured RAGService instance.
        retrieval_service: A configured RetrievalService instance.
        config: Run configuration including workspace_id and parameters.
            The evaluation_workspace_id in config is used for all retrieval
            and RAG calls, keeping evaluation isolated from user workspaces.
    """

    def __init__(
        self,
        rag_service,
        retrieval_service,
        config: BenchmarkRunConfig,
        reranker=None,
        candidate_top_k: int = 20,
        sparse_retriever=None,
        rrf_k: int = 60,
    ) -> None:
        self._rag_service = rag_service
        self._retrieval_service = retrieval_service
        self._config = config
        self._workspace_id = config.evaluation_workspace_id
        self._reranker = reranker
        self._candidate_top_k = candidate_top_k
        self._sparse_retriever = sparse_retriever
        self._rrf_k = rrf_k

    def evaluate_dataset(self, dataset: BenchmarkDataset) -> BenchmarkResult:
        """Run all cases in the dataset and return a full BenchmarkResult."""
        run_id = uuid4().hex
        timestamp = datetime.now(UTC).isoformat()

        logger.info(
            "Evaluation run started: run_id=%s dataset=%s cases=%d workspace=%s",
            run_id,
            dataset.version,
            len(dataset.cases),
            self._workspace_id,
        )

        case_results = []
        for i, case in enumerate(dataset.cases):
            if i > 0 and self._config.inter_case_delay_seconds > 0:
                time.sleep(self._config.inter_case_delay_seconds)
            result = self._evaluate_case(case)
            case_results.append(result)

        benchmark_result = BenchmarkResult.from_case_results(
            run_id=run_id,
            timestamp=timestamp,
            config=self._config,
            results=case_results,
        )

        logger.info(
            "Evaluation run complete: run_id=%s total=%d labelled=%d "
            "hit_rate=%s mrr=%s",
            run_id,
            benchmark_result.total_cases,
            benchmark_result.labelled_cases,
            benchmark_result.hit_rate,
            benchmark_result.mean_reciprocal_rank,
        )

        return benchmark_result

    def _evaluate_case(self, case: BenchmarkCase) -> CaseResult:
        """Evaluate a single benchmark case."""
        from app.services.rag.models import RAGRequest
        from app.services.retrieval.models import RetrievalQuery

        t_start = time.perf_counter()

        # --- Retrieval phase ---
        # workspace_id is explicitly propagated from config to keep evaluation
        # isolated from user workspaces and to avoid the 'workspace_id required'
        # error in RetrievalService.search().
        t_ret_start = time.perf_counter()
        retrieval_error: str | None = None
        chunks = []
        retrieved_doc_ids: list[str] = []
        candidate_chunks = []
        candidate_doc_ids: list[str] = []
        candidate_chunk_ids: list[str] = []
        candidate_hit_at_20: bool | None = None
        reranking_latency_ms: float | None = None
        dense_latency_ms: float | None = None
        sparse_latency_ms: float | None = None
        fusion_latency_ms: float | None = None
        dense_hit_at_depth: bool | None = None
        sparse_hit_at_depth: bool | None = None

        try:
            if self._sparse_retriever is not None:
                from evaluation.fusion import reciprocal_rank_fusion

                # Stage A (Dense retrieval)
                t_d_start = time.perf_counter()
                dense_query = RetrievalQuery(
                    text=case.question,
                    top_k=self._candidate_top_k,
                    workspace_id=self._workspace_id,
                )
                dense_candidates = self._retrieval_service.search(dense_query)
                dense_latency_ms = (time.perf_counter() - t_d_start) * 1000

                # Stage A (Sparse BM25 retrieval)
                t_s_start = time.perf_counter()
                sparse_candidates = self._sparse_retriever.search(
                    query=case.question,
                    top_k=self._candidate_top_k,
                )
                sparse_latency_ms = (time.perf_counter() - t_s_start) * 1000

                # Stage B (Reciprocal Rank Fusion)
                t_f_start = time.perf_counter()
                chunks = reciprocal_rank_fusion(
                    {"dense": dense_candidates, "sparse": sparse_candidates},
                    k=self._rrf_k,
                    top_k=self._config.retrieval_top_k,
                )
                fusion_latency_ms = (time.perf_counter() - t_f_start) * 1000

                candidate_chunks = dense_candidates
                candidate_doc_ids = list(
                    {c.document_id for c in dense_candidates if c.document_id}
                )
                candidate_chunk_ids = [
                    c.id for c in dense_candidates if hasattr(c, "id") and c.id
                ]

                dense_doc_ids = {
                    c.document_id for c in dense_candidates if c.document_id
                }
                dense_chunk_id_set = {
                    c.id for c in dense_candidates if hasattr(c, "id") and c.id
                }
                sparse_doc_ids = {
                    c.document_id for c in sparse_candidates if c.document_id
                }
                sparse_chunk_id_set = {
                    c.id for c in sparse_candidates if hasattr(c, "id") and c.id
                }

                is_labelled_cand = bool(
                    case.expected_document_ids or case.expected_chunk_ids
                )
                if is_labelled_cand:
                    dense_hit_at_depth = any(
                        d in dense_doc_ids for d in case.expected_document_ids
                    ) or any(c in dense_chunk_id_set for c in case.expected_chunk_ids)
                    sparse_hit_at_depth = any(
                        d in sparse_doc_ids for d in case.expected_document_ids
                    ) or any(c in sparse_chunk_id_set for c in case.expected_chunk_ids)
                    candidate_hit_at_20 = dense_hit_at_depth or sparse_hit_at_depth
                else:
                    dense_hit_at_depth = False
                    sparse_hit_at_depth = False
                    candidate_hit_at_20 = False

            elif self._reranker is not None:
                retrieval_query = RetrievalQuery(
                    text=case.question,
                    top_k=self._candidate_top_k,
                    workspace_id=self._workspace_id,
                )
                retrieved_initial = self._retrieval_service.search(retrieval_query)
                candidate_chunks = retrieved_initial
                candidate_doc_ids = list(
                    {c.document_id for c in candidate_chunks if c.document_id}
                )
                candidate_chunk_ids = [
                    c.id for c in candidate_chunks if hasattr(c, "id") and c.id
                ]
                is_labelled_cand = bool(
                    case.expected_document_ids or case.expected_chunk_ids
                )
                if is_labelled_cand:
                    candidate_hit_at_20 = any(
                        d in candidate_doc_ids for d in case.expected_document_ids
                    ) or any(c in candidate_chunk_ids for c in case.expected_chunk_ids)
                else:
                    candidate_hit_at_20 = False

                # Stage B: Cross-encoder reranking
                chunks, reranking_latency_ms = self._reranker.rerank(
                    query=case.question,
                    candidates=candidate_chunks,
                    top_k=self._config.retrieval_top_k,
                )
            else:
                retrieval_query = RetrievalQuery(
                    text=case.question,
                    top_k=self._config.retrieval_top_k,
                    workspace_id=self._workspace_id,
                )
                chunks = self._retrieval_service.search(retrieval_query)

            retrieved_doc_ids = list({c.document_id for c in chunks if c.document_id})
        except Exception as exc:
            # Record the infrastructure failure visibly. This is NOT treated as
            # a retrieval miss; it is an error distinct from genuine zero-retrieval.
            retrieval_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Retrieval infrastructure failure for case %s: %s",
                case.id,
                retrieval_error,
            )

        t_ret_end = time.perf_counter()
        retrieval_latency_ms = (t_ret_end - t_ret_start) * 1000

        # Compute retrieval metrics.
        # Cases with empty expected_document_ids and expected_chunk_ids are unlabelled:
        # hit=False, reciprocal_rank=0. They are excluded from aggregate Hit Rate/MRR
        # in BenchmarkResult.from_case_results() via expected_count == 0 check.
        is_labelled = bool(case.expected_document_ids or case.expected_chunk_ids)
        retrieved_chunk_ids = [c.id for c in chunks if hasattr(c, "id") and c.id]
        hit_at_1 = False
        hit_at_3 = False
        if is_labelled and retrieval_error is None:
            hit = any(
                d in retrieved_doc_ids for d in case.expected_document_ids
            ) or any(c in retrieved_chunk_ids for c in case.expected_chunk_ids)
            reciprocal_rank = 0.0
            for rank, chunk in enumerate(chunks, start=1):
                doc_match = (
                    chunk.document_id in case.expected_document_ids
                    if case.expected_document_ids
                    else False
                )
                chunk_match = (
                    chunk.id in case.expected_chunk_ids
                    if case.expected_chunk_ids
                    else False
                )
                if doc_match or chunk_match:
                    reciprocal_rank = 1.0 / rank
                    if rank == 1:
                        hit_at_1 = True
                    if rank <= 3:
                        hit_at_3 = True
                    break
        else:
            # Unlabelled case or infrastructure failure: mark as miss so the
            # case does not artificially contribute to Hit Rate.
            hit = False
            reciprocal_rank = 0.0

        expected_count = max(
            len(case.expected_document_ids), len(case.expected_chunk_ids)
        )

        dense_scores = (
            [
                float(c.metadata["dense_score"])
                for c in chunks
                if c.metadata
                and "dense_score" in c.metadata
                and c.metadata["dense_score"] is not None
            ]
            if self._sparse_retriever is not None
            else [
                float(c.score)
                for c in chunks
                if hasattr(c, "score") and c.score is not None
            ]
        )
        sparse_scores = [
            float(c.metadata["sparse_score"])
            for c in chunks
            if c.metadata
            and "sparse_score" in c.metadata
            and c.metadata["sparse_score"] is not None
        ]
        rrf_scores = [
            float(c.metadata["rrf_score"])
            for c in chunks
            if c.metadata
            and "rrf_score" in c.metadata
            and c.metadata["rrf_score"] is not None
        ]
        rerank_scores = [
            float(c.rerank_score)
            for c in chunks
            if hasattr(c, "rerank_score") and c.rerank_score is not None
        ]

        candidate_cnt = (
            (len(dense_candidates) + len(sparse_candidates))
            if self._sparse_retriever is not None
            else (len(candidate_chunks) if self._reranker is not None else None)
        )

        retrieval_metrics = RetrievalMetrics(
            case_id=case.id,
            hit=hit,
            reciprocal_rank=reciprocal_rank,
            retrieved_count=len(chunks),
            expected_count=expected_count,
            retrieved_doc_ids=retrieved_doc_ids,
            expected_doc_ids=list(case.expected_document_ids),
            retrieval_latency_ms=retrieval_latency_ms,
            retrieval_error=retrieval_error,
            hit_at_1=hit_at_1,
            hit_at_3=hit_at_3,
            retrieved_chunk_ids=retrieved_chunk_ids,
            expected_chunk_ids=list(case.expected_chunk_ids),
            candidate_hit_at_20=candidate_hit_at_20,
            candidate_count=candidate_cnt,
            candidate_doc_ids=candidate_doc_ids,
            candidate_chunk_ids=candidate_chunk_ids,
            reranking_latency_ms=reranking_latency_ms,
            dense_scores=dense_scores,
            rerank_scores=rerank_scores,
            dense_latency_ms=dense_latency_ms,
            sparse_latency_ms=sparse_latency_ms,
            fusion_latency_ms=fusion_latency_ms,
            sparse_scores=sparse_scores,
            rrf_scores=rrf_scores,
            dense_hit_at_depth=dense_hit_at_depth,
            sparse_hit_at_depth=sparse_hit_at_depth,
        )

        # --- Generation phase ---
        t_gen_start = time.perf_counter()
        answer = ""
        sources_count = 0
        has_context = False

        if self._rag_service is not None:
            try:
                rag_request = RAGRequest(
                    query=case.question,
                    top_k=self._config.retrieval_top_k,
                    workspace_id=self._workspace_id,
                )
                rag_response = self._rag_service.answer(rag_request)
                answer = rag_response.answer
                sources_count = len(rag_response.sources)
                has_context = sources_count > 0
            except Exception as exc:
                # Generation failures are recorded in the answer string so that
                # they appear in output without crashing the run.
                gen_error = f"{type(exc).__name__}: {exc}"
                answer = f"[Evaluation Error: {gen_error}]"
                logger.warning("Generation failure for case %s: %s", case.id, gen_error)
        else:
            sources_count = len(chunks)
            has_context = sources_count > 0
            answer = ""

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
