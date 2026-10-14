"""Executable runner for KIP v1.2 Gemini Embedding 2 input-formatting experiment.

Controlled comparison between:
- Control: Unmodified raw query text and raw document-chunk text.
- Treatment: Asymmetric task-prefixed query ("task: question answering | query: ...")
  and document-chunk formatting ("title: none | text: ...").

Evaluated against the 18-document reference corpus (corpus_v1_2) and the 25-case
benchmark dataset (kip_v1_2_benchmark.json) using isolated Qdrant collections.

Usage:
    python evaluation/run_v1_2_formatting_experiment.py
"""

import hashlib
import json
import logging
import os
import pathlib
import sys
from datetime import UTC, datetime

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
logger = logging.getLogger("evaluation.run_v1_2_formatting_experiment")


def preflight_check(
    corpus_dir: pathlib.Path,
    dataset_path: pathlib.Path,
    api_key: str | None,
) -> tuple[dict[str, str], dict]:
    """Validate prerequisites before spending API quota."""
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
                f"Preflight failed: Corpus fixture {txt_file.name} contains CR bytes."
            )
        doc_id = hashlib.sha256(raw_bytes).hexdigest()
        corpus_ids[txt_file.name] = doc_id

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
                    f"Preflight failed: Case {case_id} expects unknown "
                    f"document ID {expected_id}."
                )

    return corpus_ids, dataset_data


