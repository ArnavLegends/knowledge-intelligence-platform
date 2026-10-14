"""Executable runner for the KIP v1.1 retrieval and RAG baseline.

This script executes the genuine provider-backed baseline using:
- LLM Provider: Google Gemini (`gemini-2.5-flash`)
- Embedding Provider: Google Gemini (`gemini-embedding-2`, 768 dimensions)
- Vector Store: Qdrant with dedicated collection `kip_eval_v1_1_baseline`
- Evaluation Workspace: `kip-eval-workspace`
- Reference Corpus: `benchmarks/corpus/` (text fixtures only)
- Benchmark Dataset: `benchmarks/kip_v1_1_baseline.json` (7 labelled cases)

Usage:
    python evaluation/run_v1_1_baseline.py
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
logger = logging.getLogger("evaluation.run_v1_1_baseline")


def preflight_check(
    corpus_dir: pathlib.Path,
    dataset_path: pathlib.Path,
    api_key: str | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Validate prerequisites before spending API quota.

    Returns:
        tuple of (corpus_doc_ids_dict, dataset_json_dict).

    Raises:
        ValueError: If preflight invariants fail.
    """
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

    # 1. Identify ONLY text corpus fixtures (filter out README.md or scripts)
    txt_files = sorted(corpus_dir.glob("*.txt"))
    if not txt_files:
        raise ValueError(
            f"Preflight failed: No .txt corpus fixtures found in {corpus_dir}"
        )

    corpus_ids: dict[str, str] = {}
    for txt_file in txt_files:
        raw_bytes = txt_file.read_bytes()
        # Verify strict LF line endings for deterministic document IDs
        if b"\r" in raw_bytes:
            raise ValueError(
                f"Preflight failed: Corpus fixture {txt_file.name} "
                "contains CR bytes (CRLF). Corpus files must use LF line endings."
            )
        doc_id = hashlib.sha256(raw_bytes).hexdigest()
        corpus_ids[txt_file.name] = doc_id

    # 2. Validate dataset cases against corpus IDs
    dataset_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset_data.get("cases", [])
    if not cases:
        raise ValueError("Preflight failed: Benchmark dataset contains no cases.")

    valid_corpus_hashes = set(corpus_ids.values())
    for case in cases:
        case_id = case.get("id")
        expected_ids = case.get("expected_document_ids", [])
        if not expected_ids:
            raise ValueError(
                f"Preflight failed: Case {case_id} has empty expected_document_ids."
            )
        for expected_id in expected_ids:
            if expected_id not in valid_corpus_hashes:
                raise ValueError(
                    f"Preflight failed: Case {case_id} expects document ID "
                    f"{expected_id} which does not match any indexed corpus fixture."
                )

    return corpus_ids, dataset_data


