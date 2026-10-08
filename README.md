# Knowledge Intelligence Platform (KIP)

> A modular AI Knowledge Intelligence Platform for Retrieval-Augmented Generation (RAG) with multi-tenant cloud storage.

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version: 1.1.0](https://img.shields.io/badge/version-1.1.0-green.svg)](https://github.com/ArnavLegends/knowledge-intelligence-platform)

## Overview

The Knowledge Intelligence Platform (KIP) is a robust, production-oriented knowledge assistant capable of retrieving, understanding, and synthesizing information from uploaded documents.

Designed with modern AI engineering practices, KIP implements a complete FastAPI-based Retrieval-Augmented Generation (RAG) backend engine, a Streamlit frontend, and a multi-tenant vector storage architecture supporting both local development and zero-cost cloud deployments.

## Current Project Status: v1.1.0 — Multi-Tenant Cloud Knowledge Layer

The repository provides a complete, production-ready RAG application:

- **Multi-Tenant Workspaces**: Cryptographically secure, bearer-token workspace isolation (`X-KIP-Workspace-ID`). Every document, chunk, and retrieval operation is strictly workspace-scoped.
- **Pluggable Vector Storage**:
  - **Qdrant**: Cloud-ready multitenant vector database with payload filtering and deterministic point UUIDs.
  - **ChromaDB**: In-memory and local persistent vector database for fast development and testing.
- **Pluggable Embeddings**:
  - **Google Gemini**: `gemini-embedding-2` with 768 output dimensionality.
  - **OpenAI**: `text-embedding-3-small` / `text-embedding-3-large`.
- **Pluggable LLMs**: Google Gemini (`gemini-2.5-flash`) and OpenAI (`gpt-4o-mini`).
- **Document Ingestion**: Parsing for TXT, Markdown, PDF, and DOCX files with content-hash idempotency.
- **Semantic Retrieval**: Top-k similarity search with thresholds and cross-tenant leakage protection.
- **REST APIs**: Full OpenAPI/Swagger documentation with workspace authentication headers.
- **Streamlit Frontend**: Multi-tenant UI with workspace creation, token resumption, and document listing.
- **Zero-Cost Cloud Deployment**: Streamlit Community Cloud + Render Free FastAPI + Qdrant Free Cloud + Gemini Free Tier.

## Architecture

```text
Streamlit UI  ──(X-KIP-Workspace-ID)──>  FastAPI Backend  ──>  Qdrant / ChromaDB
                                              │
                                              └──>  Gemini / OpenAI LLM
```

## Quick Start & Local Development

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

## Testing and Code Quality

- **Tests**: `pytest` (offline, deterministic, no cloud credentials required)
- **Linting**: `ruff check .`
- **Formatting**: `ruff format --check .`

## Documentation

- [Deployment Guide](docs/deployment.md) — Comprehensive guide for Streamlit Cloud + Render + Qdrant
- [API Reference](docs/API-Reference.md)
- [Architecture](docs/Architecture.md)
- [Changelog](docs/Changelog.md)

## Public Testing Guide (v1.1)

KIP is open for public testing via the deployed Streamlit application. To try it:

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

### Feedback Configuration (`FEEDBACK_WEBHOOK_URL`)

The feedback endpoint (`POST /api/v1/feedback`) forwards submissions to an external
HTTPS webhook so that feedback is **not** stored on the ephemeral Render filesystem.

| Variable | Description |
|---|---|
| `FEEDBACK_WEBHOOK_URL` | HTTPS URL that accepts a JSON POST `{ category, message, timestamp }`. Leave blank to disable (submissions will return a 503 with a clear message). |

Set this in your Render environment variables or in `.env` for local testing.
Any webhook that accepts JSON works — Slack incoming webhooks, Make/Zapier, custom endpoints, etc.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.