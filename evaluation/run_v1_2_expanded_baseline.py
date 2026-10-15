"""Executable runner for the KIP v1.2 expanded retrieval baseline.

Evaluates the 80-case, 50-document expanded benchmark against the production
Gemini + Qdrant retrieval path using an isolated Qdrant collection.

Configuration:
- Embedding Provider: Google Gemini (gemini-embedding-2, 768 dimensions)
- Vector Store:       Qdrant, dedicated collection kip_eval_v1_2_expanded
- Evaluation Workspace: kip-eval-workspace-v1-2-expanded
- Reference Corpus:   benchmarks/corpus_v1_2_expanded/ (50 .txt files, LF only)
- Benchmark Dataset:  benchmarks/kip_v1_2_expanded_benchmark.json (80 cases)
- Chunk Size / Overlap: 1000 / 200 characters (matches corpus ID generation)

Generation is intentionally omitted (rag_service=None) to:
- Isolate retrieval quality from generation quality
- Conserve LLM API quota
- Match the evaluation model of the v1.2 formatting experiment

Usage:
    python evaluation/run_v1_2_expanded_baseline.py

Environment variables (or .env):
    LLM_API_KEY        Required — used for Gemini embedding
    QDRANT_URL         Optional — Qdrant Cloud or local URL (default: local)
    QDRANT_API_KEY     Optional — Qdrant Cloud API key
"""

import hashlib
import json
import logging
import os
import pathlib
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
logger = logging.getLogger("evaluation.run_v1_2_expanded_baseline")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORPUS_DIR = repo_root / "benchmarks" / "corpus_v1_2_expanded"
DATASET_PATH = repo_root / "benchmarks" / "kip_v1_2_expanded_benchmark.json"
COLLECTION_NAME = "kip_eval_v1_2_expanded"
EVAL_WORKSPACE = "kip-eval-workspace-v1-2-expanded"
BENCHMARK_VERSION = "v1.2-expanded-baseline"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
RETRIEVAL_TOP_K = 5
# Gemini embedding rate-limit spacing between cases
INTER_CASE_DELAY_SECONDS = 0.5


# ---------------------------------------------------------------------------
# Preflight validation
# ---------------------------------------------------------------------------


