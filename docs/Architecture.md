# System Architecture

**Document Version:** 3.0
**Project Version:** v1.3.0
**Status:** Active System Architecture Document
**Last Updated:** 2026-10-15

---

# Purpose

This document defines the high-level architecture of the Knowledge Intelligence Platform (KIP).

It describes the overall organization of the system, major software components, architectural principles, communication patterns, data flow, and technology boundaries.

The objective is to provide a stable architectural blueprint that guides implementation while allowing individual components to evolve independently over time.

This document explicitly distinguishes between:
- **CURRENT REALITY (v1.3)**: Subsystems and flows implemented and verified in the codebase today: multi-tenant RAG, zero-cost in-memory LRU caching, async executor offloading, timeout resilience with HTTP 504 mapping, and structured latency telemetry.
- **RESEARCH OUTCOMES (v1.2)**: Empirical evaluation across 5 candidate retrieval techniques on the 50-doc/80-case benchmark; dense whole-document baseline verified and retained as production standard.
- **PROPOSED MILESTONES (v1.4–v1.8)**: Incremental improvements to workspace document management, evidence trust, secondary corpus validation, and bounded workflows.
- **CONDITIONAL (v2.0+)**: Architectural patterns (conversational memory, tool calling, agents, graph databases, relational databases) strictly conditional on demonstrated need.

---

# Architecture Philosophy

The Knowledge Intelligence Platform follows a modular, layered architecture designed to maximize scalability, maintainability, extensibility, and reproducibility.

The architecture emphasizes:

- Separation of concerns
- Modular components
- Independent services
- Loose coupling
- High cohesion
- Configuration-driven behavior
- Replaceable AI components
- Production-oriented engineering
- Continuous evolution

Every major subsystem should have a clearly defined responsibility and communicate through stable interfaces.

The architecture should allow individual technologies—such as language models, embedding models, vector databases, and orchestration frameworks—to be replaced without requiring major system redesign.

---

# Architectural Goals

The architecture is designed to achieve the following objectives:

## Scalability

Support increasing datasets, users, models, and workloads without fundamental architectural changes.

## Maintainability

Ensure that components remain understandable, modular, and easy to modify.

## Extensibility

Allow new capabilities to be integrated without affecting unrelated parts of the system.

## Reliability

Promote predictable system behavior through robust engineering practices.

## Observability

Support monitoring, logging, debugging, tracing, and performance analysis.

## Portability

Enable deployment across local development, cloud platforms, and containerized environments.

## Reproducibility

Ensure experiments and benchmarks can be reproduced consistently across environments.

---

# High-Level System Architecture

The Knowledge Intelligence Platform follows a layered architecture in which each layer has a clearly defined responsibility.

**Implemented layers** are shown with their active components. **Research outcomes and conditional layers** are marked explicitly.

```text
                    User / Browser
                         │
                         ▼
             Frontend Interface (Streamlit)
                         │
                         │ HTTPS (X-KIP-Workspace-ID Header)
                         ▼
                  FastAPI Backend
       ┌─────────────────┼──────────────────┐
       ▼                 ▼                  ▼
   Documents       RAG / Retrieval    LLM Service
   Ingestion             │             (Gemini / OpenAI)
       ▼                 ▼                  │
    Chunking         Retrieval              │
       ▼              Service               │
   Embeddings            │                  │
(Gemini / OpenAI)        ▼                  │
       ▼              Context               │
  Vector Store        Builder               │
(Qdrant / Chroma)        │                  │
       │                 └─────────┬────────┘
       │                           ▼
       └──────────────────> Grounded Response
                                   │
               Feedback Pipeline   ▼
FastAPI ──(Authenticated GET)──> Apps Script ──> Google Sheet

[ACTIVE v1.3] In-Memory LRU Caching (EmbeddingCache + SearchCache)
[ACTIVE v1.3] Async Executor (ThreadPoolExecutor offloading + wall-clock timeouts)
[RESEARCH v1.2] Dense Whole-Document Retrieval Retained (Hybrid & Reranking Rejected)
[PROPOSED v1.4] Workspace Document Operations & Evidence Trust
[CONDITIONAL v2.0+] Memory System (v2.0), Tool Calling (v2.1), Agentic Workflows (v2.2)
[CONDITIONAL v2.4+] Knowledge Graph (v2.4), Multimodal (v3.0), Enterprise RBAC (v4.0)
```

