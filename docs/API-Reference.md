# API Reference

**Document Version:** 2.0  
**Project Version:** v1.1.0 (Feature Frozen)  
**Status:** Complete / Frozen  

---

## Overview

This document describes the REST API endpoints currently implemented in the Knowledge Intelligence Platform backend.

The API is versioned under `/api/v1`. Interactive API documentation is also available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

> **Multi-Tenancy Workspace Header:** All workspace-scoped endpoints (`/documents`, `/retrieval/search`, `/rag/answer`) accept an optional header:  
> `X-KIP-Workspace-ID: <token>`  
> When omitted, requests default to the `"default"` workspace. When provided, data ingestion, vector querying, and document inventories are strictly isolated to that workspace token.

> **Provider Keys:** Endpoints backed by embedding generation or LLM generation (`/retrieval/search`, `/rag/answer`, `/llm/generate`) require a valid `LLM_API_KEY` (for Google Gemini or OpenAI) to be configured. The test suite mocks or bypasses these providers appropriately.

---

## Health Endpoints

### `GET /health`

Returns a simple health status for operational monitoring.

**Response:**
```json
{
  "status": "healthy"
}
```

---

### `GET /ready`

Returns application-level readiness to serve requests.

**Response:**
```json
{
  "status": "ready"
}
```

---

## Document Ingestion & Inventory

### `POST /api/v1/documents`

Ingest an uploaded file, extract text, chunk content, generate embeddings, and index into the active workspace's vector collection.

**Headers:**
- `X-KIP-Workspace-ID` (optional, string): The workspace token to scope the document to.

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | File | The file to upload. Supported formats: `.txt`, `.md`, `.pdf`, `.docx`. |

> **Idempotency Note:** Document upload is idempotent based on exact file content (SHA-256) scoped to the workspace. If the exact same file content is uploaded multiple times to the same workspace, the API returns the existing document metadata with `chunks_indexed=0`, preventing duplicate vectors.

**Response:** `200 OK`

