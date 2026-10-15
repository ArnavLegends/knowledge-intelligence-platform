"""Executable runner for the KIP v1.2 hybrid retrieval experiment.

Evaluates an isolated two-channel hybrid retrieval pipeline:
  Channel A (Dense Retrieval):  Gemini embedding-2 (768d) + Qdrant top-20 search
  Channel B (Sparse Retrieval): Deterministic BM25Okapi top-20 search
  Fusion (RRF):                 Reciprocal Rank Fusion with smoothing k=60 to return top-5.

Evaluates against the identical 80-case expanded benchmark and 50-document corpus,
comparing results against the frozen v1.2 expanded baseline.

Configuration:
- Embedding Provider:  Google Gemini (gemini-embedding-2, 768 dimensions)
- Vector Store:        Qdrant, dedicated collection kip_eval_v1_2_expanded
- Evaluation Workspace: kip-eval-workspace-v1-2-expanded
- Reference Corpus:    benchmarks/corpus_v1_2_expanded/ (50 .txt files, LF only)
- Benchmark Dataset:   benchmarks/kip_v1_2_expanded_benchmark.json (80 cases)
- Candidate Top-K:     20 (Dense) + 20 (Sparse)
- Final Top-K:         5
- RRF Smoothing (k):   60
- Inter-case delay:    0.5s

Usage:
    python evaluation/run_v1_2_hybrid_experiment.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import statistics
import sys
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv

# Ensure repo root and backend package are in pythonpath
repo_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "backend"))

# Load .env before initializing settings
load_dotenv(repo_root / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("evaluation.run_v1_2_hybrid_experiment")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORPUS_DIR = repo_root / "benchmarks" / "corpus_v1_2_expanded"
DATASET_PATH = repo_root / "benchmarks" / "kip_v1_2_expanded_benchmark.json"
CONTROL_BASELINE_PATH = (
    repo_root / "benchmarks" / "kip_v1_2_expanded_baseline_20261014_112147.json"
)
COLLECTION_NAME = "kip_eval_v1_2_expanded"
EVAL_WORKSPACE = "kip-eval-workspace-v1-2-expanded"
EXPERIMENT_VERSION = "v1.2-hybrid-treatment"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
CANDIDATE_TOP_K = 20
FINAL_TOP_K = 5
RRF_K = 60
INTER_CASE_DELAY_SECONDS = 0.5

SENSITIVE_CASE_IDS = {"exp-005", "exp-007", "exp-008", "exp-074", "exp-079"}


# ---------------------------------------------------------------------------
# Preflight validation
# ---------------------------------------------------------------------------


def preflight_check(
    corpus_dir: pathlib.Path,
    dataset_path: pathlib.Path,
    api_key: str | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Validate all prerequisites before spending API quota."""
    if not api_key or not api_key.strip():
        raise ValueError(
            "Preflight failed: LLM_API_KEY is not configured in environment or .env."
        )

    if not corpus_dir.exists() or not corpus_dir.is_dir():
        raise ValueError(
            f"Preflight failed: Corpus directory not found at {corpus_dir}"
        )

    if not dataset_path.exists():
        raise ValueError(f"Preflight failed: Dataset file not found at {dataset_path}")

    txt_files = list(corpus_dir.glob("*.txt"))
    if len(txt_files) != 50:
        raise ValueError(
            f"Preflight failed: Expected 50 corpus files in {corpus_dir}, "
            f"found {len(txt_files)}."
        )

    corpus_ids: dict[str, str] = {}
    for txt_file in txt_files:
        raw_bytes = txt_file.read_bytes()
        if b"\r" in raw_bytes:
            raise ValueError(
                f"Preflight failed: Corpus fixture {txt_file.name} contains "
                "CR bytes (CRLF line endings). Corpus files must use LF only."
            )
        doc_id = hashlib.sha256(raw_bytes).hexdigest()
        corpus_ids[txt_file.name] = doc_id

    expected_corpus_size = 50
    if len(corpus_ids) != expected_corpus_size:
        raise ValueError(
            f"Preflight failed: Expected {expected_corpus_size} corpus files, "
            f"found {len(corpus_ids)}."
        )

    dataset_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset_data.get("cases", [])

    if len(cases) != 80:
        raise ValueError(
            f"Preflight failed: Expected 80 benchmark cases, found {len(cases)}."
        )

    case_ids = [c.get("id") for c in cases]
    if len(case_ids) != len(set(case_ids)):
        dupes = [cid for cid in case_ids if case_ids.count(cid) > 1]
        raise ValueError(f"Preflight failed: Duplicate case IDs found: {set(dupes)}")

    # Check sensitive cases exist in dataset
    found_sensitive = SENSITIVE_CASE_IDS.intersection(set(case_ids))
    if len(found_sensitive) != len(SENSITIVE_CASE_IDS):
        missing = SENSITIVE_CASE_IDS - found_sensitive
        raise ValueError(
            f"Preflight failed: Sensitive cases missing from dataset: {missing}"
        )

    return corpus_ids, dataset_data