Each implemented layer performs a specific function while communicating through well-defined interfaces. This separation reduces coupling and allows components to evolve independently throughout the lifetime of the project.

---

# Major System Components

## Frontend

> **Status: Implemented (v1.1.0).** An interactive Streamlit frontend is implemented at `frontend/app.py`.

The frontend provides the user interface for workspace session management, document uploads (TXT, MD, PDF, DOCX) with progress indicators, workspace document library listing, grounded natural-language Q&A with Top-K slider controls (1–20), citation inspection with provenance scores, Render backend cold-start resilience pings, and in-app feedback submission.

*Architectural Note on Frontend Migration*: An eventual migration to React or Next.js is classified as **Planned → Deferred** until customized UX requirements necessitate migrating away from Streamlit.

---

## Backend API

Acts as the central coordination layer of the platform.

Responsibilities include:

- Request handling
- Authentication
- Routing
- Configuration
- Workflow coordination
- API responses

---

## Retrieval Engine

Responsible for locating relevant information from indexed knowledge sources.

Responsibilities include:

- **Current Production Reality (v1.3)**:
  - Dense semantic vector retrieval scoped to the active workspace.
  - Workspace metadata filtering (`workspace_id` payload match).
  - Top-$k$ context selection and ranking by cosine similarity score.
  - Multi-tenant search caching (`SearchCache`) with TTL and eviction hooks.
  - Asynchronous thread-pool offloading via `run_blocking` to protect the event loop.
- **Research Evaluation Outcomes (v1.2)**:
  - Evaluated 5 candidate retrieval techniques across 50 documents and 80 labelled benchmark cases.
  - Hybrid search (BM25 + dense) and cross-encoder reranking were empirically evaluated and rejected for failing to outperform the dense baseline.
  - Dense whole-document retrieval remains the verified production baseline (MRR: 0.7623).
- **Proposed Future Research (v1.5)**:
  - Evaluation of dense retrieval generalization on an independent secondary corpus.

---

## AI Orchestrator

Coordinates interactions across RAG pipeline components.

Responsibilities include:

- **Current (v1.3)**:
  - RAG workflow execution (`RAGService`)
  - Grounded prompt construction (`ContextBuilder`)
  - Response generation with citation and provenance attribution (`LLMService`)
- **Planned / Deferred (v2.0+)**:
  - Multi-turn conversation memory management (v2.0)
  - External tool orchestration (v2.1)
  - Autonomous multi-step agent coordination (v2.2)

---

## Language Model Layer

Provides abstraction over supported LLM providers.

The current implementation separates application use from provider details:

```
FastAPI
   ↓
LLM Service
   ↓
LLM Manager
   ↓
LLM Provider
   ↓
Provider Adapter
```

FastAPI routes and future orchestrators depend on the LLM Service. The LLM Manager selects the configured provider. Provider adapters isolate vendor SDKs and translate to a provider-agnostic request/response contract.

Responsibilities include:

- Model invocation
- Prompt execution
- Streaming responses
- Provider abstraction
- Model configuration

---

## Document Ingestion

Transforms uploaded files into a normalized internal Document without persisting storage or creating embeddings.

The current implementation is:

```text
Uploaded File (.txt, .md, .pdf, .docx)
   ↓
Validation (MAX_UPLOAD_BYTES ≤ 2 MB)
   ↓
Parser Selection (ParserRegistry)
   ↓
Parser (TXTParser, MarkdownParser, PDFParser, DOCXParser)
   ↓
Normalized Document
```

FastAPI routes depend on DocumentIngestionService. Parser selection uses an extensible `ParserRegistry` supporting Plain Text (`.txt`), Markdown (`.md`, `.markdown`), Portable Document Format (`.pdf` via `pypdf`), and Microsoft Word (`.docx` via `python-docx`). Additional formats can be added without modifying the core ingestion service.

Responsibilities include:

- Upload validation and file size enforcement
- Format-specific parser selection
- Text extraction and metadata normalization
- Normalized document representation
- **Document Identity**: Generates a deterministic `document_id` based on the exact SHA-256 hash of the raw file content (`hashlib.sha256(content).hexdigest()`). This ensures idempotent behavior: repeatedly uploading the exact same file yields the exact same logical document, preventing duplicate downstream processing.

---

## Document Chunking

Converts a normalized `Document` into deterministic, ordered `Chunk` objects. Chunking is strictly separated from LLMs and databases.

The current implementation is:

```text
Document
   ↓
ChunkingService
   ↓
DocumentChunker
   ↓
FixedSizeChunker
   ↓
Chunks
```

Responsibilities include:

- Segmenting full-text documents
- Preserving source metadata and ordering
- Supporting configurable overlap and sizes (`CHUNK_SIZE`, `CHUNK_OVERLAP`)
- Preparing text for future embedding storage
- **Chunk Identity**: Generates a deterministic `chunk_id` using a SHA-256 hash of the `document_id` and the chunk's `index` (`hashlib.sha256(f"{doc_id}:{chunk_index}".encode()).hexdigest()`). Because document IDs are content-based, chunk IDs remain perfectly stable across re-indexing operations.

---

## Document Indexing

Coordinates the full transformation of a normalized Document into searchable vectors.

The current implementation is:

```text
Document
   ↓
DocumentIndexingService
   ├── ChunkingService
   ├── EmbeddingService
   └── VectorStoreService
```

Responsibilities include:
- Accepting a normalized Document
- Creating chunks
- Generating embeddings
- Storing vectors scoped to the active workspace
- Returning an indexing summary

---

## Embedding Pipeline

Transforms an ordered list of `Chunk` objects into normalized `Embedding` objects using an external embedding provider.

The current implementation is:

```text
Chunk
   ↓
EmbeddingService
   ↓
EmbeddingManager
   ↓
EmbeddingProvider (Gemini / OpenAI)
   ↓
Provider Adapter
   ↓
Normalized Embedding
```

Responsibilities include:

- Creating internal provider-agnostic embedding requests
- Delegating text embedding generation to configured providers:
  - **Google Gemini**: `GeminiEmbeddingProvider` utilizing `gemini-embedding-2` (768 output dimensions) with batched chunk processing via `types.Content` objects.
  - **OpenAI**: `OpenAIEmbeddingProvider` utilizing `text-embedding-3-small` or `text-embedding-3-large`.
- Preserving source chunk identities and metadata
- Translating provider errors into internal exceptions

---

## Vector Storage

Persists normalized `Embedding` records for later retrieval, keeping application logic isolated from specific vector database vendors.

The current implementation supports dual vector storage backends:

```text
EmbeddingService
   ↓
Embedding
   ↓
VectorStoreService
   ↓
VectorStoreManager
   ↓
VectorStoreProvider
   ├── ChromaVectorStoreProvider (Local Development & Automated Test Suite)
   └── QdrantVectorStoreProvider (Cloud Deployed Multi-Tenant Store)
   ↓
Stored Vectors
```

### Dual Vector Store Roles
1. **ChromaDB** (`VECTOR_STORE_PROVIDER=chroma`):
   - Fast, local vector database.
   - Test suites enforce an in-memory Chroma instance (`tests/conftest.py`) to prevent disk pollution.
2. **Qdrant Cloud** (`VECTOR_STORE_PROVIDER=qdrant`):
   - Cloud production vector store hosted on Qdrant Cloud Free Tier.
   - Implements indexed payload multitenancy in a single shared collection (`knowledge_base`).
   - Uses deterministic UUID5 point IDs: `uuid5(NAMESPACE_URL, f"kip://{workspace_id}/{chunk_id}")`.

Responsibilities include:

- Persisting vector embeddings
- Preserving source chunk identities, workspace IDs, and metadata
- Supporting similarity search with tenant payload filtering
- Translating provider errors into internal exceptions

---

## Multi-Tenant Workspace Architecture

> **Status: Implemented (v1.1.0).** Cryptographically isolated multi-tenancy.

KIP enforces workspace-level tenant isolation:
- **Workspace Token**: Every request includes `X-KIP-Workspace-ID: <token>` containing a high-entropy URL-safe token.
- **FastAPI Dependency**: Validated in `backend/app/core/workspace.py` before route execution.
- **Payload-Based Multitenancy**: In Qdrant Cloud, vectors are tagged with `"workspace_id": "<token>"`. Searches strictly filter by `workspace_id == requested_workspace_id`.
- **Cross-Tenant Leakage Prevention**: Verified by automated multi-tenancy tests (`tests/test_workspace_multitenancy.py`).
- **Workspace Limits**: Free-tier safeguards enforce `MAX_DOCUMENTS_PER_WORKSPACE=50` and `MAX_CHUNKS_PER_WORKSPACE=1000`.

---

## Feedback Pipeline Architecture

