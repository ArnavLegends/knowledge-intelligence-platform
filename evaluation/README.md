# KIP Evaluation Harness

## Purpose

This directory contains the lightweight, self-contained AI evaluation harness for
measuring retrieval hit rates, Mean Reciprocal Rank (MRR), keyword coverage, and
stage latencies across the Knowledge Intelligence Platform.

## Current Status (v1.2.0)

The evaluation harness is fully implemented, provider-backed baselines have been
executed (v1.1 and v1.2 experiments), and a 50-document / 80-case expanded
benchmark has been constructed to eliminate top-k saturation. All tests pass
(276+ tests). See **Benchmark Datasets** for the full dataset inventory.

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
| **v1.2 experiment** | `benchmarks/kip_v1_2_benchmark.json` | 25 cases, all with `expected_document_ids` and `expected_chunk_ids` | Hit Rate@1/3/5, MRR, Input-Formatting Comparison |
| **v1.2 expanded** | `benchmarks/kip_v1_2_expanded_benchmark.json` | 80 cases, all labelled, 6 categories, with `expected_document_ids` and `expected_chunk_ids` | Discriminative Hit@1/3/5, MRR, hard negatives, cross-document, paraphrase |

## Reference Corpora

- **v1.1 Baseline Corpus (`benchmarks/corpus/`):** 3 version-controlled text files (LF line endings only) covering overview, chunking, and retrieval topics. See [`benchmarks/corpus/README.md`](../benchmarks/corpus/README.md).
- **v1.2 Formatting Corpus (`benchmarks/corpus_v1_2/`):** 18 version-controlled text files (14 KIP architecture documents + 4 adversarial distractors). Designed so top-5 retrieval covers ~28% of corpus candidates (18 chunks), eliminating the v1.1 Hit Rate@5 saturation. See [`benchmarks/corpus_v1_2/README.md`](../benchmarks/corpus_v1_2/README.md).
- **v1.2 Expanded Corpus (`benchmarks/corpus_v1_2_expanded/`):** 50 version-controlled text files (38 KIP architecture documents + 12 hard-negative distractors). Top-5 retrieval covers 10% of corpus; top-10 covers 20%. Eliminates saturation on both Hit@3 and Hit@5. See [`benchmarks/corpus_v1_2_expanded/README.md`](../benchmarks/corpus_v1_2_expanded/README.md).

Document IDs in all corpora are derived as `SHA-256(raw_file_bytes)`, matching KIP's `DocumentIngestionService`. Chunk IDs are derived as `SHA-256(document_id + ':' + str(chunk_index))`.

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

### 5. KIP v1.2 Controlled Input-Formatting Experiment (Gemini Embedding 2)

A controlled empirical experiment was executed comparing KIP's baseline raw-text embedding inputs (**Control**) against Google's documented asymmetric question-answering textual input formatting (**Treatment**) using the production `gemini-embedding-2` model (768 dimensions), isolated Qdrant collections, and the 18-document reference corpus.

#### Experimental Setup

- **Control Condition:**
  - Query: Raw query text (`{query}`)
  - Document Chunks: Raw chunk text (`{chunk}`)
  - Qdrant Collection: `kip_eval_v1_2_control`
- **Treatment Condition:**
  - Query: `task: question answering | query: {query}`
  - Document Chunks: `title: none | text: {chunk}`
  - Qdrant Collection: `kip_eval_v1_2_formatted`
- **API Constraint:** Google's official documentation notes that `task_type` is unsupported for `gemini-embedding-2`. Formatting was applied exclusively via text prefixes; no `task_type` API parameter was passed.
- **Payload Invariant:** In both conditions, Qdrant payload metadata retained the raw chunk text (`meta["text"] = chunk.text`) for provenance and display.
- **Corpus & Benchmark:** 18 documents (~14 KB, LF line endings, 1 chunk/doc) in `benchmarks/corpus_v1_2/` and 25 labelled queries in `benchmarks/kip_v1_2_benchmark.json`. Top-5 retrieval evaluates 5 out of 18 chunks (~28% of corpus).
- **Evaluation Scope:** Pure dense retrieval (LLM generation omitted to isolate retrieval quality and conserve quota).
- **Execution Script:** `python evaluation/run_v1_2_formatting_experiment.py`

#### Measured Results

| Metric | Control (Raw Text) | Treatment (Formatted Text) | Absolute Delta |
|---|---|---|---|
| **Hit Rate @ 1** | **0.8400** (21/25) | **0.8400** (21/25) | `+0.0000` |
| **Hit Rate @ 3** | **1.0000** (25/25) | **1.0000** (25/25) | `+0.0000` |
| **Hit Rate @ 5** | **1.0000** (25/25) | **1.0000** (25/25) | `+0.0000` |
| **Mean Reciprocal Rank (MRR)** | **0.9133** | **0.9133** | `+0.0000` |
| **Mean Retrieval Latency** | 556.89 ms | 536.51 ms | `-20.38 ms` |

#### Paired Query Behavior & Analysis

