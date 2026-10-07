# Research Record: E2E Integration and Multi-Format Ingestion

**Date:** 2026-10-07
**Milestone:** v0.4.0

## Engineering Architecture
This milestone achieved two primary goals:
1. Validating the full end-to-end integration of the RAG pipeline.
2. Expanding document ingestion to support multiple formats (Markdown, PDF, DOCX).

### E2E RAG Validation Methodology
- Used deterministic fake embedding generation (SHA-256 mapped to vectors) to eliminate network/API variability during E2E testing.
- Used a fake LLM provider that accurately echoed parsed queries.
- Proved that uploading a document through the `POST /api/v1/documents` endpoint correctly stores vectors in the ephemeral ChromaDB vector store.
- Demonstrated that subsequent queries via `POST /api/v1/rag/answer` properly retrieve the previously indexed chunks and maintain provenance identifiers back to the original document.

### Multi-Format Ingestion Architecture
We integrated three additional formats into the existing `DocumentIngestionService` architecture:
- **Markdown (`.md`, `.markdown`)**: Parsed natively as UTF-8, similar to `.txt`.
- **PDF (`.pdf`)**: Integrated `pypdf` for text extraction. Gracefully handles unreadable or scanned PDFs (no OCR).
- **DOCX (`.docx`)**: Integrated `python-docx` for reliable paragraph-by-paragraph text extraction.

**Normalization Strategy:**
All format-specific parsers implement the generic `DocumentParser` interface, guaranteeing they produce the standardized `ParseResult`. This ensures that downstream chunking, embedding, and vector storage remain entirely decoupled from the file type.

## Limitations
- OCR is specifically excluded; scanned PDFs without embedded text layers will yield empty results.
- Markdown structural elements (e.g., tables) are not semantically preserved in this release; they are treated as plain text.
- DOCX parsing only extracts paragraph text, omitting tables, images, and headers.

## Scientific Disclaimer
This record documents an *engineering integration milestone*. No scientific evaluation of retrieval quality, embedding distribution, or LLM hallucination rates was conducted. These formats are now structurally supported by the data pipeline but have not been formally evaluated for RAG quality improvements.