# ---------------------------------------------------------------------------
# Category-level aggregation
# ---------------------------------------------------------------------------


def _aggregate_by_category(case_results, dataset_cases) -> dict[str, Any]:
    """Compute Hit@1/3/5, MRR, candidate hit rates, and latencies broken down by category."""
    id_to_category: dict[str, str] = {}
    for case in dataset_cases:
        cat = (case.metadata or {}).get("category", "unknown")
        id_to_category[case.id] = cat

    buckets: dict[str, list] = {}
    for cr in case_results:
        cat = id_to_category.get(cr.case_id, "unknown")
        if cat not in buckets:
            buckets[cat] = []
        buckets[cat].append(cr)

    summary: dict[str, Any] = {}
    for cat, results in sorted(buckets.items()):
        labelled = [r for r in results if r.retrieval.expected_count > 0]
        n = len(labelled)
        if n == 0:
            continue

        cand_labelled = [
            r for r in labelled if r.retrieval.candidate_hit_at_20 is not None
        ]
        cand_hit_rate = (
            sum(1 for r in cand_labelled if r.retrieval.candidate_hit_at_20)
            / len(cand_labelled)
            if cand_labelled
            else None
        )

        dense_cand_labelled = [
            r for r in labelled if r.retrieval.dense_hit_at_depth is not None
        ]
        dense_cand_hit_rate = (
            sum(1 for r in dense_cand_labelled if r.retrieval.dense_hit_at_depth)
            / len(dense_cand_labelled)
            if dense_cand_labelled
            else None
        )

        sparse_cand_labelled = [
            r for r in labelled if r.retrieval.sparse_hit_at_depth is not None
        ]
        sparse_cand_hit_rate = (
            sum(1 for r in sparse_cand_labelled if r.retrieval.sparse_hit_at_depth)
            / len(sparse_cand_labelled)
            if sparse_cand_labelled
            else None
        )

        summary[cat] = {
            "total_cases": len(results),
            "labelled_cases": n,
            "candidate_hit_rate_at_20": cand_hit_rate,
            "dense_candidate_hit_rate_at_20": dense_cand_hit_rate,
            "sparse_candidate_hit_rate_at_20": sparse_cand_hit_rate,
            "hit_rate_at_1": sum(1 for r in labelled if r.retrieval.hit_at_1) / n,
            "hit_rate_at_3": sum(1 for r in labelled if r.retrieval.hit_at_3) / n,
            "hit_rate_at_5": sum(1 for r in labelled if r.retrieval.hit) / n,
            "mean_reciprocal_rank": (
                sum(r.retrieval.reciprocal_rank for r in labelled) / n
            ),
            "mean_dense_latency_ms": (
                sum(r.retrieval.dense_latency_ms or 0.0 for r in labelled) / n
            ),
            "mean_sparse_latency_ms": (
                sum(r.retrieval.sparse_latency_ms or 0.0 for r in labelled) / n
            ),
            "mean_fusion_latency_ms": (
                sum(r.retrieval.fusion_latency_ms or 0.0 for r in labelled) / n
            ),
            "mean_total_latency_ms": (sum(r.total_latency_ms for r in labelled) / n),
            "errors": [
                {"case_id": r.case_id, "error": r.retrieval.retrieval_error}
                for r in labelled
                if r.retrieval.retrieval_error
            ],
        }

    return summary


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------


