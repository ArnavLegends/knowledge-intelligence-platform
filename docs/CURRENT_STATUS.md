# KIP Current Status (v1.3.0)

**Document Version:** 1.3  
**Project Version:** v1.3.0  
**Status:** Canonical System State  
**Last Updated:** 2026-10-15  

---

## 1. Executive Summary

Knowledge Intelligence Platform (KIP) v1.3.0 is a zero-cost, multi-tenant RAG (Retrieval-Augmented Generation) platform engineered for low latency, event-loop concurrency, and bounded resource consumption. It provides document ingestion across four file formats (PDF, DOCX, TXT, MD), semantic vector search with backend-validated, workspace-scoped Qdrant filtering, grounded question-answering with strict citations and provenance, an interactive Streamlit UI, authenticated feedback collection persisted to Google Sheets, zero-cost thread-safe in-memory LRU caching (embedding and search), bounded thread-pool executor offloading (`run_blocking`), deadline timeout enforcement with HTTP 504 mapping, and structured wall-clock latency telemetry.

---

## 2. Active System Architecture

| Component | Technology | Provider / Environment | Configuration / Specs |
|-----------|------------|------------------------|----------------------|
| **LLM Provider** | Gemini 2.5 Flash (`gemini-2.5-flash`) | Google AI Studio | Free tier, grounded response generation |
| **Embeddings** | Gemini Embedding 2 (`gemini-embedding-2`) | Google AI Studio | 768 dimensions, raw-text default with optional formatter hooks |
| **Vector Database** | Qdrant Cloud Managed | Qdrant Cloud Free Tier | Collection `knowledge_base`, Cosine distance, 768 dims |
| **Backend API** | FastAPI + Uvicorn | Render Free Web Service | Python 3.11, auto-reload dev / single worker prod |
| **Frontend UI** | Streamlit | Streamlit Community Cloud | Multi-tenancy UI, provenance inspector, feedback box |
| **Feedback Persistence** | Google Apps Script (`doGet()`) + Google Sheets | Google Workspace | Authenticated HTTPS GET webhook with automatic redirect handling |
| **Document Parsers** | PyPDF, python-docx, UTF-8 text parser | In-process | PDF, DOCX, TXT, MD support |

---

## 3. Implemented Capabilities (v1.1.0 & v1.2 Research Preparation)

- **Multi-Tenant Workspaces:**
  - Dynamic workspace access token creation (`wksp_...`)
  - Workspace scoping via `X-KIP-Workspace-ID` header and Qdrant payload filtering (`workspace_id` match)
  - Strict tenant isolation across document indexing, vector retrieval, and question-answering
  - Complete UI state reset on workspace creation or switching

- **Multi-Format Ingestion:**
  - File upload via API (`POST /api/v1/documents`) and Streamlit UI
  - Formats: PDF, DOCX, TXT, Markdown
  - Configurable chunking (default 1000 chars, 200 chars overlap)
  - Batch embedding generation via Gemini API (`gemini-embedding-2`, 768 dims)
  - Vector indexing into Qdrant Cloud

- **Grounded Retrieval & QA:**
  - Query embedding generation via Gemini (`gemini-embedding-2`)
  - Filtered top-$k$ vector similarity search in Qdrant (scoped to tenant workspace)
  - Strict grounding prompt: refuses queries lacking context support
  - Provenance attribution: returns chunk content, document names, scores, and chunk indices
  - Interactive provenance viewer in Streamlit UI

- **User Feedback Collection:**
  - In-app user feedback submission in Streamlit UI (category selection and free-text message with a 30-word limit, optional workspace ID)
  - Backend API validation (`POST /api/v1/feedback`)
  - Transport to Google Apps Script via authenticated HTTPS GET (`doGet()`) using `requests.get()` with automatic HTTP 302 redirect handling
  - Automatic append to Google Sheets for evaluation and review

