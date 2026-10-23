# Changelog

All notable changes to the Knowledge Intelligence Platform are documented in this file.

The project follows Semantic Versioning (SemVer).

Version format:

MAJOR.MINOR.PATCH

Examples:

- v0.1.0
- v0.2.0
- v1.0.0
- v1.1.0

For a detailed commit-by-commit engineering narrative explaining the evolutionary rationale of each milestone, see [PROJECT_HISTORY.md](PROJECT_HISTORY.md).

---

## Categories

Changes are grouped using the following categories:

- Added
- Changed
- Improved
- Fixed
- Removed
- Deprecated
- Security

Each release documents significant engineering changes while maintaining historical accuracy.

---

## [v1.4.0] — Security-First Engineering Revamp

**Release Date:** 2026-10-23
**Theme:** Security Hardening, Document Persistence & Lifecycle, Runtime Reliability, RAG Citation Enrichment, Benchmark Data Integrity

This release executes the KIP Engineering Excellence Plan across five stages. Original Document Inventory features from the prior development track are preserved and extended.

### Added

#### Backend

- **`DELETE /api/v1/documents/{document_id}`** endpoint with strict workspace isolation:
  - Verifies document exists in the requesting workspace before deletion.
  - Deletes all associated embedding vectors scoped to `(document_id, workspace_id)` — does not affect documents of identical content in other workspaces.
  - Evicts workspace search cache immediately on deletion.
  - Returns `200` with `{document_id, deleted, workspace_id, message}` on success.
  - Returns `404` with structured error `{"error": {"code": "not_found", ...}}` when document is absent from workspace.
  - Rejects missing or invalid workspace tokens with `400` (consistent with other endpoints).
- **`indexed_at` metadata field** on `WorkspaceDocumentItem`:
  - Populated during chunk indexing as an ISO 8601 timestamp.
  - Surfaced by `GET /api/v1/documents` for all newly indexed documents.
  - Returns `null` for documents indexed before v1.4 (legacy records).
- **Parser error improvements:**
  - PDF parser: detects encrypted/password-protected PDFs and returns an actionable error (preserves `Could not read PDF file:` prefix for compatibility).
  - DOCX parser: detects corrupted DOCX files and returns an actionable diagnostic (preserves `Could not read DOCX file:` prefix for compatibility).

#### Frontend (`frontend/app.py`)

- **Document inventory `indexed_at` display**: each document expander now shows `indexed_at` (formatted) or `"Unavailable (legacy record)"` for pre-v1.4 entries.
- **Delete Document button**: each document expander includes a `🗑️ Delete` button that calls `DELETE /api/v1/documents/{doc_id}`, refreshes the document list, clears the last query/answer, and displays success/error feedback.
- **Evidence source improvements**: sources renamed to "Evidence Sources"; source citation header maps to `[N] filename` notation; added rank, relevance score, and chunk ID to source captions; expander label changed to `▸ Inspect Evidence Passage [N]`.
- **Upload error diagnostics**: `_api_error_message` now maps HTTP 400/415/429/502/503/504 to actionable user-facing messages distinguishing document format errors from infrastructure timeouts.

#### Documentation

- **`docs/evaluation/v1.5_generalization_protocol.md`**: Frozen draft research protocol for the v1.5 secondary corpus evaluation, covering RQs, 4 falsifiable hypotheses, corpus selection procedure, 60-query set across 6 categories, evaluation Tracks A/B/C/D (D gated on implementation), metrics (MRR, Hit@K, Precision@K, CF, UCR, abstention), latency scopes, configuration hashes, threats to validity, and 5 decision gates.
- **`docs/API-Reference.md`** (Document Version 3.1): Updated `GET /api/v1/documents` schema to reflect actual response array format and `indexed_at`; added `DELETE /api/v1/documents/{document_id}` documentation.

### Changed

- `GET /api/v1/documents` now requires `X-KIP-Workspace-ID` (consistent with other scoped endpoints); previously it defaulted silently to `"default"` workspace.

### Research Integrity (Phase 1)

