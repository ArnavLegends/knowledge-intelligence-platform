# KIP Evaluation Corpus — v1.1 Baseline

## Purpose

This directory contains the small, version-controlled reference corpus used for the
KIP v1.1 retrieval evaluation baseline. The corpus is ingested into an isolated
evaluation workspace to measure genuine dense-retrieval quality (Hit Rate, MRR) before
any v1.2 retrieval improvements are made.

## Corpus Documents

| File | Topic | Size (bytes) | Document ID |
|------|-------|-------------|-------------|
| `kip_overview.txt` | Platform overview, formats, frontend, feedback | 893 | `07123957b17b180eef3505c6b2dc1f76a161cedcc618081eb882de99dbf2a324` |
| `kip_chunking_and_embeddings.txt` | Chunking defaults, chunk IDs, document IDs, embeddings | 844 | `42fdd2502a96a31974aad6a476bdba4c28fe896cf126d25ca984f6cc7f551bd9` |
| `kip_retrieval_and_rag.txt` | Qdrant search, distance metric, context assembly, generation | 799 | `c018e2ecd67d7fae0592d751086f9ee5c5496ded23692bbbf1f74d112b14aa14` |

## Design Constraints

- **LF line endings only.** All corpus files use Unix LF (`\n`) exclusively.
  CRLF would change the SHA-256 hash and invalidate the document IDs in the
  benchmark dataset. Verify with `benchmarks/derive_corpus_ids.py`.
- **Content-frozen.** Do not edit corpus files after publishing the baseline.
  Any content change changes the document ID and invalidates all benchmark cases
  pointing to that document.
- **Distinguishable distractors by topic.** Each document covers a distinct topic
  area so that dense retrieval can be expected to score relevant chunks higher than
  irrelevant ones, making Hit Rate and MRR meaningful.

## Document ID Derivation

Document IDs are computed using the same mechanism as KIP's `DocumentIngestionService`:

```python
document_id = hashlib.sha256(raw_file_bytes).hexdigest()
```

To verify or re-derive IDs:

```bash
python benchmarks/derive_corpus_ids.py
```

The script reads each `.txt` file in this directory, computes its SHA-256 ID, and
reports its byte count and whether CRLF is present.

## Relationship to Benchmark Datasets

| Dataset | File | `expected_document_ids` |
|---------|------|------------------------|
| v1.0 baseline | `benchmarks/kip_v1_baseline.json` | Empty (unlabelled, preserved as historical artifact) |
| v1.1 baseline | `benchmarks/kip_v1_1_baseline.json` | Populated from this corpus |

The v1.0 dataset is preserved as-is. Its `expected_document_ids` are empty because
it was created before the v1.1 corpus and ground-truth derivation process existed.
It remains valid for keyword-coverage measurement but must not be used for retrieval
metric (Hit Rate / MRR) evaluation.

## Reproducible Evaluation

To run a full retrieval-backed evaluation against this corpus, you must:

1. Index the three corpus documents into the evaluation workspace (`kip-eval-workspace`)
   using KIP's actual ingestion pipeline (not a mock) with the production embedding provider.
2. Run the `EvaluationRunner` with `config.evaluation_workspace_id = "kip-eval-workspace"`.
3. The runner will propagate the workspace to both `RetrievalQuery` and `RAGRequest`.

> **Note:** The automated test suite uses deterministic fake embedding providers
> (SHA-256-based vectors) and does not require live API credentials. It validates
> structural correctness and metric computation, not real retrieval quality.
> A genuine retrieval quality baseline requires live Gemini API access.