```json
{
  "id": "uuid-string",
  "filename": "quarterly_report.pdf",
  "media_type": "application/pdf",
  "text": "The full extracted text content of the document...",
  "metadata": {},
  "source": "quarterly_report.pdf",
  "ingested_at": "2026-10-08T12:00:00"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| `400` | Empty file, unsupported file format, or parsing error |
| `413` | File exceeds `MAX_UPLOAD_BYTES` (2 MB) or workspace exceeds `MAX_DOCUMENTS_PER_WORKSPACE` / `MAX_CHUNKS_PER_WORKSPACE` |
| `422` | Missing required `file` multipart field |

---

### `GET /api/v1/documents`

Retrieve the list of all ingested documents within the requesting workspace.

**Headers:**
- `X-KIP-Workspace-ID` (optional, string): The workspace token.

**Response:** `200 OK`

```json
{
  "documents": [
    {
      "id": "doc-uuid-1",
      "filename": "quarterly_report.pdf",
      "media_type": "application/pdf",
      "chunk_count": 14,
      "size_bytes": 1048576,
      "ingested_at": "2026-10-08T12:00:00"
    }
  ],
  "total_documents": 1,
  "total_chunks": 14,
  "workspace_id": "ws-token"
}
```

---

## Retrieval

### `POST /api/v1/retrieval/search`

Perform a semantic similarity search against the indexed knowledge base within the requesting workspace.

**Headers:**
- `X-KIP-Workspace-ID` (optional, string): The workspace token.

**Request Body (`application/json`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | `string` | ✅ Yes | The search query. |
| `top_k` | `integer` | No | Max results to return. Defaults to `RETRIEVAL_DEFAULT_TOP_K` (default: 5). |
| `threshold` | `float` | No | Maximum distance threshold to filter results. Defaults to `RETRIEVAL_DEFAULT_THRESHOLD` (default: none). |

**Example Request:**
```json
{
  "query": "What is retrieval-augmented generation?",
  "top_k": 3
}
```

**Response:** `200 OK`

```json
{
  "results": [
    {
      "id": "chunk-uuid",
      "document_id": "doc-uuid",
      "text": "Retrieval-Augmented Generation is...",
      "score": 0.12,
      "metadata": {}
    }
  ]
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| `422` | Missing required `query` field or validation error |

---

## RAG Generation

### `POST /api/v1/rag/answer`

Generate a grounded answer using retrieved knowledge from the knowledge base within the requesting workspace.

**Headers:**
- `X-KIP-Workspace-ID` (optional, string): The workspace token.

**Request Body (`application/json`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | `string` | ✅ Yes | The question to answer. |
| `top_k` | `integer` | No | Max context chunks to retrieve. Defaults to `RETRIEVAL_DEFAULT_TOP_K` (default: 5). |
| `threshold` | `float` | No | Retrieval distance threshold. Defaults to `RETRIEVAL_DEFAULT_THRESHOLD` (default: none). |

**Example Request:**
```json
{
  "query": "What is retrieval-augmented generation?",
  "top_k": 5
}
```

**Response:** `200 OK`

```json
{
  "answer": "Retrieval-Augmented Generation (RAG) is a technique that...",
  "sources": [
    {
      "chunk_id": "chunk-uuid",
      "document_id": "doc-uuid",
      "text": "The source text used as context...",
      "rank": 1,
      "score": 0.12,
      "metadata": {}
    }
  ]
}
```

If no relevant context is found in the knowledge base, the `answer` field will contain the configured empty-context message and `sources` will be an empty list.

**Error Responses:**

| Status | Condition |
|--------|-----------|
| `422` | Missing required `query` field |
| `502` | Downstream LLM provider failure |

---

## User Feedback

### `POST /api/v1/feedback`

Submit user feedback regarding generated answers, system usability, or bug reports.

**Request Body (`application/json`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | `string` | ✅ Yes | One of: `"helpful"`, `"incorrect"`, `"unclear"`, `"bug"`, `"suggestion"`. |
| `message` | `string` | ✅ Yes | Feedback message. Maximum length: 30 words. |
| `workspace_id` | `string` | No | Associated workspace token (defaults to `"anonymous"` or active workspace). |

**Example Request:**
```json
{
  "category": "helpful",
  "message": "Answer was concise and accurately cited section 3.",
  "workspace_id": "demo-workspace-token"
}
```

**Response:** `200 OK`

```json
{
  "status": "received",
  "persisted": true,
  "category": "helpful",
  "timestamp": "2026-10-08T12:00:00Z"
}
```

> **Transport Architecture:** The backend validates feedback against schema constraints (including 30-word limit). When `FEEDBACK_WEBHOOK_URL` is configured, the backend dispatches an authenticated HTTPS GET request with query parameters (`token`, `category`, `message`, `workspace_id`, `timestamp`) to Google Apps Script (`doGet`), which appends the row to Google Sheets. If the webhook is not configured or offline, feedback is safely logged and `persisted: false` is returned.

**Error Responses:**

| Status | Condition |
|--------|-----------|
| `422` | Invalid category or message exceeding 30 words |

---

## LLM Generation

### `POST /api/v1/llm/generate`

Send a multi-turn chat request directly to the configured language model.

> This is a low-level endpoint that bypasses retrieval. Use `/api/v1/rag/answer` for knowledge-base-grounded responses.

**Request Body (`application/json`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | `array[Message]` | ✅ Yes | At least one message. |
| `model` | `string` | No | Override the configured default model. |
| `temperature` | `float` | No | Generation temperature (0.0–2.0). |
| `max_output_tokens` | `integer` | No | Maximum tokens to generate (≥1). |

**Message Object:**

| Field | Type | Values |
|-------|------|--------|
| `role` | `string` | `"system"`, `"user"`, `"assistant"` |
| `content` | `string` | Non-empty, non-blank string |

**Example Request:**
```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain RAG in one sentence."}
  ],
  "temperature": 0.7
}
```

**Response:** `200 OK`

```json
{
  "content": "RAG is a technique that retrieves relevant documents...",
  "model": "gemini-2.5-flash",
  "provider": "gemini",
  "usage": {
    "prompt_tokens": 42,
    "completion_tokens": 30,
    "total_tokens": 72
  },
  "finish_reason": "stop"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| `422` | Validation failure (empty messages, blank content, out-of-range temperature, etc.) |
| `502` | Downstream LLM provider failure |

---

## Configuration Reference

Key configuration values that affect API behavior are set via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | LLM provider: `gemini` or `openai` |
| `LLM_MODEL` | `gemini-2.5-flash` | Default LLM model (`gemini-2.5-flash`, `gpt-4o-mini`) |
| `LLM_API_KEY` | — | API key for Gemini or OpenAI (required for live execution) |
| `EMBEDDING_PROVIDER` | `gemini` | Embedding provider: `gemini` or `openai` |
| `EMBEDDING_MODEL` | `gemini-embedding-2` | Default embedding model (`gemini-embedding-2` / `text-embedding-004`, `text-embedding-3-small`) |
| `EMBEDDING_DIMENSIONS` | `768` | Dimension size of embedding vectors (`768` for Gemini, `1536` for OpenAI) |
| `VECTOR_STORE_PROVIDER` | `qdrant` | Vector store backend: `qdrant` or `chroma` |
| `QDRANT_URL` | — | Cluster URL for Qdrant Cloud |
| `QDRANT_API_KEY` | — | API key for Qdrant Cloud |
| `QDRANT_COLLECTION` | `knowledge_base` | Qdrant collection name |
| `VECTOR_STORE_PERSIST_DIRECTORY` | `./.chroma_data` | Where ChromaDB persists data (when provider is `chroma`) |
| `RETRIEVAL_DEFAULT_TOP_K` | `5` | Default number of results for retrieval |
| `RETRIEVAL_DEFAULT_THRESHOLD` | — | Default similarity threshold |
| `MAX_UPLOAD_BYTES` | `2097152` (2 MB) | Maximum upload file size |
| `MAX_DOCUMENTS_PER_WORKSPACE` | `50` | Maximum indexed documents per workspace |
| `MAX_CHUNKS_PER_WORKSPACE` | `1000` | Maximum indexed chunks per workspace |
| `FEEDBACK_WEBHOOK_URL` | — | Google Apps Script Web App URL (`/exec`) for feedback persistence |
| `FEEDBACK_WEBHOOK_TOKEN` | — | Shared secret token for authenticating feedback webhook GET requests |