- `README.md`: Fixed navigation anchors; qualified grounding claim (citations indicate retrieved evidence, not absolute factual correctness).
- `docs/Benchmarking.md`: Split combined pilot/expanded row; clarified MRR 0.7094–0.7762 as expanded-only range; labeled all latency measurement scopes explicitly.
- `docs/evaluation/v1.2_research_synthesis.md`: Qualified whole-document truncation claim; retained empirical observation without unsupported certainty.
- `docs/Product-Roadmap.md`: Reconciled historical milestones (Documentation Reconciliation & Community Phase marked Historical/Completed).
- `docs/CURRENT_STATUS.md`: Qualified executive summary with free-tier constraints and grounding qualifications; separated pilot vs. expanded benchmark populations.

### Tests

- `tests/test_documents_api.py`: Added 4 tests:
  - `test_list_documents_metadata_and_legacy_records` — verifies `indexed_at` field and `null` for legacy records.
  - `test_delete_document_success` — verifies 200 response, `workspace_id` in body, correct mock call.
  - `test_delete_document_not_found` — verifies 404 structured error when document absent.
  - `test_delete_document_rejects_missing_or_invalid_workspace` — verifies 400 for missing/short tokens.
- `tests/test_workspace_multitenancy.py`: Added 3 tests:
  - `test_workspace_document_deletion_is_isolated` — verifies service-level deletion isolation across tenants.
  - `test_workspace_deletion_api_endpoint_flow` — verifies cross-workspace 404, successful deletion, and idempotent re-delete.
  - Extended `test_workspace_listing_api_endpoint` to assert `indexed_at is not None`.
- `tests/test_frontend.py`: Updated expander label assertion from `"retrieved excerpt"` to `"Evidence Passage"` to match UI changes.

---

# [v1.3.0] — Performance Engineering & Concurrency Hardening

**Release Date:** 2026-10-15
**Theme:** Performance Engineering, Bounded Zero-Cost Caching, Async Thread Offloading, Timeout Resilience & Observability

### Added

#### In-Memory Zero-Infrastructure Caching Foundation
- **Thread-Safe Bounded LRU Cache Foundation (`app.services.cache.lru_cache.LRUCache`)**:
  - Pure Python thread-safe generic LRU cache using `collections.OrderedDict` protected by `threading.RLock`.
  - Zero external infrastructure cost (no Redis/Memcached required, free-tier friendly).
  - Explicit size capacity enforcement and LRU eviction tracking.
- **Embedding Cache (`app.services.cache.embedding_cache.EmbeddingCache`)**:
  - In-memory cache keyed by SHA-256 of `(normalized_text, model, dimensions)`.
  - Integrated into `EmbeddingManager`: transparent lookup on single-input requests (queries) while bulk batch ingestion safely bypasses cache.
  - Reduces upstream provider latency from ~1.8 ms to 0.01 ms on cache hits (100% reduction in provider calls for repeated queries).
- **Multi-Tenant Search Cache (`app.services.cache.search_cache.SearchCache`)**:
  - In-memory TTL-backed cache keyed by SHA-256 of all query-affecting parameters: `(workspace_id, collection, vector_hash, top_k, threshold, document_id, canonical_filters)`.
  - Strict tenant isolation: every key embeds `workspace_id`.
  - Workspace-level (`invalidate_workspace`) and document-level (`invalidate_document`) invalidation indexes.
  - Automatically triggered on document indexing and document deletion.
  - Reduces vector store query latency from simulated network time to 0.04 ms on cache hits.

#### Bounded Async Thread Offloading & Timeout Protection
- **Async Blocking Executor (`app.core.async_executor`)**:
  - Process-level `ThreadPoolExecutor` with bounded worker ceiling (`RETRIEVAL_EXECUTOR_WORKERS`, default: 4).
  - `run_blocking(fn, *args, timeout=...)` helper offloading CPU/synchronous I/O from FastAPI's async event loop.
  - Graceful pool shutdown (`shutdown_executor`) registered with application lifespan in `app.main`.
- **Endpoint-Level Timeout Resilience & HTTP 504 Protection**:
  - `POST /api/v1/retrieval/search`: Offloaded to thread pool with overall timeout `embedding_timeout_seconds + qdrant_timeout_seconds + 2.0s`. Translates timeouts to HTTP 504 Gateway Timeout.
  - `POST /api/v1/rag/answer`: Offloaded to thread pool with overall timeout `embedding_timeout_seconds + qdrant_timeout_seconds + llm_timeout_seconds + 3.0s`. Translates timeouts to HTTP 504 Gateway Timeout.
