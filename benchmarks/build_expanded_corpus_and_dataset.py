"""Builder script for KIP v1.2 expanded benchmark corpus and dataset.

Generates:
1. 50 reference documents in benchmarks/corpus_v1_2_expanded/ (38 genuine KIP architecture docs + 12 hard negatives).
2. Derives stable SHA-256 document IDs and chunk IDs.
3. Generates 80 labelled benchmark cases in benchmarks/kip_v1_2_expanded_benchmark.json across 6 categories.
4. Generates benchmarks/corpus_v1_2_expanded/README.md.
"""

import hashlib
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "benchmarks" / "corpus_v1_2_expanded"
BENCHMARK_PATH = REPO_ROOT / "benchmarks" / "kip_v1_2_expanded_benchmark.json"

CORPUS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 50 Corpus Documents Definitions (Strict LF, 700-950 chars each)
# ---------------------------------------------------------------------------

DOCUMENTS: dict[str, str] = {
    # 1. Overview
    "kip_overview.txt": (
        "KIP (Knowledge Intelligence Platform) is a zero-cost, multi-tenant RAG platform.\n"
        "It supports document ingestion in PDF, DOCX, TXT, and Markdown formats.\n"
        "Documents are chunked using a fixed-size character chunker with configurable size and overlap.\n"
        "Each chunk is assigned a deterministic SHA-256 ID derived from the document ID and chunk index.\n"
        "The platform uses Gemini dense embeddings (gemini-embedding-2, 768 dimensions) for semantic search.\n"
        "Vector storage uses Qdrant Cloud with cosine similarity and workspace_id payload filtering.\n"
        "Retrieval is scoped strictly to the active workspace; cross-tenant access is rejected at multiple layers.\n"
        "The frontend is a Streamlit application hosted on Streamlit Community Cloud.\n"
        "User feedback is collected via a category and free-text message with a 30-word limit.\n"
        "Feedback is forwarded to Google Sheets via an authenticated Google Apps Script webhook.\n"
    ),
    # 2. Multitenancy
    "kip_multitenancy_architecture.txt": (
        "KIP enforces multi-tenant workspace isolation at every tier of the ingestion and retrieval stack.\n"
        "Tenants operate in isolated logical namespaces identified by an opaque workspace_id.\n"
        "All incoming REST API requests must supply the X-KIP-Workspace-ID HTTP header.\n"
        "The backend workspace dependency validates the presence and non-emptiness of the workspace header.\n"
        "In the vector database layer, tenant isolation is maintained through Qdrant payload filters.\n"
        "Every chunk indexed in Qdrant contains a payload field named workspace_id matching the active tenant.\n"
        "During vector similarity search, a strict Filter condition matching workspace_id is appended to queries.\n"
        "Qdrant evaluates payload filters before returning top-k nearest neighbors, preventing cross-tenant leakage.\n"
        "Document deletion and retrieval endpoints reject requests lacking workspace authorization.\n"
    ),
    # 3. Security & Threat Model
    "kip_security_threat_model.txt": (
        "The KIP security threat model defends against tenant cross-contamination and unauthorized data access.\n"
        "Workspaces are decoupled by cryptographically random tokens generated with python secrets module.\n"
        "Workspace tokens use the wksp_ prefix and have a minimum entropy of 256 bits to prevent enumeration.\n"
        "Tenant boundary validation occurs prior to document parsing to prevent malicious file injection.\n"
        "Uploaded files are inspected in-memory with strict MIME-type and extension validation.\n"
        "Payloads are checked against maximum size boundaries (2097152 bytes) to mitigate denial of service.\n"
        "Vector search queries strictly constrain candidate points to the caller's authorized workspace.\n"
        "Feedback submissions enforce rate limits and string sanitization before dispatching to Google Sheets.\n"
        "All internal exceptions are caught and sanitized to ensure database connection strings remain hidden.\n"
    ),
    # 4. Configuration
    "kip_configuration_settings.txt": (
        "KIP utilizes Pydantic BaseSettings in app.core.config for centralized environment configuration.\n"
        "Configuration variables are loaded from environment variables and local .env files with fallback defaults.\n"
        "Key vector store variables include VECTOR_STORE_PROVIDER (default: qdrant) and QDRANT_COLLECTION (knowledge_base).\n"
        "Embedding settings specify EMBEDDING_PROVIDER (gemini), EMBEDDING_MODEL (gemini-embedding-2), and dimensions (768).\n"
        "LLM gateway settings define LLM_PROVIDER (gemini), LLM_MODEL (gemini-2.5-flash), and LLM_API_KEY credentials.\n"
        "Ingestion chunking parameters default to CHUNK_SIZE=1000 characters and CHUNK_OVERLAP=200 characters.\n"
        "Feedback settings include FEEDBACK_WEBHOOK_URL and FEEDBACK_WEBHOOK_TOKEN for authenticated delivery.\n"
        "Workspace limits are bounded by MAX_DOCUMENTS_PER_WORKSPACE=50 and MAX_CHUNKS_PER_WORKSPACE=1000.\n"
    ),
    # 5. Docker & Deployment
    "kip_docker_and_deployment.txt": (
        "KIP is packaged for containerized cloud deployment using lightweight Docker images.\n"
        "The production Dockerfile is based on python:3.11-slim to minimize container image footprint.\n"
        "The container installs dependencies via pip with no-cache-dir flags and runs as a non-root user.\n"
        "Uvicorn serves the FastAPI backend application on host 0.0.0.0 and port 8000.\n"
        "Render Free Web Service hosts the container with automatic git-push trigger deployments.\n"
        "Health checks are exposed at GET /api/v1/health returning status ok and version information.\n"
        "Container environment variables are injected securely via Render dashboard secret management.\n"
        "Render instances receive HTTP traffic through automatic TLS termination with Let's Encrypt certificates.\n"
    ),
    # 6. Cold Start Mitigation
    "kip_cold_start_mitigation.txt": (
        "Free cloud hosting tiers on Render spin down backend containers after fifteen minutes of inactivity.\n"
        "To mitigate user friction during spin-up, the Streamlit frontend implements cold-start resilience.\n"
        "On initial browser page load, the frontend issues a non-blocking ping to the GET /api/v1/health endpoint.\n"
        "If the container is dormant, the frontend catches HTTP connection timeouts and displays a wake-up banner.\n"
        "An exponential backoff retry loop polls the health endpoint up to ten attempts with a two-second interval.\n"
        "User interactions are buffered while the backend completes initialization and establishes Qdrant connectivity.\n"
        "Once the health probe returns status 200, the wake-up banner clears and normal UI controls are unlocked.\n"
        "This architectural handshake prevents abrupt 502 Bad Gateway errors from reaching public users.\n"
    ),
    # 7. Document Parsers
    "kip_document_parsers.txt": (
        "KIP document ingestion supports four distinct file formats: PDF, DOCX, TXT, and Markdown.\n"
        "Each incoming file upload is routed to a specialized parser based on its MIME type and file extension.\n"
        "PDF files are parsed using PyPDF, which extracts text streams across all document pages sequentially.\n"
        "DOCX files are processed using python-docx to iterate over body paragraphs and table text blocks.\n"
        "TXT and Markdown files are decoded directly as UTF-8 character sequences without specialized extraction.\n"
        "All parsers enforce a strict maximum upload boundary: files exceeding 2097152 bytes (2 MB) are rejected.\n"
        "Files with unsupported media types or corrupted headers trigger an IngestionError with HTTP 415 or 400.\n"
        "Extracted text undergoes whitespace normalization while preserving logical paragraph and heading breaks.\n"
    ),
    # 8. PDF Parser Internals
    "kip_pdf_parser_internals.txt": (
        "The PDF parser implementation in KIP wraps the PyPDF PdfReader library within a protected execution block.\n"
        "Upon file upload, raw bytes are wrapped in an io.BytesIO stream to avoid writing temporary files to disk.\n"
        "The parser loops through reader.pages, calling extract_text with visitor functions to assemble page strings.\n"
        "Pages that contain only scanned images or produce zero extractable characters generate an informative warning.\n"
        "Extracted text from each page is annotated with page_number metadata to preserve provenance for citations.\n"
        "If a PDF is encrypted with a password, the parser catches PdfReadError and raises IngestionError immediately.\n"
        "Total extracted characters are validated against a minimum length threshold to ensure document substance.\n"
        "The resulting text stream is packaged into a Document domain entity alongside document_id and filename.\n"
    ),
    # 9. DOCX Parser Internals
    "kip_docx_parser_internals.txt": (
        "The DOCX parser implementation in KIP extracts textual content from Microsoft Word OpenXML documents.\n"
        "Uploaded byte streams are parsed in memory using docx.Document without requiring local disk serialization.\n"
        "The parser iterates over document.paragraphs, extracting clean text while skipping empty whitespace lines.\n"
        "To capture structured tabular information, the parser loops through document.tables and cell rows.\n"
        "Table cells are joined with pipe delimiters to preserve tabular column relationships within the text stream.\n"
        "Headers and footers are filtered out to prevent repetitive boilerplate from polluting embedding representations.\n"
        "Special XML formatting artifacts and embedded images are safely ignored during paragraph extraction.\n"
        "The combined paragraph and table text is returned as a single normalized string for downstream chunking.\n"
    ),
    # 10. Idempotency Service
    "kip_idempotency_service.txt": (
        "KIP provides deterministic, content-addressed document identity to guarantee idempotency during ingestion.\n"
        "When a document is uploaded, DocumentIngestionService computes document_id = SHA-256(raw_file_bytes).\n"
        "Because document identity depends strictly on raw file bytes, identical files always produce identical IDs.\n"
        "During chunking, each chunk is assigned an ID computed as SHA-256(document_id + ':' + str(chunk_index)).\n"
        "In Qdrant, point IDs are derived as UUID5(NAMESPACE_URL, 'kip://' + workspace_id + '/' + chunk_id).\n"
        "Re-uploading the same document into the same workspace generates the identical point IDs in Qdrant.\n"
        "Qdrant upsert semantics overwrite existing points with identical IDs rather than creating duplicate entries.\n"
        "Idempotent indexing eliminates redundant vector allocations and ensures reproducible benchmark evaluations.\n"
    ),
    # 11. Chunking and Embeddings
    "kip_chunking_and_embeddings.txt": (
        "KIP splits documents into overlapping fixed-size character chunks.\n"
        "The default chunk size is 1000 characters with 200 characters of overlap.\n"
        "This produces a step size of 800 characters between chunk start positions.\n"
        "Chunk IDs are computed as SHA-256(document_id + ':' + chunk_index).\n"
        "Re-indexing the same document always produces the same chunk IDs, enabling idempotent upserts.\n"
        "Document IDs are computed as SHA-256 of the raw file bytes, making them content-addressed.\n"
        "Embeddings are produced by the GeminiEmbeddingProvider using the gemini-embedding-2 model.\n"
        "The embedding dimensions are configurable; the production default is 768.\n"
        "Both document chunks and queries are embedded using the same symmetric model call.\n"
        "No task-type parameter is currently set; both index and query use the default embedding mode.\n"
    ),
    # 12. Chunk Metadata Provenance
    "kip_chunk_metadata_provenance.txt": (
        "Every chunk generated by ChunkingService carries structured metadata for downstream provenance attribution.\n"
        "The Chunk domain model encapsulates id, document_id, text, index, character_count, and metadata dict.\n"
        "Provenance fields populated during ingestion include source_filename, chunk_index, and media_type.\n"
        "When chunks are embedded, EmbeddingService preserves this provenance by copying it into EmbeddingInput.metadata.\n"
        "The vector store provider stores these metadata attributes inside the Qdrant payload alongside the vector.\n"
        "When a search query retrieves candidate vectors, the vector store returns the payload text and provenance.\n"
        "RAG response models package retrieved chunks into source references displayed to users in the Streamlit UI.\n"
        "This immutable provenance chain guarantees that generated answers can be audited down to exact chunk indices.\n"
    ),
    # 13. Batch Ingestion Limits
    "kip_batch_ingestion_limits.txt": (
        "To safeguard zero-cost cloud infrastructure, KIP enforces strict capacity limits across all workspaces.\n"
        "A single workspace may index a maximum of MAX_DOCUMENTS_PER_WORKSPACE = 50 distinct documents.\n"
        "The total number of vector chunks stored in a single workspace cannot exceed MAX_CHUNKS_PER_WORKSPACE = 1000.\n"
        "When an upload request would breach workspace capacity, the API rejects it with HTTP 429 or 400.\n"
        "Individual file uploads are bounded by MAX_UPLOAD_SIZE_BYTES = 2097152 bytes (2 MB).\n"
        "Embedding requests are submitted in batches of up to 100 chunks to comply with provider rate limits.\n"
        "These hard limits protect Gemini API free quotas and Qdrant Cloud cluster memory from exhaustion.\n"
        "Workspaces nearing capacity must delete obsolete documents via the document management API before re-indexing.\n"
    ),
    # 14. Retrieval and RAG
    "kip_retrieval_and_rag.txt": (
        "KIP retrieval uses dense vector search over a Qdrant collection named knowledge_base.\n"
        "The vector distance metric is COSINE; similarity scores are in [-1, 1], where 1 is identical.\n"
        "Qdrant converts cosine distance to a score: score = 1 - distance.\n"
        "During search, the query text is embedded using the configured Gemini embedding model.\n"
        "The top_k parameter defaults to 5 results per retrieval query.\n"
        "All searches apply a must match filter on payload.workspace_id to enforce multi-tenant isolation.\n"
        "Retrieved chunks are passed to the RAG pipeline which constructs a prompt with strict grounding rules.\n"
        "The generation model is Gemini 2.5 Flash via the GeminiLLMProvider.\n"
        "If no chunks match the query or if the similarity score is below the threshold, retrieval returns empty.\n"
        "When context is empty, the RAG service returns a predefined message without calling the generation LLM.\n"
    ),
    # 15. Embedding Manager
    "kip_embedding_manager.txt": (
        "EmbeddingManager serves as the central orchestration component for vector embedding operations in KIP.\n"
        "It maintains an extensible registry of embedding providers and maps settings.embedding_provider to adapters.\n"
        "Supported providers include GeminiEmbeddingProvider (primary default) and OpenAIEmbeddingProvider (fallback).\n"
        "The embed() method validates input batch sizes and delegates text transformation to the active provider.\n"
        "Vectors returned by the underlying provider are verified for dimensionality matching settings.embedding_dimensions.\n"
        "EmbeddingManager ensures vectors are normalized for cosine distance calculations in Qdrant.\n"
        "If an external provider returns an error or quota exhaustion, EmbeddingManager raises an EmbeddingError.\n"
        "This decoupling isolates upper-level indexing and retrieval services from third-party SDK dependencies.\n"
    ),
    # 16. Gemini Embedding Provider
    "kip_gemini_embedding_provider.txt": (
        "GeminiEmbeddingProvider integrates Google Gemini embedding models into KIP using the official google-genai SDK.\n"
        "The production embedding model is gemini-embedding-2, which produces 768-dimensional dense vectors.\n"
        "The provider submits texts using the batchEmbedContents API endpoint to maximize batch throughput.\n"
        "Each input text is packaged into a Content object containing a single text Part.\n"
        "In accordance with official Google Gemini documentation, task_type is unsupported for gemini-embedding-2.\n"
        "Input texts are passed directly as content without task-type parameters to prevent API validation errors.\n"
        "Output vector values are extracted from the Embedding.values array and verified to contain 768 float elements.\n"
        "HTTP timeouts and network disconnects are caught and wrapped into standardized KIP EmbeddingError exceptions.\n"
    ),
    # 17. OpenAI Embedding Provider
    "kip_openai_embedding_provider.txt": (
        "OpenAIEmbeddingProvider provides an alternative embedding adapter in KIP for OpenAI vector models.\n"
        "When EMBEDDING_PROVIDER is set to openai, KIP routes embedding requests through openai.OpenAI client.\n"
        "The default OpenAI embedding model is text-embedding-3-small configured with 1536 output dimensions.\n"
        "Input batches are submitted to client.embeddings.create using the input text list parameter.\n"
        "OpenAI returns normalized embedding vectors directly suitable for cosine similarity search.\n"
        "The adapter extracts vectors in source order and constructs KIP Embedding domain entities.\n"
        "If the OPENAI_API_KEY environment variable is missing, provider initialization raises a ConfigurationError.\n"
        "The provider is fully tested using deterministic fakes to ensure test isolation without live API costs.\n"
    ),
    # 18. Vector Store Adapters
    "kip_vector_store_adapters.txt": (
        "KIP decouples vector storage through an abstract VectorStoreProvider interface.\n"
        "Concrete implementations must implement index_chunks, search, delete_by_document, and delete_by_workspace.\n"
        "VectorStoreService coordinates vector operations through the active provider selected via settings.\n"
        "The production provider is QdrantVectorStoreProvider, which connects to Qdrant Cloud via HTTP client.\n"
        "The fallback and local testing provider is ChromaVectorStoreProvider, supporting in-memory vector storage.\n"
        "All vector search operations require an explicit workspace_id argument to prevent cross-tenant queries.\n"
        "Vector operations translate domain Chunk and RetrievalQuery models into provider-native query structures.\n"
        "Provider errors such as connection timeouts or missing collections are mapped to VectorStoreError exceptions.\n"
    ),
    # 19. Qdrant Provider Internals
    "kip_qdrant_provider_internals.txt": (
        "QdrantVectorStoreProvider manages high-performance vector search in KIP using the qdrant-client library.\n"
        "It connects to Qdrant Cloud or local Docker instances via HTTP or gRPC using QDRANT_URL and QDRANT_API_KEY.\n"
        "During collection initialization, it creates the knowledge_base collection with Distance.COSINE and size 768.\n"
        "A payload index is created on the workspace_id field with FieldType.KEYWORD to optimize tenant filtering.\n"
        "Vector search executes client.search() with a strict Filter containing a FieldCondition for workspace_id.\n"
        "Candidate points returned by Qdrant include payload text, document_id, chunk_index, and distance scores.\n"
        "Distance values are mapped to similarity scores using score = 1 - distance, bounded between 0.0 and 1.0.\n"
        "Document deletion calls client.delete() with a combined filter on document_id and workspace_id.\n"
    ),
    # 20. Chroma Provider Internals
    "kip_chroma_provider_internals.txt": (
        "ChromaVectorStoreProvider implements vector storage in KIP using the chromadb embedded library.\n"
        "It is designed primarily for local development, automated CI workflows, and fast unit test suites.\n"
        "When persist_directory is None, Chroma initializes an ephemeral in-memory client without filesystem writes.\n"
        "Collections are created with metadata={'hnsw:space': 'cosine'} to enforce cosine distance metric calculations.\n"
        "Tenant isolation is applied using Chroma's where={'workspace_id': workspace_id} metadata query filter.\n"
        "Vectors and metadata are inserted via collection.upsert() with chunk IDs matching SHA-256 derivations.\n"
        "SearchResults returned by Chroma are transformed into KIP RetrievedChunk models with cosine scores.\n"
        "Chroma enables 100% offline test execution without requiring network access to cloud vector databases.\n"
    ),
    # 21. LLM Gateway
    "kip_llm_gateway.txt": (
        "LLMManager acts as the unified gateway for generative language model interactions in KIP.\n"
        "It abstracts provider implementations behind the LLMProvider protocol to enable model swapping.\n"
        "The production provider is GeminiLLMProvider, which communicates with the gemini-2.5-flash model.\n"
        "A secondary provider is OpenAILLMProvider, which interfaces with gpt-4o-mini for fallback testing.\n"
        "The gateway exposes generate_response(prompt, system_instruction, temperature) with strict typing.\n"
        "Temperature defaults to 0.0 to ensure deterministic, reproducible generation for RAG evaluations.\n"
        "The gateway enforces request timeouts and handles transient provider rate-limit errors gracefully.\n"
        "Responses are returned as LLMResponse entities containing text, finish_reason, and usage metrics.\n"
    ),
    # 22. Grounded RAG Prompting
    "kip_grounded_rag_prompting.txt": (
        "KIP enforces strict response grounding in RAGService to eliminate hallucinations in question-answering.\n"
        "The RAG prompt template injects retrieved context chunks under explicit numbered XML source tags.\n"
        "System instructions command the model to answer questions using ONLY facts explicitly provided in context.\n"
        "If the retrieved context does not contain sufficient facts to answer, the model must state its inability.\n"
        "Every factual claim in the generated answer must be attributed to a source tag such as [Source 1].\n"
        "Speculation, extrapolation, and reliance on pre-trained external knowledge are forbidden by prompt rules.\n"
        "The system prompt instructs the model to ignore misleading instructions embedded inside user documents.\n"
        "This defensive prompt engineering ensures high answer faithfulness across enterprise knowledge bases.\n"
    ),
    # 23. Empty Context Guard
    "kip_empty_context_guard.txt": (
        "KIP RAGService incorporates an empty-context short-circuit guard to conserve LLM API costs and quota.\n"
        "When RetrievalService returns zero chunks, the system bypasses the generation LLM entirely.\n"
        "Similarly, if all retrieved chunks have similarity scores falling below the relevance threshold, context is empty.\n"
        "Under empty-context conditions, RAGService immediately returns a deterministic refusal message:\n"
        "'I do not have sufficient information in the provided knowledge base to answer this question.'\n"
        "The response sources list is set to empty and total generation latency is recorded as 0.0 milliseconds.\n"
        "This optimization prevents wasteful LLM inference roundtrips on unanswerable or out-of-domain queries.\n"
        "Automated evaluation suites verify that empty-context paths never trigger external generative API calls.\n"
    ),
    # 24. RAG Service Orchestration
    "kip_rag_service_orchestration.txt": (
        "RAGService coordinates the end-to-end question answering pipeline across KIP subsystem components.\n"
        "Upon receiving a RAGRequest, RAGService extracts query text, workspace_id, and retrieval top_k.\n"
        "Step 1: It invokes RetrievalService.search() with a workspace-scoped RetrievalQuery entity.\n"
        "Step 2: If chunks are retrieved, it formats the context block into ordered [Source X] XML sections.\n"
        "Step 3: It constructs the grounded RAG prompt and passes it to LLMService for generative completion.\n"
        "Step 4: It parses the LLM output, pairs source references with retrieved chunks, and records latencies.\n"
        "Step 5: It packages the final output into a RAGResponse entity containing answer, sources, and metadata.\n"
        "Any unexpected exception during retrieval or generation is caught and wrapped into a RAGError entity.\n"
    ),
    # 25. Provenance Attribution
    "kip_provenance_attribution.txt": (
        "Provenance attribution is a core architectural requirement for transparency in KIP RAG workflows.\n"
        "Every chunk returned by RetrievalService contains document_id, filename, chunk_index, and similarity score.\n"
        "When RAGService generates an answer, it returns a list of SourceReference objects matching retrieved context.\n"
        "The Streamlit frontend renders each source reference in an interactive expandable provenance card.\n"
        "Users can inspect the exact text excerpt, source document name, chunk index, and cosine similarity score.\n"
        "This visual transparency allows users to verify whether LLM claims align with uploaded documentation.\n"
        "In automated evaluation, keyword coverage and document hit metrics are verified against this provenance chain.\n"
        "No answer is considered verified in KIP without verifiable provenance linking to active workspace chunks.\n"
    ),
    # 26. OpenAI LLM Provider
    "kip_openai_llm_provider.txt": (
        "OpenAILLMProvider offers an alternative generative adapter for OpenAI language models in KIP.\n"
        "When LLM_PROVIDER is configured as openai, KIP instantiates OpenAILLMProvider with OPENAI_API_KEY.\n"
        "The provider uses the openai.OpenAI client to send chat completion requests to the gpt-4o-mini model.\n"
        "System instructions are transmitted in the developer or system message role for prompt grounding.\n"
        "Temperature is pinned to 0.0 to enforce deterministic generation during benchmark evaluations.\n"
        "The provider extracts generated message content and token usage counts from ChatCompletion choices.\n"
        "Rate-limiting HTTP 429 errors from OpenAI are caught and transformed into KIP LLMRateLimitError.\n"
        "This modular provider architecture enables seamless multi-vendor benchmarking without code rewrites.\n"
    ),
    # 27. API Specifications
    "kip_api_specifications.txt": (
        "KIP exposes a RESTful API built on FastAPI with OpenAPI documentation at /docs.\n"
        "Health check: GET /api/v1/health returns status ok, platform version, and uptime.\n"
        "Document upload: POST /api/v1/documents accepts multipart file uploads (PDF, DOCX, TXT, MD).\n"
        "Upload requests require an X-KIP-Workspace-ID header and return document_id, filename, chunks_indexed.\n"
        "Document listing: GET /api/v1/documents returns all indexed documents in the active workspace.\n"
        "Retrieval query: POST /api/v1/retrieval/search accepts query text, top_k, returns retrieved chunks.\n"
        "RAG question: POST /api/v1/rag/query accepts query text, top_k, returns answer and source references.\n"
        "Feedback: POST /api/v1/feedback accepts category and message, returns delivery status.\n"
        "Error responses follow RFC 7807 with detail, error_code, and HTTP status codes (400, 404, 422, 500).\n"
    ),
    # 28. Feedback Webhook
    "kip_feedback_webhook.txt": (
        "KIP collects user feedback through an in-app modal and forwards it to Google Sheets.\n"
        "The feedback submission requires a category (UI/UX, Performance, Accuracy, Feature Request, Other) and message.\n"
        "Messages are limited to 30 words to encourage concise, actionable user input.\n"
        "Feedback transport uses an authenticated HTTPS GET request with query parameters to Google Apps Script.\n"
        "The Google Apps Script web app implements doGet(e) to receive parameters and append a row to Google Sheets.\n"
        "Requests are authenticated via a shared secret token passed in the token query parameter.\n"
        "The backend uses python requests.get() which automatically follows HTTP 302 redirects from Apps Script.\n"
        "Secrets and destination URLs are strictly redacted from application logs to prevent credential leakage.\n"
    ),
    # 29. Feedback Token Security
    "kip_feedback_token_security.txt": (
        "Feedback webhook transport in KIP is protected by shared secret token validation.\n"
        "The environment variable FEEDBACK_WEBHOOK_TOKEN defines a high-entropy secret string.\n"
        "When FastAPI dispatches feedback to Google Apps Script, the token is included as an HTTPS query parameter.\n"
        "The Apps Script doGet() handler verifies that parameter e.parameter.token matches ScriptProperties.token.\n"
        "If the token is missing or invalid, Apps Script rejects the request with HTTP 401 Unauthorized.\n"
        "If FEEDBACK_WEBHOOK_URL is unconfigured, the backend returns HTTP 503 feedback_destination_unconfigured.\n"
        "Logs and error handlers automatically mask token values using regex redaction before output.\n"
        "This shared-secret mechanism prevents unauthorized external actors from writing spam into feedback sheets.\n"
    ),
    # 30. Streamlit Frontend State
    "kip_streamlit_frontend_state.txt": (
        "The KIP frontend is built with Streamlit and manages state through st.session_state.\n"
        "Session keys include active_workspace_id, chat_history, uploaded_documents, and backend_status.\n"
        "When a user connects, the application generates a default workspace access token or loads an existing one.\n"
        "Switching workspaces clears chat_history and cached document listings to maintain strict tenant privacy.\n"
        "Network calls to the FastAPI backend use requests.Session with default connection timeouts (10 seconds).\n"
        "To ensure responsiveness, document upload triggers a spinner widget while chunks are indexed in Qdrant.\n"
        "The UI automatically persists the current workspace_id in the browser session until the tab is closed.\n"
        "State resets are idempotent, preventing residual cross-tenant context from persisting across sessions.\n"
    ),
    # 31. Streamlit UI Components
    "kip_streamlit_ui_components.txt": (
        "The Streamlit UI organizes KIP capabilities into four primary visual interaction components.\n"
        "Component 1: The Workspace Sidebar enables token creation, workspace switching, and connection health display.\n"
        "Component 2: The Document Manager provides drag-and-drop file upload and displays active indexed documents.\n"
        "Component 3: The Query & RAG View renders chat history, response streams, and expandable provenance cards.\n"
        "Component 4: The Feedback Dialog renders a category dropdown and a free-text text area with word counting.\n"
        "The provenance component visually renders chunk text, document filename, chunk index, and similarity scores.\n"
        "Error banners display user-friendly troubleshooting guidance when backend services encounter timeouts.\n"
        "The layout uses responsive columns to ensure readability across mobile and desktop browser viewports.\n"
    ),
    # 32. Error Handling Protocols
    "kip_error_handling_protocols.txt": (
        "KIP enforces centralized, structured exception handling across all FastAPI routes and backend services.\n"
        "Custom exception classes derive from KIPBaseException: IngestionError, RetrievalError, LLMError, VectorStoreError.\n"
        "Each custom exception defines a machine-readable error_code and human-readable detail description.\n"
        "FastAPI exception handlers map IngestionError to HTTP 400 or 415 depending on the parser failure mode.\n"
        "RetrievalError without an active workspace maps to HTTP 400 with detail 'workspace_id is required'.\n"
        "VectorStoreError and LLMError map to HTTP 502 Bad Gateway or 503 Service Unavailable.\n"
        "Uncaught internal exceptions return HTTP 500 while masking raw stack traces from external API responses.\n"
        "Structured logging records full error traces internally with contextual request_id and tenant workspace_id.\n"
    ),
    # 33. Evaluation Framework
    "kip_evaluation_framework.txt": (
        "The KIP evaluation framework in the evaluation/ package provides automated benchmarking for RAG pipelines.\n"
        "EvaluationRunner executes BenchmarkDataset cases against KIP retrieval and generation services directly.\n"
        "Evaluation runs are isolated from production user workspaces using dedicated workspace IDs (kip-eval-workspace).\n"
        "The runner records retrieval metrics: Hit Rate (fraction of queries retrieving target docs) and MRR.\n"
        "Answer-level metrics include keyword coverage: the fraction of ground-truth keywords in generated answers.\n"
        "Stage latencies are recorded separately: retrieval latency, generation latency, and total latency in milliseconds.\n"
        "The framework supports offline evaluation using deterministic fakes (DeterministicEmbeddingProvider) in CI.\n"
        "Provider-backed evaluation scripts run against live Gemini APIs and Qdrant to measure real-world performance.\n"
    ),
    # 34. Retrieval Metrics Definitions
    "kip_retrieval_metrics_definitions.txt": (
        "KIP evaluation calculates mathematical retrieval metrics based on standard information retrieval formulas.\n"
        "Hit Rate@k measures the fraction of labelled queries where at least one target document appears in top-k.\n"
        "Reciprocal Rank (RR) is defined as 1 / rank of the first relevant document, and 0.0 if no target is in top-k.\n"
        "Mean Reciprocal Rank (MRR) is the average of Reciprocal Rank values across all labelled benchmark cases.\n"
        "Precision@k calculates the number of relevant retrieved documents in top-k divided by k.\n"
        "Average Precision (AP) averages Precision@k values at each rank where a relevant document is retrieved.\n"
        "Mean Average Precision (MAP) calculates the mean of AP values across all multi-document benchmark queries.\n"
        "Unlabelled cases (empty expected_document_ids) are strictly excluded to prevent artificial metric inflation.\n"
    ),
    # 35. Benchmark Dataset Schema
    "kip_benchmark_dataset_schema.txt": (
        "Benchmark datasets in KIP are strictly typed using Pydantic domain models in evaluation/models.py.\n"
        "BenchmarkCase encapsulates id, question, reference_answer, expected_document_ids, and expected_keywords.\n"
        "BenchmarkDataset packages a dataset version string, description, and list of BenchmarkCase instances.\n"
        "RetrievalMetrics captures case_id, hit, reciprocal_rank, retrieved_doc_ids, and retrieval_latency_ms.\n"
        "Retrieval infrastructure failures are recorded in retrieval_error, distinguishing errors from misses.\n"
        "AnswerMetrics captures keyword_hits, keyword_misses, keyword_coverage, and generation_latency_ms.\n"
        "BenchmarkResult aggregates run_id, timestamp, config, case_results, hit_rate, and mean_reciprocal_rank.\n"
        "All benchmark and result models serialize cleanly to JSON for persistent version-controlled records.\n"
    ),
    # 36. Ground Truth Derivation
    "kip_ground_truth_derivation.txt": (
        "Ground truth document and chunk IDs in KIP benchmarks are derived using the platform's actual hashing logic.\n"
        "Document IDs are derived as document_id = hashlib.sha256(raw_file_bytes).hexdigest() from corpus files.\n"
        "Chunk IDs are derived as chunk_id = hashlib.sha256(f'{document_id}:{chunk_index}'.encode()).hexdigest().\n"
        "To ensure hash stability across operating systems, all corpus text files must use Unix LF line endings.\n"
        "A carriage return byte (CRLF) alters raw file bytes, changing the SHA-256 hash and invalidating ground truth.\n"
        "The derive_corpus_ids.py utility script inspects corpus files, verifies LF endings, and outputs hashes.\n"
        "Benchmark cases reference these exact SHA-256 hashes in expected_document_ids and expected_chunk_ids.\n"
        "This deterministic protocol eliminates guesswork and ensures 100% reproducible retrieval evaluation.\n"
    ),
    # 37. Evaluation Workspace Isolation
    "kip_evaluation_workspace_isolation.txt": (
        "Evaluation operations in KIP must never contaminate or interact with user tenant workspaces.\n"
        "The EvaluationRunner explicitly injects config.evaluation_workspace_id into all queries and RAG requests.\n"
        "The standard evaluation workspace identifier is 'kip-eval-workspace' (or versioned variants).\n"
        "During benchmark preflight, reference corpus documents are indexed strictly into the evaluation workspace.\n"
        "Qdrant payload filters ensure vector searches retrieve points belonging solely to the evaluation workspace.\n"
        "After evaluation concludes, automated test fixtures delete all points matching the evaluation workspace ID.\n"
        "This isolation invariant ensures that evaluation tests can run safely alongside active production traffic.\n"
        "Runner tests verify that omitting workspace_id raises a RetrievalError rather than falling back to defaults.\n"
    ),
    # 38. Paired Experiment Protocol
    "kip_paired_experiment_protocol.txt": (
        "KIP evaluates retrieval optimizations using a rigorous paired comparative experimentation protocol.\n"
        "Every experiment defines a Control condition (existing baseline) and a Treatment condition (optimization candidate).\n"
        "Both conditions are evaluated against the exact same corpus snapshot, query set, and ground-truth labels.\n"
        "To prevent vector contamination, Control and Treatment are indexed into separate dedicated Qdrant collections.\n"
        "The runner evaluates queries in identical order and computes paired differences (delta RR, delta latency).\n"
        "Results record per-query rank shifts to determine whether aggregate gains mask individual case regressions.\n"
        "Timestamped result JSON files are persisted in benchmarks/ for verifiable, peer-reviewable research records.\n"
        "Optimizations are adopted into production only when empirical paired improvements outweigh regressions.\n"
    ),
    # -----------------------------------------------------------------------
    # Hard Negatives & Semantic Distractors (Docs 39-50)
    # -----------------------------------------------------------------------
    # 39. Distractor: Alternative Chunkers
    "distractor_alternative_chunkers.txt": (
        "Alternative document chunking strategies include semantic chunking and recursive character splitting.\n"
        "Semantic chunkers analyze sentence embeddings to detect natural topic transitions before splitting text.\n"
        "Recursive chunkers split text hierarchically using double newlines, single newlines, and spaces.\n"
        "Sentence-window chunking attaches surrounding sentences as contextual metadata around small central chunks.\n"
        "Document-specific chunkers parse markdown headers (#, ##) or HTML tags to preserve section boundaries.\n"
        "These methods aim to preserve semantic cohesion at the cost of non-deterministic chunk boundaries.\n"
        "KIP currently uses a fixed character chunker; alternative chunkers are candidates for v1.2 research.\n"
        "Evaluating chunking strategies requires measuring Hit Rate and MRR across varying chunk sizes and overlaps.\n"
    ),
    # 40. Distractor: Legacy Chroma Settings
    "distractor_legacy_chroma_settings.txt": (
        "In earlier KIP prototype versions (v0.2 and v0.3), vector storage relied on local embedded Chroma instances.\n"
        "Chroma configuration utilized CHROMA_PERSIST_DIRECTORY pointing to local disk paths like data/chroma.\n"
        "The embedded client used DuckDB and Parquet files for persistence with collection name 'knowledge_base'.\n"
        "In v1.1, KIP migrated its production cloud architecture to Qdrant Cloud to support multi-tenant isolation.\n"
        "Legacy Chroma persistence settings remain in the codebase strictly for offline unit testing in tests/.\n"
        "Chroma settings must not be used in cloud deployment configurations on Render or Streamlit Cloud.\n"
        "Production environments require QDRANT_URL and QDRANT_API_KEY environment variables instead.\n"
    ),
    # 41. Distractor: Hybrid Search Proposals
    "distractor_hybrid_search_proposals.txt": (
        "Hybrid search combines dense semantic vector retrieval with sparse lexical keyword matching.\n"
        "Sparse retrieval algorithms such as BM25 and SPLADE excel at exact keyword lookups and acronym matching.\n"
        "Dense vector retrieval excels at semantic similarity, paraphrase matching, and conceptual understanding.\n"
        "Hybrid search merges candidate results using Reciprocal Rank Fusion (RRF) or convex score combination.\n"
        "Qdrant supports hybrid search by storing both dense vector embeddings and sparse lexical vector representations.\n"
        "Cross-encoder rerankers can be applied after hybrid fusion to score candidate passages against queries.\n"
        "KIP currently uses pure dense vector search; hybrid search is a proposed research direction for v1.2+.\n"
        "Evaluating hybrid search requires comparing Hit Rate, MRR, and retrieval latency against pure dense retrieval.\n"
    ),
    # 42. Distractor: External Judge Evaluators
    "distractor_external_judge_evaluators.txt": (
        "Automated RAG evaluation frameworks such as Ragas, DeepEval, and TruLens use LLMs as evaluative judges.\n"
        "These frameworks measure semantic metrics: faithfulness, answer relevance, context precision, and recall.\n"
        "Faithfulness measures whether all claims in a generated answer are grounded in the retrieved context.\n"
        "Context precision evaluates whether retrieved chunks are sorted with the most relevant passages first.\n"
        "LLM-as-judge evaluation introduces non-determinism, cost, and reliance on powerful judge models like GPT-4.\n"
        "KIP v1.1 deliberately avoids external LLM judge frameworks, relying on mechanical evaluation in runner.py.\n"
        "Mechanical metrics (Hit Rate, MRR, keyword coverage) are deterministic, fast, and require no judge API quota.\n"
        "Integration with Ragas or DeepEval is planned as an optional evaluation mode for future research versions.\n"
    ),
    # 43. Distractor: Redis Caching
    "distractor_redis_caching_architecture.txt": (
        "Redis semantic caching accelerates RAG query execution by storing vector embeddings and generated answers.\n"
        "When an incoming query matches a previously cached query vector within a cosine threshold (e.g. 0.98),\n"
        "the system returns the cached answer instantly without invoking Qdrant search or generative LLMs.\n"
        "Redis Enterprise supports RediSearch with HNSW vector indexing for low-latency similarity lookups.\n"
        "Cache keys are partitioned by workspace_id to guarantee multi-tenant privacy across cached responses.\n"
        "TTL eviction policies ensure stale knowledge entries expire automatically after twenty-four hours.\n"
        "KIP v1.1 does not incorporate Redis semantic caching; this optimization is scheduled for v1.3 performance.\n"
        "Caching introduces cache invalidation challenges when tenant documents are updated or deleted.\n"
    ),
    # 44. Distractor: Conversational Memory
    "distractor_conversational_memory_store.txt": (
        "Conversational memory systems enable multi-turn dialogue comprehension across sequential user queries.\n"
        "Memory architectures maintain chat history buffers, rolling window summaries, and entity knowledge graphs.\n"
        "When a user asks a follow-up question containing pronouns, the memory module rewrites the standalone query.\n"
        "Summary memory compresses long conversation histories using recursive LLM summarization techniques.\n"
        "Session stores persist conversational state in PostgreSQL or DynamoDB keyed by session_id and user_id.\n"
        "KIP v1.1 operates in single-turn question answering mode without cross-turn conversational memory tracking.\n"
        "Conversational memory is explicitly deferred to milestone v2.0 on the long-term product roadmap.\n"
    ),
    # 45. Distractor: Agentic Tool Calling
    "distractor_agentic_tool_calling.txt": (
        "Agentic AI workflows utilize autonomous multi-step reasoning architectures such as LangGraph and CrewAI.\n"
        "Agents break down complex questions into sub-tasks and execute external tool calls sequentially.\n"
        "Common tools include mathematical calculators, live web search scrapers, Python code sandboxes, and SQL query engines.\n"
        "The agent inspects intermediate tool outputs and adjusts its execution trajectory using ReAct loops.\n"
        "Tool-augmented architectures handle questions that cannot be answered from private documents alone.\n"
        "KIP v1.1 is a direct single-step RAG platform; autonomous agent workflows are deferred to v2.2 milestones.\n"
        "Agentic loops introduce latency overhead and risk non-terminating reasoning cycles if unconstrained.\n"
    ),
    # 46. Distractor: Neo4j Knowledge Graph
    "distractor_neo4j_knowledge_graph.txt": (
        "GraphRAG combines vector search with graph databases like Neo4j to capture multi-hop entity relationships.\n"
        "During document indexing, an information extraction pipeline extracts entities, relations, and claims.\n"
        "Extracted nodes and edges are stored in Neo4j using labeled property graph models and Cypher query schemas.\n"
        "When a user asks a multi-hop question, the system queries the graph using Cypher to traverse connected nodes.\n"
        "Graph context is merged with dense vector chunks to provide comprehensive structural context to the LLM.\n"
        "KIP currently relies strictly on dense vector search in Qdrant; Neo4j integration is deferred to v2.4.\n"
        "Knowledge graphs require significant computational overhead for entity extraction and ontology alignment.\n"
    ),
    # 47. Distractor: Kubernetes Orchestration
    "distractor_kubernetes_cluster_orchestration.txt": (
        "Enterprise-grade Kubernetes deployment architectures deploy KIP across distributed cloud container clusters.\n"
        "Helm charts define Kubernetes Deployment manifests, Horizontal Pod Autoscalers (HPA), and Service topologies.\n"
        "Ingress controllers manage TLS termination, rate-limiting annotations, and path-based routing to pods.\n"
        "Worker pods scale horizontally based on CPU utilization and incoming HTTP request queue depths.\n"
        "Stateful workloads such as Qdrant clusters run on dedicated node pools backed by persistent SSD volumes.\n"
        "KIP v1.1 is deployed as a single-instance container on Render Free Tier rather than a Kubernetes cluster.\n"
        "Kubernetes orchestration is deferred to enterprise milestone v3.0+ to maintain zero deployment cost.\n"
    ),
    # 48. Distractor: OAuth2 SSO Authentication
    "distractor_oauth2_sso_authentication.txt": (
        "Enterprise single sign-on (SSO) systems manage user authentication through OpenID Connect (OIDC) and SAML 2.0.\n"
        "Identity providers such as Keycloak, Okta, and Azure Active Directory issue cryptographically signed JWTs.\n"
        "Role-Based Access Control (RBAC) maps user identity claims to granular workspace and document permissions.\n"
        "API gateways validate JWT signatures, expiration timestamps, and audience claims on every HTTP request.\n"
        "KIP v1.1 uses lightweight, bearer-token workspace identifiers rather than full OAuth2 SSO authentication.\n"
        "Bearer tokens provide multi-tenant isolation without requiring external identity provider infrastructure.\n"
        "Full enterprise OAuth2 and RBAC integrations are scheduled for milestone v3.0 on the product roadmap.\n"
    ),
    # 49. Distractor: Streaming WebSocket RAG
    "distractor_streaming_websocket_rag.txt": (
        "Streaming response generation streams LLM output tokens to the user interface in real-time as they generate.\n"
        "Implementations utilize Server-Sent Events (SSE) or bidirectional WebSocket channels over HTTP/2.\n"
        "As the language model produces token deltas, the backend flushes chunked HTTP packets to client listeners.\n"
        "Streaming significantly improves perceived user latency by displaying words before generation completes.\n"
        "KIP v1.1 processes RAG queries synchronously: the full answer is generated before returning the response JSON.\n"
        "Synchronous responses simplify deterministic evaluation, latency profiling, and feedback attribution.\n"
        "Streaming WebSocket and SSE token delivery are deferred to future frontend optimization cycles.\n"
    ),
    # 50. Distractor: Cohere Reranking
    "distractor_cohere_reranking_pipeline.txt": (
        "Neural reranking utilizes cross-encoder models such as Cohere Rerank or BGE-Reranker to re-order candidates.\n"
        "Unlike bi-encoder dense embeddings that encode query and document independently into vector space,\n"
        "cross-encoders process query and candidate chunk simultaneously through multi-head self-attention layers.\n"
        "Cross-encoders capture fine-grained token-level cross-interactions, significantly improving rank precision.\n"
        "A typical two-stage pipeline retrieves 20 candidate chunks with dense search, then reranks top-5 for the LLM.\n"
        "KIP v1.1 performs single-stage retrieval directly from Qdrant without secondary cross-encoder reranking.\n"
        "Cohere Rerank and local cross-encoder models are primary candidates for v1.2 retrieval research experiments.\n"
    ),
}

