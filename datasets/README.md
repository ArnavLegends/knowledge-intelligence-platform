# Datasets

## Purpose

This directory is designated for external sample corpora and evaluation datasets for the Knowledge Intelligence Platform.

## Current Status (v1.3.0)

**Active Benchmark Corpora Stored in `benchmarks/`.** The primary frozen evaluation corpora and ground-truth benchmark datasets for the platform are centralized and version-controlled under [`benchmarks/`](../benchmarks/):

- **v1.1 Baseline Corpus:** `benchmarks/corpus/` (3 documents) & `benchmarks/kip_v1_1_baseline.json` (7 cases).
- **v1.2 Pilot Corpus:** `benchmarks/corpus_v1_2/` (18 documents) & `benchmarks/kip_v1_2_benchmark.json` (25 cases).
- **v1.2 Expanded Corpus:** `benchmarks/corpus_v1_2_expanded/` (50 documents) & `benchmarks/kip_v1_2_expanded_benchmark.json` (80 cases across 6 query categories).

## Future Role

- **v1.5 (Proposed):** Storage for a second, independently sourced document collection to evaluate retrieval generalization, answer grounding, and cross-document reasoning outside the frozen v1.2 KIP architecture corpus.
- Domain-specific open test corpora and external ingestion fixtures.

## Related Documentation

- [Benchmarks README](../benchmarks/README.md)
- [Evaluation Harness README](../evaluation/README.md)
- [Benchmarking Methodology](../docs/Benchmarking.md)