- **Client-Side Timeout Settings**:
  - `EMBEDDING_TIMEOUT_SECONDS` (default: 15.0s)
  - `LLM_TIMEOUT_SECONDS` (default: 30.0s)
  - `QDRANT_TIMEOUT_SECONDS` (default: 10.0s)
  - `RETRIEVAL_EXECUTOR_WORKERS` (default: 4)

#### Observability & Telemetry
- Structured wall-clock performance instrumentation logged at `INFO` level:
  - Retrieval: `search_cache=hit|miss embed_ms=%.1f search_ms=%.1f total_ms=%.1f workspace=%s top_k=%d doc_scope=%s`
  - RAG: `RAG complete: retrieve_ms=%.1f generate_ms=%.1f total_ms=%.1f workspace=%s chunks=%d`
  - Zero PII or query text logged, preserving data privacy and security invariants.

### Changed
- Promoted performance latency logs from `DEBUG` to `INFO` so telemetry is visible under Render's production `LOG_LEVEL=INFO`.
- Standardized pytest temporary directory handling via `--basetemp=.pytest_temp` in `pyproject.toml` and `.gitignore` to resolve Windows symlink unlinking permission issues.

### Verified
- Automated test suite expanded to 396 tests with 100% pass rate (0 failures).
- Historical benchmark audit verified 8/8 suites passing with zero material discrepancies.

---

# [v1.2.0] — Retrieval Intelligence Research & Benchmark Suite

**Release Date:** 2026-10-14
**Theme:** Retrieval Intelligence Research, Ground-Truth Benchmarking & Hypothesis Testing

### Added

- **Expanded Reference Corpus & Benchmark Dataset**:
  - Curated 50-document evaluation corpus (`benchmarks/corpus_v1_2_expanded/`) spanning architecture documents and 4 adversarial distractors.
  - Labelled 80-case evaluation benchmark across six query categories: exact token lookup, semantic paraphrase, cross-document synthesis, multi-concept query, adversarial distractor, and unanswerable query.
  - Established canonical frozen dense baseline on Google Gemini `gemini-embedding-2` (768 dimensions) + Qdrant Cloud (`benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json`): MRR = 0.7623, Hit@1 = 0.6875, Hit@3 = 0.8375, Hit@5 = 0.8750.
- **Asymmetric Formatting Hooks & 25-Case Pilot**:
  - Added optional `doc_formatter` to `EmbeddingService` and `query_formatter` to `RetrievalService`.
  - Conducted controlled experiment on 25-case pilot benchmark (`benchmarks/kip_v1_2_benchmark.json`): Both control and treatment achieved identical aggregate MRR = 0.9133 and Hit@1 = 0.8400. Raw-text default retained.
- **Evaluation Runner & Metric Auditor**:
  - Fine-grained retrieval evaluation in `evaluation/runner.py` computing Hit@1, Hit@3, Hit@5, MRR, keyword coverage, and stage latencies.
  - Automated metric auditor (`evaluation/validate_benchmark_metrics.py` and `tests/test_benchmark_audit.py`) validating mathematical integrity across historical benchmark runs.

### Evaluated & Concluded (Negative Findings Retained)
- **Candidate Techniques Evaluated**:
  1. *Asymmetric Input Formatting*: Neutral (MRR 0.9133 on 25-case pilot); raw-text embedding retained.
  2. *Cross-Encoder Reranking*: Did not meet preregistered acceptance criteria; rejected.
  3. *Hybrid BM25 + Dense Retrieval*: Did not outperform dense baseline; rejected.
  4. *Sentence-Boundary Chunking*: Did not satisfy adoption criteria; rejected.
  5. *Context Optimization*: Did not satisfy adoption criteria; rejected.
- **Production Standard**: Dense whole-document retrieval retained as the verified production standard. All negative and neutral experiment results, JSON artifacts, and failure analysis reports preserved for scientific reproducibility.

---

# [v1.1.0] — Multi-Tenant Cloud Knowledge Layer & Public Testing

**Release Date:** 2026-10-07 (Feature-frozen with public testing and feedback transport on 2026-10-08)
**Related Commits:** `6a5d4e6`, `1a546b6`, `7c7eefc`, `58038bf`, `b3d6bf4`, `64c6562`, `cc4ee47`, `09842ef`, `ce1c42a`

