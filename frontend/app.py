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
FEEDBACK_ENDPOINT = f"{API_BASE}/api/v1/feedback"
HEALTH_ENDPOINT = f"{API_BASE}/health"

SUPPORTED_TYPES = ["txt", "md", "markdown", "pdf", "docx"]
MAX_UPLOAD_MB = 2

st.set_page_config(
    page_title="KIP — Knowledge Intelligence Platform",
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
if "last_query_error" not in st.session_state:
    st.session_state.last_query_error = None
if "query_key_version" not in st.session_state:
    st.session_state.query_key_version = 0
if "docs_loaded_for_ws" not in st.session_state:
    st.session_state.docs_loaded_for_ws = None
if "uploader_key_version" not in st.session_state:
    st.session_state.uploader_key_version = 0
if "last_index_result" not in st.session_state:
    st.session_state.last_index_result = None
if "last_index_results" not in st.session_state:
    st.session_state.last_index_results = []
if "feedback_status" not in st.session_state:
    st.session_state.feedback_status = None
if "feedback_key_version" not in st.session_state:
    st.session_state.feedback_key_version = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_headers() -> dict[str, str]:
    ws_id = st.session_state.get("workspace_id", "")
    return {"X-KIP-Workspace-ID": ws_id}


def _resolve_document_name(doc_id: str, uploaded_docs: list[dict]) -> str:
    """Resolve a document ID to its original filename from workspace documents."""
    for doc in uploaded_docs:
        if doc.get("document_id") == doc_id or doc.get("id") == doc_id:
            filename = doc.get("filename")
            if filename:
                return str(filename)
    if doc_id and len(doc_id) > 16:
        return f"Document {doc_id[:8]}…"
    return doc_id or "Document"


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
    if st.session_state.docs_loaded_for_ws is not None:
        st.session_state.last_query = ""
        st.session_state.last_answer = None
        st.session_state.last_sources = []
        st.session_state.last_query_error = None
        st.session_state.query_key_version += 1
    st.session_state.uploaded_docs = _fetch_workspace_documents()
    st.session_state.docs_loaded_for_ws = st.session_state.workspace_id


# ---------------------------------------------------------------------------
# Sidebar — Workspace Management
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Workspace")
    st.caption("Each workspace is isolated from other workspaces.")

    st.markdown("**Workspace access token**")
    st.code(st.session_state.workspace_id, language=None)
    st.caption(
        "Keep this token to resume this workspace from another browser or device."
    )

    if st.button("Create New Workspace", use_container_width=True):
        st.session_state.workspace_id = secrets.token_urlsafe(32)
        st.session_state.uploaded_docs = []
        st.session_state.last_answer = None
        st.session_state.last_sources = []
        st.session_state.last_query = ""
        st.session_state.last_query_error = None
        st.session_state.query_key_version += 1
        st.session_state.docs_loaded_for_ws = st.session_state.workspace_id
        st.session_state.last_index_result = None
        st.session_state.last_index_results = []
        st.rerun()

    st.divider()
    st.subheader("Resume existing workspace")
    st.caption("Paste a workspace access token to reconnect to an existing workspace.")
    resume_token = st.text_input(
        "Workspace access token",
        placeholder="Paste workspace access token…",
        key="resume_input",
        label_visibility="collapsed",
    )
    if st.button("Connect", use_container_width=True):
        token_clean = resume_token.strip()
        if token_clean and len(token_clean) >= 8:
            st.session_state.workspace_id = token_clean
            st.session_state.uploaded_docs = _fetch_workspace_documents()
            st.session_state.docs_loaded_for_ws = token_clean
            st.session_state.last_answer = None
            st.session_state.last_sources = []
            st.session_state.last_query = ""
            st.session_state.last_query_error = None
            st.session_state.query_key_version += 1
            st.session_state.last_index_result = None
            st.session_state.last_index_results = []
            st.rerun()
        else:
            st.error("Please enter a valid workspace token (minimum 8 characters).")

    if st.button("Reload Documents", use_container_width=True):
        st.session_state.uploaded_docs = _fetch_workspace_documents()
        st.rerun()

    st.divider()
    st.caption(
        "ℹ️ **Security Note:** Anyone possessing this workspace access token "
        "can access and query documents in this workspace."
    )


# ---------------------------------------------------------------------------
# UI — Header
# ---------------------------------------------------------------------------

st.title("KIP — Knowledge Intelligence Platform")
st.caption("Workspace knowledge, retrieval, and grounded generation")

# Compact operational status
if hasattr(st, "runtime") and st.runtime.exists():
    backend_ok, status_msg = _check_backend_status(API_BASE)
    if backend_ok:
        st.caption(
            f"● **Operational** · API connected (`{API_BASE}`) · [Docs]({API_DOCS})"
        )
    elif "waking up" in status_msg:
        st.warning(
            "⏳ **Backend waking up** — The free Render instance may take "
            "up to a minute after inactivity. Please wait or check status.",
            icon=None,
        )
        if st.button("Check Status Now", key="retry_health_check"):
            st.cache_data.clear()
            st.rerun()
    else:
        st.error(status_msg, icon=None)

# Public orientation section
with st.expander("👋 Welcome to KIP — Start Here", expanded=False):
    st.markdown("### Welcome to KIP")
    st.markdown(
        "KIP (Knowledge Intelligence Platform) is a multi-document RAG system "
        "that lets you upload documents, retrieve relevant knowledge, and ask grounded "
        "questions about them."
    )
    st.markdown("#### How to test")
    st.markdown(
        "1. Upload one or more TXT, Markdown, PDF, or DOCX files.\n"
        "2. Ask a question about the uploaded documents.\n"
        "3. Try a cross-document question.\n"
        "4. Try a question whose answer is NOT in the documents.\n"
        "5. Check whether the returned answer is actually supported by the sources."
    )
    st.markdown("#### What helps us")
    st.markdown(
        "We are especially looking for:\n"
        "- incorrect or unsupported answers\n"
        "- irrelevant retrieval\n"
        "- missing information\n"
        "- cross-document mistakes\n"
        "- unexpected errors\n"
        "- slow or confusing behavior\n"
        "- UX problems\n"
        "- improvement ideas"
    )

st.divider()

# ---------------------------------------------------------------------------
# Layout: two columns
# ---------------------------------------------------------------------------

col_left, col_right = st.columns([1, 1], gap="large")

# ---------------------------------------------------------------------------
# Left column: Document upload & Workspace Documents
# ---------------------------------------------------------------------------

with col_left:
    st.subheader("Upload Documents")

    uploader_key = f"file_uploader_{st.session_state.uploader_key_version}"
    uploaded_files = st.file_uploader(
        "Select documents to index into this workspace",
        type=SUPPORTED_TYPES,
        accept_multiple_files=True,
        help=f"Supported: {', '.join(f'.{t}' for t in SUPPORTED_TYPES)}. Max {MAX_UPLOAD_MB} MB per file.",
        key=uploader_key,
    )

    top_k = st.slider(
        "Top-K retrieved chunks",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
        help="Number of chunks to retrieve for answering questions.",
    )

    if uploaded_files:
        count = len(uploaded_files)
        doc_word = "Document" if count == 1 else "Documents"
        st.markdown(f"**Selected {count} {doc_word}:**")

        oversized_files = []
        for uf in uploaded_files:
            file_bytes = uf.getvalue()
            file_size_mb = len(file_bytes) / (1024 * 1024)
            ext = (
                uf.name.rsplit(".", 1)[-1].upper()
                if "." in uf.name
                else "FILE"
            )
            if file_size_mb > MAX_UPLOAD_MB:
                oversized_files.append((uf.name, file_size_mb))
                st.markdown(
                    f"- ⚠️ `{uf.name}` *({file_size_mb:.2f} MB · {ext})* — **Exceeds {MAX_UPLOAD_MB} MB limit**"
                )
            else:
                st.markdown(
                    f"- 📄 `{uf.name}` *({file_size_mb:.2f} MB · {ext})*"
                )

        if oversized_files:
            oversized_names = ", ".join(f"'{name}'" for name, _ in oversized_files)
            st.error(
                f"File size exceeds maximum allowed {MAX_UPLOAD_MB} MB: {oversized_names}. "
                "Please remove oversized files to proceed."
            )
        else:
            button_label = f"Index {count} {doc_word}"
            if st.button(button_label, type="primary", use_container_width=True):
                results = []
                for uf in uploaded_files:
                    file_bytes = uf.getvalue()
                    file_size_mb = len(file_bytes) / (1024 * 1024)
                    if file_size_mb > MAX_UPLOAD_MB:
                        results.append({
                            "status": "FAILED",
                            "filename": uf.name,
                            "error": f"File size ({file_size_mb:.1f} MB) exceeds maximum allowed {MAX_UPLOAD_MB} MB.",
                        })
                        continue

                    with st.spinner(f"Indexing '{uf.name}'…"):
                        try:
                            result = _upload_document(
                                file_bytes,
                                uf.name,
                                uf.type or "application/octet-stream",
                            )
                            chunks_indexed = result.get("chunks_indexed", 0)
                            if chunks_indexed > 0:
                                results.append({
                                    "status": "SUCCESS",
                                    "filename": result.get("filename", uf.name),
                                    "chunks": chunks_indexed,
                                })
                            else:
                                results.append({
                                    "status": "ALREADY INDEXED",
                                    "filename": result.get("filename", uf.name),
                                    "chunks": 0,
                                })
                        except requests.HTTPError as e:
                            results.append({
                                "status": "FAILED",
                                "filename": uf.name,
                                "error": _api_error_message(e),
                            })
                        except requests.ConnectionError:
                            results.append({
                                "status": "FAILED",
                                "filename": uf.name,
                                "error": "Cannot reach the backend. Is it running?",
                            })
                        except Exception as e:
                            results.append({
                                "status": "FAILED",
                                "filename": uf.name,
                                "error": str(e),
                            })

                st.session_state.last_index_results = results
                if results:
                    st.session_state.last_index_result = {
                        "success": any(r["status"] == "SUCCESS" for r in results),
                        "filename": results[0].get("filename", ""),
                        "chunks": results[0].get("chunks", 0),
                    }
                # Synchronize documents list
                st.session_state.uploaded_docs = _fetch_workspace_documents()
                # Reset file uploader widget safely
                st.session_state.uploader_key_version += 1
                st.rerun()

    # Display indexing feedback if present
    if st.session_state.last_index_results:
        for res in st.session_state.last_index_results:
            status = res.get("status")
            filename = res.get("filename", "Document")
            if status == "SUCCESS":
                chunks = res.get("chunks", 0)
                st.success(
                    f"✅ **{filename}** newly indexed successfully — {chunks} chunks stored."
                )
            elif status == "ALREADY INDEXED":
                st.info(
                    f"ℹ️ **{filename}** was already indexed in this workspace."
                )
            elif status == "FAILED":
                err = res.get("error", "Indexing failed")
                st.error(
                    f"❌ **{filename}** failed: {err}"
                )
    elif st.session_state.last_index_result:
        idx_res = st.session_state.last_index_result
        if idx_res.get("chunks", 0) > 0:
            st.success(
                f"✅ **{idx_res['filename']}** newly indexed successfully — "
                f"{idx_res['chunks']} chunks stored."
            )
        else:
            st.info(
                f"ℹ️ **{idx_res['filename']}** was already indexed in this workspace."
            )

    # Indexed documents list
    st.divider()
    if st.session_state.uploaded_docs:
        st.markdown("#### Workspace Documents")
        seen_doc_ids = set()
        for doc in st.session_state.uploaded_docs:
            doc_id = doc.get("document_id", doc.get("id", "unknown"))
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            chunks = doc.get("chunks_indexed", 0)
            filename = doc.get("filename", "document")
            with st.expander(
                f"📄 {filename} — {chunks} chunks",
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
        st.info(
            "No documents indexed in this workspace yet. "
            "Select documents above and click Index."
        )

# ---------------------------------------------------------------------------
# Right column: Query & Answer
# ---------------------------------------------------------------------------

with col_right:
    st.subheader("Ask a Question")

    query_key = f"query_input_{st.session_state.query_key_version}"
    query = st.text_area(
        "Enter your question",
        value=st.session_state.last_query,
        height=100,
        placeholder="What is the main topic of the uploaded document?",
        key=query_key,
    )

    ask_btn = st.button("Ask", type="primary", use_container_width=True)

    if ask_btn:
        if not query.strip():
            st.warning("Please enter a question before submitting.")
        else:
            st.session_state.last_query = query
            st.session_state.last_query_error = None
            with st.spinner("Retrieving workspace context and generating answer…"):
                try:
                    data = _ask_question(query.strip(), top_k)
                    st.session_state.last_answer = data.get("answer", "")
                    st.session_state.last_sources = data.get("sources", [])
                except requests.HTTPError as e:
                    st.session_state.last_answer = None
                    st.session_state.last_sources = []
                    err_msg = f"Query failed: {_api_error_message(e)}"
                    st.session_state.last_query_error = err_msg
                    st.error(err_msg)
                except requests.ConnectionError:
                    st.session_state.last_answer = None
                    st.session_state.last_sources = []
                    err_msg = "Cannot reach the backend. Is it running?"
                    st.session_state.last_query_error = err_msg
                    st.error(err_msg)
                except Exception as e:
                    st.session_state.last_answer = None
                    st.session_state.last_sources = []
                    err_msg = f"Unexpected error: {e}"
                    st.session_state.last_query_error = err_msg
                    st.error(err_msg)

    # Display answer
    if st.session_state.last_answer is not None:
        st.markdown("#### Answer")
        st.write(st.session_state.last_answer)

        sources = st.session_state.last_sources
        if sources:
            st.divider()
            st.markdown(f"##### Sources ({len(sources)})")
            for i, src in enumerate(sources, start=1):
                doc_id = src.get("document_id", "")
                filename = _resolve_document_name(
                    doc_id, st.session_state.uploaded_docs
                )
                score = src.get("score")
                score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
                rank = src.get("rank", i)
                chunk_id = src.get("chunk_id", "—")
                excerpt = src.get("text", "")

                st.markdown(f"**{i}. {filename}**")
                st.caption(f"Chunk {rank} · Relevance: {score_str}")

                with st.expander("▸ View retrieved excerpt", expanded=False):
                    st.text(excerpt)
                    st.caption(f"Chunk ID: `{chunk_id}` · Document ID: `{doc_id}`")
        else:
            st.divider()
            st.info(
                "No relevant context was found in the workspace knowledge base for this question. "
                "Try uploading a document that contains the answer first."
            )

st.divider()

# Feedback collection
with st.expander("💬 Help Improve KIP", expanded=False):
    st.subheader("Help Improve KIP")
    st.caption(
        "Found a bug, incorrect answer, retrieval problem, confusing behavior, or improvement idea?"
    )
    fb_category = st.selectbox(
        "Category",
        options=[
            "Bug",
            "Incorrect Answer",
            "Retrieval",
            "UX",
            "Performance",
            "Improvement Idea",
            "Other",
        ],
        key="feedback_category_select",
    )
    fb_key = f"feedback_msg_{st.session_state.feedback_key_version}"
    fb_message = st.text_area(
        "Feedback (up to 30 words)",
        height=80,
        placeholder="Describe the issue or suggestion…",
        key=fb_key,
    )
    fb_words = fb_message.strip().split() if fb_message.strip() else []
    fb_word_count = len(fb_words)
    st.caption(f"{fb_word_count} / 30 words")

    fb_send_btn = st.button("Send Feedback", key="send_feedback_btn")
    if fb_send_btn:
        if fb_word_count == 0:
            st.warning("Please enter feedback before submitting.")
        elif fb_word_count > 30:
            st.error(
                f"Feedback exceeds maximum of 30 words ({fb_word_count} / 30 words). Please shorten before sending."
            )
        else:
            try:
                fb_payload = {
                    "category": fb_category,
                    "message": fb_message.strip(),
                    "workspace_id": st.session_state.workspace_id,
                }
                res = requests.post(FEEDBACK_ENDPOINT, json=fb_payload, timeout=10)
                res.raise_for_status()
                st.session_state.feedback_status = (
                    "success",
                    "Thanks — your feedback has been recorded.",
                )
                st.session_state.feedback_key_version += 1
                st.rerun()
            except requests.HTTPError as e:
                err_msg = _api_error_message(e)
                st.session_state.feedback_status = (
                    "error",
                    f"Feedback submission failed: {_api_error_message(e)}",
                )
            except Exception as e:
                st.session_state.feedback_status = (
                    "error",
                    f"Feedback submission failed: {e}",
                )

    if st.session_state.feedback_status:
        kind, text = st.session_state.feedback_status
        if kind == "success":
            st.success(text)
        else:
            st.error(text)

st.caption(
    "KIP v1.1.0 · Knowledge Intelligence Platform · "
    "FastAPI + ChromaDB / Qdrant multi-tenant cloud architecture."
)