def preflight_check(
    corpus_dir: pathlib.Path,
    dataset_path: pathlib.Path,
    api_key: str | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Validate all prerequisites before spending API quota.

    Returns:
        (corpus_ids_by_filename, dataset_json_dict)

    Raises:
        ValueError: If any preflight invariant fails. The message names the
                    exact failed check so the operator can fix it without
                    re-reading the script.
    """
    if not api_key or not api_key.strip():
        raise ValueError(
            "Preflight failed: LLM_API_KEY is not configured in environment or .env. "
            "Set it before running the expanded baseline."
        )

    if not corpus_dir.exists() or not corpus_dir.is_dir():
        raise ValueError(
            f"Preflight failed: Corpus directory not found at {corpus_dir}"
        )

    if not dataset_path.exists():
        raise ValueError(
            f"Preflight failed: Benchmark dataset not found at {dataset_path}"
        )

    # --- Corpus: enumerate, LF-check, SHA-256 ---
    txt_files = sorted(corpus_dir.glob("*.txt"))
    if not txt_files:
        raise ValueError(
            f"Preflight failed: No .txt corpus fixtures found in {corpus_dir}"
        )

    corpus_ids: dict[str, str] = {}
    for txt_file in txt_files:
        raw_bytes = txt_file.read_bytes()
        if b"\r" in raw_bytes:
            raise ValueError(
                f"Preflight failed: Corpus fixture {txt_file.name} contains "
                "CR bytes (CRLF line endings). Corpus files must use LF only. "
                "This would produce wrong SHA-256 document IDs."
            )
        doc_id = hashlib.sha256(raw_bytes).hexdigest()
        corpus_ids[txt_file.name] = doc_id

    expected_corpus_size = 50
    if len(corpus_ids) != expected_corpus_size:
        raise ValueError(
            f"Preflight failed: Expected {expected_corpus_size} corpus files, "
            f"found {len(corpus_ids)}. The expanded corpus must be intact."
        )

    # --- Dataset: parse, non-empty, all cases labelled, IDs in corpus ---
    dataset_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset_data.get("cases", [])

    if not cases:
        raise ValueError("Preflight failed: Benchmark dataset contains no cases.")

    expected_case_count = 80
    if len(cases) != expected_case_count:
        raise ValueError(
            f"Preflight failed: Expected {expected_case_count} benchmark cases, "
            f"found {len(cases)}. Run benchmarks/generate_80_cases.py to regenerate."
        )

    # Unique case IDs
    case_ids = [c.get("id") for c in cases]
    if len(case_ids) != len(set(case_ids)):
        dupes = [cid for cid in case_ids if case_ids.count(cid) > 1]
        raise ValueError(
            f"Preflight failed: Duplicate case IDs found: {sorted(set(dupes))}"
        )

    valid_corpus_hashes = set(corpus_ids.values())
    missing_labels: list[str] = []
    unknown_ids: list[tuple[str, str]] = []

    for case in cases:
        case_id = case.get("id")
        expected_ids = case.get("expected_document_ids", [])

        if not expected_ids:
            missing_labels.append(case_id)
            continue

        for expected_id in expected_ids:
            if expected_id not in valid_corpus_hashes:
                unknown_ids.append((case_id, expected_id))

    if missing_labels:
        raise ValueError(
            f"Preflight failed: {len(missing_labels)} cases have empty "
            f"expected_document_ids: "
            f"{missing_labels[:5]}{'...' if len(missing_labels) > 5 else ''}. "
            "All expanded benchmark cases must be labelled."
        )

    if unknown_ids:
        lines = "\n  ".join(f"{cid}: {did[:16]}..." for cid, did in unknown_ids[:5])
        raise ValueError(
            f"Preflight failed: {len(unknown_ids)} expected document IDs not found "
            f"in corpus_v1_2_expanded:\n  {lines}\n"
            "Re-run benchmarks/generate_80_cases.py if corpus files changed."
        )

    return corpus_ids, dataset_data


# ---------------------------------------------------------------------------
# Category-level metric aggregation
# ---------------------------------------------------------------------------


def _aggregate_by_category(case_results, dataset_cases) -> dict[str, Any]:
    """Compute Hit@1/3/5 and MRR broken down by benchmark category.

    Only counts labelled cases (expected_count > 0) in each category.
    Categories with no labelled cases are omitted from the output.
    """
    # Build case_id -> category map
    id_to_category: dict[str, str] = {}
    for case in dataset_cases:
        cat = (case.metadata or {}).get("category", "unknown")
        id_to_category[case.id] = cat

    # Accumulate per-category
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
        summary[cat] = {
            "total_cases": len(results),
            "labelled_cases": n,
            "hit_rate_at_1": sum(1 for r in labelled if r.retrieval.hit_at_1) / n,
            "hit_rate_at_3": sum(1 for r in labelled if r.retrieval.hit_at_3) / n,
            "hit_rate_at_5": sum(1 for r in labelled if r.retrieval.hit) / n,
            "mean_reciprocal_rank": (
                sum(r.retrieval.reciprocal_rank for r in labelled) / n
            ),
            "mean_retrieval_latency_ms": (
                sum(r.retrieval.retrieval_latency_ms for r in labelled) / n
            ),
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


def run_expanded_baseline() -> pathlib.Path:
    """Execute the live expanded baseline and persist the result.

    Returns:
        Path to the timestamped result file.

    Raises:
        ValueError: On preflight failure (no API calls made).
        Exception:  On runtime failure (partial results logged).
    """
    api_key = os.environ.get("LLM_API_KEY", "")

    logger.info("=" * 70)
    logger.info("KIP v1.2 EXPANDED RETRIEVAL BASELINE")
    logger.info("Corpus: %s", CORPUS_DIR)
    logger.info("Benchmark: %s", DATASET_PATH)
    logger.info("Collection: %s", COLLECTION_NAME)
    logger.info("Workspace: %s", EVAL_WORKSPACE)
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
    for fname, doc_id in sorted(corpus_ids.items()):
        logger.info("  %s -> %s", fname, doc_id)

    # -----------------------------------------------------------------------
    # Phase 1: Service initialisation
    # -----------------------------------------------------------------------
    logger.info("Phase 1: Initialising services...")

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
        retrieval_default_top_k=RETRIEVAL_TOP_K,
        # Raise workspace limits to accommodate 50-document evaluation corpus
        max_documents_per_workspace=100,
        max_chunks_per_workspace=2000,
    )

    logger.info(
        "Services: Embedding=%s/%s VectorStore=%s (collection=%s)",
        settings.embedding_provider,
        settings.embedding_model,
        settings.vector_store_provider,
        settings.qdrant_collection,
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
    # Phase 2: Index 50-document corpus into isolated evaluation workspace
    # -----------------------------------------------------------------------
    logger.info(
        "Phase 2: Indexing %d corpus documents into workspace '%s' "
        "(collection '%s')...",
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
            logger.info(
                "  Indexed %-55s -> %d chunk(s)", txt_file.name, res.chunks_indexed
            )
            total_indexed += 1
        else:
            logger.info("  Skipped (already indexed): %s", txt_file.name)
            total_skipped += 1

    logger.info(
        "Indexing complete: %d newly indexed, %d already present.",
        total_indexed,
        total_skipped,
    )

    # -----------------------------------------------------------------------
    # Phase 3: Configure and execute evaluation
    # -----------------------------------------------------------------------
    logger.info("Phase 3: Running 80-case benchmark evaluation...")

    dataset = BenchmarkDataset(**raw_dataset)

    config = BenchmarkRunConfig(
        benchmark_version=BENCHMARK_VERSION,
        evaluation_workspace_id=EVAL_WORKSPACE,
        llm_provider="none",
        llm_model="none",
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        retrieval_top_k=RETRIEVAL_TOP_K,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        live_llm_available=False,
        inter_case_delay_seconds=INTER_CASE_DELAY_SECONDS,
    )

    runner = EvaluationRunner(
        rag_service=None,
        retrieval_service=ret_service,
        config=config,
    )

    result = runner.evaluate_dataset(dataset)

    # -----------------------------------------------------------------------
    # Phase 4: Category-level aggregation
    # -----------------------------------------------------------------------
    logger.info("Phase 4: Computing category-level metrics...")
    category_metrics = _aggregate_by_category(result.case_results, dataset.cases)

    # -----------------------------------------------------------------------
    # Phase 5: Build enriched output document
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
            "benchmark_version": BENCHMARK_VERSION,
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
            "embedding": {
                "provider": settings.embedding_provider,
                "model": settings.embedding_model,
                "dimensions": settings.embedding_dimensions,
                "doc_formatter": "none (raw text)",
                "query_formatter": "none (raw text)",
            },
            "retrieval": {
                "top_k": RETRIEVAL_TOP_K,
                "vector_store": settings.vector_store_provider,
                "collection": COLLECTION_NAME,
                "workspace": EVAL_WORKSPACE,
            },
            "generation": "omitted (retrieval-only evaluation)",
            "indexing_summary": {
                "newly_indexed": total_indexed,
                "already_present": total_skipped,
            },
        },
        "category_metrics": category_metrics,
    }

    # -----------------------------------------------------------------------
    # Phase 6: Persist results
    # -----------------------------------------------------------------------
    timestamped_file = (
        repo_root / "benchmarks" / f"kip_v1_2_expanded_baseline_{timestamp_slug}.json"
    )
    timestamped_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Result saved to: %s", timestamped_file)

    # -----------------------------------------------------------------------
    # Phase 7: Display summary
    # -----------------------------------------------------------------------
    n_labelled = result.labelled_cases
    n_errors = sum(1 for cr in result.case_results if cr.retrieval.retrieval_error)

    print("\n" + "=" * 75)
    print("KIP v1.2 EXPANDED RETRIEVAL BASELINE RESULTS")
    print("=" * 75)
    print(f"Run ID:                {result.run_id}")
    print(f"Timestamp:             {result.timestamp}")
    print(f"Corpus:                {len(corpus_ids)} documents (corpus_v1_2_expanded)")
    print("Benchmark:             80 cases (6 categories)")
    print(f"Collection:            {COLLECTION_NAME}")
    print(f"Workspace:             {EVAL_WORKSPACE}")
    emb_label = f"{settings.embedding_provider}/{settings.embedding_model}"
    print(f"Embedding:             {emb_label}")
    print(f"Chunk size / overlap:  {CHUNK_SIZE} / {CHUNK_OVERLAP} chars")
    print(f"Top-K:                 {RETRIEVAL_TOP_K}")
    print("-" * 75)
    print(f"Total Cases:           {result.total_cases}")
    print(f"Labelled Cases:        {n_labelled}  (denominator for retrieval metrics)")
    err_note = "(infrastructure failures, not counted as misses)"
    print(f"Retrieval Errors:      {n_errors}  {err_note}")
    print("-" * 75)

    def _fmt(val: float | None, fmt: str = ".4f") -> str:
        return f"{val:{fmt}}" if val is not None else "N/A"

    print(
        f"Hit Rate @ 1:          {_fmt(result.hit_rate_at_1)}"
        f"  ({int((result.hit_rate_at_1 or 0) * n_labelled)}/{n_labelled})"
    )
    print(
        f"Hit Rate @ 3:          {_fmt(result.hit_rate_at_3)}"
        f"  ({int((result.hit_rate_at_3 or 0) * n_labelled)}/{n_labelled})"
    )
    print(
        f"Hit Rate @ 5:          {_fmt(result.hit_rate_at_5)}"
        f"  ({int((result.hit_rate_at_5 or 0) * n_labelled)}/{n_labelled})"
    )
    print(f"Mean Reciprocal Rank:  {_fmt(result.mean_reciprocal_rank)}")
    print(f"Mean Retrieval Latency:{result.mean_retrieval_latency_ms:.2f} ms")
    print("-" * 75)
    print("Category Breakdown:")
    print(
        f"  {'Category':<25} {'Cases':>5}  "
        f"{'H@1':>6}  {'H@3':>6}  {'H@5':>6}  {'MRR':>6}"
    )
    print("  " + "-" * 58)
    for cat, cm in sorted(category_metrics.items()):
        n_c = cm["labelled_cases"]
        print(
            f"  {cat:<25} {n_c:>5}  "
            f"{cm['hit_rate_at_1']:>6.4f}  "
            f"{cm['hit_rate_at_3']:>6.4f}  "
            f"{cm['hit_rate_at_5']:>6.4f}  "
            f"{cm['mean_reciprocal_rank']:>6.4f}"
        )
    if category_metrics:
        cat_errors = {
            cat: len(cm["errors"])
            for cat, cm in category_metrics.items()
            if cm["errors"]
        }
        if cat_errors:
            print(f"  Errors by category: {cat_errors}")
    print("-" * 75)
    print("Per-Case Breakdown:")
    for cr in result.case_results:
        ret = cr.retrieval
        cat = ""
        for case in dataset.cases:
            if case.id == cr.case_id:
                cat = (case.metadata or {}).get("category", "")[:12]
                break
        status = "HIT" if ret.hit else "MISS"
        h1 = "Y" if ret.hit_at_1 else "N"
        h3 = "Y" if ret.hit_at_3 else "N"
        err_str = f" [ERR: {ret.retrieval_error[:40]}]" if ret.retrieval_error else ""
        print(
            f"  [{cr.case_id}] {status:<4}  H@1:{h1} H@3:{h3}"
            f"  RR:{ret.reciprocal_rank:.3f}  Lat:{ret.retrieval_latency_ms:.0f}ms"
            f"  ({cat}){err_str}"
        )
    print("=" * 75)
    print(f"Result saved to: {timestamped_file.name}")
    print("=" * 75 + "\n")

    return timestamped_file


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_expanded_baseline()
    except ValueError as exc:
        # Preflight failures: report cleanly without traceback
        logger.error("Preflight failure: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Baseline execution failed: %s", exc)
        sys.exit(1)