## Added

### Multi-Tenancy & Workspace Isolation
- **Workspace Bearer Tokens**: Cryptographically secure bearer-token tenant isolation via `X-KIP-Workspace-ID` header. All document indexing, document listing, retrieval, and RAG operations are strictly isolated per workspace token.
- **Qdrant Cloud Provider**: Added `QdrantVectorStoreProvider` using `qdrant-client` for persistent cloud vector storage with indexed payload filtering by `workspace_id`.
- **Deterministic Point IDs**: Point IDs in Qdrant are generated deterministically using UUID5 scoped to the workspace (`uuid5(NAMESPACE_URL, "kip://<workspace_id>/<chunk_id>")`), guaranteeing point stability across restarts.
- **Workspace Document Management**: Added `GET /api/v1/documents` endpoint to list all documents, chunk counts, media types, and sizes belonging strictly to the caller's workspace.
- **Workspace Limits**: Free-tier safeguards enforcing `MAX_DOCUMENTS_PER_WORKSPACE=50` and `MAX_CHUNKS_PER_WORKSPACE=1000`.

### Cloud Deployment & Operational Resilience
- **Zero-Cost Deployment**: Added `render.yaml` infrastructure-as-code configuration for Render Free Web Service, and Streamlit Community Cloud frontend configuration.
- **Render Cold-Start Handling**: Added frontend ping and auto-retry with exponential backoff and informative user status messages while sleeping Render containers wake up.
- **Streamlit UX State Reset**: Switching or creating workspaces now resets previous question, answer, sources, error state, and uploader key.
- **Configurable Top-K**: Expanded retrieval Top-K slider in UI from 1 to 20 without silent backend truncation.
- **Cross-Document RAG**: Added verified support for multi-document retrieval contributions to a single query.

### Public Testing & Community Feedback
- **Public Testing UX**: Added "Welcome to KIP" orientation section, suggested test workflows, and in-app feedback box.
- **Public Feedback API**: Added `POST /api/v1/feedback` endpoint with category validation, non-empty message checks, and strict 30-word limit.
- **Authenticated GET Feedback Transport**: Switched backend-to-Apps-Script transport in `ce1c42a` to dispatch authenticated HTTPS `GET` requests with URL query parameters to Google Apps Script `doGet()`, persisting submissions to Google Sheets. Resolves Google Apps Script `doPost` HTTP 404 routing failure on free web apps.
- **Credential Protection**: Secured via `FEEDBACK_WEBHOOK_URL` and `FEEDBACK_WEBHOOK_TOKEN` with secrets never returned in error responses or logs.

## Changed

- **Gemini Batch Embeddings**: Refactored `GeminiEmbeddingProvider` to correctly batch chunk texts into `types.Content` objects, resolving serialization failures during multi-file indexing.

## Fixed

- **Status Code Preservation**: Fixed exception handlers in `backend/app/core/exceptions.py` to preserve original HTTP error status codes from downstream services.
- **Eager Workspace Validation**: Enforced workspace token validation prior to initializing heavy service dependencies.
- **Streamlit Encoding**: Normalized `.streamlit/config.toml` encoding to UTF-8.

---

# [v1.0.1] — Document Idempotency Service Wiring Patch

**Release Date:** 2026-10-07
**Related Commits:** `fcdb6b8`

## Fixed

- **Idempotency Detection**: Connected `indexing_service.document_exists()` in `POST /api/v1/documents` so duplicate uploads of identical file content return existing document metadata with `chunks_indexed=0`, preventing duplicate vector generation.

---

# [v1.0.0] — Production RAG Platform

**Release Date:** 2026-10-07
**Related Commits:** `1b8d3f7`

## Added

### Multi-Format Document Ingestion
- **Multi-Format Parsers**: Implemented parsers for Markdown (`.md`, `.markdown`), PDF (`.pdf`), and DOCX (`.docx`) using `pypdf` and `python-docx` respectively.
- **Parser Registry**: Extensible registry pattern allowing format additions without modifying the core ingestion service.
- **Multi-Format E2E Tests**: Added E2E tests for the ingestion pipelines validating full end-to-end provenance.

### Deterministic Identity & Idempotency
- **Content-Based Document IDs**: Generated via SHA-256 hash of raw file content (`document_id = sha256(content)`).
- **Deterministic Chunk IDs**: Generated via SHA-256 hash of document ID and chunk index (`chunk_id = sha256(f"{doc_id}:{chunk_index}")`).

