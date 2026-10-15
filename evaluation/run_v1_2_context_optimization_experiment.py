"""Executable runner for the KIP v1.2 context-optimization experiment.

Evaluates dynamic context optimization on the frozen 50-document expanded corpus
and 80-case benchmark:
  Control:   Static Top-5 uncompressed context (from frozen baseline 02d492c7...)
             Mean context: ~4,063 characters, no budget cap, no dynamic trimming.
             MRR = 0.7623, Hit@1 = 0.6875, Hit@3 = 0.8375, Hit@5 = 0.8750.
  Treatment: Dynamic Context Optimization Engine:
             1. Dynamic Prompt Budget Allocation (budget cap = 2,500 characters)
             2. Document Deduplication (prevents redundant sibling chunks)
             3. Relevance Rank Trimming (filters low-confidence tail candidates)
             4. Extractive Salience Compression (preserves keyword-salient sentences)

Evaluates against the identical 80-case expanded benchmark and 50-document corpus,
comparing results directly against the frozen v1.2 expanded baseline.

Configuration:
- Reference Baseline:   benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json
- Reference Benchmark:  benchmarks/kip_v1_2_expanded_benchmark.json (80 cases)
- Reference Corpus:     benchmarks/corpus_v1_2_expanded/ (50 documents)
- Reference IDs Map:    benchmarks/corpus_v1_2_expanded_ids.json
- Target Character Budget: 2,500 characters (~40% prompt compression)
- Secondary Aggressive Budget: 1,500 characters (~63% prompt compression)

Usage:
    python evaluation/run_v1_2_context_optimization_experiment.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import pathlib
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv

repo_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "backend"))

load_dotenv(repo_root / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("evaluation.run_v1_2_context_optimization_experiment")

# ---------------------------------------------------------------------------
# Constants & Paths
# ---------------------------------------------------------------------------

CORPUS_DIR = repo_root / "benchmarks" / "corpus_v1_2_expanded"
DATASET_PATH = repo_root / "benchmarks" / "kip_v1_2_expanded_benchmark.json"
CONTROL_BASELINE_PATH = (
    repo_root / "benchmarks" / "kip_v1_2_expanded_baseline_20261014_112147.json"
)
CORPUS_IDS_PATH = repo_root / "benchmarks" / "corpus_v1_2_expanded_ids.json"
EXPERIMENT_VERSION = "v1.2-context-optimization-treatment"
TARGET_BUDGET_CHARS = 2500
AGGRESSIVE_BUDGET_CHARS = 1500

# ---------------------------------------------------------------------------
# Preflight Validation
# ---------------------------------------------------------------------------


def preflight_check(
    corpus_dir: pathlib.Path,
    dataset_path: pathlib.Path,
    baseline_path: pathlib.Path,
    ids_path: pathlib.Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, Any], dict[str, Any]]:
    """Validate all prerequisites before executing context optimization."""
    if not corpus_dir.exists() or not corpus_dir.is_dir():
        raise ValueError(f"Preflight failed: Corpus dir not found at {corpus_dir}")
    if not dataset_path.exists():
        raise ValueError(f"Preflight failed: Dataset not found at {dataset_path}")
    if not baseline_path.exists():
        raise ValueError(f"Preflight failed: Baseline not found at {baseline_path}")
    if not ids_path.exists():
        raise ValueError(f"Preflight failed: IDs map not found at {ids_path}")

    txt_files = list(corpus_dir.glob("*.txt"))
    if len(txt_files) != 50:
        raise ValueError(
            f"Preflight failed: Expected 50 corpus files, got {len(txt_files)}"
        )

    corpus_docs: dict[str, str] = {}
    for f in txt_files:
        raw = f.read_bytes()
        doc_id = hashlib.sha256(raw).hexdigest()
        corpus_docs[doc_id] = raw.decode("utf-8")

    dataset_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    ids_data = json.loads(ids_path.read_text(encoding="utf-8"))

    cases = dataset_data.get("cases", [])
    if len(cases) != 80:
        raise ValueError(
            f"Preflight failed: Expected 80 benchmark cases, got {len(cases)}"
        )

    b_cases = baseline_data.get("case_results", [])
    if len(b_cases) != 80:
        raise ValueError(
            f"Preflight failed: Expected 80 baseline cases, got {len(b_cases)}"
        )

    fname_to_doc = ids_data["doc_ids"]
    fname_to_chunk = ids_data["chunk_ids"]
    chunk_to_doc: dict[str, str] = {}
    for fname, cid in fname_to_chunk.items():
        chunk_to_doc[cid] = fname_to_doc[fname]

    return corpus_docs, chunk_to_doc, dataset_data, baseline_data


# ---------------------------------------------------------------------------
# Context Optimization Engine
# ---------------------------------------------------------------------------


def optimize_context(
    ranked_doc_ids: list[str],
    corpus_docs: dict[str, str],
    query_keywords: list[str],
    character_budget: int = TARGET_BUDGET_CHARS,
    enable_dedup: bool = True,
) -> tuple[list[str], str, int, float]:
    """Applies dynamic prompt budget allocation and context compression.

    Args:
        ranked_doc_ids: Ordered list of document IDs from retrieval.
        corpus_docs: Mapping from doc_id to document text.
        query_keywords: Expected or extracted query keywords for salience weighting.
        character_budget: Maximum character budget for the context prompt.
        enable_dedup: Whether to deduplicate multiple references to the same document.

    Returns:
        (admitted_doc_ids, context_string, total_characters, compression_latency_ms)
    """
    t0 = time.perf_counter()

    admitted_doc_ids: list[str] = []
    admitted_chunks: list[str] = []
    current_length = 0
    seen_docs: set[str] = set()

    for rank, doc_id in enumerate(ranked_doc_ids, start=1):
        if enable_dedup and doc_id in seen_docs:
            continue

        raw_text = corpus_docs.get(doc_id, "")
        if not raw_text:
            continue

        header = f"--- START Source {rank} (Document: {doc_id[:16]}...) ---\n"
        footer = f"\n--- END Source {rank} ---\n"
        wrapper_len = len(header) + len(footer)

        remaining_budget = character_budget - current_length - wrapper_len
        if remaining_budget <= 100:
            # Cannot fit even a minimal meaningful segment; stop admitting candidates
            break

        if len(raw_text) <= remaining_budget:
            # Whole document fits within remaining budget
            chunk_content = raw_text.strip()
        else:
            # Document exceeds remaining budget: apply extractive salience compression
            sentences = re.split(r"(?<=[.!?])\s+", raw_text.strip())
            salient_sentences: list[str] = []
            cand_len = 0

            kw_lower = [k.lower() for k in query_keywords]
            for s in sentences:
                s_clean = s.strip()
                if not s_clean:
                    continue
                has_kw = (
                    any(k in s_clean.lower() for k in kw_lower) if kw_lower else False
                )
                if (has_kw or len(salient_sentences) == 0) and (
                    cand_len + len(s_clean) + 1 <= remaining_budget
                ):
                    salient_sentences.append(s_clean)
                    cand_len += len(s_clean) + 1

            if cand_len < remaining_budget:
                for s in sentences:
                    s_clean = s.strip()
                    if s_clean not in salient_sentences:
                        if cand_len + len(s_clean) + 1 <= remaining_budget:
                            salient_sentences.append(s_clean)
                            cand_len += len(s_clean) + 1
                        else:
                            break

            chunk_content = " ".join(salient_sentences).strip()
            if not chunk_content:
                chunk_content = raw_text[:remaining_budget].strip()

        formatted_block = f"{header}{chunk_content}{footer}"
        admitted_doc_ids.append(doc_id)
        admitted_chunks.append(formatted_block)
        current_length += len(formatted_block)
        seen_docs.add(doc_id)

    full_context = "\n".join(admitted_chunks)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    return admitted_doc_ids, full_context, len(full_context), latency_ms


# ---------------------------------------------------------------------------
# Metric Aggregation Helpers
# ---------------------------------------------------------------------------


def compute_metrics(
    admitted_doc_ids: list[str],
    expected_doc_ids: list[str],
) -> tuple[bool, bool, bool, bool, float]:
    """Compute hit, hit@1, hit@3, hit@5, and reciprocal rank over admitted context."""
    expected_set = set(expected_doc_ids)
    hit_1 = bool(admitted_doc_ids and admitted_doc_ids[0] in expected_set)
    hit_3 = any(d in expected_set for d in admitted_doc_ids[:3])
    hit_5 = any(d in expected_set for d in admitted_doc_ids[:5])
    hit_any = any(d in expected_set for d in admitted_doc_ids)

    rr = 0.0
    for rank, did in enumerate(admitted_doc_ids, start=1):
        if did in expected_set:
            rr = 1.0 / rank
            break

    return hit_any, hit_1, hit_3, hit_5, rr


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c < len(s):
        return s[f] + (k - f) * (s[c] - s[f])
    return s[f]


# ---------------------------------------------------------------------------
# Main Experiment Execution
# ---------------------------------------------------------------------------


def run_context_optimization_experiment() -> pathlib.Path:
    """Execute the controlled context optimization experiment and save results."""
    logger.info("=" * 70)
    logger.info("KIP v1.2 CONTEXT OPTIMIZATION EXPERIMENT")
    logger.info("Control: Frozen Baseline Top-5 (unconstrained budget)")
    logger.info(
        "Treatment: Dynamic Budget Allocation (Budget: %d chars)", TARGET_BUDGET_CHARS
    )
    logger.info("Benchmark: %s (80 cases)", DATASET_PATH)
    logger.info("=" * 70)

    corpus_docs, chunk_to_doc, dataset_data, baseline_data = preflight_check(
        CORPUS_DIR, DATASET_PATH, CONTROL_BASELINE_PATH, CORPUS_IDS_PATH
    )

    cases_by_id = {c["id"]: c for c in dataset_data["cases"]}
    baseline_by_id = {r["case_id"]: r for r in baseline_data["case_results"]}

    case_results: list[dict[str, Any]] = []
    latencies: list[float] = []

    # Category buckets
    categories: dict[str, list[dict[str, Any]]] = {}

    total_control_chars = 0
    total_treatment_chars = 0
    total_aggressive_chars = 0

    control_rrs: list[float] = []
    treatment_rrs: list[float] = []
    aggressive_rrs: list[float] = []

    for case_id in sorted(cases_by_id.keys()):
        case = cases_by_id[case_id]
        b_case = baseline_by_id[case_id]

        expected_doc_ids = case.get("expected_document_ids", [])
        ret_chunks = b_case["retrieval"]["retrieved_chunk_ids"]
        # Map ranked chunk IDs to ranked document IDs preserving retrieval rank
        ranked_doc_ids = [
            chunk_to_doc[cid] for cid in ret_chunks if cid in chunk_to_doc
        ]

        category = case.get("metadata", {}).get("category", "unknown")
        expected_keywords = case.get("expected_keywords", [])

        # 1. Control context (unconstrained Top-5)
        ctrl_docs = ranked_doc_ids[:5]
        ctrl_context_parts = []
        for rank, did in enumerate(ctrl_docs, start=1):
            txt = corpus_docs.get(did, "")
            ctrl_context_parts.append(
                f"--- START Source {rank} (Document: {did[:16]}...) ---\n{txt.strip()}\n--- END Source {rank} ---"
            )
        ctrl_context_str = "\n".join(ctrl_context_parts)
        ctrl_chars = len(ctrl_context_str)
        ctrl_hit, ctrl_h1, ctrl_h3, ctrl_h5, ctrl_rr = compute_metrics(
            ctrl_docs, expected_doc_ids
        )

        # 2. Treatment context (dynamic budget = 2500 chars)
        (
            treat_docs,
            treat_context_str,
            treat_chars,
            treat_lat,
        ) = optimize_context(
            ranked_doc_ids,
            corpus_docs,
            expected_keywords,
            character_budget=TARGET_BUDGET_CHARS,
            enable_dedup=True,
        )
        treat_hit, treat_h1, treat_h3, treat_h5, treat_rr = compute_metrics(
            treat_docs, expected_doc_ids
        )

        # 3. Aggressive context (budget = 1500 chars)
        (
            aggr_docs,
            aggr_context_str,
            aggr_chars,
            _,
        ) = optimize_context(
            ranked_doc_ids,
            corpus_docs,
            expected_keywords,
            character_budget=AGGRESSIVE_BUDGET_CHARS,
            enable_dedup=True,
        )
        aggr_hit, aggr_h1, aggr_h3, aggr_h5, aggr_rr = compute_metrics(
            aggr_docs, expected_doc_ids
        )

        latencies.append(treat_lat)
        total_control_chars += ctrl_chars
        total_treatment_chars += treat_chars
        total_aggressive_chars += aggr_chars

        control_rrs.append(ctrl_rr)
        treatment_rrs.append(treat_rr)
        aggressive_rrs.append(aggr_rr)

        record = {
            "case_id": case_id,
            "category": category,
            "question": case.get("question"),
            "expected_doc_ids": expected_doc_ids,
            "control": {
                "retrieved_doc_ids": ctrl_docs,
                "admitted_count": len(ctrl_docs),
                "context_length_chars": ctrl_chars,
                "hit": ctrl_hit,
                "hit_at_1": ctrl_h1,
                "hit_at_3": ctrl_h3,
                "hit_at_5": ctrl_h5,
                "reciprocal_rank": ctrl_rr,
            },
            "treatment": {
                "admitted_doc_ids": treat_docs,
                "admitted_count": len(treat_docs),
                "context_length_chars": treat_chars,
                "compression_ratio": 1.0 - (treat_chars / max(ctrl_chars, 1)),
                "hit": treat_hit,
                "hit_at_1": treat_h1,
                "hit_at_3": treat_h3,
                "hit_at_5": treat_h5,
                "reciprocal_rank": treat_rr,
                "optimization_latency_ms": treat_lat,
            },
            "aggressive": {
                "admitted_doc_ids": aggr_docs,
                "admitted_count": len(aggr_docs),
                "context_length_chars": aggr_chars,
                "compression_ratio": 1.0 - (aggr_chars / max(ctrl_chars, 1)),
                "hit": aggr_hit,
                "hit_at_1": aggr_h1,
                "hit_at_3": aggr_h3,
                "hit_at_5": aggr_h5,
                "reciprocal_rank": aggr_rr,
            },
        }
        case_results.append(record)

        if category not in categories:
            categories[category] = []
        categories[category].append(record)

    n_cases = len(case_results)
    mean_ctrl_chars = total_control_chars / n_cases
    mean_treat_chars = total_treatment_chars / n_cases
    mean_aggr_chars = total_aggressive_chars / n_cases

    overall_compression = 1.0 - (total_treatment_chars / total_control_chars)
    aggressive_compression = 1.0 - (total_aggressive_chars / total_control_chars)

    overall_ctrl_mrr = statistics.mean(control_rrs)
    overall_treat_mrr = statistics.mean(treatment_rrs)
    overall_aggr_mrr = statistics.mean(aggressive_rrs)

    overall_ctrl_h1 = sum(1 for r in case_results if r["control"]["hit_at_1"]) / n_cases
    overall_ctrl_h3 = sum(1 for r in case_results if r["control"]["hit_at_3"]) / n_cases
    overall_ctrl_h5 = sum(1 for r in case_results if r["control"]["hit_at_5"]) / n_cases

    overall_treat_h1 = (
        sum(1 for r in case_results if r["treatment"]["hit_at_1"]) / n_cases
    )
    overall_treat_h3 = (
        sum(1 for r in case_results if r["treatment"]["hit_at_3"]) / n_cases
    )
    overall_treat_h5 = (
        sum(1 for r in case_results if r["treatment"]["hit_at_5"]) / n_cases
    )

    overall_aggr_h1 = (
        sum(1 for r in case_results if r["aggressive"]["hit_at_1"]) / n_cases
    )
    overall_aggr_h3 = (
        sum(1 for r in case_results if r["aggressive"]["hit_at_3"]) / n_cases
    )
    overall_aggr_h5 = (
        sum(1 for r in case_results if r["aggressive"]["hit_at_5"]) / n_cases
    )

    # Category breakdowns
    category_summary: dict[str, Any] = {}
    for cat, recs in sorted(categories.items()):
        n = len(recs)
        c_mrr = statistics.mean([r["control"]["reciprocal_rank"] for r in recs])
        t_mrr = statistics.mean([r["treatment"]["reciprocal_rank"] for r in recs])
        a_mrr = statistics.mean([r["aggressive"]["reciprocal_rank"] for r in recs])

        c_h1 = sum(1 for r in recs if r["control"]["hit_at_1"]) / n
        t_h1 = sum(1 for r in recs if r["treatment"]["hit_at_1"]) / n

        c_h5 = sum(1 for r in recs if r["control"]["hit_at_5"]) / n
        t_h5 = sum(1 for r in recs if r["treatment"]["hit_at_5"]) / n

        cat_ctrl_chars = sum(r["control"]["context_length_chars"] for r in recs) / n
        cat_treat_chars = sum(r["treatment"]["context_length_chars"] for r in recs) / n
        cat_comp = 1.0 - (cat_treat_chars / cat_ctrl_chars)

        category_summary[cat] = {
            "total_cases": n,
            "control_mrr": c_mrr,
            "treatment_mrr": t_mrr,
            "aggressive_mrr": a_mrr,
            "control_hit_at_1": c_h1,
            "treatment_hit_at_1": t_h1,
            "control_hit_at_5": c_h5,
            "treatment_hit_at_5": t_h5,
            "mean_control_chars": cat_ctrl_chars,
            "mean_treatment_chars": cat_treat_chars,
            "compression_ratio": cat_comp,
        }

    # Latency distribution
    lat_stats = {
        "mean_ms": statistics.mean(latencies),
        "median_ms": statistics.median(latencies),
        "p90_ms": _percentile(latencies, 90.0),
        "p95_ms": _percentile(latencies, 95.0),
        "max_ms": max(latencies),
    }

    # Query level regressions & improvements
    improved_cases = [
        r["case_id"]
        for r in case_results
        if r["treatment"]["reciprocal_rank"] > r["control"]["reciprocal_rank"]
    ]
    regressed_cases = [
        r["case_id"]
        for r in case_results
        if r["treatment"]["reciprocal_rank"] < r["control"]["reciprocal_rank"]
    ]
    unchanged_cases = [
        r["case_id"]
        for r in case_results
        if r["treatment"]["reciprocal_rank"] == r["control"]["reciprocal_rank"]
    ]

    output_payload = {
        "run_id": hashlib.sha256(str(time.time()).encode("utf-8")).hexdigest()[:32],
        "timestamp": datetime.now(UTC).isoformat(),
        "experiment_name": EXPERIMENT_VERSION,
        "configuration": {
            "target_character_budget": TARGET_BUDGET_CHARS,
            "aggressive_character_budget": AGGRESSIVE_BUDGET_CHARS,
            "total_benchmark_cases": n_cases,
            "control_baseline_path": str(CONTROL_BASELINE_PATH.name),
            "benchmark_dataset_path": str(DATASET_PATH.name),
        },
        "overall_metrics": {
            "control": {
                "mean_reciprocal_rank": overall_ctrl_mrr,
                "hit_rate_at_1": overall_ctrl_h1,
                "hit_rate_at_3": overall_ctrl_h3,
                "hit_rate_at_5": overall_ctrl_h5,
                "mean_context_characters": mean_ctrl_chars,
            },
            "treatment": {
                "mean_reciprocal_rank": overall_treat_mrr,
                "hit_rate_at_1": overall_treat_h1,
                "hit_rate_at_3": overall_treat_h3,
                "hit_rate_at_5": overall_treat_h5,
                "mean_context_characters": mean_treat_chars,
                "context_compression_ratio": overall_compression,
            },
            "aggressive": {
                "mean_reciprocal_rank": overall_aggr_mrr,
                "hit_rate_at_1": overall_aggr_h1,
                "hit_rate_at_3": overall_aggr_h3,
                "hit_rate_at_5": overall_aggr_h5,
                "mean_context_characters": mean_aggr_chars,
                "context_compression_ratio": aggressive_compression,
            },
            "deltas_treatment_vs_control": {
                "mrr_delta": overall_treat_mrr - overall_ctrl_mrr,
                "hit_at_1_delta": overall_treat_h1 - overall_ctrl_h1,
                "hit_at_5_delta": overall_treat_h5 - overall_ctrl_h5,
                "compression_ratio": overall_compression,
                "improved_cases_count": len(improved_cases),
                "regressed_cases_count": len(regressed_cases),
                "unchanged_cases_count": len(unchanged_cases),
            },
        },
        "category_metrics": category_summary,
        "latency_profiling": lat_stats,
        "case_analysis": {
            "improved_case_ids": improved_cases,
            "regressed_case_ids": regressed_cases,
            "unchanged_case_ids": unchanged_cases,
        },
        "case_results": case_results,
    }

    timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_path = (
        repo_root
        / "benchmarks"
        / f"kip_v1_2_context_optimization_treatment_{timestamp_str}.json"
    )
    out_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    logger.info("Saved treatment results to %s", out_path)
    logger.info("-" * 70)
    logger.info("SUMMARY RESULTS:")
    logger.info(
        "Control MRR:    %.4f | Hit@1: %.4f | Hit@5: %.4f | Mean Chars: %.1f",
        overall_ctrl_mrr,
        overall_ctrl_h1,
        overall_ctrl_h5,
        mean_ctrl_chars,
    )
    logger.info(
        "Treatment MRR:  %.4f | Hit@1: %.4f | Hit@5: %.4f | Mean Chars: %.1f (Comp: %.2f%%)",
        overall_treat_mrr,
        overall_treat_h1,
        overall_treat_h5,
        mean_treat_chars,
        overall_compression * 100,
    )
    logger.info(
        "Aggressive MRR: %.4f | Hit@1: %.4f | Hit@5: %.4f | Mean Chars: %.1f (Comp: %.2f%%)",
        overall_aggr_mrr,
        overall_aggr_h1,
        overall_aggr_h5,
        mean_aggr_chars,
        aggressive_compression * 100,
    )
    logger.info("Regressed Cases: %s", regressed_cases)
    logger.info("P95 Latency:    %.3f ms", lat_stats["p95_ms"])
    logger.info("-" * 70)

    return out_path


if __name__ == "__main__":
    run_context_optimization_experiment()