def run_hybrid_experiment() -> pathlib.Path:
    """Execute the live hybrid retrieval experiment and persist results."""
    api_key = os.environ.get("LLM_API_KEY", "")

    logger.info("=" * 70)
    logger.info("KIP v1.2 HYBRID RETRIEVAL EXPERIMENT (DENSE + BM25 + RRF)")
    logger.info("Corpus: %s", CORPUS_DIR)
    logger.info("Benchmark: %s", DATASET_PATH)
    logger.info("Control Baseline: %s", CONTROL_BASELINE_PATH)
    logger.info("Collection: %s", COLLECTION_NAME)
    logger.info("Workspace: %s", EVAL_WORKSPACE)
    logger.info(
        "Dense Top-K: %d | Sparse Top-K: %d | RRF k: %d | Final Top-K: %d",
        CANDIDATE_TOP_K,
        CANDIDATE_TOP_K,
        RRF_K,
        FINAL_TOP_K,
    )
    logger.info("=" * 70)

    # -----------------------------------------------------------------------
    # Phase 0: Preflight
    # -----------------------------------------------------------------------
    logger.info("Phase 0: Preflight validation...")
    corpus_ids, raw_dataset = preflight_check(CORPUS_DIR, DATASET_PATH, api_key)
    logger.info(
        "Preflight passed. %d corpus files, %d benchmark cases.",
        len(corpus_ids),
        len(raw_dataset["cases"]),
    )

    # -----------------------------------------------------------------------
    # Phase 1: Initialize services and build indexes
    # -----------------------------------------------------------------------
    logger.info("Phase 1: Initializing services...")

    from app.core.config import Settings
    from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
    from app.services.chunking.service import ChunkingService
    from app.services.documents.models import Document
    from app.services.embeddings.manager import EmbeddingManager
    from app.services.embeddings.service import EmbeddingService
    from app.services.indexing.service import DocumentIndexingService
    from app.services.retrieval.models import RetrievedChunk
    from app.services.retrieval.service import RetrievalService
    from app.services.vector_store.manager import VectorStoreManager
    from app.services.vector_store.service import VectorStoreService
    from evaluation.bm25 import BM25Index
    from evaluation.models import BenchmarkDataset, BenchmarkRunConfig
    from evaluation.runner import EvaluationRunner

    settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_api_key=api_key,
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=768,
        vector_store_provider="qdrant",
        qdrant_collection=COLLECTION_NAME,
        qdrant_url=os.environ.get("QDRANT_URL") or None,
        qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        retrieval_default_top_k=FINAL_TOP_K,
        max_documents_per_workspace=100,
        max_chunks_per_workspace=2000,
    )

    emb_service = EmbeddingService(
        manager=EmbeddingManager(settings=settings),
        doc_formatter=None,
    )
    vs_service = VectorStoreService(manager=VectorStoreManager(settings=settings))
    chunker = ChunkingService(
        FixedSizeChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    )
    indexing_service = DocumentIndexingService(
        chunking_service=chunker,
        embedding_service=emb_service,
        vector_store_service=vs_service,
        settings=settings,
    )
    ret_service = RetrievalService(
        embedding_service=emb_service,
        vector_store_service=vs_service,
        settings=settings,
        query_formatter=None,
    )

    # -----------------------------------------------------------------------
    # Phase 2: Index corpus into Qdrant & build BM25 lexical index
    # -----------------------------------------------------------------------
    logger.info(
        "Phase 2: Indexing %d documents into workspace '%s'...",
        len(corpus_ids),
        EVAL_WORKSPACE,
    )

    bm25_chunks: list[RetrievedChunk] = []
    total_indexed = 0
    total_skipped = 0

    for txt_file in sorted(CORPUS_DIR.glob("*.txt")):
        raw = txt_file.read_bytes()
        doc_id = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8")
        doc = Document.create(
            document_id=doc_id,
            filename=txt_file.name,
            media_type="text/plain",
            text=text,
        )
        # 1. Qdrant dense vector index
        res = indexing_service.index_document(doc, workspace_id=EVAL_WORKSPACE)
        if res.chunks_indexed > 0:
            total_indexed += 1
        else:
            total_skipped += 1

        # 2. Extract chunk for BM25 index (1 chunk per doc in this benchmark)
        chunks = chunker.chunk_document(doc)
        for c in chunks:
            bm25_chunks.append(
                RetrievedChunk(
                    id=c.id,
                    document_id=doc_id,
                    text=c.text,
                    score=0.0,
                    metadata={
                        "filename": txt_file.name,
                        "workspace_id": EVAL_WORKSPACE,
                    },
                )
            )

    logger.info(
        "Indexing complete: %d newly indexed, %d present.", total_indexed, total_skipped
    )
    logger.info("Building BM25 index over %d chunks...", len(bm25_chunks))
    bm25_index = BM25Index(k1=1.5, b=0.75)
    bm25_index.index_chunks(bm25_chunks)
    logger.info(
        "BM25 index built. Unique vocabulary: %d terms.",
        len(bm25_index.doc_frequencies),
    )

    # -----------------------------------------------------------------------
    # Phase 3: Execute Two-Channel Hybrid Evaluation Run
    # -----------------------------------------------------------------------
    logger.info(
        "Phase 3: Running 80-case benchmark (Dense top-%d + Sparse top-%d -> RRF(k=%d) -> top-%d)...",
        CANDIDATE_TOP_K,
        CANDIDATE_TOP_K,
        RRF_K,
        FINAL_TOP_K,
    )

    dataset = BenchmarkDataset(**raw_dataset)

    config = BenchmarkRunConfig(
        benchmark_version=EXPERIMENT_VERSION,
        evaluation_workspace_id=EVAL_WORKSPACE,
        llm_provider="none",
        llm_model="none",
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        retrieval_top_k=FINAL_TOP_K,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        live_llm_available=False,
        inter_case_delay_seconds=INTER_CASE_DELAY_SECONDS,
    )

    runner = EvaluationRunner(
        rag_service=None,
        retrieval_service=ret_service,
        config=config,
        sparse_retriever=bm25_index,
        candidate_top_k=CANDIDATE_TOP_K,
        rrf_k=RRF_K,
    )

    result = runner.evaluate_dataset(dataset)

    # -----------------------------------------------------------------------
    # Phase 4: Category-level aggregation & Latency Profiling
    # -----------------------------------------------------------------------
    logger.info("Phase 4: Computing category metrics and latency percentiles...")
    category_summary = _aggregate_by_category(result.case_results, dataset.cases)

    total_latencies = [cr.total_latency_ms for cr in result.case_results]
    dense_latencies = [
        cr.retrieval.dense_latency_ms
        for cr in result.case_results
        if cr.retrieval.dense_latency_ms is not None
    ]
    sparse_latencies = [
        cr.retrieval.sparse_latency_ms
        for cr in result.case_results
        if cr.retrieval.sparse_latency_ms is not None
    ]
    fusion_latencies = [
        cr.retrieval.fusion_latency_ms
        for cr in result.case_results
        if cr.retrieval.fusion_latency_ms is not None
    ]

    def _percentile(data: list[float], p: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1
        if c < len(sorted_data):
            return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
        return sorted_data[f]

    latency_profiling = {
        "end_to_end_ms": {
            "mean": statistics.mean(total_latencies),
            "median": statistics.median(total_latencies),
            "p90": _percentile(total_latencies, 90.0),
            "p95": _percentile(total_latencies, 95.0),
            "min": min(total_latencies),
            "max": max(total_latencies),
        },
        "dense_retrieval_ms": {
            "mean": statistics.mean(dense_latencies),
            "median": statistics.median(dense_latencies),
            "p90": _percentile(dense_latencies, 90.0),
            "p95": _percentile(dense_latencies, 95.0),
        },
        "sparse_retrieval_ms": {
            "mean": statistics.mean(sparse_latencies),
            "median": statistics.median(sparse_latencies),
            "p90": _percentile(sparse_latencies, 90.0),
            "p95": _percentile(sparse_latencies, 95.0),
        },
        "rrf_fusion_ms": {
            "mean": statistics.mean(fusion_latencies),
            "median": statistics.median(fusion_latencies),
            "p90": _percentile(fusion_latencies, 90.0),
            "p95": _percentile(fusion_latencies, 95.0),
        },
    }

    # Pre-fusion candidate recall across all labelled cases
    labelled_cases = [r for r in result.case_results if r.retrieval.expected_count > 0]
    dense_cand_hits = sum(1 for r in labelled_cases if r.retrieval.dense_hit_at_depth)
    sparse_cand_hits = sum(1 for r in labelled_cases if r.retrieval.sparse_hit_at_depth)
    combined_cand_hits = sum(
        1 for r in labelled_cases if r.retrieval.candidate_hit_at_20
    )
    n_labelled = len(labelled_cases)

    candidate_recall_summary = {
        "dense_hit_rate_at_20": dense_cand_hits / n_labelled if n_labelled > 0 else 0.0,
        "sparse_hit_rate_at_20": sparse_cand_hits / n_labelled
        if n_labelled > 0
        else 0.0,
        "combined_candidate_hit_rate_at_20": combined_cand_hits / n_labelled
        if n_labelled > 0
        else 0.0,
    }

    # -----------------------------------------------------------------------
    # Phase 5: Persist Experiment Artifact
    # -----------------------------------------------------------------------
    out_dir = repo_root / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    treatment_filename = f"kip_v1_2_hybrid_treatment_{stamp}.json"
    out_path = out_dir / treatment_filename

    payload = result.model_dump()
    payload["run_metadata"] = {
        "experiment_name": "v1.2-hybrid-retrieval-treatment",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "runner_script": "evaluation/run_v1_2_hybrid_experiment.py",
        "control_baseline_path": str(CONTROL_BASELINE_PATH),
        "corpus_directory": str(CORPUS_DIR),
        "dataset_path": str(DATASET_PATH),
        "collection_name": COLLECTION_NAME,
        "workspace_id": EVAL_WORKSPACE,
        "dense_candidate_top_k": CANDIDATE_TOP_K,
        "sparse_candidate_top_k": CANDIDATE_TOP_K,
        "final_top_k": FINAL_TOP_K,
        "rrf_k": RRF_K,
        "sparse_retriever": "BM25Okapi(k1=1.5, b=0.75)",
        "fusion_method": "Reciprocal Rank Fusion",
        "sensitive_cases_evaluated": list(sorted(SENSITIVE_CASE_IDS)),
        "sensitive_cases_handling": "Evaluated strictly with original benchmark labels.",
        "candidate_recall": candidate_recall_summary,
        "latency_profiling": latency_profiling,
    }
    payload["category_metrics"] = category_summary

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Saved treatment result to: %s", out_path)

    # -----------------------------------------------------------------------
    # Phase 6: Side-by-side comparison with Control Baseline
    # -----------------------------------------------------------------------
    with open(CONTROL_BASELINE_PATH, encoding="utf-8") as f:
        control_data = json.load(f)

    c_mrr = control_data.get("mean_reciprocal_rank", 0.0)
    c_h1 = control_data.get("hit_rate_at_1", 0.0)
    c_h3 = control_data.get("hit_rate_at_3", 0.0)
    c_h5 = control_data.get("hit_rate_at_5", 0.0)
    c_p95_lat = 643.0  # Measured control baseline P95 latency

    t_mrr = result.mean_reciprocal_rank or 0.0
    t_h1 = result.hit_rate_at_1 or 0.0
    t_h3 = result.hit_rate_at_3 or 0.0
    t_h5 = result.hit_rate_at_5 or 0.0
    t_p95_lat = latency_profiling["end_to_end_ms"]["p95"]

    c_hard_neg_mrr = (
        control_data.get("category_metrics", {})
        .get("hard_negative", {})
        .get("mean_reciprocal_rank", 0.0)
    )
    t_hard_neg_mrr = category_summary.get("hard_negative", {}).get(
        "mean_reciprocal_rank", 0.0
    )

    c_multi_mrr = (
        control_data.get("category_metrics", {})
        .get("multi_concept", {})
        .get("mean_reciprocal_rank", 0.0)
    )
    t_multi_mrr = category_summary.get("multi_concept", {}).get(
        "mean_reciprocal_rank", 0.0
    )

    c_exact_h1 = (
        control_data.get("category_metrics", {})
        .get("exact_terminology", {})
        .get("hit_rate_at_1", 0.0)
    )
    t_exact_h1 = category_summary.get("exact_terminology", {}).get("hit_rate_at_1", 0.0)

    print("\n" + "=" * 78)
    print("KIP v1.2 HYBRID RETRIEVAL EXPERIMENT: TREATMENT VS CONTROL")
    print("=" * 78)
    print(
        f"{'Metric':<32} {'Control (Dense)':<18} {'Treatment (Hybrid)':<20} {'Delta':<10}"
    )
    print("-" * 78)
    print(f"{'Overall MRR':<32} {c_mrr:<18.4f} {t_mrr:<20.4f} {t_mrr - c_mrr:+.4f}")
    print(f"{'Hit Rate @ 1':<32} {c_h1:<18.4f} {t_h1:<20.4f} {t_h1 - c_h1:+.4f}")
    print(f"{'Hit Rate @ 3':<32} {c_h3:<18.4f} {t_h3:<20.4f} {t_h3 - c_h3:+.4f}")
    print(f"{'Hit Rate @ 5':<32} {c_h5:<18.4f} {t_h5:<20.4f} {t_h5 - c_h5:+.4f}")
    print(
        f"{'Pre-Fusion Dense Hit@20':<32} {'N/A':<18} {candidate_recall_summary['dense_hit_rate_at_20']:<20.4f} {'-':<10}"
    )
    print(
        f"{'Pre-Fusion Sparse Hit@20':<32} {'N/A':<18} {candidate_recall_summary['sparse_hit_rate_at_20']:<20.4f} {'-':<10}"
    )
    print(
        f"{'Pre-Fusion Combined Hit@20':<32} {'N/A':<18} {candidate_recall_summary['combined_candidate_hit_rate_at_20']:<20.4f} {'-':<10}"
    )
    print(
        f"{'Hard Negative MRR':<32} {c_hard_neg_mrr:<18.4f} {t_hard_neg_mrr:<20.4f} {t_hard_neg_mrr - c_hard_neg_mrr:+.4f}"
    )
    print(
        f"{'Multi-Concept MRR':<32} {c_multi_mrr:<18.4f} {t_multi_mrr:<20.4f} {t_multi_mrr - c_multi_mrr:+.4f}"
    )
    print(
        f"{'Exact Terminology Hit@1':<32} {c_exact_h1:<18.4f} {t_exact_h1:<20.4f} {t_exact_h1 - c_exact_h1:+.4f}"
    )
    print(
        f"{'P95 Latency (ms)':<32} {c_p95_lat:<18.1f} {t_p95_lat:<20.1f} {t_p95_lat - c_p95_lat:+.1f}"
    )
    print("=" * 78)

    print("\nCategory Comparison (MRR):")
    print(
        f"{'Category':<22} {'Cases':<8} {'Control MRR':<15} {'Treatment MRR':<15} {'Delta':<10}"
    )
    print("-" * 70)
    for cat in sorted(category_summary.keys()):
        c_cat_mrr = (
            control_data.get("category_metrics", {})
            .get(cat, {})
            .get("mean_reciprocal_rank", 0.0)
        )
        t_cat_mrr = category_summary[cat]["mean_reciprocal_rank"]
        print(
            f"{cat:<22} {category_summary[cat]['labelled_cases']:<8} {c_cat_mrr:<15.4f} {t_cat_mrr:<15.4f} {t_cat_mrr - c_cat_mrr:+.4f}"
        )

    print("\nStage Latency Breakdown (Mean ms):")
    print(
        f"  Dense Retrieval:  {latency_profiling['dense_retrieval_ms']['mean']:.2f} ms (P95: {latency_profiling['dense_retrieval_ms']['p95']:.2f} ms)"
    )
    print(
        f"  Sparse Retrieval: {latency_profiling['sparse_retrieval_ms']['mean']:.2f} ms (P95: {latency_profiling['sparse_retrieval_ms']['p95']:.2f} ms)"
    )
    print(
        f"  RRF Fusion:       {latency_profiling['rrf_fusion_ms']['mean']:.2f} ms (P95: {latency_profiling['rrf_fusion_ms']['p95']:.2f} ms)"
    )
    print(
        f"  End-to-End Total: {latency_profiling['end_to_end_ms']['mean']:.2f} ms (P95: {latency_profiling['end_to_end_ms']['p95']:.2f} ms)"
    )

    # Evaluation targets check
    primary_pass = t_mrr >= 0.8500
    hard_neg_pass = t_hard_neg_mrr >= 0.6500
    multi_concept_pass = t_multi_mrr >= 1.0000
    exact_term_pass = t_exact_h1 > c_exact_h1
    latency_guardrail_pass = (t_p95_lat - c_p95_lat) <= 300.0

    print("\nSuccess and Rejection Criteria Assessment:")
    print(
        f"  [1] Primary Target (Overall MRR >= 0.8500):       {t_mrr:.4f} -> {'PASSED' if primary_pass else 'FAILED'}"
    )
    print(
        f"  [2] Secondary Target (Hard Neg MRR >= 0.6500):     {t_hard_neg_mrr:.4f} -> {'PASSED' if hard_neg_pass else 'FAILED'}"
    )
    print(
        f"  [3] Safety Target (Multi-Concept MRR == 1.0000):   {t_multi_mrr:.4f} -> {'PASSED' if multi_concept_pass else 'FAILED'}"
    )
    print(
        f"  [4] Secondary Target (Exact Term Hit@1 > {c_exact_h1:.4f}): {t_exact_h1:.4f} -> {'PASSED' if exact_term_pass else 'FAILED'}"
    )
    print(
        f"  [5] Latency Guardrail (Delta P95 <= +300ms):       {t_p95_lat - c_p95_lat:+.1f} ms -> {'PASSED' if latency_guardrail_pass else 'REJECTED'}"
    )

    return out_path


if __name__ == "__main__":
    run_hybrid_experiment()