### Multi-Provider AI Gateway
- **Google Gemini Integration**: Added `GeminiProvider` (`gemini-2.5-flash`) and `GeminiEmbeddingProvider` (`gemini-embedding-2`, 768 dimensions) using Google's `google-genai` SDK.

### Evaluation Framework & Benchmarks
- **Evaluation Harness**: Implemented `evaluation/models.py` and `evaluation/runner.py` measuring mechanical metrics: document hit rate, Mean Reciprocal Rank (MRR), keyword coverage, and stage latencies without external network dependencies.
- **Benchmark Baseline**: Added deterministic baseline benchmark dataset `benchmarks/kip_v1_baseline.json` with 5 standardized cases.

### Frontend
- **Streamlit UI**: Implemented interactive single-page application in `frontend/app.py` for uploading documents, querying the knowledge base, and inspecting source citations.

## Changed

- **FastAPI Factory Dependencies**: Added service factory getters (e.g. `get_indexing_service`, `get_rag_service`, `get_retrieval_service`) to support DI overrides in tests.
- **Dependencies**: Added `pypdf`, `python-docx`, and `google-genai` to `pyproject.toml`.

---

# [v0.4.0] — Multi-Format Document Ingestion (Pre-v1.0 Milestone)

**Date:** 2026-10-07
**Related Commits:** Part of the v1.0.0 productization development cycle leading to `1b8d3f7`

## Added
- **Multi-Format Parsers**: Implemented parsers for Markdown (`.md`, `.markdown`), PDF (`.pdf`), and DOCX (`.docx`) using `pypdf` and `python-docx` respectively.
- **Multi-Format E2E Tests**: Added E2E tests for the new ingestion pipelines validating full end-to-end provenance.

## Changed
- **Dependencies**: Added `pypdf` and `python-docx` to `pyproject.toml`.
- **Validation**: Updated format validation to reject files like `.unknown` properly instead of `.pdf`.

---

# [v0.3.0] — End-to-End RAG Workflow (Core Foundation Milestone)

**Date:** 2026-10-07
**Related Commits:** Core RAG pipeline stabilization leading to `1b8d3f7`

## Added
- **E2E Integration Test**: Added `tests/test_e2e_rag.py` to ensure the core pipeline works perfectly without depending on real external APIs.
- **FastAPI Factory Dependencies**: Added service factory getters (e.g. `get_indexing_service`, `get_rag_service`, `get_retrieval_service`) to support DI overrides in tests.

## Changed
- **Orchestration**: Refactored `POST /api/v1/documents` to trigger both ingestion and indexing.
- **Chunk IDs**: Implemented deterministic SHA-256-based chunk IDs instead of random UUIDs to ensure idempotency.
- **Service Injection**: Refactored `DocumentIndexingService`, `RetrievalService`, and `RAGService` to use strict constructor dependency injection without hidden defaults.
- **Dependency Loading**: The API endpoints now correctly load services using FastAPI's `Depends()`.

---

# [v0.2.1] — Repository Professionalization & Documentation Synchronization

**Date:** 2026-09-17
**Related Commits:** `1b9832f`, `a67fb7f`, `d09b855`

## Changed

### Repository Hygiene
- Added `tests/conftest.py` to enforce in-memory ChromaDB during all test runs, preventing generation of `.chroma_data` runtime data in the project root.
- Removed pre-existing `.chroma_data` directory from the project root.

