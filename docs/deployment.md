# Knowledge Intelligence Platform (KIP) — Deployment Guide

## 1. Architecture Overview

KIP v1.1.0 is architected for zero-cost ($0 / ₹0) public deployment across free-tier cloud infrastructure:

```text
┌────────────────────────────────┐
│   Streamlit Community Cloud    │  (Frontend UI)
│          KIP Frontend          │
└───────────────┬────────────────┘
                │ HTTPS (KIP_API_BASE_URL)
                ▼
┌────────────────────────────────┐
│        FastAPI on Render       │  (Stateless API Backend)
│         Render Free Tier       │
└───────────────┬────────────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
┌───────────────┐ ┌────────────────┐
│  Qdrant Free  │ │  Gemini API    │
│  Vector Store │ │  Free Tier     │
└───────────────┘ └────────────────┘
```

- **Frontend:** Streamlit Community Cloud (runs `frontend/app.py`). Contains NO database or LLM secrets; only knows `KIP_API_BASE_URL`.
- **Backend:** FastAPI Web Service hosted on Render Free tier. Binds `0.0.0.0` and `$PORT`. Holds credentials securely in backend environment variables.
- **Vector Database:** Qdrant Cloud Free tier cluster. Uses a single collection (`knowledge_base`) with indexed payload-based multitenancy.
- **Embeddings & LLM:** Google Gemini Free Tier (`gemini-embedding-2` with 768 dimensions and `gemini-2.5-flash`).

---

## 2. Multi-Tenancy & Workspace Isolation

KIP v1.1.0 enforces workspace-based multi-tenancy:
- **Private Workspace Token:** Each user or session generates or inputs a high-entropy workspace token (via `secrets.token_urlsafe(32)`).
- **Mandatory Header:** Every document upload, document listing, semantic retrieval, and RAG query sends `X-KIP-Workspace-ID: <token>`.
- **Deterministic Point IDs:** Vector IDs in Qdrant are generated deterministically using UUID5 scoped to the workspace (`uuid5(NAMESPACE_URL, "kip://<workspace_id>/<chunk_id>")`).
- **Strict Query Filtering:** All vector searches and document listings filter strictly by `workspace_id == requested_workspace_id`. Cross-workspace contamination is blocked at both the vector engine and service layers.
- **Idempotency:** Uploading the same document twice in the same workspace is an idempotent no-op. Uploading the same document in two different workspaces creates two independent, isolated document entries.

---

## 3. Persistence Model

### What Persists:
- **Documents & Metadata:** Document IDs, filenames, chunk counts, media types, and sizes persist in Qdrant payloads.
- **Embeddings & Chunks:** Text chunks and their normalized embedding vectors persist across Render backend restarts and sleeping instances.
- **Resumed Sessions:** Entering an existing workspace token connects immediately to that workspace's knowledge base.

### What Does NOT Persist Yet:
- User accounts / passwords (authentication is token-based bearer access in v1.1.0).
- Cross-session chat transcript history.

---

## 4. Free-Tier Operational Characteristics

1. **Render Cold Starts:**
   - On the Render Free tier, the service spins down after 15 minutes of inactivity.
   - The first request after sleep may take 30–50 seconds to respond. Subsequent requests respond instantly.
2. **Qdrant Free Cluster:**
   - Free clusters remain active as long as requests are periodically made.
   - Single collection multitenancy keeps resource utilization well below cluster limits.
3. **Workspace Limits:**
   - `MAX_DOCUMENTS_PER_WORKSPACE=50`
   - `MAX_CHUNKS_PER_WORKSPACE=1000`
   - Prevents quota exhaustion on free clusters.

---

## 5. Step-by-Step Deployment Instructions

### Step 1: Create Free Qdrant Cluster
1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io).
2. Create a **Free Tier** cluster (choose any region).
3. Copy the **Cluster URL** (e.g., `https://xxxxxx.us-east4-0.gcp.cloud.qdrant.io:6333`).
4. Generate an **API Key** from the Qdrant Cloud console.

### Step 2: Deploy Backend to Render
1. Sign up at [render.com](https://render.com).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository (`ArnavLegends/knowledge-intelligence-platform`).
4. Select the **Free** plan.
5. Set:
   - **Runtime:** `Python`
   - **Build Command:** `pip install -e .`
   - **Start Command:** `PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Add Environment Variables in the Render Dashboard:
   - `ENVIRONMENT`: `production`
   - `DEBUG`: `false`
   - `VECTOR_STORE_PROVIDER`: `qdrant`
   - `QDRANT_URL`: `<your-qdrant-cluster-url>`
   - `QDRANT_API_KEY`: `<your-qdrant-api-key>`
   - `QDRANT_COLLECTION`: `knowledge_base`
   - `LLM_PROVIDER`: `gemini`
   - `EMBEDDING_PROVIDER`: `gemini`
   - `LLM_MODEL`: `gemini-2.5-flash`
   - `EMBEDDING_MODEL`: `gemini-embedding-2`
   - `EMBEDDING_DIMENSIONS`: `768`
   - `LLM_API_KEY`: `<your-gemini-api-key>`
7. Deploy the service. Note your Render URL (e.g. `https://kip-api.onrender.com`). Verify `https://kip-api.onrender.com/health` returns `{"status":"healthy"}`.

### Step 3: Deploy Frontend to Streamlit Community Cloud
1. Sign up at [share.streamlit.io](https://share.streamlit.io).
2. Click **Create app**.
3. Select the repository, branch `main`, and main file path: `frontend/app.py`.
4. In Advanced Settings, add the environment variable:
   ```text
   KIP_API_BASE_URL = "https://kip-api.onrender.com"
   ```
5. Deploy. Streamlit will use the repository's root `.streamlit/config.toml` and `requirements.txt`.
