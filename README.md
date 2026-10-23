# Knowledge Intelligence Platform (KIP)

> A modular AI Knowledge Intelligence Platform for Retrieval-Augmented Generation (RAG) with multi-tenant cloud storage, reproducible evaluation, and free-tier cloud deployment.

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version: 1.4.0](https://img.shields.io/badge/version-1.4.0-green.svg)](https://github.com/ArnavLegends/knowledge-intelligence-platform)
[![CI](https://github.com/ArnavLegends/knowledge-intelligence-platform/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ArnavLegends/knowledge-intelligence-platform/actions/workflows/ci.yml)

---

## 1. Overview

The **Knowledge Intelligence Platform (KIP)** is a robust, production-oriented knowledge assistant capable of retrieving, understanding, and synthesizing information from uploaded documents.

Designed with modern AI engineering practices, KIP implements a complete FastAPI-based Retrieval-Augmented Generation (RAG) backend engine, a Streamlit frontend, and a multi-tenant vector storage architecture supporting both local development and free-tier cloud deployments.

The `/api/v1/rag/answer` endpoint synthesizes answers from retrieved passages with explicit provenance tracking back to original source documents and chunk ranks. When questions cannot be answered from the uploaded knowledge base, KIP's prompt instructs the model to decline; however, while citations indicate retrieved evidence, citations do not guarantee absolute factual correctness. The separate `/api/v1/llm/generate` endpoint is **disabled by default** (returns HTTP 403) and requires an admin key to enable.

### Quick Navigation
| Question / Goal | Location |
|---|---|
| **What does KIP do & what is implemented?** | [Implemented Capabilities (v1.3 Reality)](#implemented-capabilities-v13-reality) & [CURRENT_STATUS.md](docs/CURRENT_STATUS.md) |
| **How do I run KIP locally?** | [Quick Start & Local Development](#13-quick-start--local-development) (`git clone` → `pip install` → `.env` → `run`) |
| **What empirical evidence backs retrieval claims?** | [v1.2 Research Outcomes](#10-evaluation-framework) & [Research Synthesis](docs/evaluation/v1.2_research_synthesis.md) |
| **Where are the architecture & REST APIs?** | [High-Level Architecture](#3-architecture), [REST API Quick Reference](#15-api-quick-reference), [deployment.md](docs/deployment.md) |
| **Where are the project history & future roadmap?** | [PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md), [Product-Roadmap.md](docs/Product-Roadmap.md), [Research-Roadmap.md](docs/Research-Roadmap.md) |

---

## 2. Current Project Status: v1.4.0 — Security-First Engineering Revamp

The repository provides a complete, production-oriented RAG application currently at version **v1.4.0**:

- **Completed Milestones**:
  - **v1.1**: Multi-Tenant Cloud Knowledge Layer (bearer tokens, Qdrant Cloud, Render deployment, Google Sheets feedback)
  - **v1.2**: Retrieval Intelligence Research (5 candidate techniques evaluated across 18-doc pilot and 50-doc/80-case expanded benchmark; dense baseline retained)
  - **v1.3**: Performance Engineering (in-memory LRU caching, thread-pool offloading, timeout enforcement, structured latency telemetry)
  - **v1.4**: Security-First Engineering Revamp (workspace token hashing, document persistence & lifecycle, runtime reliability hardening, RAG citation enrichment)
- **Current Milestone**: [v1.5 Retrieval Generalization & Answer Quality](docs/Product-Roadmap.md)

### Implemented Capabilities (v1.4 Reality)
- **Multi-Tenant Workspaces**: Cryptographically secure, bearer-token workspace isolation (`X-KIP-Workspace-ID`). Every document, chunk, and retrieval operation is strictly workspace-scoped.
- **In-Memory Caching Layer (Zero Infrastructure Cost)**:
  - Thread-safe generic LRU cache (`LRUCache`) using `collections.OrderedDict` + `threading.RLock`.
  - `EmbeddingCache`: SHA-256 keyed cache reducing repeated query embedding latency to ~0.01 ms (100% provider call reduction).
  - `SearchCache`: Multi-tenant, TTL-backed vector search cache with workspace and document eviction hooks triggered during document indexing and deletion.
- **Async Concurrency & Thread-Pool Offloading**:
  - `run_blocking` (`app.core.async_executor`): Bounded `ThreadPoolExecutor` offloading blocking embedding, vector store, and LLM calls from FastAPI's async event loop.
  - Process-level thread pool lifecycle shutdown wired into application `lifespan`.
- **Timeout Protection & HTTP 504 Mapping**:
  - Enforced wall-clock timeout budgets on retrieval and RAG endpoints, preventing worker exhaustion from hung upstream API calls.
- **Production Observability**:
  - Structured wall-clock performance instrumentation (`embed_ms`, `search_ms`, `total_ms`) and cache hits/misses logged at `INFO` level without logging user queries or PII.
- **Pluggable Vector Storage**:
  - **Qdrant Cloud**: Cloud-ready multitenant vector database with payload filtering and deterministic point UUIDs (`uuid5(NAMESPACE_URL, "kip://<workspace_id>/<chunk_id>")`).
  - **ChromaDB**: In-memory and local persistent vector database for fast development and testing.
- **Pluggable Embeddings**:
  - **Google Gemini**: `gemini-embedding-2` with 768 output dimensionality (supports batched chunk processing).
  - **OpenAI**: `text-embedding-3-small` / `text-embedding-3-large`.
- **Pluggable LLMs**: Google Gemini (`gemini-2.5-flash`) and OpenAI (`gpt-4o-mini`).
- **Document Ingestion**: Parsing for Plain Text (`.txt`), Markdown (`.md`, `.markdown`), Portable Document Format (`.pdf`), and Microsoft Word (`.docx`) files with content-hash idempotency.
- **Deterministic Identity**: SHA-256 content hashing for documents and chunks, ensuring idempotent uploads and stable vector references.
- **Semantic Retrieval**: Top-k similarity search (configurable 1–20) with distance thresholds and cross-tenant leakage protection.
- **REST APIs**: Full OpenAPI/Swagger documentation with workspace authentication headers.
- **Streamlit Frontend**: Multi-tenant UI with workspace creation, token resumption, multi-file upload progress tracking, document listing, grounded Q&A, and citation viewing.
- **Free-Tier Cloud Deployment**: Streamlit Community Cloud + Render Free FastAPI + Qdrant Free Cloud + Gemini Free Tier (subject to provider quotas and availability).
- **Public Feedback Pipeline**: Ingests user feedback via `POST /api/v1/feedback` and persists submissions directly to Google Sheets via authenticated HTTPS GET transport to Google Apps Script `doGet()`.
- **Evaluation Harness & Auditing**: Mechanical evaluation runner (`evaluation/runner.py`) and automated benchmark metric auditor (`evaluation/validate_benchmark_metrics.py`).

> **Explicit Scope Boundary**: KIP currently focuses on single-step grounded RAG, robust workspace multi-tenancy, and high-efficiency in-process performance. It does **not** currently implement autonomous agent workflows, conversational memory, knowledge graphs, multimodal OCR, React/Next.js frontend, Kubernetes, relational databases (PostgreSQL), or distributed caches (Redis). These capabilities are conditionally positioned on the forward-looking roadmap.

For a concise summary of the current system, see [CURRENT_STATUS.md](docs/CURRENT_STATUS.md). For the complete commit-by-commit engineering evolution, see [PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md).

---

## 3. Architecture

KIP follows a modular, layered architecture with strict separation of concerns:

```text
User / Browser
      │
      ▼
Streamlit Frontend (frontend/app.py)
      │
      │ HTTPS (X-KIP-Workspace-ID Header)
      ▼
FastAPI Backend (backend/app/main.py)
      ├── Async Executor Pool (ThreadPoolExecutor + Wall-Clock Timeouts)
      ├── In-Memory Caching Layer (EmbeddingCache + SearchCache)
      ├── Document Ingestion & Parsers (TXT, MD, PDF, DOCX)
      ├── Chunking Service (FixedSizeChunker + SHA-256 Chunk IDs)
      ├── Embedding Service (Gemini / OpenAI Provider Adapters)
      ├── Vector Store Service (Qdrant Cloud / ChromaDB)
      ├── Retrieval Service (Top-K Semantic Search + Payload Filter)
      ├── Context Builder (Deterministic Prompt Assembly)
      ├── LLM Service (Gemini / OpenAI Gateway)
      └── Feedback Service (Authenticated GET Transport)
            │
            ▼
      Google Apps Script (doGet) → Google Sheet
```

For complete architectural specifications, see [Architecture.md](docs/Architecture.md).

---

## 4. Supported Document Formats

KIP extracts text via an extensible `ParserRegistry` pattern:
- **Plain Text (`.txt`)**: Decoded directly via UTF-8.
- **Markdown (`.md`, `.markdown`)**: Decoded via UTF-8. Formatting is preserved as linear text.
- **PDF (`.pdf`)**: Extracted page-by-page via `pypdf`. Extracts embedded text layers.
- **Word (`.docx`)**: Extracted paragraph-by-paragraph via `python-docx`.

---

## 5. Retrieval & RAG Flow

1. **Ingestion & Indexing**:
   - Upload file → Check SHA-256 hash against workspace index.
   - If previously indexed, return existing metadata (`chunks_indexed=0`).
   - If new, segment text into chunks, generate embeddings, and store in vector storage scoped to the caller's workspace.
2. **Query & Retrieval**:
   - User submits a question with a Top-K preference (1–20).
   - Backend generates query embedding and queries the vector store with a strict `workspace_id == requested_workspace_id` payload filter.
3. **Context Assembly & Response Generation**:
   - Retrieved chunks are assembled into a structured prompt delimited from system instructions.
   - If no chunks pass retrieval thresholds, KIP returns an explicit empty-context fallback message.
   - When context exists, the LLM generates a grounded answer with ranked source citations.

---

## 6. LLM & Embedding Providers

KIP uses a provider abstraction layer to isolate third-party vendor SDKs:

| Provider | LLM Model | Embedding Model | Output Dimensions | Typical Use Case |
|---|---|---|---|---|
| **Google Gemini** | `gemini-2.5-flash` | `gemini-embedding-2` | 768 | Production zero-cost deployment |
| **OpenAI** | `gpt-4o-mini` | `text-embedding-3-small` | 1536 / 768 | High-throughput / OpenAI workloads |

Switching providers is purely configuration-driven via `LLM_PROVIDER` and `EMBEDDING_PROVIDER` environment variables.

---

## 7. Vector Storage: ChromaDB vs. Qdrant

KIP incorporates dual vector store support:
- **ChromaDB** (`VECTOR_STORE_PROVIDER=chroma`):
  - Used for local development and automated testing.
  - Test suites execute against an in-memory Chroma instance (`tests/conftest.py`), ensuring fast, isolated, disk-clean test runs.
- **Qdrant Cloud** (`VECTOR_STORE_PROVIDER=qdrant`):
  - Used for cloud deployments (Render).
  - Uses a single shared collection (`knowledge_base`) with indexed payload filtering by `workspace_id`.
  - Deterministic UUID5 point IDs (`uuid5(NAMESPACE_URL, "kip://<workspace_id>/<chunk_id>")`) guarantee point stability across server restarts.

---

## 8. Multi-Workspace Behavior

- **Workspace Token**: Every session is scoped by a high-entropy URL-safe token (e.g., generated via `secrets.token_urlsafe(32)`).
- **Mandatory Header**: All knowledge operations require `X-KIP-Workspace-ID: <token>`.
- **Tenant Isolation**: Document listings, indexing, retrieval, and RAG answers are strictly isolated to the caller's workspace. Cross-workspace data leakage is blocked at both API dependency and vector query filter layers.
- **Workspace Limits**: Free-tier safeguards enforce `MAX_DOCUMENTS_PER_WORKSPACE=50` and `MAX_CHUNKS_PER_WORKSPACE=1000`.

---

## 9. Deterministic Document & Chunk Identity

To guarantee idempotency and avoid duplicate vector generation:
- **Document ID**: `sha256(raw_file_content).hexdigest()`. Re-uploading identical file bytes produces the identical document ID.
- **Chunk ID**: `sha256(f"{doc_id}:{chunk_index}".encode()).hexdigest()`. Chunk identifiers remain immutable across indexing runs.
- **Qdrant Point ID**: `uuid5(NAMESPACE_URL, f"kip://{workspace_id}/{chunk_id}")`. Guarantees point uniqueness per workspace.

---

## 10. Evaluation Framework

KIP includes a deterministic evaluation harness and automated metric validation:
- **Runner**: `evaluation/runner.py` executes benchmark cases against retrieval and generation pipelines.
- **Auditor**: `evaluation/validate_benchmark_metrics.py` validates benchmark artifact integrity and ensures zero metric calculation drift across releases.
- **Benchmark Corpora**:
  - `benchmarks/corpus_v1_2/` & `benchmarks/corpus_v1_2_expanded/`: 50 documents (including adversarial distractors) and 80 labelled cases across six query categories.
- **Frozen Dense Baseline**: Evaluated live on Gemini `gemini-embedding-2` + Qdrant (`benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json`):
  - MRR: **0.7623** | Hit@1: **0.6875** | Hit@3: **0.8375** | Hit@5: **0.8750**
- **v1.2 Research Outcomes**: Across five evaluated candidate techniques in the v1.2 research cycle, none satisfied preregistered adoption criteria over the dense control baseline:
  - *Input Formatting Pilot* (18 documents, 25 labelled cases): Evaluated asymmetric prompt prefixes; yielded a neutral ranking outcome (MRR 0.9133, net change 0.0000).
  - *Expanded Benchmark Treatments* (50 documents, 80 labelled cases): Cross-encoder reranking, hybrid BM25+dense retrieval, sentence-boundary chunking, and context optimization were evaluated against the frozen dense baseline (MRR 0.7623, Hit@1 0.6875, Hit@3 0.8375, Hit@5 0.8750) and rejected under documented criteria. Dense whole-document retrieval is retained as the production standard.

---

## 11. Streamlit Frontend

The user interface (`frontend/app.py`) provides:
- **Workspace Management**: Generate a new workspace token or reconnect to an existing workspace.
- **Multi-File Uploads**: Upload multiple TXT, MD, PDF, or DOCX files with individual status badges.
- **Indexed Document Library**: Displays all documents indexed in the active workspace with chunk counts and media types.
- **Grounded Q&A**: Natural language question input with Top-K slider (1–20), rendering generated answers and cited sources.
- **Cold-Start Resilience**: Automatically detects Render free-tier sleep cycles and presents user-friendly status indicators while the container spins up.
- **Community Feedback**: In-app feedback box forwarding submissions to the feedback pipeline.

---

## 12. Deployment Architecture

KIP is architected for zero-cost ($0 / ₹0) operation leveraging available provider free tiers:

```text
Streamlit Community Cloud (frontend/app.py)
        │ HTTPS (KIP_API_BASE_URL)
        ▼
FastAPI on Render Free Tier (backend/app/main.py)
        ├── Qdrant Cloud Free Tier (knowledge_base collection)
        ├── Google Gemini API Free Tier (gemini-2.5-flash / gemini-embedding-2)
        └── Authenticated HTTPS GET ──> Google Apps Script (doGet) ──> Google Sheet
```

> **Free-Tier Operational Context**: KIP's cloud deployment runs entirely on free-tier allocations (Render Free FastAPI, Streamlit Community Cloud, Qdrant Cloud Free, Google Gemini Free Tier, and Google Apps Script). Operation is zero-cost within these tiers, subject to provider quotas, rate limits, sleep/cold-start behavior (e.g., Render 15-minute spin-down), and upstream provider pricing changes.

For step-by-step instructions, see [deployment.md](docs/deployment.md).

---

## 13. Quick Start & Local Development

### Prerequisites
- Python 3.11+
- Virtual environment (`venv`)

### Installation

```bash
git clone https://github.com/ArnavLegends/knowledge-intelligence-platform.git
cd knowledge-intelligence-platform

# Install dependencies (development mode)
pip install -e ".[dev]"
```

### Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
For local offline testing, default values work without third-party credentials. For live LLM or Qdrant usage, populate the respective API keys in `.env`.

### Running the Services

1. **FastAPI Backend**:
```bash
PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
API docs available at: `http://127.0.0.1:8000/docs`

2. **Streamlit Frontend**:
```bash
streamlit run frontend/app.py
```
UI available at: `http://localhost:8501`

---

## 14. Testing and Code Quality

The automated test suite runs offline and deterministically without cloud credentials:

- **Tests**: `pytest` (current suite: **397 passed** tests, 100% pass rate)
- **Coverage**: `pytest --cov=backend/app --cov-report=term-missing`
- **Linting**: `ruff check .`
- **Formatting**: `ruff format --check .`

---

## 15. API Quick Reference

All endpoints are versioned under `/api/v1` (except root health endpoints):

| Method | Path | Workspace Required? | Description |
|---|---|:---:|---|
| `GET` | `/health` | No | Operational health/liveness check. |
| `GET` | `/ready` | No | Application readiness check. |
| `POST` | `/api/v1/documents` | **Yes** (`X-KIP-Workspace-ID`) | Upload and index a document (`multipart/form-data`). |
| `GET` | `/api/v1/documents` | **Yes** (`X-KIP-Workspace-ID`) | List documents and chunk counts in the workspace. |
| `POST` | `/api/v1/retrieval/search` | **Yes** (`X-KIP-Workspace-ID`) | Perform semantic similarity search over workspace chunks (thread-offloaded). |
| `POST` | `/api/v1/rag/answer` | **Yes** (`X-KIP-Workspace-ID`) | Ask a question and generate a grounded RAG response with citations (thread-offloaded). |
| `POST` | `/api/v1/llm/generate` | No | Direct prompt invocation bypassing retrieval. |
| `POST` | `/api/v1/feedback` | Optional | Submit user feedback (max 30 words). |

Detailed schemas and error responses are documented in [API-Reference.md](docs/API-Reference.md).

---

## 16. Public Testing Guide

KIP is designed for interactive testing via deployed Streamlit instances or locally via `streamlit run frontend/app.py` (see [Quick Start](#13-quick-start--local-development)). When testing an active instance:

1. Upload one or more TXT, Markdown, PDF, or DOCX files.
2. Ask a question about the uploaded documents.
3. Try a cross-document question (spanning multiple files).
4. Try a question whose answer is **not** in the documents — KIP should say so.
5. Check whether the returned answer is supported by the cited sources.

**What helps us most:**
- Incorrect or unsupported answers
- Irrelevant retrieved chunks
- Cross-document mistakes
- Unexpected errors or slow behavior
- UX confusion or improvement ideas

Use the **"Help Improve KIP"** feedback box in the app to report anything you notice.

### Feedback Configuration (`FEEDBACK_WEBHOOK_URL` & `FEEDBACK_WEBHOOK_TOKEN`)

The feedback endpoint (`POST /api/v1/feedback`) forwards submissions to an external Google Apps Script web app so that feedback is **not** stored on the ephemeral Render filesystem.

```text
POST /api/v1/feedback (Client)
        ↓
FastAPI validates category, non-empty message, ≤ 30 words
        ↓
HTTPS GET with query params (?token=...&category=...&message=...)
        ↓
Google Apps Script doGet() appends row to Google Sheet
```

*Historical Note*: Earlier v1.1 development used an external POST webhook. During production deployment to Google Apps Script, free web apps returned HTTP 404 before reaching `doPost()`. The transport was transitioned in commit `ce1c42a` to an authenticated HTTPS `GET` query-parameter transport dispatched to `doGet()`.

| Variable | Description |
|---|---|
| `FEEDBACK_WEBHOOK_URL` | HTTPS URL for the deployed Google Apps Script `/exec` endpoint (`doGet` handler). |
| `FEEDBACK_WEBHOOK_TOKEN` | Shared secret token matching the `WEBHOOK_TOKEN` constant in Apps Script. Backend-only; never exposed to frontend code. |

Set these in your Render environment variables or in `.env` for local testing. Leave blank to disable (submissions will return a 503 with a clear message).

---

## 17. Current Limitations & Operational Boundaries

1. **No OCR for Scanned PDFs**: `PDFParser` extracts embedded text layers via `pypdf`. Scanned documents without OCR text layers yield empty text.
2. **Unstructured Document Formatting**: Markdown tables and DOCX headers are parsed as plain linear text.
3. **Bearer Token Multi-Tenancy**: Tenant isolation relies on high-entropy bearer tokens; full RBAC and OAuth authentication are not yet implemented.
4. **Free-Tier Cold Starts**: On the Render Free tier, the backend spins down after 15 minutes of inactivity; waking up may require 30–50 seconds.
5. **Provider Quotas**: Gemini Free Tier rate limits can impact rapid, continuous requests.
6. **Workload & Scale Validation Boundary**: While in-memory LRU caching and thread-pool executor offloading (`max_workers=4`) prevent event loop blocking, realistic multi-tenant concurrency and saturation testing remain intentionally scheduled for the 50–60% development checkpoint (v1.7). A bounded thread count does not constitute demonstrated enterprise-scale queueing.

---

## 18. Research & Roadmap Direction

KIP is engineered as an empirical AI systems platform. The **v1.2** research cycle systematically evaluated candidate techniques across a 25-case pilot and the frozen 50-document, 80-case expanded benchmark:
- Negative and neutral findings were preserved; dense whole-document retrieval remains the production baseline.
- Next research milestones focus on **v1.5 Retrieval Generalization** (testing dense retrieval on an independent second corpus) and **v1.6 Evidence-Grounded Workflows** (multi-document comparison).
- Future capabilities (memory, tool-use, agents, knowledge graphs) are strictly conditional and require demonstrated value over deterministic orchestration.

For full research strategy details, see [Research-Roadmap.md](docs/Research-Roadmap.md) and [Product-Roadmap.md](docs/Product-Roadmap.md).

---

## 19. Documentation Index

- [CURRENT_STATUS.md](docs/CURRENT_STATUS.md) — Canonical current-state reference (v1.3.0)
- [PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md) — Complete chronological engineering history across all completed milestones
- [Product-Roadmap.md](docs/Product-Roadmap.md) — Forward-looking product roadmap (v1.4 proposed / next)
- [Changelog.md](docs/Changelog.md) — Release notes and milestone summaries
- [Architecture.md](docs/Architecture.md) — System architecture, caching model, executor offloading, and dataflow
- [API-Reference.md](docs/API-Reference.md) — Complete OpenAPI REST endpoint reference and schemas
- [deployment.md](docs/deployment.md) — Comprehensive guide for Streamlit Cloud + Render + Qdrant + Apps Script
- [Research-Roadmap.md](docs/Research-Roadmap.md) — AI systems research agenda, experiment lifecycle, and v1.2 findings
- [Benchmarking.md](docs/Benchmarking.md) — Benchmarking methodology, metric definitions, and baseline records
- [Development-Workflow.md](docs/Development-Workflow.md) — Engineering conventions, Git workflows, and testing rules
- [Vision.md](docs/Vision.md) — Strategic long-term mission and core values
- [SRS.md](docs/SRS.md) — Software Requirements Specification

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.