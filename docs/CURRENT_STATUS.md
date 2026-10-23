# KIP Current Status (v1.4.0)

**Document Version:** 1.4  
**Project Version:** v1.4.0  
**Status:** Canonical System State  
**Last Updated:** 2026-10-23  

---

## 1. Executive Summary

Knowledge Intelligence Platform (KIP) v1.4.0 is a multi-tenant RAG (Retrieval-Augmented Generation) platform engineered with enterprise-grade security, document lifecycle management, and runtime reliability. v1.4 adds: workspace token hashing with constant-time verification and immediate revocation, a disabled-by-default LLM generation endpoint, RAG prompt-injection hardening, atomic document persistence with fsync-safe writes and traversal protection, SQLite-backed document metadata and version tracking, lifecycle-aware RAG filtering (active-doc-only evidence), on-demand document reindexing from retained source files, hardened filename validation (null-byte/control-char rejection, 255-byte ceiling), `FixedSizeChunker` whitespace-safety, chunk deduplication in context assembly, human-readable filename citations (`ContextItem.filename`), and latency telemetry in `RAGResponse` (`retrieve_ms`, `generate_ms`). Prior v1.3 capabilities — thread-pool offloading, LRU caching, deadline-enforced HTTP 504 responses, and structured latency logging — are fully preserved.

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
  - Frozen Dense Baseline (80 cases, 50 docs): MRR: 0.7623, Hit@1: 0.6875, Hit@3: 0.8375, Hit@5: 0.8750, P95 retrieval latency: 643.0 ms.
  - v1.2 Research Outcomes (Strict Population Separation):
    - Input-Formatting Pilot (18 docs, 25 labelled cases): Evaluated asymmetric prompt prefixes; neutral MRR change (0.9133 vs 0.9133 control, Δ = +0.0000; mean retrieval latency 536.5 ms).
    - Expanded Benchmark Treatments (50 docs, 80 labelled cases): Evaluated cross-encoder reranking (MRR 0.7762, end-to-end P95 latency 1,691.5 ms), hybrid BM25+dense RRF (MRR 0.7094, end-to-end P95 latency 618.9 ms), sentence-boundary chunking (MRR 0.7471, retrieval P95 latency 618.6 ms), and context optimization (MRR 0.7542, optimization-stage P95 latency 0.042 ms). All four candidate treatments failed preregistered targets (MRR ≥ 0.8200) or safety invariants (MRR range 0.7094–0.7762 applies strictly to these four treatments); dense whole-document retrieval is retained as the production default.
  - Metric Auditor: `evaluation/validate_benchmark_metrics.py` verifying artifact integrity and zero mathematical drift.

---

## 4. Test Suite Metrics

- **Total Test Count:** ~380 automated tests (excluding heavy evaluation and cache benchmarks)
- **Passing Rate:** 100% across all non-integration tests
- **Subsystem Breakdown:**
  - Stage A Security (`tests/test_stage_a_security.py`): Workspace token hashing, LLM endpoint protection, prompt injection
  - Stage B Persistence (`tests/test_stage_b_persistence.py`): Atomic storage, versioning, replacement, lifecycle filtering
  - Stage C Reliability (`tests/test_stage_c_reliability.py`): Filename validation, parser safety, chunker robustness
  - Caching & Performance (`tests/test_cache.py`, `tests/test_cache_benchmark.py`, `tests/test_async_executor.py`): 72 tests
  - Benchmark Auditing (`tests/test_benchmark_audit.py`): 8 tests
  - Backend API endpoints: 45+ tests
  - RAG Core (Chunking, Embeddings, Vector Store, LLM, Retrieval): 135 tests
  - Ingestion (PDF, DOCX, TXT, MD, Multi-Document, Workspaces): 62 tests
  - Workspace & Multi-Tenancy: 31 tests
  - Evaluation & Configuration: 44 tests

---

## 5. Explicitly Deferred Capabilities & Roadmap Status

The following capabilities are positioned on the forward-looking roadmap:

- **v1.2 (Retrieval Intelligence):** Research complete. Dense whole-document retrieval baseline retained as production default.
- **v1.3 (Performance Engineering):** Complete. Zero-cost thread-safe LRU caching, async thread-pool offloading, timeout enforcement with HTTP 504 handling, structured latency telemetry.
- **v1.4 (Security-First Engineering Revamp):** **Complete.** Workspace token security, document persistence & lifecycle, runtime reliability hardening, RAG citation enrichment, benchmark data integrity fixes.
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
5. **Workload and Concurrency Validation Guardrail:** While thread-pool executor offloading (`max_workers=4`) prevents blocking FastAPI's async event loop, a configured worker ceiling is not evidence of unbounded queueing capacity or high-concurrency production throughput. Realistic multi-tenant workload testing and saturation profiling remain intentionally scheduled for the v1.7 development checkpoint (~50–60% mark). Do not extrapolate 397 passing tests to mean production-scale reliability.

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
