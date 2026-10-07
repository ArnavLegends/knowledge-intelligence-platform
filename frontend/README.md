# Frontend

## Status

**Implemented (v1.1.0).** A clean Streamlit frontend is available at `frontend/app.py` supporting multi-tenant workspaces and persistent cloud deployment.

## Running the Frontend

Start the backend first:

```bash
cd backend
uvicorn app.main:app --reload
```

Then in a second terminal (from the repo root):

```bash
streamlit run frontend/app.py
```

The UI will open at `http://localhost:8501`.

## Features

- **Multi-Tenant Workspaces:** Private workspace token in sidebar; switch or resume existing workspaces.
- **Document Management:** Upload documents (TXT, Markdown, PDF, DOCX) and automatically view indexed documents for the active workspace.
- **Grounded Q&A:** Natural-language questioning with RAG, displaying answers and source citations with provenance scores.
- **Resilient Error Handling:** Graceful display of vector store and upstream LLM errors without crashing.

## Security Model

Workspace access uses private bearer tokens (`X-KIP-Workspace-ID`). All knowledge indexing and retrieval are strictly scoped to the active workspace.

## Configuration

The backend URL is configured via the `KIP_API_BASE_URL` environment variable.

| Variable | Default | Description |
|---|---|---|
| `KIP_API_BASE_URL` | `http://127.0.0.1:8000` | URL of the KIP FastAPI backend |

**Local development** — no configuration needed; default points to localhost.

**Deployed environment** — set `KIP_API_BASE_URL` in Streamlit Community Cloud settings:

```bash
export KIP_API_BASE_URL=https://kip-api.onrender.com
streamlit run frontend/app.py
```

Do **not** hardcode credentials or backend URLs directly in `app.py`.
