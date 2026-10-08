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
└───────┬───────────────┬────────┘
        │               │ HTTPS GET
        ▼               ▼
┌───────────────┐ ┌────────────────────────┐
│  Qdrant Free  │ │  Google Apps Script    │
│  Vector Store │ │  Web App (doGet)       │
└───────┬───────┘ └───────────┬────────────┘
        │                     ▼
        ▼             ┌────────────────┐
┌───────────────┐     │  Google Sheet  │
│  Gemini API   │     │  (Feedback DB) │
│  Free Tier    │     └────────────────┘
└───────────────┘
```

- **Frontend:** Streamlit Community Cloud (runs `frontend/app.py`). Contains NO database or LLM secrets; only knows `KIP_API_BASE_URL`.
- **Backend:** FastAPI Web Service hosted on Render Free tier. Binds `0.0.0.0` and `$PORT`. Holds credentials securely in backend environment variables.
- **Vector Database:** Qdrant Cloud Free tier cluster. Uses a single collection (`knowledge_base`) with indexed payload-based multitenancy.
- **Embeddings & LLM:** Google Gemini Free Tier (`gemini-embedding-2` / `text-embedding-004` with 768 dimensions and `gemini-2.5-flash`).
- **Feedback Persistence:** Google Apps Script Web App receiving authenticated HTTPS GET query parameters and appending to a Google Sheet (`Sheet1`).

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
- **User Feedback:** Submitted feedback entries (rating category, text, workspace ID, timestamp) persist in Google Sheets via the Apps Script GET webhook.

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
4. **Google Apps Script Execution Limits:**
   - Free Google accounts support up to 20,000 URL fetch / web app invocations daily, far exceeding expected testing volume.

---

## 5. Step-by-Step Deployment Instructions

### Step 1: Create Free Qdrant Cluster
1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io).
2. Create a **Free Tier** cluster (choose any region).
3. Copy the **Cluster URL** (e.g., `https://xxxxxx.us-east4-0.gcp.cloud.qdrant.io:6333`).
4. Generate an **API Key** from the Qdrant Cloud console.

### Step 2: Configure Feedback Persistence Webhook (Google Apps Script + Google Sheet)
1. Create a new Google Sheet named `KIP User Feedback`.
2. Open **Extensions** -> **Apps Script**.
3. Implement a `doGet(e)` handler that extracts query parameters (`token`, `category`, `message`, `workspace_id`, `timestamp`), verifies the token against a shared secret, and appends the row to `Sheet1`.
   *(Note: Earlier v1.1 implementation used an HTTP POST webhook. During production validation, Google Apps Script returned HTTP 404 on POST requests before runtime invocation. Commit `ce1c42a` migrated transport to authenticated HTTPS GET query parameters, verified end-to-end).*
4. Click **Deploy** -> **New deployment**.
5. Select **Web app**, set **Execute as: Me**, and set **Who has access: Anyone**.
6. Copy the Web App URL (ending in `/exec`).
7. Note your shared secret token (e.g., generated with `python -c "import secrets; print(secrets.token_urlsafe(32))"`).

### Step 3: Deploy Backend to Render
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
   - `FEEDBACK_WEBHOOK_URL`: `https://script.google.com/macros/s/<DEPLOYMENT_ID>/exec`
   - `FEEDBACK_WEBHOOK_TOKEN`: `<your-shared-secret-token>`
   - `MAX_DOCUMENTS_PER_WORKSPACE`: `50`
   - `MAX_CHUNKS_PER_WORKSPACE`: `1000`
7. Deploy the service. Note your Render URL (e.g. `https://kip-api.onrender.com`). Verify `https://kip-api.onrender.com/health` returns `{"status":"healthy"}`.

### Step 4: Deploy Frontend to Streamlit Community Cloud
1. Sign up at [share.streamlit.io](https://share.streamlit.io).
2. Click **Create app**.
3. Select the repository, branch `main`, and main file path: `frontend/app.py`.
4. In Advanced Settings, add the environment variable:
   ```text
   KIP_API_BASE_URL = "https://kip-api.onrender.com"
   ```
5. Deploy. Streamlit will use the repository's root `.streamlit/config.toml` and `requirements.txt`.

---

## 6. Verification and Smoke Testing

Once all components are deployed:
1. **Health Probe:**
   ```bash
   curl -s https://kip-api.onrender.com/health
   # Expected: {"status":"healthy"}
   ```
2. **Frontend Availability:**
   - Navigate to your Streamlit Community Cloud URL.
   - Confirm the "Welcome to KIP" banner, workspace connection bar, and zero initial error toasts.
3. **Workspace Ingestion & Qdrant Verification:**
   - Click "Create New Workspace" or use the default.
   - Upload a sample Markdown or PDF file.
   - Verify indexing succeeds and appears in the Document Inventory with chunk count.
   - Run a query and inspect the answer and provenance attribution card.
4. **Feedback Persistence Verification:**
   - Submit a test feedback entry ("Great retrieval speed").
   - Confirm success toast in Streamlit and verify a new row appears in the linked Google Sheet.