> **Status: Implemented (v1.1.0).** Zero-cost persistent feedback loop.

```text
Client (Streamlit / API)
   │
   │ POST /api/v1/feedback
   ▼
FastAPI Backend (backend/app/api/v1/feedback.py)
   │
   ├─ Validates category in ALLOWED_CATEGORIES
   ├─ Validates message is non-empty and ≤ 30 words
   ├─ Validates FEEDBACK_WEBHOOK_URL and FEEDBACK_WEBHOOK_TOKEN
   │
   │ Authenticated HTTPS GET
   │ Query params: ?token=...&category=...&message=...&workspace_id=...&timestamp=...
   ▼
Google Apps Script Web App (doGet handler)
   │
   ├─ Validates token matches WEBHOOK_TOKEN
   ├─ Validates category and 30-word limit
   ├─ Appends row to Google Sheet
   ▼
Returns HTTP 200 "OK" ──> FastAPI returns HTTP 200 {"status": "recorded"}
```

*Historical Transition*: Earlier v1.1 implementations evaluated an HTTP POST webhook. During cloud testing on free Google Apps Script web apps, direct POST requests returned HTTP 404 before reaching Apps Script runtime code. The transport was redesigned in commit `ce1c42a` to an authenticated HTTPS `GET` query-parameter transport dispatched to `doGet()`, which verified end-to-end persistence in Google Sheets.

---

## Retrieval System

Connects embedding and vector-storage layers into a semantic retrieval pipeline.

The retrieval flow:

```text
User Query
   ↓
RetrievalService
   ↓
EmbeddingService (Query Vector)
   ↓
VectorStoreService
   ↓
VectorStoreManager / QdrantAdapter or ChromaAdapter
   ↓
Retrieved Chunks (Scoped to Workspace)
```

Responsibilities:
- Provide unified query access across knowledge bases
- Encode user questions into embeddings
- Filter results based on workspace ID and distance thresholds
- Deterministic result ordering

Note: Memory, hybrid retrieval (BM25), reranking, and knowledge graphs are future stages.

---

## RAG Generation System

The final stage of the retrieval-augmented generation pipeline.

The RAG flow:

```text
User Query
   ↓
RAGService
   ├── RetrievalService (retrieves chunks scoped to workspace)
   ├── ContextBuilder (assembles context string)
   └── LLMService (generates grounded response via Gemini / OpenAI)
   ↓
Grounded Response + Sources
```

Responsibilities:
- Build deterministic context strings from retrieved chunks.
- Format LLM prompts combining system instructions, context data, and the user query.
- Maintain boundaries between context and instructions.
- Ensure the final response retains explicit provenance mapping with ranked source citations.
- Return predefined empty-context message when no relevant chunks are found.

## In-Memory Caching Architecture

> **Status: Implemented (v1.3.0).** Zero-infrastructure, bounded in-process caching foundation.

To improve response latencies and eliminate redundant third-party API costs without introducing external infrastructure (such as Redis or Memcached), KIP provides a thread-safe, pure-Python caching architecture:

```text
[EmbeddingManager]
       │
       ▼ Single Query Text
[EmbeddingCache] ──(Hit: <0.05ms)──> Return Cached Vector (Skip Gemini API)
       │ (Miss)
       ▼ Call Provider SDK
[GeminiEmbeddingProvider]
       │
       ▼ Store Vector
[EmbeddingCache.put]

[RetrievalService]
       │
       ▼ Query Vector + Filters + Workspace ID
[SearchCache] ──(Hit: <0.05ms)──> Return Cached Chunks (Skip Qdrant)
       │ (Miss)
       ▼ Call Vector Store
[QdrantVectorStoreProvider]
       │
       ▼ Store Chunks
[SearchCache.put]
```

### Components
1. **Thread-Safe Generic LRU (`app.services.cache.lru_cache.LRUCache`)**:
   - Implements bounded capacity using `collections.OrderedDict` protected by a reentrant lock (`threading.RLock`).
   - Evicts least-recently-used items when the configured capacity is reached.
2. **Embedding Cache (`app.services.cache.embedding_cache.EmbeddingCache`)**:
   - Keys: SHA-256 hash of `(normalized_text, model, dimensions)`.
   - Applied selectively to single query embeddings; bulk document indexing bypasses the cache to avoid cache pollution.