### Documentation Synchronization
- Rewrote `README.md` as an accurate, professional project landing page. Clearly separated current from planned technologies.
- Updated `docs/Product-Roadmap.md` (v1.1): Marked v0.1, v0.2, and core v0.3 as Complete. Positioned v1.0 as the next milestone. Clarified that PDF/DOCX/Markdown ingestion remains a v1.0 deliverable.
- Updated `docs/Research-Roadmap.md` (v1.1): Added a research infrastructure status note. Updated research themes table with a status column. Clarified that all baselines are "Not Yet Evaluated".
- Updated `docs/Benchmarking.md` (v1.1): Added explicit notice that no benchmarks have been executed. Marked evaluation tools as planned. Updated the version benchmark table to reflect the actual baseline state.
- Updated `docs/Architecture.md` (v1.1): Fixed the high-level system diagram to accurately show implemented vs. planned layers. Updated Frontend, Memory System, Knowledge Layer, and Evaluation Layer sections as planned. Corrected stale "future stages" notes in the implemented Vector Storage and Retrieval sections.
- Created `docs/API-Reference.md`: Full documentation of all implemented endpoints (`GET /health`, `GET /ready`, `POST /api/v1/documents`, `POST /api/v1/retrieval/search`, `POST /api/v1/rag/answer`, `POST /api/v1/llm/generate`), verified against actual Pydantic schemas.
- Updated folder `README.md` files for `frontend/`, `research/`, `benchmarks/`, `evaluation/`, `datasets/`, `examples/`, `paper/` to accurately describe their planned status.

---

# v0.2.0 — Backend Foundation

**Release Date:** 2026-08-23
**Related Commits:** `1bfecd2`, `40f46b7`, `a454978`, `53f1faa`, `86a3576`, `40808f4`

## Added

### Language Model Application Service
- Provider-agnostic LLM message, request, and response contract
- Application-facing LLM Service above the existing LLM Manager
- Versioned generate endpoint: `POST /api/v1/llm/generate`

### Document Ingestion Foundation
- Normalized internal Document model
- Upload validation and a parser registry
- UTF-8 `.txt` parser
- Versioned upload endpoint: `POST /api/v1/documents`
- `DocumentIndexingService` orchestration for chunking, embedding, and vector storage

### Chunking & Segmentation Foundation
- `Chunk` data model for segmented text
- Configurable `CHUNK_SIZE` and `CHUNK_OVERLAP` settings
- `FixedSizeChunker` for deterministic character chunking
- `ChunkingService` to abstract chunking strategies

### Embedding Foundation
- `Embedding` data model for normalized vectors
- `EmbeddingManager` and `EmbeddingProvider` abstractions
- `OpenAIEmbeddingProvider` adapter
- `EmbeddingService` for converting chunks to embeddings

### Vector Storage Foundation
- `StoredVector` model for normalized database records
- `VectorStoreManager` and `VectorStoreProvider` abstractions
- `ChromaVectorStoreProvider` adapter mapping generic operations to ChromaDB
- `VectorStoreService` for storing embeddings generated by the embedding service

### Retrieval Foundation
- `RetrievalQuery` and `RetrievedChunk` models
- Vector store similarity search support (`VectorSearchResult`)
- `RetrievalService` coordinating embedding and vector search
- FastAPI `/api/v1/retrieval/search` endpoint

### RAG Generation Foundation
- `RAGRequest`, `ContextItem`, and `RAGResponse` models
- `ContextBuilder` for deterministic prompt assembly from chunks
- `RAGService` orchestrating the retrieval and LLM stages with empty-context handling
- FastAPI `/api/v1/rag/answer` endpoint with full provenance tracking

---

# v0.1.0 — Project Foundation

**Release Date:** 2026-07-19
**Related Commits:** `bde42e2`, `095cf64`, `2ad1d95`

## Added

### Repository
- Repository initialized
- MIT License
- Standard directory structure
- GitHub configuration

### Documentation
- README
- Vision
- Product Roadmap
- Research Roadmap
- Architecture
- Software Requirements Specification
- Benchmarking Framework
- Development Workflow
- Changelog

### Planning
- Version roadmap
- Research roadmap
- Architectural blueprint
- Benchmark methodology

---

## Planned (Historical v0.1 View)

- FastAPI backend
- Configuration management
- Logging infrastructure
- Docker support
- Continuous Integration
- Testing framework

---

# Release Guidelines

Each release should include:

- Version number
- Release date
- Summary of major changes
- Updated documentation
- Benchmark results (where applicable)
- Updated dependencies
- Known issues (if applicable)

Release notes should focus on changes that are meaningful to users and contributors.

---

# Document Governance

| Item | Value |
|------|-------|
| Document Owner | Project Maintainer |
| Project | Knowledge Intelligence Platform |
| Document Version | 3.0 |
| Project Version | v1.3.0 |
| Status | Active Changelog |
| Last Reviewed | 2026-10-15 |

## Review Policy

The Changelog should be updated for every released version of the project. Historical entries should remain immutable to preserve an accurate record of the project's evolution.
