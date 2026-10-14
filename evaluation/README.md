# KIP Evaluation Harness

## Purpose

This directory contains the lightweight, self-contained AI evaluation harness for
measuring retrieval hit rates, Mean Reciprocal Rank (MRR), keyword coverage, and
stage latencies across the Knowledge Intelligence Platform.

## Current Status (v1.1.0)

The evaluation harness is fully implemented and structurally validated by the
automated test suite (245+ tests). A genuine provider-backed retrieval quality
baseline (requiring live Gemini embedding API access) has not yet been run; see
**Remaining Limitations** below.

### Implemented Components

- **`evaluation/models.py`:** Pydantic domain models defining `BenchmarkCase`,
  `BenchmarkDataset`, `RetrievalMetrics`, `AnswerMetrics`, `CaseResult`,
  `BenchmarkRunConfig`, and `BenchmarkResult`.
- **`evaluation/runner.py`:** Execution engine that runs benchmark datasets
  (e.g. `benchmarks/kip_v1_1_baseline.json`) against the RAG pipeline or mock
  providers to compute:
  - **Hit Rate:** Fraction of *labelled* queries where at least one expected
    document was retrieved (computed only over cases with populated
    `expected_document_ids`).
  - **Mean Reciprocal Rank (MRR):** Reciprocal rank of the first relevant
    document hit, averaged over labelled cases.
  - **Keyword Coverage:** Fraction of expected ground-truth keywords found in
    the generated answer.
  - **Latency:** Retrieval latency, generation latency, and total latency in
    milliseconds.

No external evaluation packages (such as heavy LLM-as-judge frameworks) are
required for baseline execution, keeping the evaluation pipeline deterministic
and fast. Exact Match and LLM Faithfulness are defined as optional model fields
reserved for external judge configurations in v1.2+.

## Benchmark Datasets

| Dataset | File | Ground Truth | Use |
|---------|------|-------------|-----|
| v1.0 historical | `benchmarks/kip_v1_baseline.json` | No `expected_document_ids` (unlabelled) | Keyword coverage only; preserved as historical artifact |
| **v1.1 baseline** | `benchmarks/kip_v1_1_baseline.json` | 7 cases, all with `expected_document_ids` | Hit Rate, MRR, Keyword Coverage |

## Reference Corpus

The v1.1 baseline uses a small, version-controlled reference corpus in
`benchmarks/corpus/`. Document IDs are derived as `SHA-256(raw_file_bytes)`,
matching KIP's `DocumentIngestionService`. Corpus files use LF line endings
only to ensure stable IDs across platforms.

See [`benchmarks/corpus/README.md`](../benchmarks/corpus/README.md) for full
documentation.

## Evaluation Workspace

The `EvaluationRunner` uses `config.evaluation_workspace_id` (default:
`"kip-eval-workspace"`) for both `RetrievalQuery` and `RAGRequest`. This keeps
evaluation isolated from user workspaces. The workspace is explicitly propagated
— it does not rely on model defaults.

## Metric Semantics

### Hit Rate and MRR — labelled cases only

Cases with empty `expected_document_ids` are **unlabelled** and excluded from
Hit Rate and MRR aggregation. `BenchmarkResult.hit_rate` and
`mean_reciprocal_rank` are `None` when no labelled cases exist, preventing the
degenerate `hit_rate = 1.0` that previously occurred with empty ground-truth lists.

### Infrastructure failures vs genuine misses

Retrieval infrastructure failures (e.g. embedding service unavailable) are
recorded in `RetrievalMetrics.retrieval_error` and are distinguishable from
genuine retrieval misses (`retrieved_doc_ids = []` with `retrieval_error = None`).

## How to Run a Provider-Backed Evaluation

> **Requires live Gemini API credentials and a reachable Qdrant instance.**
> Do NOT run in automated CI.

### 1. Environment Variables

Set the following environment variables (or define them in `.env`):