3. **Multi-Tenant Search Cache (`app.services.cache.search_cache.SearchCache`)**:
   - Keys: SHA-256 hash of `(workspace_id, collection, vector_hash, top_k, threshold, document_id, canonical_filters)`.
   - Security Invariant: Every cache key explicitly embeds `workspace_id` to guarantee tenant isolation.
   - Automatic Invalidation: Maintains reverse index mappings allowing immediate eviction via `invalidate_workspace(workspace_id)` and `invalidate_document(workspace_id, document_id)`. These invalidation hooks are automatically invoked when documents are indexed or deleted.
   - TTL Safety Net: 60-second default time-to-live prevents stale entries if unhooked mutations occur.

---

## Concurrency & Async Execution Architecture

> **Status: Implemented (v1.3.0).** Non-blocking event-loop offloading and deadline protection.

FastAPI endpoints are asynchronous (`async def`), but AI providers (Gemini API SDK, Qdrant Client) make blocking synchronous network I/O calls. If executed directly inside async handlers, these calls block the single-threaded asyncio event loop, causing concurrent requests to stall.

```text
FastAPI Request (/api/v1/retrieval/search or /api/v1/rag/answer)
      │
      ▼ (Event Loop Thread)
run_blocking(service.search, query, timeout=17.0s)
      │
      ├─ Dispatches to process-level ThreadPoolExecutor (max_workers=4)
      │
      ├─ Event Loop remains completely non-blocking for concurrent traffic
      │
      └─ asyncio.wait_for enforces strict wall-clock deadline
            │
            ├─ On Timeout: Returns HTTP 504 Gateway Timeout cleanly
            └─ On Success: Returns formatted JSON response
```

### Key Principles
- **Bounded Worker Pool (`app.core.async_executor`)**: Process-level `ThreadPoolExecutor` initialized once with configurable `RETRIEVAL_EXECUTOR_WORKERS` (default: 4).
- **Timeout Budgets**: Endpoints enforce calculated deadlines (e.g., embedding timeout + Qdrant timeout + 2.0s buffer). Upstream stalls or hung sockets raise `TimeoutError`, translated directly to HTTP 504 Gateway Timeout.
- **Graceful Lifecycle Shutdown**: Thread pool cleanup (`shutdown_executor`) is registered with FastAPI's `lifespan` handler to terminate worker threads cleanly on application shutdown.
- **Guardrail**: A worker pool prevents event-loop stalls, but is not proof of unbounded queuing capacity. Scalability profiling is scheduled for milestone v1.7.

---

## Memory System

> **Status: Planned → Deferred (v2.0).** Memory management is not yet implemented.

When implemented, the memory system will maintain conversational and persistent memory, including context management, long-term memory retrieval, and session history. Stateless request-response RAG is prioritized in v1.1.

---

## Knowledge Layer

> **Status: Planned → Deferred (v2.4).** The knowledge graph and entity systems are not yet implemented.

When implemented, the knowledge layer will maintain structured knowledge representations including a vector store integration (implemented in v1.0/v1.1), knowledge graph, entity management, and knowledge synthesis.

---

## Evaluation Layer

> **Status: Implemented Research Benchmark & Metric Auditor (v1.2/v1.3).**

The evaluation layer provides:
- **Evaluation Runner**: `evaluation/runner.py` executes benchmark cases against isolated vector store collections, supporting both full RAG and pure-retrieval evaluations without LLM overhead.
- **Evaluation Models**: `evaluation/models.py` computes fine-grained retrieval metrics: Hit@1, Hit@3, Hit@5, Mean Reciprocal Rank (MRR), keyword coverage, and stage latencies.
- **Benchmark Corpora**:
  - `benchmarks/corpus_v1_2/`: 18 documents (14 core + 4 distractors) and 25-case pilot benchmark.
  - `benchmarks/corpus_v1_2_expanded/`: 50 documents and 80 labelled benchmark cases across six query categories.
- **Frozen Dense Baseline**: Verified against live Gemini `gemini-embedding-2` + Qdrant Cloud (MRR: 0.7623, Hit@1: 0.6875, Hit@5: 0.8750).
- **Metric Auditor**: `evaluation/validate_benchmark_metrics.py` mechanically validates all committed JSON benchmark artifacts, enforcing zero recalculation discrepancies across releases.

---

# Component Communication

The platform follows a request-driven workflow in which components communicate through clearly defined interfaces.

A typical v1.1 RAG request follows this sequence:

1. User submits a query in the frontend UI or via REST API.
2. Frontend sends the request to the FastAPI backend with the `X-KIP-Workspace-ID` header.
3. Backend validates the workspace token and routes the request to `RAGService`.
4. Retrieval engine encodes the query and identifies relevant knowledge chunks filtered by `workspace_id`.
5. Context Builder assembles retrieved chunks into a grounded context prompt.
6. Language Model service generates a response with strict provenance citations.
7. Backend logs execution metrics and returns the structured response.
8. Frontend presents the response and interactive provenance sources to the user.

*(Note: Conversational Memory System integration is planned for v2.0; external tool calling in v2.1; and autonomous agent planning in v2.2.)*

---

# System Data Flow

The Knowledge Intelligence Platform processes requests through a structured data flow that separates user interaction, knowledge retrieval, reasoning, and evaluation.

## Query Processing Flow

```
User Query
      │
      ▼
Frontend (Streamlit)
      │
      ▼ HTTPS (X-KIP-Workspace-ID)
Backend API (FastAPI)
      │
      ▼
Authentication & Validation (workspace dependency)
      │
      ▼
RAG Service (AI Orchestration)
      │
      ▼
Retrieval Engine (Dense Vector Search)
      │
      ▼
Vector Database (Qdrant Cloud / ChromaDB scoped to workspace)
      │
      ▼
Context Builder (Chunk Assembly & Prompt Formatting)
      │
      ▼
Language Model (Gemini / OpenAI Provider)
      │
      ▼
Structured Response with Provenance Citations
      │
      ▼
Frontend (Answer Display & Provenance Inspector)
      │
      ▼
User
```

*(Planned extensions: Hybrid BM25/reranking in v1.2; Memory Store parallel retrieval in v2.0; Tool/Agent loops in v2.1/v2.2.)*

Every stage has a clearly defined responsibility and communicates through stable interfaces, allowing individual components to evolve independently without affecting the overall workflow.

---

# Layered Architecture

The platform is organized into logical layers that separate presentation, application logic, AI services, storage, and infrastructure.

## Presentation Layer

Responsible for user interaction.

Examples:

- Web interface
- Administration dashboard
- Future mobile interface
- API clients

---

## Application Layer

Coordinates platform behavior.

Responsibilities include:

- Request routing
- Authentication
- Configuration
- Workflow management
- Session handling

---

## Intelligence Layer

Contains the core AI capabilities.

Responsibilities include:

- **Current (v1.3)**:
  - Dense semantic retrieval (baseline retained after v1.2 candidate rejections)
  - In-memory thread-safe LRU search and embedding caching
  - Async thread-pool offloading and timeout enforcement (HTTP 504)
  - Grounded context assembly and prompt construction
  - Language model generation with provenance mapping
- **Planned / Conditional (v1.4+)**:
  - Knowledge workspace & evidence trust (v1.4)
  - Retrieval generalization & second-corpus evaluation (v1.5)
  - Evidence-grounded knowledge workflows (v1.6)
  - Realistic workload validation (v1.7)
  - Reproducible release (v1.8)
  - Conditional capabilities: Conversational memory (v2.0), Tool execution (v2.1), Bounded agentic workflows (v2.2), Knowledge graphs (v2.4)

---

## Data Layer

Responsible for storing and retrieving information.

Examples include:

- Vector databases
- Relational databases
- Knowledge graphs
- Memory storage
- Configuration storage

---

## Infrastructure Layer

Supports platform operations.

Responsibilities include:

- Logging
- Monitoring
- CI/CD
- Containerization
- Cloud deployment
- Security
- Backup

---

# Architectural Principles

Every implementation within the Knowledge Intelligence Platform should adhere to the following architectural principles.

## Single Responsibility

Each module should perform one clearly defined responsibility.

---

## Loose Coupling

Components should communicate through interfaces rather than direct dependencies.

---

## High Cohesion

Related functionality should remain within the same module whenever possible.

---

## Replaceable Components

Embedding models, language models, vector databases, and orchestration frameworks should be replaceable without requiring architectural redesign.

---

## Configuration over Hardcoding

Behavior should be controlled through configuration files and environment variables instead of modifying source code.

---

## API First

Subsystems should expose well-defined APIs that encourage modular development and simplify testing.

---

## Observability by Design

Logging, monitoring, metrics, and tracing should be incorporated into the architecture rather than added later.

---

## Security by Design

Authentication, authorization, validation, and secure data handling should be considered fundamental architectural requirements rather than optional enhancements.

