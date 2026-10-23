"""Context construction subsystem for RAG."""

from app.services.rag.models import ContextItem
from app.services.retrieval.models import RetrievedChunk


def sanitize_context_text(text: str) -> str:
    """Neutralize delimiter-escape sequences and prompt-breaking tags in untrusted
    chunk text.
    """
    if not text:
        return ""
    # Defang structural delimiters that attempt to close source blocks prematurely
    cleaned = text.replace("--- START", "[ESCAPED_BOUNDARY: START]")
    cleaned = cleaned.replace("--- END", "[ESCAPED_BOUNDARY: END]")
    cleaned = cleaned.replace("=== START", "[ESCAPED_BOUNDARY: START]")
    cleaned = cleaned.replace("=== END", "[ESCAPED_BOUNDARY: END]")
    # Defang common injection boundary tags
    cleaned = cleaned.replace("<context_document", "&lt;context_document")
    cleaned = cleaned.replace("</context_document>", "&lt;/context_document&gt;")
    cleaned = cleaned.replace("<content>", "&lt;content&gt;")
    cleaned = cleaned.replace("</content>", "&lt;/content&gt;")
    return cleaned


class ContextBuilder:
    """Builds LLM context prompts from retrieved chunks."""

    @staticmethod
    def build_context_items(
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[ContextItem]:
        """Convert retrieved chunks into domain ContextItems while preserving order.

        Deduplicates by chunk_id so hybrid retrieval (dense + sparse) cannot
        produce duplicate context blocks. First occurrence wins (highest-ranked).
        """
        seen_ids: set[str] = set()
        items = []
        rank = 1
        for chunk in retrieved_chunks:
            # Deduplicate by chunk ID — first occurrence (best rank) wins
            if chunk.id and chunk.id in seen_ids:
                continue
            if chunk.id:
                seen_ids.add(chunk.id)

            # Extract human-readable filename for citation display
            filename: str | None = None
            if chunk.metadata:
                filename = chunk.metadata.get("filename") or chunk.metadata.get(
                    "source_filename"
                )

            items.append(
                ContextItem(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    filename=filename,
                    text=chunk.text or "",
                    rank=rank,
                    score=chunk.score,
                    metadata=chunk.metadata,
                )
            )
            rank += 1
        return items

    @staticmethod
    def build_context_string(context_items: list[ContextItem]) -> str:
        """
        Format context items into a single deterministic string with clear delimiters
        and sanitized untrusted contents to mitigate prompt boundary breakouts.
        """
        if not context_items:
            return ""

        parts = []
        for item in context_items:
            source_ref = f"Source {item.rank}"
            if item.document_id:
                source_ref += f" (Document: {item.document_id})"

            sanitized_text = sanitize_context_text(item.text.strip())
            parts.append(f"--- START {source_ref} ---")
            parts.append(sanitized_text)
            parts.append(f"--- END {source_ref} ---\n")

        return "\n".join(parts)
