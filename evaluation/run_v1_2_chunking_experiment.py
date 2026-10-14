"""Executable runner for the KIP v1.2 sentence-boundary chunking experiment.

Evaluates an isolated chunking segmentation experiment:
  Control:   FixedSizeChunker(chunk_size=1000, chunk_overlap=200) -> 50 chunks (1 chunk/doc)
  Treatment: SentenceBoundaryChunker(target_chunk_size=400, min_chunk_size=150, overlap_sentences=1)
             -> 173 sentence-aligned semantic chunks across 50 documents.

Evaluates against the identical 80-case expanded benchmark and 50-document corpus,
comparing results against the frozen v1.2 expanded baseline.

Configuration:
- Embedding Provider:  Google Gemini (gemini-embedding-2, 768 dimensions)
- Vector Store:        Qdrant, dedicated collection kip_eval_v1_2_chunking
- Evaluation Workspace: kip-eval-workspace-v1-2-chunking
- Reference Corpus:    benchmarks/corpus_v1_2_expanded/ (50 .txt files, LF only)
- Benchmark Dataset:   benchmarks/kip_v1_2_expanded_benchmark.json (80 cases)
- Target Chunk Size:   400 characters
- Min Chunk Size:      150 characters
- Sentence Overlap:    1 sentence
- Final Top-K:         5 (evaluated both raw and document-deduplicated)
- Inter-case delay:    0.5s

Usage:
    python evaluation/run_v1_2_chunking_experiment.py
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
logger = logging.getLogger("evaluation.run_v1_2_chunking_experiment")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORPUS_DIR = repo_root / "benchmarks" / "corpus_v1_2_expanded"
DATASET_PATH = repo_root / "benchmarks" / "kip_v1_2_expanded_benchmark.json"
CONTROL_BASELINE_PATH = (
    repo_root / "benchmarks" / "kip_v1_2_expanded_baseline_20261014_112147.json"
)
COLLECTION_NAME = "kip_eval_v1_2_chunking"
EVAL_WORKSPACE = "kip-eval-workspace-v1-2-chunking"
EXPERIMENT_VERSION = "v1.2-sentence-chunking-treatment"
TARGET_CHUNK_SIZE = 400
MIN_CHUNK_SIZE = 150
OVERLAP_SENTENCES = 1
FINAL_TOP_K = 5
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
        raise ValueError(f"Preflight failed: Corpus directory not found at {corpus_dir}")

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

    found_sensitive = SENSITIVE_CASE_IDS.intersection(set(case_ids))
    if len(found_sensitive) != len(SENSITIVE_CASE_IDS):
        missing = SENSITIVE_CASE_IDS - found_sensitive
        raise ValueError(f"Preflight failed: Sensitive cases missing: {missing}")

    return corpus_ids, dataset_data


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------


def _compute_metrics_from_ranked_docs(
    ranked_doc_ids: list[str],
    expected_doc_ids: list[str],
) -> tuple[bool, bool, bool, bool, float]:
    """Compute hit, hit@1, hit@3, hit@5, and reciprocal rank."""
    expected_set = set(expected_doc_ids)
    hit_1 = bool(ranked_doc_ids and ranked_doc_ids[0] in expected_set)
    hit_3 = any(d in expected_set for d in ranked_doc_ids[:3])
    hit_5 = any(d in expected_set for d in ranked_doc_ids[:5])

    rr = 0.0
    for rank, did in enumerate(ranked_doc_ids[:5], start=1):
        if did in expected_set:
            rr = 1.0 / rank
            break

    return hit_5, hit_1, hit_3, hit_5, rr


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


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------


def run_chunking_experiment() -> pathlib.Path:
    """Execute the live sentence-boundary chunking experiment and persist results."""
    api_key = os.environ.get("LLM_API_KEY", "")

    logger.info("=" * 70)
    logger.info("KIP v1.2 CHUNKING EXPERIMENT (SENTENCE BOUNDARY SEGMENTATION)")
    logger.info("Corpus: %s", CORPUS_DIR)
    logger.info("Benchmark: %s", DATASET_PATH)
    logger.info("Target Chunk Size: %d | Min Chunk Size: %d | Overlap Sentences: %d",
                TARGET_CHUNK_SIZE, MIN_CHUNK_SIZE, OVERLAP_SENTENCES)
    logger.info("Collection: %s | Workspace: %s", COLLECTION_NAME, EVAL_WORKSPACE)
    logger.info("=" * 70)

    # -----------------------------------------------------------------------
    # Phase 0: Preflight
    # -----------------------------------------------------------------------
    logger.info("Phase 0: Preflight validation...")
    corpus_ids, raw_dataset = preflight_check(CORPUS_DIR, DATASET_PATH, api_key)
    logger.info("Preflight passed. %d corpus files, %d benchmark cases.",
                len(corpus_ids), len(raw_dataset["cases"]))

    # -----------------------------------------------------------------------
    # Phase 1: Initialize services
    # -----------------------------------------------------------------------
    logger.info("Phase 1: Initializing services...")

    from app.core.config import Settings
    from app.services.chunking.chunkers.sentence_boundary import (
        SentenceBoundaryChunker,
    )
    from app.services.chunking.service import ChunkingService
    from app.services.documents.models import Document
    from app.services.embeddings.manager import EmbeddingManager
    from app.services.embeddings.service import EmbeddingService
    from app.services.indexing.service import DocumentIndexingService
    from app.services.retrieval.models import RetrievalQuery
    from app.services.retrieval.service import RetrievalService
    from app.services.vector_store.manager import VectorStoreManager
    from app.services.vector_store.service import VectorStoreService

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
        chunk_size=TARGET_CHUNK_SIZE,
        chunk_overlap=100,
        retrieval_default_top_k=FINAL_TOP_K,
        max_documents_per_workspace=100,
        max_chunks_per_workspace=2000,
    )

    emb_service = EmbeddingService(
        manager=EmbeddingManager(settings=settings),
        doc_formatter=None,
    )
    vs_service = VectorStoreService(manager=VectorStoreManager(settings=settings))
    sentence_chunker = SentenceBoundaryChunker(
        target_chunk_size=TARGET_CHUNK_SIZE,
        min_chunk_size=MIN_CHUNK_SIZE,
        overlap_sentences=OVERLAP_SENTENCES,
    )
    chunking_service = ChunkingService(sentence_chunker)
    indexing_service = DocumentIndexingService(
        chunking_service=chunking_service,
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
    # Phase 2: Index corpus using SentenceBoundaryChunker
    # -----------------------------------------------------------------------
    logger.info("Phase 2: Indexing corpus with SentenceBoundaryChunker...")
    t_index_start = time.perf_counter()

    total_chunks_indexed = 0
    total_docs_indexed = 0
    chunks_per_doc_list = []

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
        # Retry with backoff if Gemini API rate limits (100 req/min)
        res = None
        for attempt in range(5):
            try:
                res = indexing_service.index_document(doc, workspace_id=EVAL_WORKSPACE)
                break
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning(
                        "Rate limit on document %s. Sleeping 25s (attempt %d/5)...",
                        txt_file.name,
                        attempt + 1,
                    )
                    time.sleep(25.0)
                else:
                    raise

        if res is not None:
            total_docs_indexed += 1
            total_chunks_indexed += res.chunks_indexed
            chunks_per_doc_list.append(res.chunks_indexed)

        # Rate pacing: keep requests well within 100/min quota
        time.sleep(0.65)

    indexing_duration_seconds = time.perf_counter() - t_index_start
    logger.info(
        "Indexing complete: %d docs, %d chunks (mean %.2f chunks/doc) in %.2fs (%.1fms/doc).",
        total_docs_indexed,
        total_chunks_indexed,
        total_chunks_indexed / total_docs_indexed,
        indexing_duration_seconds,
        (indexing_duration_seconds / total_docs_indexed) * 1000,
    )

    # -----------------------------------------------------------------------
    # Phase 3: Cold-start warmup
    # -----------------------------------------------------------------------
    logger.info("Phase 3: Warmup query to eliminate TLS/HTTP cold-start outliers...")
    warmup_start = time.perf_counter()
    _ = ret_service.search(
        RetrievalQuery(
            text="Warmup ping query for initialization",
            top_k=5,
            workspace_id=EVAL_WORKSPACE,
        )
    )
    warmup_latency_ms = (time.perf_counter() - warmup_start) * 1000
    logger.info("Warmup query completed in %.2fms. Ready for benchmark evaluation.", warmup_latency_ms)

    # -----------------------------------------------------------------------
    # Phase 4: Execute Benchmark Evaluation
    # -----------------------------------------------------------------------
    logger.info("Phase 4: Running 80-case benchmark (measuring raw and deduped top-%d)...", FINAL_TOP_K)

    cases = raw_dataset["cases"]
    case_results: list[dict[str, Any]] = []
    latencies: list[float] = []

    for i, case in enumerate(cases):
        if i > 0 and INTER_CASE_DELAY_SECONDS > 0:
            time.sleep(INTER_CASE_DELAY_SECONDS)

        cid = case["id"]
        question = case["question"]
        cat = case.get("metadata", {}).get("category", "unknown")
        expected_doc_ids = case.get("expected_document_ids", [])

        # Time steady-state query retrieval
        t_q_start = time.perf_counter()
        retrieval_error: str | None = None
        retrieved_chunks = []
        try:
            # Query top 10 chunks to allow both raw top-5 and deduped top-5 analysis
            q = RetrievalQuery(
                text=question,
                top_k=10,
                workspace_id=EVAL_WORKSPACE,
            )
            for q_attempt in range(5):
                try:
                    retrieved_chunks = ret_service.search(q)
                    break
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        logger.warning(
                            "Rate limit on query %s. Sleeping 25s (attempt %d/5)...",
                            cid,
                            q_attempt + 1,
                        )
                        time.sleep(25.0)
                    else:
                        raise
        except Exception as exc:
            retrieval_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Retrieval failed for %s: %s", cid, retrieval_error)

        t_q_end = time.perf_counter()
        query_latency_ms = (t_q_end - t_q_start) * 1000
        latencies.append(query_latency_ms)

        # 1. Raw Top-5 chunk retrieval metrics
        raw_top_5_chunks = retrieved_chunks[:FINAL_TOP_K]
        raw_doc_ids = [c.document_id for c in raw_top_5_chunks if c.document_id]
        h5_raw, h1_raw, h3_raw, _, rr_raw = _compute_metrics_from_ranked_docs(
            raw_doc_ids, expected_doc_ids
        )

        # 2. Document-deduplicated Top-5 retrieval metrics
        # (first chunk seen per unique document, preserving highest scoring chunk)
        seen_docs: set[str] = set()
        dedup_chunks = []
        for c in retrieved_chunks:
            did = c.document_id
            if did and did not in seen_docs:
                seen_docs.add(did)
                dedup_chunks.append(c)
                if len(dedup_chunks) >= FINAL_TOP_K:
                    break

        dedup_doc_ids = [c.document_id for c in dedup_chunks]
        h5_dedup, h1_dedup, h3_dedup, _, rr_dedup = _compute_metrics_from_ranked_docs(
            dedup_doc_ids, expected_doc_ids
        )

        case_results.append({
            "case_id": cid,
            "category": cat,
            "question": question,
            "expected_doc_ids": expected_doc_ids,
            "query_latency_ms": query_latency_ms,
            "retrieval_error": retrieval_error,
            # Raw results
            "raw_retrieved_chunk_ids": [c.id for c in raw_top_5_chunks],
            "raw_retrieved_doc_ids": raw_doc_ids,
            "raw_hit": h5_raw,
            "raw_hit_at_1": h1_raw,
            "raw_hit_at_3": h3_raw,
            "raw_reciprocal_rank": rr_raw,
            # Deduped results
            "dedup_retrieved_chunk_ids": [c.id for c in dedup_chunks],
            "dedup_retrieved_doc_ids": dedup_doc_ids,
            "dedup_hit": h5_dedup,
            "dedup_hit_at_1": h1_dedup,
            "dedup_hit_at_3": h3_dedup,
            "dedup_reciprocal_rank": rr_dedup,
        })

    # -----------------------------------------------------------------------
    # Phase 5: Aggregate metrics and profiling
    # -----------------------------------------------------------------------
    n = len(case_results)
    mean_rr_raw = sum(cr["raw_reciprocal_rank"] for cr in case_results) / n
    hit_1_raw = sum(1 for cr in case_results if cr["raw_hit_at_1"]) / n
    hit_3_raw = sum(1 for cr in case_results if cr["raw_hit_at_3"]) / n
    hit_5_raw = sum(1 for cr in case_results if cr["raw_hit"]) / n

    mean_rr_dedup = sum(cr["dedup_reciprocal_rank"] for cr in case_results) / n
    hit_1_dedup = sum(1 for cr in case_results if cr["dedup_hit_at_1"]) / n
    hit_3_dedup = sum(1 for cr in case_results if cr["dedup_hit_at_3"]) / n
    hit_5_dedup = sum(1 for cr in case_results if cr["dedup_hit"]) / n

    # Category aggregation (both raw and dedup)
    cat_buckets: dict[str, list] = {}
    for cr in case_results:
        cat = cr["category"]
        if cat not in cat_buckets:
            cat_buckets[cat] = []
        cat_buckets[cat].append(cr)

    category_summary: dict[str, Any] = {}
    for cat, items in sorted(cat_buckets.items()):
        cnt = len(items)
        category_summary[cat] = {
            "total_cases": cnt,
            "raw_mrr": sum(cr["raw_reciprocal_rank"] for cr in items) / cnt,
            "raw_hit_at_1": sum(1 for cr in items if cr["raw_hit_at_1"]) / cnt,
            "raw_hit_at_3": sum(1 for cr in items if cr["raw_hit_at_3"]) / cnt,
            "raw_hit_at_5": sum(1 for cr in items if cr["raw_hit"]) / cnt,
            "dedup_mrr": sum(cr["dedup_reciprocal_rank"] for cr in items) / cnt,
            "dedup_hit_at_1": sum(1 for cr in items if cr["dedup_hit_at_1"]) / cnt,
            "dedup_hit_at_3": sum(1 for cr in items if cr["dedup_hit_at_3"]) / cnt,
            "dedup_hit_at_5": sum(1 for cr in items if cr["dedup_hit"]) / cnt,
            "mean_latency_ms": sum(cr["query_latency_ms"] for cr in items) / cnt,
        }

    latency_profiling = {
        "mean": statistics.mean(latencies),
        "median": statistics.median(latencies),
        "p90": _percentile(latencies, 90.0),
        "p95": _percentile(latencies, 95.0),
        "min": min(latencies),
        "max": max(latencies),
        "warmup_query_ms": warmup_latency_ms,
        "indexing_duration_seconds": indexing_duration_seconds,
    }

    # -----------------------------------------------------------------------
    # Phase 6: Save Treatment Artifact
    # -----------------------------------------------------------------------
    out_dir = repo_root / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    treatment_filename = f"kip_v1_2_chunking_treatment_{stamp}.json"
    out_path = out_dir / treatment_filename

    run_id = hashlib.md5(stamp.encode()).hexdigest()
    artifact_data = {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "experiment_name": "v1.2-sentence-boundary-chunking",
        "configuration": {
            "chunker": "SentenceBoundaryChunker",
            "target_chunk_size": TARGET_CHUNK_SIZE,
            "min_chunk_size": MIN_CHUNK_SIZE,
            "overlap_sentences": OVERLAP_SENTENCES,
            "total_documents": total_docs_indexed,
            "total_chunks_indexed": total_chunks_indexed,
            "mean_chunks_per_doc": total_chunks_indexed / total_docs_indexed,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "vector_store_provider": settings.vector_store_provider,
            "collection_name": COLLECTION_NAME,
            "workspace_id": EVAL_WORKSPACE,
            "top_k": FINAL_TOP_K,
        },
        "overall_metrics": {
            "raw": {
                "mean_reciprocal_rank": mean_rr_raw,
                "hit_rate_at_1": hit_1_raw,
                "hit_rate_at_3": hit_3_raw,
                "hit_rate_at_5": hit_5_raw,
            },
            "deduped": {
                "mean_reciprocal_rank": mean_rr_dedup,
                "hit_rate_at_1": hit_1_dedup,
                "hit_rate_at_3": hit_3_dedup,
                "hit_rate_at_5": hit_5_dedup,
            },
        },
        "latency_profiling": latency_profiling,
        "category_metrics": category_summary,
        "case_results": case_results,
    }

    out_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
    logger.info("Saved chunking treatment result to: %s", out_path)

    # -----------------------------------------------------------------------
    # Phase 7: Side-by-Side Comparison with Control Baseline
    # -----------------------------------------------------------------------
    with open(CONTROL_BASELINE_PATH, encoding="utf-8") as f:
        control_data = json.load(f)

    c_mrr = control_data.get("mean_reciprocal_rank", 0.0)
    c_h1 = control_data.get("hit_rate_at_1", 0.0)
    c_h3 = control_data.get("hit_rate_at_3", 0.0)
    c_h5 = control_data.get("hit_rate_at_5", 0.0)
    c_p95_lat = 643.0  # Measured baseline P95 latency

    c_cats = control_data.get("category_metrics", {})

    print("\n" + "=" * 85)
    print("KIP v1.2 CHUNKING EXPERIMENT: TREATMENT VS CONTROL BASELINE")
    print("=" * 85)
    print(f"{'Metric':<32} {'Control (1000ch)':<18} {'Treatment (Raw)':<18} {'Treatment (Dedup)':<18}")
    print("-" * 85)
    print(f"{'Overall MRR':<32} {c_mrr:<18.4f} {mean_rr_raw:<18.4f} {mean_rr_dedup:<18.4f}")
    print(f"{'Hit Rate @ 1':<32} {c_h1:<18.4f} {hit_1_raw:<18.4f} {hit_1_dedup:<18.4f}")
    print(f"{'Hit Rate @ 3':<32} {c_h3:<18.4f} {hit_3_raw:<18.4f} {hit_3_dedup:<18.4f}")
    print(f"{'Hit Rate @ 5':<32} {c_h5:<18.4f} {hit_5_raw:<18.4f} {hit_5_dedup:<18.4f}")
    print(f"{'Total Index Chunks':<32} {'50 (1.0/doc)':<18} {f'{total_chunks_indexed} (3.5/doc)':<18} {f'{total_chunks_indexed} (3.5/doc)':<18}")
    print(f"{'Indexing Duration':<32} {'~28.0s':<18} {f'{indexing_duration_seconds:.1f}s':<18} {f'{indexing_duration_seconds:.1f}s':<18}")
    print(f"{'P95 Query Latency (ms)':<32} {c_p95_lat:<18.1f} {latency_profiling['p95']:<18.1f} {latency_profiling['p95']:<18.1f}")
    print("=" * 85)

    print("\nCategory Comparison (MRR):")
    print(f"{'Category':<22} {'Cases':<8} {'Control MRR':<15} {'Raw MRR':<15} {'Dedup MRR':<15} {'Delta (Dedup)':<12}")
    print("-" * 87)
    for cat in sorted(category_summary.keys()):
        c_cat_mrr = c_cats.get(cat, {}).get("mean_reciprocal_rank", 0.0)
        raw_mrr = category_summary[cat]["raw_mrr"]
        dedup_mrr = category_summary[cat]["dedup_mrr"]
        delta = dedup_mrr - c_cat_mrr
        print(f"{cat:<22} {category_summary[cat]['total_cases']:<8} {c_cat_mrr:<15.4f} {raw_mrr:<15.4f} {dedup_mrr:<15.4f} {delta:+.4f}")

    # Evaluate criteria against deduped treatment
    primary_pass = mean_rr_dedup >= 0.8200
    exact_term_pass = category_summary.get("exact_terminology", {}).get("dedup_hit_at_1", 0.0) >= 0.7500
    boundary_pass = category_summary.get("boundary_handling", {}).get("dedup_mrr", 0.0) >= 0.6500
    multi_concept_pass = category_summary.get("multi_concept", {}).get("dedup_mrr", 0.0) >= 1.0000
    latency_pass = (latency_profiling["p95"] - c_p95_lat) <= 100.0

    print("\nSuccess and Rejection Criteria Assessment (Treatment vs Control):")
    print(f"  [1] Primary Target (Overall MRR >= 0.8200):        {mean_rr_dedup:.4f} -> {'PASSED' if primary_pass else 'FAILED'}")
    print(f"  [2] Secondary (Exact Term Hit@1 >= 0.7500):        {category_summary.get('exact_terminology', {}).get('dedup_hit_at_1', 0.0):.4f} (Control: {c_cats.get('exact_terminology', {}).get('hit_rate_at_1', 0.0):.4f}) -> {'PASSED' if exact_term_pass else 'FAILED'}")
    print(f"  [3] Secondary (Boundary Handling MRR >= 0.6500):   {category_summary.get('boundary_handling', {}).get('dedup_mrr', 0.0):.4f} (Control: {c_cats.get('boundary_handling', {}).get('mean_reciprocal_rank', 0.0):.4f}) -> {'PASSED' if boundary_pass else 'FAILED'}")
    print(f"  [4] Safety Target (Multi-Concept MRR == 1.0000):    {category_summary.get('multi_concept', {}).get('dedup_mrr', 0.0):.4f} (Control: {c_cats.get('multi_concept', {}).get('mean_reciprocal_rank', 0.0):.4f}) -> {'PASSED' if multi_concept_pass else 'FAILED'}")
    print(f"  [5] Latency Guardrail (Delta P95 <= +100ms):        {latency_profiling['p95'] - c_p95_lat:+.1f} ms -> {'PASSED' if latency_pass else 'FAILED'}")

    return out_path


if __name__ == "__main__":
    run_chunking_experiment()