---

## Testability

Each subsystem should support independent testing through modular design and dependency isolation.

---

# Deployment Architecture

The Knowledge Intelligence Platform is designed to support multiple deployment environments ranging from local development to enterprise-scale cloud infrastructure.

## Development Environment

Used for feature development, testing, and experimentation.

Components:

- Frontend (Streamlit running on port 8501)
- FastAPI Backend (Uvicorn running on port 8000)
- Local Vector Database (ChromaDB persistent directory or Qdrant Cloud)
- Local PostgreSQL (optional / future)
- Local LLM (optional / future)
- Docker Compose (containerized development)

---

## Implemented Cloud Deployment (Zero-Cost Production Topology)

The current live deployment implements a zero-cost cloud topology across specialized serverless and container tiers:

- **Frontend Tier**: Streamlit Community Cloud hosting `frontend/app.py`
  - Communicates with backend via HTTPS REST calls (`BACKEND_URL`).
  - Manages client-side workspace sessions and feedback forms.
- **Backend Tier**: Render Web Service (Free Tier) hosting FastAPI via `uvicorn backend.app.main:app`
  - Handles multi-format ingestion, chunking, embedding generation, retrieval, and RAG answering.
  - Implements thread-safe in-memory LRU search and embedding caching with workspace invalidation.
  - Offloads blocking provider and database calls to a bounded thread pool (`run_blocking`) with timeout enforcement (HTTP 504).
  - Automatically spins down after 15 minutes of inactivity; exhibits a 30–50 second cold-start spin-up on next request.
- **Vector Storage Tier**: Qdrant Cloud (Free Tier)
  - Single managed cluster hosting collection `knowledge_base` with 768-dimensional vectors (COSINE distance).
  - Multi-tenant workspace isolation enforced at query time via `workspace_id` payload filters.
  - Deterministic point IDs generated via UUID5 scheme: `uuid5(NAMESPACE_URL, f"kip://{workspace_id}/{chunk_id}")`.
- **LLM / Embedding Provider**: Google Gemini API (Free Tier)
  - Text generation via `gemini-2.5-flash`.
  - Dense embeddings via Gemini embedding model (defaults to `gemini-embedding-2`, 768 dimensions), utilizing 1:1 `Content`/`Part` batch formatting.
- **Feedback Persistence Tier**: Google Apps Script Web App (`doGet`) + Google Sheet
  - Backend dispatches authenticated HTTPS GET requests with URL query parameters (`token`, `category`, `message`, `workspace_id`, `timestamp`).
  - Google Apps Script parses parameters and appends structured rows to `Sheet1`.

---

## Production Environment (Target / Enterprise)

Supports reliable, high-availability, and enterprise-scale deployments.

Components:

- Load Balancer
- Frontend Service (Streamlit or React)
- Backend API (FastAPI clustered workers)
- AI Orchestrator
- Vector Database (Clustered Qdrant or Milvus)
- Relational Database (Managed PostgreSQL for workspaces, users, audit logs)
- Object Storage (S3 / GCS for original document artifacts)
- Monitoring Stack (Prometheus, Grafana)
- Logging Infrastructure (Centralized ELK or CloudWatch)

---

## Deployment Principles

- Containerized services
- Infrastructure as Code
- Automated deployments (GitHub Actions CI/CD)
- Environment isolation (development, staging, production)
- Horizontal scalability
- High availability
- Automated backups

---

# Security Architecture

Security is considered a foundational architectural concern rather than an optional feature.

## Authentication

- User authentication (Future)
- Token-based workspace validation (`X-KIP-Workspace-ID` header, Current: v1.3.0)
- Feedback webhook token authentication (`FEEDBACK_WEBHOOK_TOKEN`, Current: v1.3.0)
- Session management

---

## Authorization

- Role-Based Access Control (RBAC) (Future)
- Permission management (Future)
- Workspace isolation via vector payload filtering (Current: v1.3.0)
- Workspace upload quotas and document size limits (Current: v1.3.0)

---

## Data Protection

- Encryption in transit (TLS/HTTPS across all public endpoints)
- Encryption at rest (managed by cloud database providers)
- Secure secret management (environment variables via cloud dashboards, zero hardcoded keys)

---

## API Security

- Input validation (Pydantic models with strict typing, length constraints, and regex validation)
- Rate limiting and retry backoff (exponential backoff for external LLM/embedding APIs)
- Request authentication via workspace headers and shared secret tokens
- API versioning (`/api/v1/` route prefixes)

