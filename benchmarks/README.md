# Benchmarks

## Purpose

This directory contains performance benchmarking scripts, ground-truth evaluation datasets, and reproducible experiment artifacts for the Knowledge Intelligence Platform.

## Current Status (v1.1.0)

**Implemented.** The initial baseline benchmark dataset was created during the v1.0 milestone.

### Implemented Artifacts

- **`benchmarks/kip_v1_baseline.json`:** Ground-truth benchmark dataset containing 5 carefully constructed test cases used for mechanical evaluation of the RAG pipeline. Each case includes:
  - `query`: the input question
  - `expected_answer`: a reference string verified against `evaluation/runner.py` Exact Match
  - `expected_context_contains`: document IDs or text snippets used for Hit Rate and Provenance Accuracy scoring
  - Associated metadata for version tracking and reproducibility

The benchmark is executed via `evaluation/runner.py` and produces a deterministic `EvaluationReport` (Hit Rate, Exact Match, Provenance Accuracy) without requiring live LLM inference.

## Planned Role (v1.2+)

Planned contents include:
- Expanded benchmark corpora (50–200 queries) for statistical significance
- Retrieval quality evaluation (precision, recall, MRR, NDCG)
- Response quality evaluation (faithfulness, answer relevancy via RAGAS)
- System performance measurements (latency p50/p95/p99, throughput)
- Version-to-version comparison reports

## Related Documentation

- [Benchmarking & Evaluation](../docs/Benchmarking.md)
- [Research Roadmap](../docs/Research-Roadmap.md)
- [Evaluation README](../evaluation/README.md)

