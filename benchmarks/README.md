# Benchmarks

## Purpose

This directory contains performance benchmarking scripts, ground-truth evaluation datasets, reference corpora, and reproducible experiment artifacts for the Knowledge Intelligence Platform.

## Current Status (v1.3.0)

**Active & Benchmark Suite Established.** The platform maintains frozen reference datasets and historical experiment artifacts supporting longitudinal evaluation across releases.

### Implemented Benchmark Datasets & Corpora

- **`benchmarks/kip_v1_baseline.json`:** Ground-truth dataset containing 5 mechanical test cases (historical v1.0 artifact).
- **`benchmarks/kip_v1_1_baseline.json`:** 7-case benchmark against `benchmarks/corpus/` (3 documents) measuring Hit Rate, MRR (0.9048), and Keyword Coverage.
- **`benchmarks/kip_v1_2_benchmark.json`:** 25-case formatting pilot dataset evaluated against `benchmarks/corpus_v1_2/` (18 documents).
- **`benchmarks/kip_v1_2_expanded_benchmark.json`:** 80-case expanded retrieval benchmark across six categories (`exact_terminology`, `paraphrase`, `hard_negative`, `multi_concept`, `boundary_handling`, `cross_document`) evaluated against `benchmarks/corpus_v1_2_expanded/` (50 documents).
- **`benchmarks/corpus_v1_2_expanded_ids.json`:** Frozen canonical mapping of SHA-256 document IDs for all 50 corpus files.

### Frozen Baseline & Experiment Results

- **Expanded Baseline Result:** `benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json` (MRR: 0.7623, Hit@1: 0.6875, Hit@3: 0.8375, Hit@5: 0.8750).
- **Formatting Pilot Results:** `benchmarks/kip_v1_2_formatting_control_20261014_094111.json`, `benchmarks/kip_v1_2_formatting_treatment_20261014_094111.json` (Neutral MRR 0.9133).
- **Cross-Encoder Reranking Result:** `benchmarks/kip_v1_2_reranking_treatment_20261014_115445.json` (MRR 0.7762, latency +1,048 ms; rejected).
- **Hybrid Retrieval Result:** `benchmarks/kip_v1_2_hybrid_treatment_20261014_121435.json` (MRR 0.7094; rejected).
- **Sentence Chunking Result:** `benchmarks/kip_v1_2_chunking_treatment_20261014_124804.json` (MRR 0.7471; rejected).
- **Context Optimization Result:** `benchmarks/kip_v1_2_context_optimization_treatment_20261015_062231.json` (MRR 0.7542; rejected).

Metric integrity across these artifacts is mechanically validated by `evaluation/validate_benchmark_metrics.py`.

## Future Evaluation Role

- **v1.5 (Proposed):** Retrieval generalization assessment on a small, independently sourced second document collection separate from the frozen v1.2 benchmark.
- **v1.7 (Proposed):** Operational validation and realistic workload/concurrency benchmarking scheduled for the ~50–60% development checkpoint.

## Related Documentation

- [Benchmarking & Evaluation](../docs/Benchmarking.md)
- [Research Roadmap](../docs/Research-Roadmap.md)
- [Evaluation README](../evaluation/README.md)
- [Research Synthesis](../docs/evaluation/v1.2_research_synthesis.md)

