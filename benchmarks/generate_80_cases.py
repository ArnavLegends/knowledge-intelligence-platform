"""Generate 80 labelled benchmark cases for KIP v1.2 expanded benchmark.

Loads derived document and chunk IDs from benchmarks/corpus_v1_2_expanded_ids.json,
constructs 80 grounded benchmark cases across 6 challenge categories, and writes
benchmarks/kip_v1_2_expanded_benchmark.json.
"""

import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MAPPING_PATH = REPO_ROOT / "benchmarks" / "corpus_v1_2_expanded_ids.json"
BENCHMARK_PATH = REPO_ROOT / "benchmarks" / "kip_v1_2_expanded_benchmark.json"

mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
doc_ids = mapping["doc_ids"]
chunk_ids = mapping["chunk_ids"]


def make_case(cid, q, ans, docs, keywords, cat, extra=None):
    return {
        "id": cid,
        "question": q,
        "reference_answer": ans,
        "expected_document_ids": [doc_ids[d] for d in docs],
        "expected_chunk_ids": [chunk_ids[d] for d in docs],
        "expected_keywords": keywords,
        "metadata": {
            "category": cat,
            "corpus_docs": docs,
            **(extra or {}),
        },
    }


cases = []

# ===========================================================================
# Category 1: Exact Terminology & Entity Lookups (16 cases: exp-001 to exp-016)
# ===========================================================================
cases.append(
    make_case(
        "exp-001",
        "What HTTP header must accompany every workspace-scoped API request in KIP?",
        "Every workspace-scoped request must supply the X-KIP-Workspace-ID header.",
        ["kip_multitenancy_architecture.txt"],
        ["X-KIP-Workspace-ID", "header", "workspace"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-002",
        "What is the maximum upload file size in bytes supported by KIP document parsers?",
        "The maximum upload size limit is 2097152 bytes (2 MB).",
        ["kip_document_parsers.txt"],
        ["2097152", "2 MB", "maximum upload"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-003",
        "What are the default character chunk size and overlap values in KIP?",
        "The default chunk size is 1000 characters with 200 characters of overlap.",
        ["kip_chunking_and_embeddings.txt"],
        ["1000", "200", "overlap"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-004",
        "What is the effective step size in characters between consecutive chunk starts?",
        "The effective step size is 800 characters between chunk start positions.",
        ["kip_chunking_and_embeddings.txt"],
        ["800", "step size", "start positions"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-005",
        "What is the default Qdrant vector store collection name used by KIP?",
        "KIP uses a default Qdrant collection named knowledge_base.",
        ["kip_retrieval_and_rag.txt"],
        ["knowledge_base", "collection", "Qdrant"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-006",
        "How many dimensions does the production Gemini embedding model generate in KIP?",
        "The gemini-embedding-2 model produces 768-dimensional dense vectors.",
        ["kip_gemini_embedding_provider.txt"],
        ["768", "gemini-embedding-2", "dimensions"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-007",
        "What language model drives generative responses in KIP production deployments?",
        "The production generative model is Gemini 2.5 Flash via GeminiLLMProvider.",
        ["kip_llm_gateway.txt"],
        ["Gemini 2.5 Flash", "gemini-2.5-flash", "GeminiLLMProvider"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-008",
        "What endpoint serves the system health check in the FastAPI backend?",
        "The health check endpoint is exposed at GET /api/v1/health.",
        ["kip_docker_and_deployment.txt"],
        ["/api/v1/health", "GET", "health check"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-009",
        "What is the maximum number of documents permitted in a single workspace?",
        "A single workspace may index a maximum of 50 documents (MAX_DOCUMENTS_PER_WORKSPACE=50).",
        ["kip_batch_ingestion_limits.txt"],
        ["50", "MAX_DOCUMENTS_PER_WORKSPACE", "workspace"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-010",
        "What is the ceiling on total vector chunks allowed in a single workspace?",
        "A workspace can store up to 1000 chunks (MAX_CHUNKS_PER_WORKSPACE=1000).",
        ["kip_batch_ingestion_limits.txt"],
        ["1000", "MAX_CHUNKS_PER_WORKSPACE", "chunks"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-011",
        "What is the word limit enforced on user feedback messages?",
        "Feedback messages are strictly limited to a maximum of 30 words.",
        ["kip_feedback_webhook.txt"],
        ["30 words", "feedback", "limit"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-012",
        "What Google Apps Script HTTP handler function receives KIP feedback submissions?",
        "The Google Apps Script web app implements doGet(e) to receive HTTPS GET requests.",
        ["kip_feedback_webhook.txt"],
        ["doGet", "Google Apps Script", "GET"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-013",
        "How is Qdrant cosine distance converted to a similarity score in KIP?",
        "Qdrant converts cosine distance to a similarity score using: score = 1 - distance.",
        ["kip_retrieval_and_rag.txt"],
        ["score = 1 - distance", "cosine", "similarity"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-014",
        "What base class from Pydantic manages centralized application settings in KIP?",
        "KIP uses Pydantic BaseSettings in app.core.config.",
        ["kip_configuration_settings.txt"],
        ["BaseSettings", "Pydantic", "app.core.config"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-015",
        "What is the default temperature setting passed to LLM generation in KIP?",
        "Temperature defaults to 0.0 to ensure deterministic, reproducible generation.",
        ["kip_llm_gateway.txt"],
        ["0.0", "temperature", "deterministic"],
        "exact_terminology",
    )
)
cases.append(
    make_case(
        "exp-016",
        "What prefix is prepended to cryptographically random workspace access tokens?",
        "Workspace tokens use the wksp_ prefix and have at least 256 bits of entropy.",
        ["kip_security_threat_model.txt"],
        ["wksp_", "prefix", "tokens"],
        "exact_terminology",
    )
)

# ===========================================================================
# Category 2: Natural-Language Paraphrases (16 cases: exp-017 to exp-032)
# ===========================================================================
cases.append(
    make_case(
        "exp-017",
        "Which file types can organizations feed into their private enterprise knowledge vaults?",
        "KIP supports PDF, DOCX, TXT, and Markdown files.",
        ["kip_document_parsers.txt"],
        ["PDF", "DOCX", "TXT", "Markdown"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-018",
        "How does the platform ensure that repeatedly re-indexing a text file never duplicates data?",
        "Document IDs are derived from SHA-256 of file bytes, enabling idempotent upserts.",
        ["kip_idempotency_service.txt"],
        ["SHA-256", "idempotent", "upsert"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-019",
        "Why does the system refuse to answer inquiries when no relevant background context exists?",
        "The empty context guard short-circuits generation to eliminate hallucinations and save API costs.",
        ["kip_empty_context_guard.txt"],
        ["empty context", "refusal", "short-circuit"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-020",
        "In what way does the chat interface let people verify where factual statements came from?",
        "Expandable provenance cards display excerpt text, document name, chunk index, and similarity scores.",
        ["kip_provenance_attribution.txt"],
        ["provenance", "source reference", "chunk index"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-021",
        "How does the cloud service gracefully wake up sleeping containers on free hosting tiers?",
        "The Streamlit frontend pings the health check with exponential retry backoff while displaying a wake-up banner.",
        ["kip_cold_start_mitigation.txt"],
        ["cold start", "exponential backoff", "health check"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-022",
        "What prevents one enterprise tenant from reading another organization's confidential embeddings?",
        "Mandatory workspace_id payload filtering in Qdrant isolates tenant vectors at the database tier.",
        ["kip_multitenancy_architecture.txt"],
        ["workspace_id", "payload filter", "tenant isolation"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-023",
        "How does the software handle Word document tables so that column data remains understandable?",
        "Table cells are joined with pipe delimiters to preserve column layout relationships.",
        ["kip_docx_parser_internals.txt"],
        ["pipe delimiters", "tables", "docx"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-024",
        "What mechanism guarantees that evaluating retrieval improvements will never touch customer workspaces?",
        "EvaluationRunner explicitly injects a dedicated evaluation workspace ID such as kip-eval-workspace.",
        ["kip_evaluation_workspace_isolation.txt"],
        ["evaluation workspace", "kip-eval-workspace", "isolation"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-025",
        "How does the system ensure evaluation tests produce identical results across Windows and Linux machines?",
        "Corpus files strictly use Unix LF line endings to ensure deterministic SHA-256 hash calculation.",
        ["kip_ground_truth_derivation.txt"],
        ["LF", "SHA-256", "line endings"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-026",
        "What fallback vector database adapter allows developer testing without external cloud network calls?",
        "ChromaVectorStoreProvider initializes an ephemeral in-memory Chroma client for offline testing.",
        ["kip_chroma_provider_internals.txt"],
        ["Chroma", "in-memory", "offline testing"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-027",
        "Why does the Gemini embedding provider omit the task type parameter when generating embeddings?",
        "Google Gemini documentation states task_type is unsupported for gemini-embedding-2.",
        ["kip_gemini_embedding_provider.txt"],
        ["task_type", "unsupported", "gemini-embedding-2"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-028",
        "How does the user interface prevent session data from leaking when a person switches tenants?",
        "Switching workspaces clears the chat history and cached document lists in Streamlit session state.",
        ["kip_streamlit_frontend_state.txt"],
        ["session state", "clears", "workspace switching"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-029",
        "What prevents random web crawlers from injecting malicious feedback rows into Google Sheets?",
        "A shared secret token passed as a query parameter is authenticated by the Apps Script handler.",
        ["kip_feedback_token_security.txt"],
        ["shared secret token", "FEEDBACK_WEBHOOK_TOKEN", "authenticated"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-030",
        "How does the RAG prompt instruct the language model to handle inquiries it cannot verify?",
        "System instructions mandate that the model refuse to answer if facts are not in context.",
        ["kip_grounded_rag_prompting.txt"],
        ["strict grounding", "refuse", "context"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-031",
        "What happens when an uploaded PDF file contains password encryption?",
        "PyPDF catches PdfReadError and raises an IngestionError immediately.",
        ["kip_pdf_parser_internals.txt"],
        ["PdfReadError", "IngestionError", "password"],
        "paraphrase",
    )
)
cases.append(
    make_case(
        "exp-032",
        "How does the platform handle unexpected server crashes to avoid exposing internal tracebacks?",
        "Centralized FastAPI exception handlers return standardized RFC 7807 error responses.",
        ["kip_error_handling_protocols.txt"],
        ["RFC 7807", "centralized exception", "error_code"],
        "paraphrase",
    )
)

# ===========================================================================
# Category 3: Multi-Concept & Cross-Domain Disambiguation (16 cases: exp-033 to exp-048)
# ===========================================================================
cases.append(
    make_case(
        "exp-033",
        "How do workspace IDs propagate from HTTP request headers into Qdrant vector search filters?",
        "FastAPI extracts X-KIP-Workspace-ID, which RetrievalService attaches to Qdrant payload filters.",
        ["kip_multitenancy_architecture.txt"],
        ["X-KIP-Workspace-ID", "payload filter", "RetrievalService"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-034",
        "How does DocumentIngestionService connect file byte hashing with chunk identifier generation?",
        "Document ID is SHA-256(raw_bytes); chunk ID is SHA-256(doc_id + ':' + chunk_index).",
        ["kip_idempotency_service.txt"],
        ["SHA-256", "chunk_index", "raw_bytes"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-035",
        "How does the PDF parser attach page metadata that downstream provenance models expose to users?",
        "PyPDF annotates each page string with page_number, which Chunk metadata propagates to source cards.",
        ["kip_pdf_parser_internals.txt"],
        ["page_number", "PyPDF", "provenance"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-036",
        "How do workspace capacity limits interact with Qdrant Cloud cluster memory protections?",
        "Limits of 50 docs and 1000 chunks prevent free-tier cluster memory and API quota exhaustion.",
        ["kip_batch_ingestion_limits.txt"],
        ["50 documents", "1000 chunks", "quota exhaustion"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-037",
        "How does EmbeddingManager isolate upper retrieval services from specific third-party embedding SDKs?",
        "EmbeddingManager uses a provider registry to route embed requests to Gemini or OpenAI adapters.",
        ["kip_embedding_manager.txt"],
        ["EmbeddingManager", "provider registry", "decoupling"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-038",
        "How does QdrantVectorStoreProvider map cosine distance metrics into similarity scores?",
        "Cosine distance returned by Qdrant is transformed via score = 1 - distance, bounded [0, 1].",
        ["kip_qdrant_provider_internals.txt"],
        ["score = 1 - distance", "Cosine", "QdrantVectorStoreProvider"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-039",
        "How does RAGService coordinate query vectorization, prompt formatting, and generative LLM completion?",
        "RAGService queries RetrievalService, formats source XML blocks, and calls LLMService.",
        ["kip_rag_service_orchestration.txt"],
        ["RetrievalService", "source XML", "LLMService"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-040",
        "How do feedback modal submissions in Streamlit securely route through FastAPI to Google Sheets?",
        "Streamlit posts to FastAPI, which validates the payload and issues an authenticated HTTPS GET to Apps Script.",
        ["kip_feedback_webhook.txt"],
        ["HTTPS GET", "FastAPI", "Google Apps Script"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-041",
        "How does EvaluationRunner maintain test isolation while measuring retrieval latency and MRR?",
        "EvaluationRunner uses config.evaluation_workspace_id and times the retrieval phase in milliseconds.",
        ["kip_evaluation_framework.txt"],
        ["evaluation_workspace_id", "retrieval latency", "MRR"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-042",
        "How does KIP calculate Mean Reciprocal Rank (MRR) across labelled evaluation cases?",
        "MRR averages 1/rank of the first relevant hit across cases with populated expected IDs.",
        ["kip_retrieval_metrics_definitions.txt"],
        ["Mean Reciprocal Rank", "1/rank", "labelled cases"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-043",
        "How does the paired experiment protocol compare Control and Treatment conditions without data contamination?",
        "Both conditions evaluate identical queries over identical corpora indexed into separate Qdrant collections.",
        ["kip_paired_experiment_protocol.txt"],
        ["Control", "Treatment", "separate Qdrant collections"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-044",
        "How does the Streamlit UI layout connect file uploads with backend parsing status spinners?",
        "Document Manager renders drag-and-drop file inputs and displays a spinner while indexing.",
        ["kip_streamlit_ui_components.txt"],
        ["Document Manager", "spinner", "Streamlit"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-045",
        "How does Pydantic BaseSettings handle fallback defaults when environment variables are omitted?",
        "BaseSettings loads environment variables and falls back to defined class attributes.",
        ["kip_configuration_settings.txt"],
        ["BaseSettings", "environment variables", "fallback"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-046",
        "How does the Dockerfile configure the non-root execution environment for Render hosting?",
        "The Dockerfile uses python:3.11-slim, installs dependencies, and runs Uvicorn on port 8000.",
        ["kip_docker_and_deployment.txt"],
        ["python:3.11-slim", "Uvicorn", "non-root"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-047",
        "How does the security model ensure workspace bearer tokens cannot be guessed by adversaries?",
        "Tokens are generated with python secrets module providing at least 256 bits of cryptographic entropy.",
        ["kip_security_threat_model.txt"],
        ["256 bits", "entropy", "secrets module"],
        "multi_concept",
    )
)
cases.append(
    make_case(
        "exp-048",
        "How does the DOCX parser handle paragraph extraction without writing temporary files to disk?",
        "The parser loads raw byte streams directly into docx.Document in memory.",
        ["kip_docx_parser_internals.txt"],
        ["in memory", "docx.Document", "byte stream"],
        "multi_concept",
    )
)

# ===========================================================================
# Category 4: Hard Negative Disambiguation (16 cases: exp-049 to exp-064)
# (Targeting active architecture vs superficially similar distractors)
# ===========================================================================
cases.append(
    make_case(
        "exp-049",
        "What document chunking strategy does KIP actively implement in its production ingestion service?",
        "KIP implements fixed-size character chunking with sliding window overlap (1000/200), not semantic or recursive splitting.",
        ["kip_chunking_and_embeddings.txt"],
        ["fixed-size character chunking", "1000", "200"],
        "hard_negative",
        {"distractor_doc": "distractor_alternative_chunkers.txt"},
    )
)
cases.append(
    make_case(
        "exp-050",
        "What vector store engine powers multi-tenant cloud retrieval in active KIP deployments?",
        "KIP uses Qdrant Cloud with workspace payload filters, not local Chroma DuckDB files.",
        ["kip_qdrant_provider_internals.txt"],
        ["Qdrant Cloud", "payload filter", "knowledge_base"],
        "hard_negative",
        {"distractor_doc": "distractor_legacy_chroma_settings.txt"},
    )
)
cases.append(
    make_case(
        "exp-051",
        "Does KIP currently utilize sparse lexical search like BM25 or SPLADE in its retrieval pipeline?",
        "No, KIP uses dense vector search only; hybrid BM25 and SPLADE search are proposed research candidates.",
        ["kip_retrieval_and_rag.txt"],
        ["dense vector search", "cosine", "Qdrant"],
        "hard_negative",
        {"distractor_doc": "distractor_hybrid_search_proposals.txt"},
    )
)
cases.append(
    make_case(
        "exp-052",
        "How are benchmark evaluations conducted in KIP: through external LLM judges or mechanical metrics?",
        "KIP uses deterministic mechanical metrics (Hit Rate, MRR, keyword coverage) in runner.py, not external LLM judges like Ragas.",
        ["kip_evaluation_framework.txt"],
        ["mechanical metrics", "deterministic", "EvaluationRunner"],
        "hard_negative",
        {"distractor_doc": "distractor_external_judge_evaluators.txt"},
    )
)
cases.append(
    make_case(
        "exp-053",
        "What caching technology is deployed in KIP v1.1 to cache embedding vectors and LLM answers?",
        "KIP v1.1 has no Redis semantic cache; caching is deferred to v1.3 performance engineering.",
        ["kip_empty_context_guard.txt"],
        ["empty context guard", "bypasses LLM", "no Redis"],
        "hard_negative",
        {"distractor_doc": "distractor_redis_caching_architecture.txt"},
    )
)
cases.append(
    make_case(
        "exp-054",
        "Does KIP v1.1 support multi-turn conversational dialogue memory across successive user questions?",
        "No, KIP operates in single-turn question-answering mode; conversational memory is deferred to v2.0.",
        ["kip_streamlit_frontend_state.txt"],
        ["single-turn", "session state", "chat history"],
        "hard_negative",
        {"distractor_doc": "distractor_conversational_memory_store.txt"},
    )
)
cases.append(
    make_case(
        "exp-055",
        "What autonomous multi-step reasoning framework like LangGraph or CrewAI powers KIP workflows?",
        "KIP does not use autonomous agentic frameworks; it is a direct single-step RAG platform.",
        ["kip_rag_service_orchestration.txt"],
        ["RAGService", "direct RAG", "single-step"],
        "hard_negative",
        {"distractor_doc": "distractor_agentic_tool_calling.txt"},
    )
)
cases.append(
    make_case(
        "exp-056",
        "Does KIP store knowledge relationships in a Neo4j property graph database for GraphRAG?",
        "No, KIP relies strictly on dense vector search in Qdrant; Neo4j graph integration is deferred to v2.4.",
        ["kip_vector_store_adapters.txt"],
        ["VectorStoreProvider", "Qdrant", "dense vector"],
        "hard_negative",
        {"distractor_doc": "distractor_neo4j_knowledge_graph.txt"},
    )
)
cases.append(
    make_case(
        "exp-057",
        "How is the KIP production backend hosted: on a Kubernetes cluster or Render Free Tier?",
        "KIP is deployed as a single container on Render Free Tier, not on a distributed Kubernetes cluster.",
        ["kip_docker_and_deployment.txt"],
        ["Render Free Web Service", "Docker", "container"],
        "hard_negative",
        {"distractor_doc": "distractor_kubernetes_cluster_orchestration.txt"},
    )
)
cases.append(
    make_case(
        "exp-058",
        "What authentication standard protects KIP tenant workspaces: OAuth2/OIDC SSO or bearer tokens?",
        "KIP uses lightweight cryptographically random bearer tokens (wksp_...), not enterprise OAuth2/OIDC SSO.",
        ["kip_security_threat_model.txt"],
        ["bearer tokens", "wksp_", "256 bits"],
        "hard_negative",
        {"distractor_doc": "distractor_oauth2_sso_authentication.txt"},
    )
)
cases.append(
    make_case(
        "exp-059",
        "How are language model tokens transmitted to the UI: via streaming WebSockets or synchronous JSON?",
        "KIP processes RAG queries synchronously returning a complete response entity, not streaming WebSockets/SSE.",
        ["kip_api_specifications.txt"],
        ["synchronous", "POST /api/v1/rag/query", "response JSON"],
        "hard_negative",
        {"distractor_doc": "distractor_streaming_websocket_rag.txt"},
    )
)
cases.append(
    make_case(
        "exp-060",
        "Does the active KIP retrieval pipeline include a second-stage cross-encoder reranker like Cohere Rerank?",
        "No, KIP performs single-stage retrieval directly from Qdrant; cross-encoder reranking is a research candidate.",
        ["kip_retrieval_and_rag.txt"],
        ["single-stage", "Qdrant", "top_k"],
        "hard_negative",
        {"distractor_doc": "distractor_cohere_reranking_pipeline.txt"},
    )
)
cases.append(
    make_case(
        "exp-061",
        "Where does ChromaVectorStoreProvider store vector files during automated pytest execution?",
        "It stores vectors in memory (persist_directory=None), not in legacy disk paths like data/chroma.",
        ["kip_chroma_provider_internals.txt"],
        ["in-memory", "persist_directory is None", "ephemeral"],
        "hard_negative",
        {"distractor_doc": "distractor_legacy_chroma_settings.txt"},
    )
)
cases.append(
    make_case(
        "exp-062",
        "How does KIP prevent hallucinations: by prompting strict grounding or through post-generation Ragas checks?",
        "KIP enforces strict grounding prompt instructions in RAGService, not post-generation LLM-as-judge scoring.",
        ["kip_grounded_rag_prompting.txt"],
        ["grounding prompt", "XML source tags", "refuse"],
        "hard_negative",
        {"distractor_doc": "distractor_external_judge_evaluators.txt"},
    )
)
cases.append(
    make_case(
        "exp-063",
        "How does the Streamlit UI handle dormant backend containers on Render without caching answers in Redis?",
        "The UI polls the health endpoint with exponential retry backoff and displays a wake-up banner.",
        ["kip_cold_start_mitigation.txt"],
        ["cold start", "exponential backoff", "health check"],
        "hard_negative",
        {"distractor_doc": "distractor_redis_caching_architecture.txt"},
    )
)
cases.append(
    make_case(
        "exp-064",
        "What entity coordinates vector transformations without introducing LangChain or LlamaIndex dependencies?",
        "EmbeddingManager coordinates vector transformations through internal provider classes without framework overhead.",
        ["kip_embedding_manager.txt"],
        ["EmbeddingManager", "provider registry", "internal"],
        "hard_negative",
        {"distractor_doc": "distractor_agentic_tool_calling.txt"},
    )
)

# ===========================================================================
# Category 5: Cross-Document Multi-Target Queries (8 cases: exp-065 to exp-072)
# (Queries requiring facts from two distinct documents)
# ===========================================================================
cases.append(
    make_case(
        "exp-065",
        "How do document parser upload limits and workspace chunk capacities work together to bound tenant resource usage?",
        "Parser limits restrict individual files to 2 MB, while workspace bounds enforce maximums of 50 documents and 1000 chunks.",
        ["kip_document_parsers.txt", "kip_batch_ingestion_limits.txt"],
        ["2097152", "50 documents", "1000 chunks"],
        "cross_document",
    )
)
cases.append(
    make_case(
        "exp-066",
        "How do PDF and DOCX parsers extract structured textual information from complex business files?",
        "PyPDF extracts text page by page with page_number metadata, while python-docx extracts paragraphs and pipe-delimited tables.",
        ["kip_pdf_parser_internals.txt", "kip_docx_parser_internals.txt"],
        ["PyPDF", "python-docx", "pipe delimiters"],
        "cross_document",
    )
)
cases.append(
    make_case(
        "exp-067",
        "How does the content-addressed hashing algorithm establish deterministic document and chunk IDs?",
        "Document ID is SHA-256 of raw file bytes; chunk ID is SHA-256 of document_id and chunk_index.",
        ["kip_idempotency_service.txt", "kip_ground_truth_derivation.txt"],
        ["SHA-256", "raw_file_bytes", "chunk_index"],
        "cross_document",
    )
)
cases.append(
    make_case(
        "exp-068",
        "What embedding providers are supported in KIP and what output dimensionalities do they produce?",
        "GeminiEmbeddingProvider produces 768-dimensional vectors; OpenAIEmbeddingProvider produces 1536-dimensional vectors.",
        ["kip_gemini_embedding_provider.txt", "kip_openai_embedding_provider.txt"],
        ["768", "1536", "gemini-embedding-2", "text-embedding-3-small"],
        "cross_document",
    )
)
cases.append(
    make_case(
        "exp-069",
        "How do Qdrant Cloud and embedded Chroma vector store implementations enforce workspace tenant filtering?",
        "Qdrant applies payload FieldCondition on workspace_id; Chroma applies where={'workspace_id': workspace_id}.",
        ["kip_qdrant_provider_internals.txt", "kip_chroma_provider_internals.txt"],
        ["Qdrant", "Chroma", "workspace_id"],
        "cross_document",
    )
)
cases.append(
    make_case(
        "exp-070",
        "What language model providers can power answer generation and what models do they target?",
        "GeminiLLMProvider targets gemini-2.5-flash; OpenAILLMProvider targets gpt-4o-mini.",
        ["kip_llm_gateway.txt", "kip_openai_llm_provider.txt"],
        ["gemini-2.5-flash", "gpt-4o-mini", "GeminiLLMProvider"],
        "cross_document",
    )
)
cases.append(
    make_case(
        "exp-071",
        "How does user feedback travel from the Streamlit UI to Google Sheets with token authentication?",
        "Streamlit sends feedback to FastAPI, which dispatches an HTTPS GET request to Google Apps Script with secret token verification.",
        ["kip_feedback_webhook.txt", "kip_feedback_token_security.txt"],
        ["doGet", "FEEDBACK_WEBHOOK_TOKEN", "Google Apps Script"],
        "cross_document",
    )
)
cases.append(
    make_case(
        "exp-072",
        "How do EvaluationRunner and Pydantic benchmark schemas measure Hit Rate and Mean Reciprocal Rank?",
        "EvaluationRunner runs cases against retrieval, populating RetrievalMetrics and aggregating Hit Rate and MRR in BenchmarkResult.",
        ["kip_evaluation_framework.txt", "kip_benchmark_dataset_schema.txt"],
        ["EvaluationRunner", "RetrievalMetrics", "BenchmarkResult"],
        "cross_document",
    )
)

# ===========================================================================
# Category 6: Boundary & Failure Handling (8 cases: exp-073 to exp-080)
# ===========================================================================
cases.append(
    make_case(
        "exp-073",
        "What error is raised when a client issues a vector retrieval search without providing a workspace ID?",
        "RetrievalService raises a RetrievalError stating that workspace_id is required.",
        ["kip_error_handling_protocols.txt"],
        ["RetrievalError", "workspace_id is required", "HTTP 400"],
        "boundary_handling",
    )
)
cases.append(
    make_case(
        "exp-074",
        "How does the platform prevent denial-of-service through oversized document uploads?",
        "Document parsers reject any file whose size exceeds the MAX_UPLOAD_SIZE_BYTES limit (2097152 bytes).",
        ["kip_document_parsers.txt"],
        ["2097152", "MAX_UPLOAD_SIZE_BYTES", "rejected"],
        "boundary_handling",
    )
)
cases.append(
    make_case(
        "exp-075",
        "What happens when a search query returns zero matching vectors or all scores fall below threshold?",
        "RAGService short-circuits and returns a predefined message without calling the generation LLM.",
        ["kip_empty_context_guard.txt"],
        ["empty context", "short-circuit", "refusal"],
        "boundary_handling",
    )
)
cases.append(
    make_case(
        "exp-076",
        "What HTTP status code is returned when user feedback is submitted with an unconfigured webhook destination?",
        "FastAPI returns HTTP 503 with error code feedback_destination_unconfigured.",
        ["kip_feedback_token_security.txt"],
        ["503", "feedback_destination_unconfigured", "unconfigured"],
        "boundary_handling",
    )
)
cases.append(
    make_case(
        "exp-077",
        "How does the evaluation runner distinguish an infrastructure outage from a genuine retrieval miss?",
        "Infrastructure failures are recorded in RetrievalMetrics.retrieval_error, leaving misses with error None.",
        ["kip_benchmark_dataset_schema.txt"],
        ["retrieval_error", "infrastructure failure", "retrieval miss"],
        "boundary_handling",
    )
)
cases.append(
    make_case(
        "exp-078",
        "What happens if an unlabelled benchmark case with empty expected document IDs is evaluated?",
        "The case is marked as unlabelled and excluded from aggregate Hit Rate and MRR calculations.",
        ["kip_retrieval_metrics_definitions.txt"],
        ["unlabelled", "empty expected_document_ids", "excluded"],
        "boundary_handling",
    )
)
cases.append(
    make_case(
        "exp-079",
        "How does KIP protect database connection secrets when unexpected internal errors occur?",
        "Exception handlers sanitize error details and return RFC 7807 responses without exposing tracebacks or credentials.",
        ["kip_error_handling_protocols.txt"],
        ["sanitized", "RFC 7807", "mask"],
        "boundary_handling",
    )
)
cases.append(
    make_case(
        "exp-080",
        "What prevents benchmark ground truth IDs from breaking when running tests on Windows systems?",
        "All corpus fixtures are verified to use Unix LF line endings, preventing CRLF hash drift.",
        ["kip_ground_truth_derivation.txt"],
        ["Unix LF", "CRLF", "hash drift"],
        "boundary_handling",
    )
)

benchmark_data = {
    "version": "v1.2-expanded-benchmark",
    "description": (
        "KIP v1.2 expanded retrieval evaluation benchmark: 80 labelled cases across 6 challenge categories "
        "(exact terminology, paraphrase, multi-concept, hard negative disambiguation, cross-document, and boundary handling) "
        "evaluated against a 50-document reference corpus (corpus_v1_2_expanded). Designed to provide discriminative "
        "retrieval ranking evaluation without top-3/top-5 saturation."
    ),
    "cases": cases,
}

BENCHMARK_PATH.write_text(json.dumps(benchmark_data, indent=2), encoding="utf-8")
print(f"Successfully generated {len(cases)} benchmark cases in {BENCHMARK_PATH}")
