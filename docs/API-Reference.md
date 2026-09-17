# API Reference

**Document Version:** 1.0  
**Project Version:** v0.3 (Core Foundation)  
**Status:** Active

---

## Overview

This document describes the REST API endpoints currently implemented in the Knowledge Intelligence Platform backend.

The API is versioned under `/api/v1`. Interactive API documentation is also available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

> **Provider Keys:** Endpoints backed by embedding generation or LLM generation (`/retrieval/search`, `/rag/answer`, `/llm/generate`) require a valid `OPENAI_API_KEY` to be configured. The test suite mocks or bypasses these providers appropriately.

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

## Document Ingestion

### `POST /api/v1/documents`

Ingest an uploaded file and return a normalized document object.

**Request:** `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `file` | File | The file to upload. Currently supports `.txt` (UTF-8). |

**Response:** `200 OK`

```json
{
  "id": "uuid-string",
  "filename": "example.txt",
  "media_type": "text/plain",
  "text": "The full extracted text content of the document.",
  "metadata": {},
  "source": "example.txt",
  "ingested_at": "2026-09-17T12:00:00"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| `400` | Empty file, invalid UTF-8, or unsupported file format |
| `413` | File exceeds the configured `MAX_UPLOAD_BYTES` limit |
| `422` | Missing required `file` field |

> **Note:** Document ingestion currently supports UTF-8 `.txt` files. PDF, DOCX, and Markdown parsers are planned for v1.0.

---

## Retrieval

### `POST /api/v1/retrieval/search`

Perform a semantic similarity search against the indexed knowledge base.

**Request Body (`application/json`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | `string` | ✅ Yes | The search query. |
| `top_k` | `integer` | No | Max results to return. Defaults to `RETRIEVAL_DEFAULT_TOP_K` setting (default: 5). |
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
| `422` | Missing required `query` field |

---

## RAG Generation

### `POST /api/v1/rag/answer`

Generate a grounded answer using retrieved knowledge from the knowledge base.

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
  "model": "gpt-4o-mini",
  "provider": "openai",
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
| `LLM_PROVIDER` | `openai` | LLM provider (`openai` is the only current option) |
| `LLM_MODEL` | `gpt-4o-mini` | Default LLM model |
| `LLM_API_KEY` | — | OpenAI API key (required for live execution) |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Default embedding model |
| `VECTOR_STORE_PROVIDER` | `chroma` | Vector store backend |
| `VECTOR_STORE_PERSIST_DIRECTORY` | `./.chroma_data` | Where ChromaDB persists data (empty = in-memory) |
| `RETRIEVAL_DEFAULT_TOP_K` | `5` | Default number of results for retrieval |
| `RETRIEVAL_DEFAULT_THRESHOLD` | — | Default similarity threshold |
| `MAX_UPLOAD_BYTES` | `2097152` (2 MB) | Upload size limit |
