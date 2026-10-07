"""KIP v1.0 Streamlit Frontend.

Minimal, functional interface for the Knowledge Intelligence Platform.

What it provides:
- Upload a document (TXT, Markdown, PDF, DOCX)
- See indexing success/failure with chunk count
- Enter a question and submit it
- See the generated answer and retrieved sources
- Handles empty retrieval and API errors clearly

What it does NOT do:
- Duplicate backend logic
- Authenticate users
- Store conversation history
- Make direct calls to LLM or vector store
- Implement agent workflows

All actions call the KIP backend API at the configured base URL.
"""

import io

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "http://127.0.0.1:8000"
API_DOCS = f"{API_BASE}/docs"
UPLOAD_ENDPOINT = f"{API_BASE}/api/v1/documents"
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

if "uploaded_docs" not in st.session_state:
    st.session_state.uploaded_docs = []  # list[dict]
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []
if "last_query" not in st.session_state:
    st.session_state.last_query = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _backend_healthy() -> bool:
    try:
        r = requests.get(HEALTH_ENDPOINT, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _upload_document(file_bytes: bytes, filename: str, content_type: str) -> dict:
    files = {"file": (filename, io.BytesIO(file_bytes), content_type)}
    response = requests.post(UPLOAD_ENDPOINT, files=files, timeout=60)
    response.raise_for_status()
    return response.json()


def _ask_question(query: str, top_k: int) -> dict:
    payload = {"query": query, "top_k": top_k}
    response = requests.post(RAG_ENDPOINT, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def _api_error_message(exc: requests.HTTPError) -> str:
    try:
        body = exc.response.json()
        error = body.get("error", {})
        return f"[{error.get('code', 'error')}] {error.get('message', str(exc))}"
    except Exception:
        return str(exc)


# ---------------------------------------------------------------------------
# UI — Header
# ---------------------------------------------------------------------------

st.title("🧠 Knowledge Intelligence Platform")
st.caption(
    "Upload documents, build a knowledge base, and ask questions using RAG. "
    f"Backend: `{API_BASE}` · [API Docs]({API_DOCS})"
)

# Backend status banner
if _backend_healthy():
    st.success("✅ Backend is running", icon=None)
else:
    st.error(
        "⚠️ Backend is not reachable at "
        f"`{API_BASE}`. Start it with:\n"
        "```\n"
        "cd backend && uvicorn app.main:app --reload\n"
        "```",
        icon=None,
    )

st.divider()

# ---------------------------------------------------------------------------
# Layout: two columns
# ---------------------------------------------------------------------------

col_left, col_right = st.columns([1, 1], gap="large")

# ---------------------------------------------------------------------------
# Left column: Document upload
# ---------------------------------------------------------------------------

with col_left:
    st.subheader("📄 Upload Documents")

    uploaded_file = st.file_uploader(
        "Upload a document to index into the knowledge base",
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
                    
                    doc_info = {
                        "id": result["id"],
                        "filename": result["filename"],
                        "media_type": result["media_type"],
                        "chunks_indexed": chunks_indexed,
                        "size_bytes": len(file_bytes),
                        "metadata": result.get("metadata", {}),
                        "status": "Newly indexed" if chunks_indexed > 0 else "Already indexed",
                    }
                    
                    # Prevent duplicate logical entries in the UI session list
                    existing_ids = {d["id"] for d in st.session_state.uploaded_docs}
                    if result["id"] not in existing_ids:
                        st.session_state.uploaded_docs.append(doc_info)
                    
                    if chunks_indexed > 0:
                        st.success(
                            f"✅ **{result['filename']}** newly indexed successfully — "
                            f"{chunks_indexed} chunks stored."
                        )
                    else:
                        st.info(
                            f"ℹ️ **{result['filename']}** was already indexed in the knowledge base."
                        )
                except requests.HTTPError as e:
                    st.error(f"Upload failed: {_api_error_message(e)}")
                except requests.ConnectionError:
                    st.error("Cannot reach the backend. Is it running?")
                except Exception as e:
                    st.error(f"Unexpected error during upload: {e}")

    # Indexed documents table
    st.divider()
    if st.session_state.uploaded_docs:
        st.markdown("#### 📚 Indexed Documents This Session")
        for doc in st.session_state.uploaded_docs:
            with st.expander(
                f"📄 **{doc['filename']}** — {doc['chunks_indexed']} chunks ({doc['status']})", expanded=False
            ):
                st.json(
                    {
                        "document_id": doc["id"],
                        "media_type": doc["media_type"],
                        "chunks_indexed": doc["chunks_indexed"],
                        "size_bytes": f"{doc['size_bytes']:,} bytes",
                        "parser": doc["metadata"].get("parser", "—"),
                    }
                )
    else:
        st.info("No documents indexed in this session yet. Upload a file above to get started.")

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
            with st.spinner("Retrieving context and generating answer…"):
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
                    st.caption(f"**Chunk ID:** `{src.get('chunk_id', '—')}` | **Rank:** {src.get('rank', i)}")
                    st.markdown(f"```text\n{src.get('text', '')}\n```")
        else:
            st.info(
                "ℹ️ No relevant context was found in the knowledge base for this question. "
                "Try uploading a document that contains the answer first."
            )

st.divider()
st.caption(
    "KIP v1.0 · Knowledge Intelligence Platform · "
    "Powered by FastAPI + ChromaDB + configurable AI providers. · "
    "For evaluation and research use."
)
