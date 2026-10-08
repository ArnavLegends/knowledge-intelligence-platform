# Backend

This directory contains the FastAPI backend and AI service layer for the Knowledge Intelligence Platform (KIP).

## Current Responsibilities (v1.1.0)

- **REST API & Routing:** FastAPI application with versioned endpoints under `/api/v1` (`/documents`, `/retrieval/search`, `/rag/answer`, `/llm/generate`, `/feedback`, `/health`, `/ready`).
- **Multi-Tenancy:** Workspace-scoped vector search, document indexing, and quotas via `X-KIP-Workspace-ID` header.
- **Document Ingestion:** Multi-format parser engine supporting `.txt`, `.md`, `.pdf`, and `.docx` with deterministic SHA-256 deduplication and idempotent indexing.
- **Chunking Subsystem:** Configurable character-based sliding-window chunker (`FixedSizeChunker`) producing deterministic chunk identities.
- **Embedding Generation:** Pluggable embedding providers supporting Google Gemini (`text-embedding-004` / `gemini-embedding-2` with 1:1 Content/Part batching, 768-d) and OpenAI (`text-embedding-3-small`, 1536-d).
- **Vector Storage:** Pluggable vector store layer supporting Qdrant Cloud (serverless cluster with payload filtering and UUID5 point IDs) and local persistent ChromaDB.
- **Retrieval & RAG Pipeline:** Semantic similarity retrieval, Top-K empty vs zero-doc failure classification, prompt assembly, and grounded response generation.
- **LLM Service:** Dual provider support for Google Gemini (`gemini-2.5-flash`) and OpenAI (`gpt-4o-mini`).
- **User Feedback Pipeline:** Validation and authenticated HTTPS GET webhook transport forwarding user ratings to Google Apps Script (`doGet`) and Google Sheets.
- **Configuration & Logging:** Pydantic `BaseSettings` loading from environment variables with structured logging and defensive error handling.

## Development Milestone

- **v0.2:** Initial backend skeleton, health probes, and plain-text document ingestion.
- **v0.3:** Core RAG foundation: chunking, embedding abstraction, Chroma vector store, semantic search, and RAG prompt assembly.
- **v1.0:** Productization: multi-format parsers (.txt, .md, .pdf, .docx), Gemini provider integration, mechanical evaluation harness, Streamlit UI.
- **v1.1 (Current / Frozen):** Multi-tenant workspace isolation, Qdrant Cloud vector storage, Gemini batching fix, workspace quotas, Streamlit public UX, authenticated GET feedback persistence.

## Related Documentation

- [Architecture](../docs/Architecture.md)
- [API Reference](../docs/API-Reference.md)
- [Deployment Guide](../docs/deployment.md)
- [Product Roadmap](../docs/Product-Roadmap.md)
- [Project History](../docs/PROJECT_HISTORY.md)
- [Current Status](../docs/CURRENT_STATUS.md)