- **23 of 25 queries (92.0%)** produced identical retrieval rankings across both conditions.
- **1 query improved:** `v12-017` ("What formats can users upload to populate their private enterprise knowledge repositories?"): reciprocal rank improved from 0.5000 (rank 2) to 1.0000 (rank 1), converting a Hit@1 miss to a hit.
- **1 query degraded:** `v12-010` ("How does KIP prevent customer data leakage across different organizational tenants?"): reciprocal rank dropped from 1.0000 (rank 1) to 0.5000 (rank 2), converting a Hit@1 hit to a miss.
- Both changed cases represented rank-order swaps between two highly relevant documents (`kip_overview.txt` vs `kip_document_parsers.txt`, and `kip_security_threat_model.txt` vs `kip_multitenancy_architecture.txt`).

#### Result Artifacts

- Control Result: [`benchmarks/kip_v1_2_formatting_control_20261014_094111.json`](../benchmarks/kip_v1_2_formatting_control_20261014_094111.json)
- Treatment Result: [`benchmarks/kip_v1_2_formatting_treatment_20261014_094111.json`](../benchmarks/kip_v1_2_formatting_treatment_20261014_094111.json)

#### Pilot Evaluation Qualifications & Engineering Decision

1. **Benchmark Scale Limitations:** The evaluation covers 25 queries over an 18-document corpus. Hit Rate@3 and Hit Rate@5 reached 100% on this pilot benchmark. Because top-3 and top-5 retrieval saturated, these results cannot establish general retrieval superiority across broad, large-scale corpora.
2. **Latency Interpretation:** The 20.38 ms latency difference is within standard cloud network variance and is not claimed as statistically meaningful.
3. **Production Default Decision:** Because the aggregate retrieval performance was exactly neutral (MRR 0.9133 vs 0.9133, Hit@1 0.8400 vs 0.8400), **KIP retains raw-text embedding as the production default**. Adding task prefixes consumes additional prompt tokens without demonstrated retrieval gain on this benchmark.
4. **Extension Hooks:** Provider-neutral `doc_formatter` in `EmbeddingService` and `query_formatter` in `RetrievalService` remain in the codebase as optional extension hooks for future research.
5. **Future Research Need:** Larger, more diverse benchmark evaluation (more documents, distractor-heavy environments, cross-domain corpora) is identified as a necessary next step for future retrieval investigations (e.g. hybrid search, reranking).

### 6. KIP v1.2 Expanded Benchmark

A 50-document, 80-case benchmark was constructed to provide discriminative retrieval evaluation without the saturation observed in the 18-document pilot.

#### Corpus Construction (`benchmarks/corpus_v1_2_expanded/`)

| Category | Count | Purpose |
|---|---|---|
| KIP architecture documents | 38 | Genuine factual content covering API, chunking, embeddings, security, evaluation, etc. |
| Hard-negative distractors | 12 | Semantically adjacent but off-topic documents (Kubernetes, Redis, OAuth2, etc.) |
| **Total** | **50** | 1 chunk/doc at 1000/200 sizing → 50 chunk candidates |

- Top-5 retrieval = 10% of corpus (vs. 28% for the 18-doc pilot)
- Top-10 retrieval = 20% of corpus
- Hit@3 and Hit@5 saturation effectively eliminated for strong distractors

#### Benchmark Case Categories

| Category | Cases | Design Goal |
|---|---|---|
| `exact_terminology` | 16 | Named entities, exact config values, header names |
| `paraphrase` | 16 | Same semantics, different surface form |
| `multi_concept` | 16 | Queries requiring synthesis across multiple facts |
| `hard_negative` | 16 | Queries where distractor documents share terminology |
| `cross_document` | 8 | Queries whose answers span two source documents |
| `boundary_handling` | 8 | Edge-case queries (empty results, ambiguous scope, LF/CRLF stability) |
| **Total** | **80** | |

#### Generation

```bash
# Regenerate corpus document IDs (if corpus files change)
python benchmarks/build_expanded_corpus_and_dataset.py

# Regenerate the 80-case benchmark JSON
python benchmarks/generate_80_cases.py
```

Output: `benchmarks/kip_v1_2_expanded_benchmark.json`

All document IDs are verified offline against `benchmarks/corpus_v1_2_expanded_ids.json` and by the automated test suite (`test_v12_expanded_ids_json_consistency`).

## Remaining Limitations

1. **Keyword coverage is substring match.** `kw.lower() in answer.lower()` does
   not capture paraphrase or synonyms.

2. **Faithfulness not implemented.** Requires an LLM judge (planned v1.2+).

3. **Single-node latency.** Latency measurements are wall-clock and include
   embedding API network round-trips; not suitable for throughput profiling.

4. **Corpus scale.** The v1.1 reference corpus contains 3 documents; the v1.2 pilot
   corpus contains 18 documents. The v1.2 expanded corpus contains 50 documents and
   eliminates Hit@3/Hit@5 saturation. A live provider-backed run against the 80-case
   expanded benchmark is the recommended next step.

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
- [Corpus v1.1 README](../benchmarks/corpus/README.md)
- [Corpus v1.2 Formatting README](../benchmarks/corpus_v1_2/README.md)
- [Corpus v1.2 Expanded README](../benchmarks/corpus_v1_2_expanded/README.md)
