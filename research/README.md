# Research

## Purpose

This directory serves as the repository entry point for AI systems research conducted within the Knowledge Intelligence Platform.

## Current Status (v1.3.0)

**Active & v1.2 Research Concluded.** KIP follows an evidence-based research lifecycle where architectural decisions are validated through controlled experimentation before adoption.

The v1.2 retrieval research cycle evaluated five candidate techniques against a 50-document, 80-case frozen benchmark:
- Asymmetric embedding input formatting (neutral MRR 0.9133 on 25-case pilot)
- Cross-encoder reranking (MRR 0.7762, latency +1,048 ms; rejected)
- Hybrid BM25 + dense RRF retrieval (MRR 0.7094; rejected)
- Sentence-boundary chunking (MRR 0.7471; rejected)
- Context optimization and prompt budget allocation (MRR 0.7542; rejected)

All candidates failed preregistered adoption criteria (MRR ≥ 0.8200) or safety invariants; dense whole-document retrieval (MRR 0.7623, Hit@5 0.8750) remains the production default.

## Research Artifact Locations

- **Experiment Reports & Synthesis:** [`docs/evaluation/`](../docs/evaluation/) contains detailed reports for each v1.2 experiment, paired deltas, error classifications, and the final synthesis report.
- **Benchmark Datasets & Corpora:** [`benchmarks/`](../benchmarks/) contains ground-truth datasets, reference corpora (`corpus_v1_2_expanded/`), and raw experiment JSON result artifacts.
- **Evaluation Runners:** [`evaluation/`](../evaluation/) contains reproducible execution runners (`runner.py`, `run_v1_2_expanded_baseline.py`, experiment scripts).
- **Metric Integrity Verification:** [`evaluation/validate_benchmark_metrics.py`](../evaluation/validate_benchmark_metrics.py) mechanically validates MRR and Hit@K consistency across raw outputs.
- **Strategic Direction:** [`docs/Research-Roadmap.md`](../docs/Research-Roadmap.md) outlines research domains, hypotheses, and future research milestones (v1.5 Retrieval Generalization).

## Governance

All future research follows the Roadmap Governance and Strategic Guardrails defined in [`docs/Product-Roadmap.md`](../docs/Product-Roadmap.md): evidence before adoption, depth before breadth, and strict preservation of working baselines.
