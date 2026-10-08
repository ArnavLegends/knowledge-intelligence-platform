# Tests

This directory contains the full automated test suite for the Knowledge Intelligence Platform.

## Current Status (v1.1.0)

**245 tests — 100% passing** across all subsystems.

## Test Coverage by Subsystem

| Subsystem | Examples |
|-----------|---------|
| Scaffold / infrastructure | Project structure, imports, configuration loading |
| Document parsers | `.txt`, `.md`, `.pdf`, `.docx` ingestion and error handling |
| Chunking | Fixed-size character chunker, overlap, idempotency |
| Embedding providers | Gemini (1:1 Content/Part batching), OpenAI mock |
| Vector stores | ChromaDB insert/search/delete, Qdrant Cloud integration |
| Backend API endpoints | `/health`, `/ready`, `/documents` (POST + GET), `/retrieval/search`, `/rag/answer`, `/llm/generate`, `/feedback` |
| Multi-tenancy | Workspace isolation via `X-KIP-Workspace-ID`, cross-workspace contamination prevention, quota enforcement |
| Evaluation harness | `EvaluationSample`, `EvaluationDataset`, `evaluation/runner.py` hit rate / exact match / provenance |
| Feedback API | Schema validation, 30-word limit, category enforcement, GET webhook dispatch |

## Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov --cov-report=term-missing
```

Targeted (example — single module):

```bash
pytest tests/test_feedback_api.py -v
```

## Development Milestone

- **v0.1:** Testing framework established with scaffold validation tests.
- **v0.2:** Backend service unit tests added.
- **v0.3:** RAG pipeline integration tests (chunking, embeddings, retrieval) added.
- **v1.0:** Evaluation harness tests, multi-format parser tests, and API endpoint tests added. Test count reached ~116.
- **v1.1 (Current / Frozen):** Multi-tenancy isolation tests, Qdrant integration tests, workspace quota tests, feedback API tests added. Full suite: **245 tests**.

## Related Documentation

- [Development Workflow](../docs/Development-Workflow.md)
- [Software Requirements Specification](../docs/SRS.md)
- [Benchmarking & Evaluation](../docs/Benchmarking.md)

