# Backend

This directory contains the FastAPI backend and AI service layer for the Knowledge Intelligence Platform (KIP).

## Current Responsibilities (v1.3.0)

- **REST API & Routing:** FastAPI application with versioned endpoints under `/api/v1` (`/documents`, `/retrieval/search`, `/rag/answer`, `/llm/generate`, `/feedback`, `/health`, `/ready`).
- **Multi-Tenancy:** Workspace-scoped vector search, document indexing, search cache isolation, and quotas via `X-KIP-Workspace-ID` header.
- **In-Memory Caching:** Thread-safe, memory-bounded LRU caches for semantic searches (`SearchCache`) and text embeddings (`EmbeddingCache`) with workspace-scoped cache invalidation on document ingestion.
- **Concurrency & Offloading:** Async thread-pool offloading (`run_blocking`) for synchronous, blocking embedding and vector database network operations.
- **Timeout Management & Error Mapping:** Per-provider timeouts (`EMBEDDING_TIMEOUT_SECONDS`, `QDRANT_TIMEOUT_SECONDS`, `LLM_TIMEOUT_SECONDS`) with mapping to HTTP 504 Gateway Timeout.
- **Document Ingestion:** Multi-format parser engine supporting `.txt`, `.md`, `.pdf`, and `.docx` with deterministic SHA-256 deduplication, idempotent indexing, and automatic search cache invalidation.
- **Chunking Subsystem:** Configurable character-based sliding-window chunker (`FixedSizeChunker`) producing deterministic chunk identities.
- **Embedding Generation:** Pluggable embedding providers supporting Google Gemini (`text-embedding-004` / `gemini-embedding-2` with 1:1 Content/Part batching, 768-d) and OpenAI (`text-embedding-3-small`, 1536-d), with cached vector lookups.
- **Vector Storage:** Pluggable vector store layer supporting Qdrant Cloud (serverless cluster with payload filtering and UUID5 point IDs) and local persistent ChromaDB.
- **Retrieval & RAG Pipeline:** Semantic similarity retrieval, Top-K empty vs zero-doc failure classification, prompt assembly, grounded response generation, and structured latency telemetry.
- **LLM Service:** Dual provider support for Google Gemini (`gemini-2.5-flash`) and OpenAI (`gpt-4o-mini`).
- **User Feedback Pipeline:** Validation and authenticated HTTPS GET webhook transport forwarding user ratings to Google Apps Script (`doGet`) and Google Sheets.
- **Configuration & Logging:** Pydantic `BaseSettings` loading from environment variables with structured logging, execution timers, and defensive error handling.

## Development Milestone

- **v0.2:** Initial backend skeleton, health probes, and plain-text document ingestion.
- **v0.3:** Core RAG foundation: chunking, embedding abstraction, Chroma vector store, semantic search, and RAG prompt assembly.
- **v1.0:** Productization: multi-format parsers (.txt, .md, .pdf, .docx), Gemini provider integration, mechanical evaluation harness, Streamlit UI.
- **v1.1:** Multi-tenant workspace isolation, Qdrant Cloud vector storage, Gemini batching fix, workspace quotas, Streamlit public UX, authenticated GET feedback persistence.
- **v1.2:** Retrieval research cycle: evaluated 5 candidate techniques against 50-doc/80-case expanded benchmark; dense whole-document baseline retained.
- **v1.3 (Current):** Performance engineering: in-memory thread-safe LRU caching, thread-pool offloading, timeout enforcement (HTTP 504), and latency telemetry. All 396 tests passing.

## Related Documentation

- [Architecture](../docs/Architecture.md)
- [API Reference](../docs/API-Reference.md)
- [Deployment Guide](../docs/deployment.md)
- [Product Roadmap](../docs/Product-Roadmap.md)
- [Project History](../docs/PROJECT_HISTORY.md)
- [Current Status](../docs/CURRENT_STATUS.md)