```bash
# LLM Provider configuration
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
LLM_API_KEY=<your-gemini-api-key>

# Embedding Provider configuration
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSIONS=768

# Vector Store configuration (Qdrant Cloud or local Docker)
VECTOR_STORE_PROVIDER=qdrant
QDRANT_URL=https://<your-cluster>.cloud.qdrant.io:6333  # or http://localhost:6333
QDRANT_API_KEY=<your-qdrant-api-key>                  # omit or leave empty for local
QDRANT_COLLECTION=knowledge_base
```

### 2. Setup Prerequisites

1. Active Google Gemini API key with access to `gemini-embedding-2` and `gemini-2.5-flash`.
2. Running Qdrant vector database (either Qdrant Cloud or `docker run -p 6333:6333 qdrant/qdrant:latest`).
3. Repository virtual environment activated (`.venv`).

### 3. Turnkey Baseline Runner

KIP provides an automated, self-contained baseline runner script:

```bash
python evaluation/run_v1_1_baseline.py
```

This runner performs automated preflight checks (corpus integrity, deterministic SHA-256 ID validation, API key detection), indexes the reference corpus text fixtures into the isolated Qdrant collection `kip_eval_v1_1_baseline` under workspace `kip-eval-workspace`, executes the 7-case benchmark with rate-limit spacing (13s), and persists the output under both a timestamped file (`benchmarks/kip_v1_1_baseline_result_<timestamp>.json`) and the canonical path (`benchmarks/kip_v1_1_baseline_result.json`).

### 4. Canonical v1.1 Baseline Results

The genuine provider-backed baseline was executed and verified against live Google Gemini APIs and Qdrant:

| Metric | Measured Value | Notes |
|---|---|---|
| **Total Cases** | 7 | All 7 cases labelled with ground-truth document IDs |
| **Labelled Cases** | 7 | 100% labelled |
| **Hit Rate (Top-5)** | **1.0000** (7/7) | Every query retrieved its target corpus document |
| **Mean Reciprocal Rank (MRR)** | **0.9048** | 6 cases ranked #1 (RR=1.0), 1 case ranked #3 (RR=0.333) |
| **Mean Keyword Coverage** | **1.0000** | 100% of expected ground-truth keywords present in answers |
| **Mean Retrieval Latency** | 568.41 ms | Dense embedding via `gemini-embedding-2` + Qdrant search |
| **Mean Total Latency** | 3349.86 ms | End-to-end retrieval + `gemini-2.5-flash` generation |
| **Retrieval Errors** | 0 | No retrieval infrastructure or provider failures |
| **Generation Errors** | 0 | No rate-limit or quota failures with 13s inter-case spacing |

Canonical result artifact: [`benchmarks/kip_v1_1_baseline_result.json`](../benchmarks/kip_v1_1_baseline_result.json)

## Remaining Limitations

1. **Keyword coverage is substring match.** `kw.lower() in answer.lower()` does
   not capture paraphrase or synonyms.

2. **Faithfulness not implemented.** Requires an LLM judge (planned v1.2+).

3. **Single-node latency.** Latency measurements are wall-clock and include
   embedding API network round-trips; not suitable for throughput profiling.

4. **Corpus scale.** The v1.1 reference corpus contains 3 documents (~2.5 KB).
   Future benchmarks will expand corpus size and distractor count.

## Planned Role (v1.2+)

Planned enhancements for future versions:

- Integration with external evaluation frameworks (RAGAS, DeepEval) for
  automated LLM-as-judge evaluation of answer relevance and faithfulness.
- Automated per-version evaluation reporting against standardized benchmark
  corpora.
- Latency and throughput profiling utilities under concurrent loads.

## Related Documentation

- [Benchmarking Strategy](../docs/Benchmarking.md)
- [Research Roadmap](../docs/Research-Roadmap.md)
- [Product Roadmap](../docs/Product-Roadmap.md)
- [Corpus README](../benchmarks/corpus/README.md)
