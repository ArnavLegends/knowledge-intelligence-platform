# Tests

This directory contains the full automated test suite for the Knowledge Intelligence Platform.

## Current Status (v1.3.0)

**396 tests — 100% passing** across all subsystems, with zero warnings and Ruff lint/format cleanliness.

## Test Coverage by Subsystem

| Subsystem | Examples |
|-----------|---------|
| Scaffold / infrastructure | Project structure, imports, configuration loading |
| Document parsers | `.txt`, `.md`, `.pdf`, `.docx` ingestion, boundary handling, and error handling |
| Chunking | Fixed-size character chunker, overlap, idempotency, sentence chunker evaluations |
| Embedding providers | Gemini (1:1 Content/Part batching), OpenAI mock, cached embedding lookups |
| Vector stores | ChromaDB insert/search/delete, Qdrant Cloud integration, deterministic UUID5 points |
| In-Memory Caching | Thread-safe LRU search cache, embedding cache, TTL expiry, workspace invalidation |
| Concurrency & Offloading | Thread-pool offloading (`run_blocking`), non-blocking FastAPI async handlers |
| Timeouts & Error Mapping | Per-provider timeout enforcement, HTTP 504 Gateway Timeout mappings |
| Backend API endpoints | `/health`, `/ready`, `/documents` (POST + GET), `/retrieval/search`, `/rag/answer`, `/llm/generate`, `/feedback` |
| Multi-tenancy | Workspace isolation via `X-KIP-Workspace-ID`, cross-workspace contamination prevention, quota enforcement |
| Evaluation harness | `BenchmarkCase`, `BenchmarkDataset`, `evaluation/runner.py` hit rate, MRR, keyword coverage |
| Benchmark integrity | 50-document expanded corpus consistency, SHA-256 ID validation, 80-case uniqueness |
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
pytest tests/test_caching.py -v
```

## Development Milestone

- **v0.1:** Testing framework established with scaffold validation tests.
- **v0.2:** Backend service unit tests added.
- **v0.3:** RAG pipeline integration tests (chunking, embeddings, retrieval) added.
- **v1.0:** Evaluation harness tests, multi-format parser tests, and API endpoint tests added. Test count reached ~116.
- **v1.1:** Multi-tenancy isolation tests, Qdrant integration tests, workspace quota tests, feedback API tests added (245 tests).
- **v1.2:** Retrieval research tests: expanded corpus integrity, 80-case benchmark validation, candidate algorithm tests (285+ tests).
- **v1.3 (Current):** Performance engineering tests: in-memory LRU search and embedding caching, thread-pool offloading, timeout handling, latency telemetry, and concurrency safety. Full suite: **396 tests (100% passing)**.

## Related Documentation

- [Development Workflow](../docs/Development-Workflow.md)
- [Software Requirements Specification](../docs/SRS.md)
- [Benchmarking & Evaluation](../docs/Benchmarking.md)