- **Ground-Truth Evaluation Harness & Controlled Experimentation:**
  - Datasets: `benchmarks/kip_v1_baseline.json` (v1.0 historical), `benchmarks/kip_v1_1_baseline.json` (7 cases, SHA-256 ground truth), `benchmarks/kip_v1_2_benchmark.json` (25 cases, chunk-level ground truth)
  - Reference Corpora: `benchmarks/corpus/` (3 baseline docs) and `benchmarks/corpus_v1_2/` (18 docs, including 4 adversarial distractors)
  - Harness: `evaluation/runner.py` and `evaluation/models.py` supporting fine-grained Hit Rate@1, Hit Rate@3, Hit Rate@5, MRR, latency profiling, and pure retrieval evaluation
  - Formatting Hooks: Provider-neutral `doc_formatter` in `EmbeddingService` and `query_formatter` in `RetrievalService`
  - Canonical Baseline: Live Gemini + Qdrant baseline verified (`benchmarks/kip_v1_1_baseline_result.json`, MRR 0.9048)
  - Controlled Experiment: Asymmetric input-formatting experiment completed (`benchmarks/kip_v1_2_formatting_control_20261014_094111.json`, `benchmarks/kip_v1_2_formatting_treatment_20261014_094111.json`). Both control and treatment achieved Hit Rate@1: 0.8400, Hit Rate@3/5: 1.0000, MRR: 0.9133 on the 25-case benchmark. Raw-text embedding retained as production default.

---

## 4. Test Suite Metrics

- **Total Test Count:** 396 automated tests
- **Passing Rate:** 100% (396/396 passing)
- **Subsystem Breakdown:**
  - Caching & Performance (`tests/test_cache.py`, `tests/test_cache_benchmark.py`, `tests/test_async_executor.py`): 72 tests
  - Benchmark Auditing & Historical Verification (`tests/test_benchmark_audit.py`): 8 tests
  - Backend API endpoints (`tests/test_api.py`, `tests/test_feedback_api.py`, `tests/test_retrieval_api.py`, `tests/test_rag_api.py`, `tests/test_documents_api.py`): 45 tests
  - RAG Core (Chunking, Embeddings, Vector Store, LLM, Retrieval): 135 tests
  - Ingestion (PDF, DOCX, TXT, MD, Multi-Document, Workspaces): 62 tests
  - Workspace & Multi-Tenancy (Scoping, Isolation, Token Management): 31 tests
  - Evaluation & Configuration (Settings, Validation, Runners, v1.2 Formatter Hooks & Metrics): 43 tests

---

## 5. Explicitly Deferred Capabilities & Roadmap Status

The following capabilities are positioned on the forward-looking roadmap:

- **v1.2 (Retrieval Intelligence):** Research complete. Dense retrieval baseline retained.
- **v1.3 (Performance Engineering):** Complete. Zero-cost thread-safe LRU caching (embedding & search), async thread-pool offloading, timeout enforcement with HTTP 504 handling, and structured latency telemetry.
- **v2.0 (AI Memory):** Persistent multi-turn conversation memory, session stores, user personalization.
- **v2.1 (Tool Integration):** External tool calling, calculator, web search execution.
- **v2.2 (Agentic AI):** Autonomous multi-step planning, LangGraph/CrewAI agents.
- **v2.4 (Knowledge Graphs):** Neo4j graph integration, entity extraction.
- **v3.0+ (Enterprise Platform):** RBAC authentication, Kubernetes, PostgreSQL relational storage, React/Next.js frontend.

---

## 6. Known Operational Characteristics & Limitations

1. **Free Tier Cold Starts:** Render and Google Apps Script may exhibit cold start latencies (30–60s on Render, 2–4s on Apps Script) after periods of inactivity.
2. **Synchronous Chunk Embedding:** Document ingestion is synchronous per upload batch; very large documents (>50 pages) should be split or indexed with patience on free-tier rate limits.
3. **Apps Script Redirects:** Google Apps Script web apps return HTTP 302 redirects to `script.googleusercontent.com`. The KIP backend dispatches requests via `requests.get()`, which follows HTTP redirects automatically by default.
4. **Single-Node In-Memory Workspace Session:** Streamlit manages workspace credentials in browser session state; closing the browser requires reconnecting via the workspace access token.

---

## 7. Documentation Index

- [README.md](../README.md) — Main repository overview, quickstart, and cloud topology
- [PROJECT_HISTORY.md](PROJECT_HISTORY.md) — Comprehensive engineering chronology and commit record
- [Changelog.md](Changelog.md) — Chronological release notes and changes
- [Architecture.md](Architecture.md) — System architecture, security, and component design
- [API-Reference.md](API-Reference.md) — Complete REST API specifications
- [Product-Roadmap.md](Product-Roadmap.md) — Long-term product roadmap and version milestones
- [Research-Roadmap.md](Research-Roadmap.md) — Systematic research framework and experiment plans
- [deployment.md](deployment.md) — Cloud deployment guide (Render, Qdrant Cloud, Streamlit Cloud, Google Sheets)
- [Benchmarking.md](Benchmarking.md) — Benchmarking methodologies and evaluation results