# Write files and compute IDs
corpus_ids: dict[str, str] = {}
chunk_ids: dict[str, str] = {}

print("Writing 50 corpus documents to benchmarks/corpus_v1_2_expanded/...")
for fname, text in sorted(DOCUMENTS.items()):
    # Strict Unix LF line endings
    clean_text = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_bytes = clean_text.encode("utf-8")
    doc_id = hashlib.sha256(raw_bytes).hexdigest()
    # Chunk ID for index 0
    c_id = hashlib.sha256(f"{doc_id}:0".encode()).hexdigest()

    fpath = CORPUS_DIR / fname
    fpath.write_bytes(raw_bytes)
    corpus_ids[fname] = doc_id
    chunk_ids[fname] = c_id
    print(f"  {fname:<45} -> {doc_id[:16]}... ({len(raw_bytes)} bytes)")

print(f"\nSuccessfully wrote {len(corpus_ids)} documents.")

# Save corpus_ids mapping for building benchmark cases
mapping_path = REPO_ROOT / "benchmarks" / "corpus_v1_2_expanded_ids.json"
mapping_path.write_text(json.dumps({"doc_ids": corpus_ids, "chunk_ids": chunk_ids}, indent=2), encoding="utf-8")
print(f"Saved ID mappings to {mapping_path}")
