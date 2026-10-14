"""Executable runner for the KIP v1.2 cross-encoder reranking experiment.

Evaluates an isolated two-stage retrieval pipeline:
  Stage A (Candidate Retrieval): Dense Gemini embedding + Qdrant top-20 search
  Stage B (Neural Reranking):   cross-encoder/ms-marco-MiniLM-L-6-v2 scoring
                                and sorting candidates to return top-5.

Evaluates against the identical 80-case expanded benchmark and 50-document corpus,
comparing results against the control baseline (v1.2 expanded baseline).

Configuration:
- Embedding Provider:  Google Gemini (gemini-embedding-2, 768 dimensions)
- Vector Store:        Qdrant, dedicated collection kip_eval_v1_2_expanded
- Evaluation Workspace: kip-eval-workspace-v1-2-expanded
- Reference Corpus:    benchmarks/corpus_v1_2_expanded/ (50 .txt files, LF only)
- Benchmark Dataset:   benchmarks/kip_v1_2_expanded_benchmark.json (80 cases)
- Candidate Top-K:     20
- Final Top-K:         5
- Cross-Encoder Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (ONNX Runtime CPU)

Usage:
    python evaluation/run_v1_2_cross_encoder_experiment.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import statistics
import sys
import time
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
logger = logging.getLogger("evaluation.run_v1_2_cross_encoder_experiment")

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
EXPERIMENT_VERSION = "v1.2-cross-encoder-treatment"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
CANDIDATE_TOP_K = 20
FINAL_TOP_K = 5
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
INTER_CASE_DELAY_SECONDS = 0.5


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
        raise ValueError(
            f"Preflight failed: Dataset file not found at {dataset_path}"
        )

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
                f"Preflight failed: Corpus file {txt_file.name} contains CR bytes."
            )
        corpus_ids[txt_file.name] = hashlib.sha256(raw_bytes).hexdigest()

    dataset_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset_data.get("cases", [])
    if len(cases) != 80:
        raise ValueError(
            f"Preflight failed: Expected 80 benchmark cases, found {len(cases)}."
        )

    return corpus_ids, dataset_data


# ---------------------------------------------------------------------------
# Category-level metric aggregation
# ---------------------------------------------------------------------------


def _aggregate_by_category(case_results, dataset_cases) -> dict[str, Any]:
    """Compute metrics broken down by benchmark category."""
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

        has_rerank_lat = [
            r for r in results if r.retrieval.reranking_latency_ms is not None
        ]
        mean_rerank_lat = (
            sum(r.retrieval.reranking_latency_ms or 0.0 for r in has_rerank_lat)
            / len(has_rerank_lat)
            if has_rerank_lat
            else 0.0
        )

        summary[cat] = {
            "total_cases": len(results),
            "labelled_cases": n,
            "candidate_hit_rate_at_20": cand_hit_rate,
            "hit_rate_at_1": sum(1 for r in labelled if r.retrieval.hit_at_1) / n,
            "hit_rate_at_3": sum(1 for r in labelled if r.retrieval.hit_at_3) / n,
            "hit_rate_at_5": sum(1 for r in labelled if r.retrieval.hit) / n,
            "mean_reciprocal_rank": (
                sum(r.retrieval.reciprocal_rank for r in labelled) / n
            ),
            "mean_dense_latency_ms": (
                sum(r.retrieval.retrieval_latency_ms for r in labelled) / n
            ),
            "mean_rerank_latency_ms": mean_rerank_lat,
            "mean_total_latency_ms": (
                sum(r.total_latency_ms for r in labelled) / n
            ),
            "errors": [
                {"case_id": r.case_id, "error": r.retrieval.retrieval_error}
                for r in labelled
                if r.retrieval.retrieval_error
            ],
        }

    return summary


def _compute_distribution(values: list[float]) -> dict[str, float]:
    """Compute distribution statistics for latency values."""
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}

    s = sorted(values)
    n = len(s)
    p90_idx = min(int(n * 0.90), n - 1)
    p95_idx = min(int(n * 0.95), n - 1)

    return {
        "min": float(min(s)),
        "median": float(statistics.median(s)),
        "mean": float(statistics.mean(s)),
        "p90": float(s[p90_idx]),
        "p95": float(s[p95_idx]),
        "max": float(max(s)),
    }


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------


def run_cross_encoder_experiment() -> pathlib.Path:
    """Execute the two-stage retrieval experiment and persist results."""
    api_key = os.environ.get("LLM_API_KEY")

    logger.info("Starting KIP v1.2 Cross-Encoder Reranking Experiment...")
    corpus_ids, raw_dataset = preflight_check(CORPUS_DIR, DATASET_PATH, api_key)
    logger.info(
        "Preflight passed: %d corpus files, %d benchmark cases.",
        len(corpus_ids),
        len(raw_dataset["cases"]),
    )

    # -----------------------------------------------------------------------
    # Phase 1: Service initialisation & Model Loading
    # -----------------------------------------------------------------------
    logger.info("Phase 1: Initialising retrieval services and cross-encoder...")

    from app.core.config import Settings
    from app.services.chunking.chunkers.fixed_size import FixedSizeChunker
    from app.services.chunking.service import ChunkingService
    from app.services.documents.models import Document
    from app.services.embeddings.manager import EmbeddingManager
    from app.services.embeddings.service import EmbeddingService
    from app.services.indexing.service import DocumentIndexingService
    from app.services.retrieval.service import RetrievalService
    from app.services.vector_store.manager import VectorStoreManager
    from app.services.vector_store.service import VectorStoreService
    from evaluation.models import BenchmarkDataset, BenchmarkRunConfig
    from evaluation.reranker import CrossEncoderReranker
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

    # Initialize cross-encoder reranker and record cold-start duration
    t_load_start = time.perf_counter()
    reranker = CrossEncoderReranker(model_name=CROSS_ENCODER_MODEL)
    model_load_ms = reranker.cold_start_load_ms or ((time.perf_counter() - t_load_start) * 1000)
    logger.info("Cross-encoder model loaded in %.2f ms", model_load_ms)

    # -----------------------------------------------------------------------
    # Phase 2: Index corpus into isolated evaluation workspace
    # -----------------------------------------------------------------------
    logger.info(
        "Phase 2: Indexing %d corpus documents into workspace '%s' (collection '%s')...",
        len(corpus_ids),
        EVAL_WORKSPACE,
        COLLECTION_NAME,
    )

    total_indexed = 0
    total_skipped = 0
    for txt_file in sorted(CORPUS_DIR.glob("*.txt")):
        raw = txt_file.read_bytes()
        doc_id = hashlib.sha256(raw).hexdigest()
        doc = Document.create(
            document_id=doc_id,
            filename=txt_file.name,
            media_type="text/plain",
            text=raw.decode("utf-8"),
        )
        res = indexing_service.index_document(doc, workspace_id=EVAL_WORKSPACE)
        if res.chunks_indexed > 0:
            total_indexed += 1
        else:
            total_skipped += 1

    logger.info(
        "Indexing complete: %d newly indexed, %d already present.",
        total_indexed,
        total_skipped,
    )

    # -----------------------------------------------------------------------
    # Phase 3: Execute Two-Stage Evaluation Run
    # -----------------------------------------------------------------------
    logger.info(
        "Phase 3: Running 80-case benchmark (Stage A top-%d -> Stage B top-%d)...",
        CANDIDATE_TOP_K,
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
        reranker=reranker,
        candidate_top_k=CANDIDATE_TOP_K,
    )

    result = runner.evaluate_dataset(dataset)

    # -----------------------------------------------------------------------
    # Phase 4: Category-level aggregation & Latency Profiling
    # -----------------------------------------------------------------------
    logger.info("Phase 4: Computing category breakdowns and latency distributions...")
    category_metrics = _aggregate_by_category(result.case_results, dataset.cases)

    dense_latencies = [cr.retrieval.retrieval_latency_ms for cr in result.case_results]
    rerank_latencies = [
        cr.retrieval.reranking_latency_ms or 0.0 for cr in result.case_results
    ]
    total_latencies = [cr.total_latency_ms for cr in result.case_results]

    latency_stats = {
        "candidate_retrieval_dense_ms": _compute_distribution(dense_latencies),
        "cross_encoder_rerank_ms": _compute_distribution(rerank_latencies),
        "end_to_end_ms": _compute_distribution(total_latencies),
        "model_cold_start_load_ms": model_load_ms,
    }

    # -----------------------------------------------------------------------
    # Phase 5: Load Control Baseline for Direct Comparison
    # -----------------------------------------------------------------------
    control_data: dict[str, Any] = {}
    if CONTROL_BASELINE_PATH.exists():
        try:
            control_data = json.loads(CONTROL_BASELINE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read control baseline: %s", exc)

    # -----------------------------------------------------------------------
    # Phase 6: Build Enriched Result Artifact
    # -----------------------------------------------------------------------
    timestamp_slug = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    corpus_sha256 = hashlib.sha256(
        json.dumps(sorted(corpus_ids.items()), sort_keys=True).encode()
    ).hexdigest()
    dataset_sha256 = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()

    output: dict[str, Any] = {
        **json.loads(result.model_dump_json()),
        "run_metadata": {
            "run_id": result.run_id,
            "timestamp": result.timestamp,
            "experiment_version": EXPERIMENT_VERSION,
            "control_baseline_run_id": control_data.get("run_id"),
            "corpus_dir": str(CORPUS_DIR.relative_to(repo_root)),
            "corpus_sha256": corpus_sha256,
            "corpus_doc_count": len(corpus_ids),
            "dataset_path": str(DATASET_PATH.relative_to(repo_root)),
            "dataset_sha256": dataset_sha256,
            "dataset_case_count": len(dataset.cases),
            "chunking": {
                "algorithm": "fixed_size",
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
            },
            "candidate_retrieval": {
                "provider": settings.embedding_provider,
                "model": settings.embedding_model,
                "dimensions": settings.embedding_dimensions,
                "candidate_top_k": CANDIDATE_TOP_K,
                "vector_store": settings.vector_store_provider,
                "collection": COLLECTION_NAME,
                "workspace": EVAL_WORKSPACE,
            },
            "reranking": {
                "model_name": CROSS_ENCODER_MODEL,
                "engine": "onnxruntime",
                "execution_provider": "CPUExecutionProvider",
                "max_sequence_length": 512,
                "final_top_k": FINAL_TOP_K,
                "score_interpretation": "raw_unnormalized_logits (higher = more relevant)",
            },
            "generation": "omitted (retrieval-only evaluation)",
        },
        "category_metrics": category_metrics,
        "latency_statistics": latency_stats,
    }

    treatment_file = (
        repo_root / "benchmarks" / f"kip_v1_2_reranking_treatment_{timestamp_slug}.json"
    )
    treatment_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Treatment result saved to: %s", treatment_file)

    # -----------------------------------------------------------------------
    # Phase 7: Display Comparative Terminal Summary
    # -----------------------------------------------------------------------
    n_labelled = result.labelled_cases
    ctrl_hr1 = control_data.get("hit_rate_at_1", 0.6875)
    ctrl_hr3 = control_data.get("hit_rate_at_3", 0.8375)
    ctrl_hr5 = control_data.get("hit_rate_at_5", 0.8750)
    ctrl_mrr = control_data.get("mean_reciprocal_rank", 0.7623)
    ctrl_p95 = 643.0

    treat_hr1 = result.hit_rate_at_1 or 0.0
    treat_hr3 = result.hit_rate_at_3 or 0.0
    treat_hr5 = result.hit_rate_at_5 or 0.0
    treat_mrr = result.mean_reciprocal_rank or 0.0
    cand_h20 = result.candidate_hit_rate_at_20 or 0.0
    treat_p95 = latency_stats["end_to_end_ms"]["p95"]

    print("\n" + "=" * 78)
    print("KIP v1.2 CONTROLLED EXPERIMENT: CROSS-ENCODER RERANKING vs CONTROL BASELINE")
    print("=" * 78)
    print(f"Run ID:                  {result.run_id}")
    print(f"Treatment Model:         {CROSS_ENCODER_MODEL}")
    print(f"Pipeline:                Dense Top-{CANDIDATE_TOP_K} -> Cross-Encoder Top-{FINAL_TOP_K}")
    print(f"Benchmark Cases:         {result.total_cases} ({n_labelled} labelled)")
    print(f"Model Cold-Start:        {model_load_ms:.1f} ms")
    print("-" * 78)
    print(f"{'Metric':<25} {'Control Baseline':>18} {'Treatment (Reranked)':>22} {'Delta':>10}")
    print("-" * 78)

    def _diff(treat: float, ctrl: float, fmt: str = "+.4f") -> str:
        d = treat - ctrl
        return f"{d:{fmt}}"

    print(f"{'Candidate Hit@20':<25} {'N/A (single-stage)':>18} {cand_h20:>21.4f} {'-':>10}")
    print(f"{'Hit Rate @ 1':<25} {ctrl_hr1:>18.4f} {treat_hr1:>21.4f} {_diff(treat_hr1, ctrl_hr1):>10}")
    print(f"{'Hit Rate @ 3':<25} {ctrl_hr3:>18.4f} {treat_hr3:>21.4f} {_diff(treat_hr3, ctrl_hr3):>10}")
    print(f"{'Hit Rate @ 5':<25} {ctrl_hr5:>18.4f} {treat_hr5:>21.4f} {_diff(treat_hr5, ctrl_hr5):>10}")
    print(f"{'Mean Reciprocal Rank':<25} {ctrl_mrr:>18.4f} {treat_mrr:>21.4f} {_diff(treat_mrr, ctrl_mrr):>10}")
    print(f"{'P95 Latency (ms)':<25} {ctrl_p95:>18.1f} {treat_p95:>21.1f} {_diff(treat_p95, ctrl_p95, '+.1f'):>10}")
    print("-" * 78)
    print("Category Breakdown Comparison (MRR):")
    print(f"  {'Category':<22} {'Cases':>5} {'Candidate@20':>13} {'Control MRR':>12} {'Treat MRR':>10} {'Delta':>9}")
    print("  " + "-" * 74)

    ctrl_cats = control_data.get("category_metrics", {})
    for cat, cm in sorted(category_metrics.items()):
        c_mrr = ctrl_cats.get(cat, {}).get("mean_reciprocal_rank", 0.0)
        t_mrr = cm["mean_reciprocal_rank"]
        c_cand = cm.get("candidate_hit_rate_at_20") or 0.0
        delta = t_mrr - c_mrr
        print(
            f"  {cat:<22} {cm['labelled_cases']:>5} {c_cand:>13.4f} {c_mrr:>12.4f} {t_mrr:>10.4f} {delta:>+9.4f}"
        )

    print("-" * 78)
    print("Latency Quantiles (Treatment End-to-End):")
    e2e = latency_stats["end_to_end_ms"]
    rr_lat = latency_stats["cross_encoder_rerank_ms"]
    print(f"  Steady-State Rerank Latency: Median={rr_lat['median']:.1f}ms, Mean={rr_lat['mean']:.1f}ms, P95={rr_lat['p95']:.1f}ms")
    print(f"  Total End-to-End Latency:    Median={e2e['median']:.1f}ms, Mean={e2e['mean']:.1f}ms, P95={e2e['p95']:.1f}ms")
    print("=" * 78)
    print(f"Treatment Artifact: {treatment_file.name}")
    print("=" * 78 + "\n")

    return treatment_file


if __name__ == "__main__":
    try:
        run_cross_encoder_experiment()
    except ValueError as exc:
        logger.error("Preflight failure: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Experiment execution failed: %s", exc)
        sys.exit(1)
