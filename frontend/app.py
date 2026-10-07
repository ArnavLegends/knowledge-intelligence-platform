"""KIP v1.1.0 Streamlit Frontend with Multi-Tenant Workspaces.

Minimal, functional interface for the Knowledge Intelligence Platform.

What it provides:
- High-entropy private workspace tokens for tenant isolation
- Upload a document (TXT, Markdown, PDF, DOCX) to the active workspace
- See indexing success/failure with chunk count
- Automatic document listing synchronization from the vector database
- Enter a question and submit it scoped strictly to the current workspace
- See the generated answer and retrieved sources
- Handles empty retrieval and API errors clearly
- Seamless workspace switching / resumption

All actions call the KIP backend API at the configured base URL with the
X-KIP-Workspace-ID header.
"""

import io
import os
import secrets

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.getenv("KIP_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_DOCS = f"{API_BASE}/docs"
DOCUMENTS_ENDPOINT = f"{API_BASE}/api/v1/documents"
RAG_ENDPOINT = f"{API_BASE}/api/v1/rag/answer"
HEALTH_ENDPOINT = f"{API_BASE}/health"

SUPPORTED_TYPES = ["txt", "md", "markdown", "pdf", "docx"]
MAX_UPLOAD_MB = 2

st.set_page_config(
    page_title="KIP — Knowledge Intelligence Platform",
    page_icon="🧠",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "workspace_id" not in st.session_state or not st.session_state.workspace_id:
    st.session_state.workspace_id = secrets.token_urlsafe(32)

if "uploaded_docs" not in st.session_state:
    st.session_state.uploaded_docs = []
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []
if "last_query" not in st.session_state:
    st.session_state.last_query = ""
if "docs_loaded_for_ws" not in st.session_state:
    st.session_state.docs_loaded_for_ws = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_headers() -> dict[str, str]:
    ws_id = st.session_state.get("workspace_id", "")
    return {"X-KIP-Workspace-ID": ws_id}


def _is_local_url(url: str) -> bool:
    """Check if the given API base URL points to a local development server."""
    lower = url.lower()
    return "localhost" in lower or "127.0.0.1" in lower or "0.0.0.0" in lower


@st.cache_data(ttl=15, show_spinner=False)
def _check_backend_status(
    api_base: str = API_BASE, timeout: int | None = None
) -> tuple[bool, str]:
    """Check health of the backend API with deployment-aware messaging.

    Tolerates Render free-tier cold starts without blocking the UI indefinitely.
    Returns:
        tuple[bool, str]: (is_healthy, status_message)
    """
    health_url = f"{api_base}/health"
    if timeout is None:
        timeout = 3 if _is_local_url(api_base) else 10

    try:
        r = requests.get(health_url, timeout=timeout)
        if r.status_code == 200:
            return True, "✅ Backend is running"
        return (
            False,
            f"⚠️ Backend returned unexpected status HTTP {r.status_code} at `{api_base}`.",
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        if not _is_local_url(api_base):
            return (
                False,
                "⏳ Backend is waking up. The free Render instance may take "
                "up to a minute after inactivity. Try again shortly.",
            )
        return (
            False,
            f"⚠️ Backend is not reachable at `{api_base}`. Start it with:\n"
            "```\ncd backend && uvicorn app.main:app --reload\n```",
        )
    except Exception:
        if not _is_local_url(api_base):
            return (
                False,
                "⏳ Backend is waking up. The free Render instance may take "
                "up to a minute after inactivity. Try again shortly.",
            )
        return (
            False,
            f"⚠️ Backend is not reachable at `{api_base}`. Start it with:\n"
            "```\ncd backend && uvicorn app.main:app --reload\n```",
        )


def _backend_healthy(api_base: str = API_BASE, timeout: int | None = None) -> bool:
    """Check if the backend is currently healthy and reachable."""
    healthy, _ = _check_backend_status(api_base, timeout=timeout)
    return healthy


def _fetch_workspace_documents(timeout: int | None = None) -> list[dict]:
    """Fetch indexed documents for the current workspace.

    Tolerates Render cold-starts with production timeout consistent with upload/query.
    """
    if timeout is None:
        timeout = 30 if _is_local_url(API_BASE) else 60
    try:
        response = requests.get(
            DOCUMENTS_ENDPOINT,
            headers=_get_headers(),
            timeout=timeout,
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []


def _upload_document(file_bytes: bytes, filename: str, content_type: str) -> dict:
    files = {"file": (filename, io.BytesIO(file_bytes), content_type)}
    response = requests.post(
        DOCUMENTS_ENDPOINT,
        headers=_get_headers(),
        files=files,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _ask_question(query: str, top_k: int) -> dict:
    payload = {"query": query, "top_k": top_k}
    response = requests.post(
        RAG_ENDPOINT,
        headers=_get_headers(),
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _api_error_message(exc: requests.HTTPError) -> str:
    try:
        body = exc.response.json()
        if "detail" in body:
            return str(body["detail"])
        error = body.get("error", {})
        return f"[{error.get('code', 'error')}] {error.get('message', str(exc))}"
    except Exception:
        return str(exc)


# Synchronize documents from backend if workspace switched or on initial load
if (
    hasattr(st, "runtime")
    and st.runtime.exists()
    and st.session_state.docs_loaded_for_ws != st.session_state.workspace_id
):
    st.session_state.uploaded_docs = _fetch_workspace_documents()
    st.session_state.docs_loaded_for_ws = st.session_state.workspace_id


# ---------------------------------------------------------------------------
# Sidebar — Workspace Management
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("🏢 Workspace")
    st.caption("Each workspace is completely isolated from other users.")

    st.text_input(
        "Current Workspace Token",
        value=st.session_state.workspace_id,
        help="Copy this token to resume this workspace from any device.",
        key="current_ws_display",
        disabled=True,
    )

    if st.button("🆕 Create New Workspace", use_container_width=True):
        st.session_state.workspace_id = secrets.token_urlsafe(32)
        st.session_state.uploaded_docs = []
        st.session_state.last_answer = None
        st.session_state.last_sources = []
        st.session_state.last_query = ""
        st.session_state.docs_loaded_for_ws = st.session_state.workspace_id
        st.rerun()

    st.divider()
    st.subheader("Switch / Resume")
    resume_token = st.text_input(
        "Enter existing token",
        placeholder="Paste workspace token...",
        key="resume_input",
    )
    if st.button("🔗 Connect to Workspace", use_container_width=True):
        token_clean = resume_token.strip()
        if token_clean and len(token_clean) >= 8:
            st.session_state.workspace_id = token_clean
            st.session_state.uploaded_docs = _fetch_workspace_documents()
            st.session_state.docs_loaded_for_ws = token_clean
            st.session_state.last_answer = None
            st.session_state.last_sources = []
            st.session_state.last_query = ""
            st.rerun()
        else:
            st.error("Please enter a valid workspace token (minimum 8 characters).")

    if st.button("🔄 Refresh Documents", use_container_width=True):
        st.session_state.uploaded_docs = _fetch_workspace_documents()
        st.rerun()

    st.divider()
    st.info(
        "ℹ️ **Security Model:** Workspace access currently uses a private "
        "workspace token. Anyone who possesses the token can access that workspace. "
        "Full account authentication is planned for a later milestone."
    )


# ---------------------------------------------------------------------------
# UI — Header
# ---------------------------------------------------------------------------

st.title("🧠 Knowledge Intelligence Platform")
st.caption(
    "Upload documents, build a workspace knowledge base, and ask questions using RAG. "
    f"Backend: `{API_BASE}` · [API Docs]({API_DOCS})"
)

# Backend status banner
if hasattr(st, "runtime") and st.runtime.exists():
    backend_ok, status_msg = _check_backend_status(API_BASE)
    if backend_ok:
        st.success(status_msg, icon=None)
    elif "waking up" in status_msg:
        st.warning(status_msg, icon=None)
        if st.button("🔄 Check Status Now", key="retry_health_check"):
            st.cache_data.clear()
            st.rerun()
    else:
        st.error(status_msg, icon=None)

st.divider()

# ---------------------------------------------------------------------------
# Layout: two columns
# ---------------------------------------------------------------------------

col_left, col_right = st.columns([1, 1], gap="large")

# ---------------------------------------------------------------------------
# Left column: Document upload & Workspace Documents
# ---------------------------------------------------------------------------

with col_left:
    st.subheader("📄 Upload Documents")

    uploaded_file = st.file_uploader(
        "Upload a document to index into this workspace",
        type=SUPPORTED_TYPES,
        help=f"Supported: {', '.join(f'.{t}' for t in SUPPORTED_TYPES)}. Max {MAX_UPLOAD_MB} MB.",
        key="file_uploader",
    )

    top_k = st.slider(
        "Top-K retrieved chunks",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
        help="Number of chunks to retrieve for answering questions.",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_size_mb = len(file_bytes) / (1024 * 1024)

        if file_size_mb > MAX_UPLOAD_MB:
            st.error(
                f"File is {file_size_mb:.1f} MB. Maximum allowed is {MAX_UPLOAD_MB} MB."
            )
        else:
            with st.spinner(f"Uploading and indexing '{uploaded_file.name}'…"):
                try:
                    result = _upload_document(
                        file_bytes,
                        uploaded_file.name,
                        uploaded_file.type or "application/octet-stream",
                    )
                    chunks_indexed = result.get("chunks_indexed", 0)

                    # Refresh workspace documents from backend
                    st.session_state.uploaded_docs = _fetch_workspace_documents()

                    if chunks_indexed > 0:
                        st.success(
                            f"✅ **{result['filename']}** newly indexed successfully — "
                            f"{chunks_indexed} chunks stored."
                        )
                    else:
                        st.info(
                            f"ℹ️ **{result['filename']}** was already indexed in this workspace."
                        )
                except requests.HTTPError as e:
                    st.error(f"Upload failed: {_api_error_message(e)}")
                except requests.ConnectionError:
                    st.error("Cannot reach the backend. Is it running?")
                except Exception as e:
                    st.error(f"Unexpected error during upload: {e}")

    # Indexed documents list
    st.divider()
    if st.session_state.uploaded_docs:
        st.markdown("#### 📚 Workspace Documents")
        for doc in st.session_state.uploaded_docs:
            doc_id = doc.get("document_id", doc.get("id", "unknown"))
            chunks = doc.get("chunks_indexed", 0)
            with st.expander(
                f"📄 **{doc.get('filename', 'document')}** — {chunks} chunks",
                expanded=False,
            ):
                st.json(
                    {
                        "document_id": doc_id,
                        "media_type": doc.get("media_type", "—"),
                        "chunks_indexed": chunks,
                        "size_bytes": f"{doc.get('size_bytes', 0):,} bytes",
                        "status": doc.get("status", "indexed"),
                    }
                )
    else:
        st.info("No documents indexed in this workspace yet. Upload a file above to get started.")

# ---------------------------------------------------------------------------
# Right column: Query & Answer
# ---------------------------------------------------------------------------

with col_right:
    st.subheader("💬 Ask a Question")

    query = st.text_area(
        "Enter your question",
        value=st.session_state.last_query,
        height=100,
        placeholder="What is the main topic of the uploaded document?",
        key="query_input",
    )

    ask_btn = st.button("🔍 Ask", type="primary", use_container_width=True)

    if ask_btn:
        if not query.strip():
            st.warning("Please enter a question before submitting.")
        else:
            st.session_state.last_query = query
            with st.spinner("Retrieving workspace context and generating answer…"):
                try:
                    data = _ask_question(query.strip(), top_k)
                    st.session_state.last_answer = data.get("answer", "")
                    st.session_state.last_sources = data.get("sources", [])
                except requests.HTTPError as e:
                    st.session_state.last_answer = None
                    st.error(f"Query failed: {_api_error_message(e)}")
                except requests.ConnectionError:
                    st.session_state.last_answer = None
                    st.error("Cannot reach the backend. Is it running?")
                except Exception as e:
                    st.session_state.last_answer = None
                    st.error(f"Unexpected error: {e}")

    # Display answer
    if st.session_state.last_answer is not None:
        st.markdown("#### 💡 Answer")
        st.success(st.session_state.last_answer, icon="🤖")

        sources = st.session_state.last_sources
        if sources:
            st.markdown(f"#### 🔎 Sources ({len(sources)} retrieved)")
            for i, src in enumerate(sources, start=1):
                score = src.get("score")
                score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
                doc_id = src.get("document_id", "Unknown")

                with st.expander(
                    f"[{i}] Document: {doc_id} (Score: {score_str})",
                    expanded=(i == 1),
                ):
                    st.caption(
                        f"**Chunk ID:** `{src.get('chunk_id', '—')}` | **Rank:** {src.get('rank', i)}"
                    )
                    st.markdown(f"```text\n{src.get('text', '')}\n```")
        else:
            st.info(
                "ℹ️ No relevant context was found in the workspace knowledge base for this question. "
                "Try uploading a document that contains the answer first."
            )

st.divider()
st.caption(
    "KIP v1.1.0 · Knowledge Intelligence Platform · "
    "Powered by FastAPI + ChromaDB / Qdrant + configurable AI providers. · "
    "For evaluation and research use."
)
