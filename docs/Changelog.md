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

For a detailed commit-by-commit engineering narrative explaining the evolutionary rationale of each milestone, see [PROJECT_HISTORY.md](file:///c:/Users/arun/OneDrive/Desktop/knowledge-intelligence-platform/docs/PROJECT_HISTORY.md).

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

## [Unreleased]

- Planned v1.2 Retrieval Intelligence & Evaluation research experiments (literature review, chunking experiments, hybrid search evaluation).

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
| Document Version | 2.0 |
| Project Version | v1.1.0 (Feature Frozen) |
| Status | Active Changelog |
| Last Reviewed | 2026-10-08 |

## Review Policy

The Changelog should be updated for every released version of the project. Historical entries should remain immutable to preserve an accurate record of the project's evolution.