---

## Operational Security

- Audit logging (structured logs across ingestion, retrieval, and feedback pipelines)
- Monitoring (FastAPI `/health` endpoint for uptime probes)
- Incident detection
- Backup strategy
- Disaster recovery

Future versions may incorporate enterprise authentication providers, advanced compliance requirements, and zero-trust security models.

---

# Technology Mapping

The architecture is technology-agnostic wherever practical. Individual technologies may evolve while preserving the overall system design.

| Architectural Layer | Current Implementation (v1.3.0) | Historical / Testing | Future / Deferred Alternatives |
|---------------------|---------------------------------|----------------------|--------------------------------|
| Frontend | Streamlit (`frontend/app.py`) | Streamlit (v0.1) | React, Next.js, Vue.js |
| Backend API | FastAPI (`backend/app/main.py`) | FastAPI (v0.1) | Remains configurable |
| In-Memory Caching | Thread-safe LRU search & embedding caches (`backend/app/core/caching.py`) | Uncached (v1.0–v1.2) | Redis, Memcached (Deferred) |
| Concurrency & Offloading | Thread-pool offloading (`run_blocking`) & timeout bounds | Synchronous blocking (v1.0–v1.2) | Celery, Temporal, Async Workers |
| Orchestration | Modular Custom Pipeline (`rag/pipeline.py`) | Procedural script (v0.1) | LangChain, LangGraph, AutoGen |
| Language Models | Google Gemini (`gemini-2.5-flash`), OpenAI (`gpt-4o-mini`) | Mock / Echo (v0.1) | Anthropic Claude, Local LLMs (Ollama, vLLM) |
| Embeddings | Google Gemini (`gemini-embedding-2`, 768-d), OpenAI (`text-embedding-3-small`) | Deterministic Mock (v0.1) | Sentence Transformers, BGE, E5, Jina |
| Vector Storage | Qdrant Cloud (Managed Serverless) | ChromaDB (Local SQLite) | FAISS, Pinecone, Weaviate, Milvus |
| Workspace Isolation | Qdrant Payload Filter (`workspace_id`) | In-Memory (v0.1) | PostgreSQL Schema Isolation, Row-Level Security |
| Feedback Persistence | Google Apps Script (`doGet`) + Google Sheet | Direct POST Webhook (Deprecated) | PostgreSQL, Supabase, Airtable |
| Evaluation | Custom Mechanical Evaluator (`evaluation/runner.py`) | Manual inspection | RAGAS, DeepEval, TruLens |
| Relational Storage | In-Memory / Vector Payload Metadata | Not used | PostgreSQL, SQLite (Deferred to v2.0+) |
| Knowledge Graph | Not implemented (Deferred) | Not used | Neo4j, Memgraph, Amazon Neptune |
| Deployment | Render + Streamlit Cloud + Qdrant Cloud | Localhost | Docker Compose, Kubernetes, AWS/GCP |

Technology choices should remain modular so that components can be replaced without requiring significant architectural redesign.

---

# Future Architecture Evolution

The architecture is expected to evolve alongside advancements in AI systems engineering while preserving its core design principles.

Future architectural enhancements may include:

- Distributed AI orchestration
- Multi-agent collaboration (Deferred to v2.0+)
- Advanced reasoning pipelines
- Knowledge graph reasoning (Deferred to v3.0+)
- Federated knowledge retrieval
- Multimodal processing pipelines (Deferred to v4.0+)
- Enterprise deployment patterns
- Intelligent workflow automation
- Cloud-native AI services
- Real-time knowledge synchronization

Architectural evolution should remain incremental and evidence-based. Significant changes should be documented, benchmarked, and evaluated before adoption.

---

# Document Governance

| Item | Value |
|------|-------|
| Document Owner | Project Maintainer |
| Project | Knowledge Intelligence Platform |
| Document Version | 3.0 |
| Project Version | v1.3.0 |
| Status | Active / Governed |
| Last Reviewed | 2026-10-15 |

## Review Policy

The Architecture document should be reviewed whenever significant changes are made to the system's structure, component responsibilities, communication patterns, or deployment strategy.

Implementation details may evolve without requiring updates to this document, provided they remain consistent with the architectural principles defined herein.

Major architectural revisions should be accompanied by updated diagrams, documentation, and rationale to preserve the long-term integrity of the platform.
