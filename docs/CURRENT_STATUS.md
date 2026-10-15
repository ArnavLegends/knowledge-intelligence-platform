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
| **Async Offloading** | Process ThreadPoolExecutor | In-process (`app.core.async_executor`) | Bounded 4 workers, wall-clock timeout protection & HTTP 504 mapping |
| **In-Memory Caching** | Thread-safe LRU Cache | In-process (`app.services.cache`) | EmbeddingCache (256 cap) + SearchCache (256 cap, 60s TTL, auto-evict) |
| **Frontend UI** | Streamlit | Streamlit Community Cloud | Multi-tenancy UI, provenance inspector, feedback box |
| **Feedback Persistence** | Google Apps Script (`doGet()`) + Google Sheets | Google Workspace | Authenticated HTTPS GET webhook with automatic redirect handling |
| **Document Parsers** | PyPDF, python-docx, UTF-8 text parser | In-process | PDF, DOCX, TXT, MD support |

---

## 3. Implemented Capabilities (v1.3 System Reality)

- **Multi-Tenant Workspaces:**
  - Dynamic workspace access token creation (`wksp_...`)
  - Workspace scoping via `X-KIP-Workspace-ID` header and Qdrant payload filtering (`workspace_id` match)
  - Strict tenant isolation across document indexing, vector retrieval, and question-answering
  - Complete UI state reset on workspace creation or switching

- **In-Memory Caching Layer (Zero Infrastructure Cost):**
  - `LRUCache`: Thread-safe generic LRU container using `collections.OrderedDict` + `threading.RLock`.
  - `EmbeddingCache`: SHA-256 keyed cache reducing repeated query embedding latency to ~0.01 ms (100% provider call reduction).
  - `SearchCache`: Multi-tenant, TTL-backed vector search cache with workspace and document eviction hooks triggered during document indexing and deletion.

- **Async Concurrency & Timeout Resilience:**
  - `run_blocking` (`app.core.async_executor`): Bounded `ThreadPoolExecutor` offloading blocking embedding, vector search, and LLM calls from FastAPI's async event loop.
  - Endpoint-level wall-clock timeout budgets translating hung upstream calls directly to HTTP 504 Gateway Timeout.
  - Process-level thread pool lifecycle shutdown wired into application `lifespan`.

- **Production Latency Telemetry:**
  - Structured wall-clock performance instrumentation (`embed_ms`, `search_ms`, `total_ms`) and cache hits/misses logged at `INFO` level without logging user queries or PII.

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

- **Ground-Truth Evaluation Harness & Research Datasets:**
  - Datasets: `benchmarks/kip_v1_baseline.json` (v1.0 historical, 5 cases), `benchmarks/kip_v1_1_baseline.json` (7 cases), `benchmarks/kip_v1_2_benchmark.json` (25 cases pilot), `benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json` (50 docs, 80 cases across 6 categories).
  - Frozen Dense Baseline: MRR: 0.7623, Hit@1: 0.6875, Hit@3: 0.8375, Hit@5: 0.8750.
  - v1.2 Research Outcomes: 5 candidate techniques evaluated (input formatting, cross-encoder reranking, hybrid BM25+dense retrieval, sentence-boundary chunking, context optimization). All candidate techniques rejected; dense whole-document retrieval retained as production default.
  - Metric Auditor: `evaluation/validate_benchmark_metrics.py` verifying artifact integrity and zero mathematical drift.

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

- **v1.2 (Retrieval Intelligence):** Research complete. Dense whole-document retrieval baseline retained as production default.
- **v1.3 (Performance Engineering):** Complete. Zero-cost thread-safe LRU caching (embedding & search), async thread-pool offloading, timeout enforcement with HTTP 504 handling, and structured latency telemetry.
- **v1.4 (Knowledge Workspace & Evidence Trust):** Proposed / next milestone focusing on document management, error feedback, evidence inspection, and conditional document deletion.
- **v1.5 (Retrieval Generalization & Answer Quality):** Proposed milestone evaluating dense retrieval on an independent secondary corpus and auditing grounding/abstention.
- **v1.6 (Evidence-Grounded Knowledge Workflows):** Proposed milestone for bounded comparison and evidence briefing workflows.
- **v1.7 (Operational Validation & Reliability):** Proposed milestone for realistic concurrency, memory, and cold-start profiling at the ~50–60% development checkpoint.
- **v1.8 (Reproducible Release & Technical Case Study):** Proposed release packaging and formal feature freeze.
- **v2.x–v4.x (Conditional Explorations):** Conversational memory (v2.0), controlled tool-use (v2.1), bounded agents (v2.2), knowledge intelligence (v2.3), knowledge graphs (v2.4), multimodal (v3.0), collaboration (v3.1), cloud scale (v3.2), enterprise platform (v4.0). These remain conditional on concrete user need and demonstrated value.

---

## 6. Known Operational Characteristics & Limitations

1. **Free Tier Cold Starts:** Render and Google Apps Script may exhibit cold start latencies (30–60s on Render, 2–4s on Apps Script) after periods of inactivity.
2. **Synchronous Chunk Embedding:** Document ingestion is synchronous per upload batch; very large documents (>50 pages) should be split or indexed with patience on free-tier rate limits.
3. **Apps Script Redirects:** Google Apps Script web apps return HTTP 302 redirects to `script.googleusercontent.com`. The KIP backend dispatches requests via `requests.get()`, which follows HTTP redirects automatically by default.
4. **Single-Node In-Memory Workspace Session:** Streamlit manages workspace credentials in browser session state; closing the browser requires reconnecting via the workspace access token.
5. **Workload and Concurrency Validation Guardrail:** While thread-pool executor offloading (`max_workers=4`) prevents blocking FastAPI's async event loop, a configured worker ceiling is not evidence of unbounded queueing capacity or high-concurrency production throughput. Realistic multi-tenant workload testing and saturation profiling remain intentionally scheduled for the v1.7 development checkpoint (~50–60% mark). Do not extrapolate 396 passing tests to mean production-scale reliability.

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