def run_baseline() -> pathlib.Path:
    """Execute the live baseline and persist the result."""
    corpus_dir = repo_root / "benchmarks" / "corpus"
    dataset_path = repo_root / "benchmarks" / "kip_v1_1_baseline.json"
    api_key = os.environ.get("LLM_API_KEY", "")

    # Preflight validation
    logger.info("Executing preflight checks...")
    corpus_ids, _ = preflight_check(corpus_dir, dataset_path, api_key)
    logger.info("Preflight passed. Verified %d corpus fixtures.", len(corpus_ids))
    for fname, doc_id in corpus_ids.items():
        logger.info("  %s -> %s", fname, doc_id)

    # Set environment variables for consistent provider configuration
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["LLM_MODEL"] = "gemini-2.5-flash"
    os.environ["EMBEDDING_PROVIDER"] = "gemini"
    os.environ["EMBEDDING_MODEL"] = "gemini-embedding-2"
    os.environ["EMBEDDING_DIMENSIONS"] = "768"
    os.environ["VECTOR_STORE_PROVIDER"] = "qdrant"
    os.environ["QDRANT_COLLECTION"] = "kip_eval_v1_1_baseline"

    from app.core.config import Settings
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
    from app.services.vector_store.service import VectorStoreService
    from evaluation.models import BenchmarkDataset, BenchmarkRunConfig
    from evaluation.runner import EvaluationRunner

    eval_workspace = "kip-eval-workspace"
    dedicated_collection = "kip_eval_v1_1_baseline"

    settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_api_key=api_key,
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=768,
        vector_store_provider="qdrant",
        qdrant_collection=dedicated_collection,
        qdrant_url=os.environ.get("QDRANT_URL") or None,
        qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
        chunk_size=1000,
        chunk_overlap=200,
        retrieval_default_top_k=5,
    )

    logger.info(
        "Initializing services: LLM=%s/%s, Embedding=%s/%s, "
        "VectorStore=%s (collection=%s)",
        settings.llm_provider,
        settings.llm_model,
        settings.embedding_provider,
        settings.embedding_model,
        settings.vector_store_provider,
        settings.qdrant_collection,
    )

    emb_manager = EmbeddingManager(settings=settings)
    emb_service = EmbeddingService(manager=emb_manager)

    vs_manager = VectorStoreManager(settings=settings)
    vs_service = VectorStoreService(manager=vs_manager)

    chunking_service = ChunkingService(
        FixedSizeChunker(
            chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
        )
    )
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
    )
    llm_manager = LLMManager(settings=settings)
    llm_service = LLMService(manager=llm_manager)
    rag_service = RAGService(
        retrieval_service=ret_service,
        llm_service=llm_service,
        settings=settings,
    )

    # 1. Index reference corpus fixtures into isolated evaluation workspace
    logger.info(
        "Indexing corpus fixtures into workspace '%s' (collection '%s')...",
        eval_workspace,
        dedicated_collection,
    )
    for txt_file in sorted(corpus_dir.glob("*.txt")):
        raw = txt_file.read_bytes()
        doc_id = hashlib.sha256(raw).hexdigest()
        doc = Document.create(
            document_id=doc_id,
            filename=txt_file.name,
            media_type="text/plain",
            text=raw.decode("utf-8"),
        )
        res = indexing_service.index_document(doc, workspace_id=eval_workspace)
        logger.info("  Indexed %s -> %d chunks", txt_file.name, res.chunks_indexed)

    # 2. Load dataset
    raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    dataset = BenchmarkDataset(**raw_dataset)

    # 3. Configure evaluation run
    config = BenchmarkRunConfig(
        benchmark_version="v1.1-baseline",
        evaluation_workspace_id=eval_workspace,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
        live_llm_available=True,
        inter_case_delay_seconds=13.0,
    )

    runner = EvaluationRunner(
        rag_service=rag_service,
        retrieval_service=ret_service,
        config=config,
    )

    # 4. Execute evaluation
    logger.info("Running evaluation across %d cases...", len(dataset.cases))
    result = runner.evaluate_dataset(dataset)

    # 5. Persist output
    timestamp_slug = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    timestamped_file = (
        repo_root / "benchmarks" / f"kip_v1_1_baseline_result_{timestamp_slug}.json"
    )
    canonical_file = repo_root / "benchmarks" / "kip_v1_1_baseline_result.json"

    result_json = result.model_dump_json(indent=2)
    timestamped_file.write_text(result_json, encoding="utf-8")
    canonical_file.write_text(result_json, encoding="utf-8")

    logger.info("Baseline completed successfully.")
    logger.info("Timestamped result saved to: %s", timestamped_file)
    logger.info("Canonical result saved to: %s", canonical_file)

    # Display summary
    print("\n" + "=" * 70)
    print("KIP v1.1 RETRIEVAL & RAG BASELINE RESULTS")
    print("=" * 70)
    print(f"Run ID:                    {result.run_id}")
    print(f"Timestamp:                 {result.timestamp}")
    print(f"Workspace:                 {result.config.evaluation_workspace_id}")
    print(
        f"LLM:                       "
        f"{result.config.llm_provider} / {result.config.llm_model}"
    )
    print(
        f"Embedding:                 "
        f"{result.config.embedding_provider} / {result.config.embedding_model}"
    )
    print(f"Total Cases:               {result.total_cases}")
    print(f"Labelled Cases:            {result.labelled_cases}")
    print(
        f"Hit Rate (Top-5):          {result.hit_rate:.4f}"
        if result.hit_rate is not None
        else "Hit Rate: N/A"
    )
    print(
        f"Mean Reciprocal Rank (MRR):{result.mean_reciprocal_rank:.4f}"
        if result.mean_reciprocal_rank is not None
        else "MRR: N/A"
    )
    print(f"Mean Keyword Coverage:     {result.keyword_coverage:.4f}")
    print(f"Mean Retrieval Latency:    {result.mean_retrieval_latency_ms:.2f} ms")
    print(f"Mean Total Latency:        {result.mean_total_latency_ms:.2f} ms")
    print("-" * 70)
    print("Per-Case Breakdown:")
    for cr in result.case_results:
        ret = cr.retrieval
        ans = cr.answer_metrics
        status = "HIT" if ret.hit else "MISS"
        err_str = f" [ERROR: {ret.retrieval_error}]" if ret.retrieval_error else ""
        print(
            f"  [{cr.case_id}] {status} | RR: {ret.reciprocal_rank:.3f} | "
            f"KW Cov: {ans.keyword_coverage:.2f} | "
            f"Lat: {cr.total_latency_ms:.1f}ms{err_str}"
        )
        print(f"    Expected Docs: {ret.expected_doc_ids}")
        print(f"    Retrieved Docs:{ret.retrieved_doc_ids}")
    print("=" * 70 + "\n")

    return timestamped_file


if __name__ == "__main__":
    try:
        run_baseline()
    except Exception as exc:
        logger.exception("Baseline execution failed: %s", exc)
        sys.exit(1)