def run_experiment() -> tuple[pathlib.Path, pathlib.Path]:
    """Execute the controlled comparison experiment and persist both result sets."""
    corpus_dir = repo_root / "benchmarks" / "corpus_v1_2"
    dataset_path = repo_root / "benchmarks" / "kip_v1_2_benchmark.json"
    api_key = os.environ.get("LLM_API_KEY", "")

    logger.info("Executing preflight checks...")
    corpus_ids, _ = preflight_check(corpus_dir, dataset_path, api_key)
    logger.info("Preflight passed. Verified %d corpus fixtures.", len(corpus_ids))

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

    eval_workspace = "kip-eval-workspace-v1-2"
    control_collection = "kip_eval_v1_2_control"
    treatment_collection = "kip_eval_v1_2_formatted"

    chunker = ChunkingService(FixedSizeChunker(chunk_size=1000, chunk_overlap=200))
    raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    dataset = BenchmarkDataset(**raw_dataset)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # -----------------------------------------------------------------------
    # Condition 1: Control (Raw Text)
    # -----------------------------------------------------------------------
    logger.info("=========================================================")
    logger.info("PHASE 1: CONTROL CONDITION (Raw text, unformatted)")
    logger.info("=========================================================")

    control_settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_api_key=api_key,
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=768,
        vector_store_provider="qdrant",
        qdrant_collection=control_collection,
        qdrant_url=os.environ.get("QDRANT_URL") or None,
        qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
        chunk_size=1000,
        chunk_overlap=200,
        retrieval_default_top_k=5,
    )

    control_emb_service = EmbeddingService(
        manager=EmbeddingManager(settings=control_settings),
        doc_formatter=None,
    )
    control_vs_service = VectorStoreService(
        manager=VectorStoreManager(settings=control_settings)
    )
    control_indexing_service = DocumentIndexingService(
        chunking_service=chunker,
        embedding_service=control_emb_service,
        vector_store_service=control_vs_service,
        settings=control_settings,
    )

    logger.info(
        "Indexing 18 corpus documents into Control collection '%s'...",
        control_collection,
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
        res = control_indexing_service.index_document(doc, workspace_id=eval_workspace)
        logger.info(
            "  [Control] Indexed %s -> %d chunks", txt_file.name, res.chunks_indexed
        )

    control_ret_service = RetrievalService(
        embedding_service=control_emb_service,
        vector_store_service=control_vs_service,
        settings=control_settings,
        query_formatter=None,
    )

    control_config = BenchmarkRunConfig(
        benchmark_version="v1.2-formatting-control",
        evaluation_workspace_id=eval_workspace,
        llm_provider="none",
        llm_model="none",
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
        live_llm_available=False,
        inter_case_delay_seconds=0.5,
    )

    control_runner = EvaluationRunner(
        rag_service=None,
        retrieval_service=control_ret_service,
        config=control_config,
    )

    logger.info("Evaluating 25 benchmark cases on Control...")
    control_result = control_runner.evaluate_dataset(dataset)

    # -----------------------------------------------------------------------
    # Condition 2: Treatment (Asymmetric Formatted Text)
    # -----------------------------------------------------------------------
    logger.info("=========================================================")
    logger.info("PHASE 2: TREATMENT CONDITION (Asymmetric Q&A input formatting)")
    logger.info("=========================================================")

    def format_doc_chunk(text: str) -> str:
        return f"title: none | text: {text}"

    def format_query(text: str) -> str:
        return f"task: question answering | query: {text}"

    treatment_settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_api_key=api_key,
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=768,
        vector_store_provider="qdrant",
        qdrant_collection=treatment_collection,
        qdrant_url=os.environ.get("QDRANT_URL") or None,
        qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
        chunk_size=1000,
        chunk_overlap=200,
        retrieval_default_top_k=5,
    )

    treatment_emb_service = EmbeddingService(
        manager=EmbeddingManager(settings=treatment_settings),
        doc_formatter=format_doc_chunk,
    )
    treatment_vs_service = VectorStoreService(
        manager=VectorStoreManager(settings=treatment_settings)
    )
    treatment_indexing_service = DocumentIndexingService(
        chunking_service=chunker,
        embedding_service=treatment_emb_service,
        vector_store_service=treatment_vs_service,
        settings=treatment_settings,
    )

    logger.info(
        "Indexing 18 corpus documents into Treatment collection '%s'...",
        treatment_collection,
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
        res = treatment_indexing_service.index_document(
            doc, workspace_id=eval_workspace
        )
        logger.info(
            "  [Treatment] Indexed %s -> %d chunks",
            txt_file.name,
            res.chunks_indexed,
        )

    treatment_ret_service = RetrievalService(
        embedding_service=treatment_emb_service,
        vector_store_service=treatment_vs_service,
        settings=treatment_settings,
        query_formatter=format_query,
    )

    treatment_config = BenchmarkRunConfig(
        benchmark_version="v1.2-formatting-treatment",
        evaluation_workspace_id=eval_workspace,
        llm_provider="none",
        llm_model="none",
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
        live_llm_available=False,
        inter_case_delay_seconds=0.5,
    )

    treatment_runner = EvaluationRunner(
        rag_service=None,
        retrieval_service=treatment_ret_service,
        config=treatment_config,
    )

    logger.info("Evaluating 25 benchmark cases on Treatment...")
    treatment_result = treatment_runner.evaluate_dataset(dataset)

    # -----------------------------------------------------------------------
    # Comparative Analysis & Persistence
    # -----------------------------------------------------------------------
    control_path = (
        repo_root / "benchmarks" / f"kip_v1_2_formatting_control_{timestamp}.json"
    )
    treatment_path = (
        repo_root / "benchmarks" / f"kip_v1_2_formatting_treatment_{timestamp}.json"
    )

    control_path.write_text(control_result.model_dump_json(indent=2), encoding="utf-8")
    treatment_path.write_text(
        treatment_result.model_dump_json(indent=2), encoding="utf-8"
    )
    logger.info("Saved Control results to: %s", control_path)
    logger.info("Saved Treatment results to: %s", treatment_path)

    # Compute paired deltas
    improved = 0
    degraded = 0
    identical = 0
    deltas = []

    case_dict_control = {cr.case_id: cr for cr in control_result.case_results}
    case_dict_treatment = {cr.case_id: cr for cr in treatment_result.case_results}

    print("\n" + "=" * 90)
    print("KIP v1.2 CONTROLLED EXPERIMENT: GEMINI EMBEDDING 2 INPUT FORMATTING")
    print("=" * 90)
    print(
        f"{'Case ID':<10} | {'Control RR':<10} | {'Treat RR':<10} | "
        f"{'Delta RR':<10} | {'Ctrl Hit@1':<10} | {'Trt Hit@1':<10}"
    )
    print("-" * 90)

    for case in dataset.cases:
        cid = case.id
        c_res = case_dict_control[cid].retrieval
        t_res = case_dict_treatment[cid].retrieval

        delta_rr = t_res.reciprocal_rank - c_res.reciprocal_rank
        deltas.append(delta_rr)

        if delta_rr > 0:
            improved += 1
            change_flag = "IMPROVED"
        elif delta_rr < 0:
            degraded += 1
            change_flag = "DEGRADED"
        else:
            identical += 1
            change_flag = "SAME"

        print(
            f"{cid:<10} | {c_res.reciprocal_rank:<10.4f} | "
            f"{t_res.reciprocal_rank:<10.4f} | {delta_rr:<+10.4f} | "
            f"{str(c_res.hit_at_1):<10} | {str(t_res.hit_at_1):<10} ({change_flag})"
        )

    print("=" * 90)
    print("AGGREGATE METRICS SUMMARY:")
    print("-" * 90)
    print(
        f"{'Metric':<25} | {'Control (Raw)':<16} | "
        f"{'Treatment (Formatted)':<22} | {'Absolute Delta'}"
    )
    print("-" * 90)

    mrr_ctrl = control_result.mean_reciprocal_rank or 0.0
    mrr_trt = treatment_result.mean_reciprocal_rank or 0.0
    hr1_ctrl = control_result.hit_rate_at_1 or 0.0
    hr1_trt = treatment_result.hit_rate_at_1 or 0.0
    hr3_ctrl = control_result.hit_rate_at_3 or 0.0
    hr3_trt = treatment_result.hit_rate_at_3 or 0.0
    hr5_ctrl = control_result.hit_rate_at_5 or 0.0
    hr5_trt = treatment_result.hit_rate_at_5 or 0.0
    lat_ctrl = control_result.mean_retrieval_latency_ms
    lat_trt = treatment_result.mean_retrieval_latency_ms

    print(
        f"{'Hit Rate @ 1':<25} | {hr1_ctrl:<16.4f} | "
        f"{hr1_trt:<22.4f} | {hr1_trt - hr1_ctrl:+.4f}"
    )
    print(
        f"{'Hit Rate @ 3':<25} | {hr3_ctrl:<16.4f} | "
        f"{hr3_trt:<22.4f} | {hr3_trt - hr3_ctrl:+.4f}"
    )
    print(
        f"{'Hit Rate @ 5':<25} | {hr5_ctrl:<16.4f} | "
        f"{hr5_trt:<22.4f} | {hr5_trt - hr5_ctrl:+.4f}"
    )
    print(
        f"{'Mean Reciprocal Rank':<25} | {mrr_ctrl:<16.4f} | "
        f"{mrr_trt:<22.4f} | {mrr_trt - mrr_ctrl:+.4f}"
    )
    print(
        f"{'Mean Latency (ms)':<25} | {lat_ctrl:<16.2f} | "
        f"{lat_trt:<22.2f} | {lat_trt - lat_ctrl:+.2f}"
    )
    print("-" * 90)
    print(
        f"Paired comparison: {improved} improved, {degraded} degraded, "
        f"{identical} unchanged (total {len(dataset.cases)} cases)"
    )
    print("=" * 90 + "\n")

    return control_path, treatment_path


if __name__ == "__main__":
    run_experiment()
