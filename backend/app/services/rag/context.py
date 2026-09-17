"""Context construction subsystem for RAG."""

from app.services.rag.models import ContextItem
from app.services.retrieval.models import RetrievedChunk


class ContextBuilder:
    """Builds LLM context prompts from retrieved chunks."""

    @staticmethod
    def build_context_items(
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[ContextItem]:
        """Convert retrieved chunks into domain ContextItems while preserving order."""
        items = []
        for rank, chunk in enumerate(retrieved_chunks, start=1):
            items.append(
                ContextItem(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    text=chunk.text or "",
                    rank=rank,
                    score=chunk.score,
                    metadata=chunk.metadata,
                )
            )
        return items

    @staticmethod
    def build_context_string(context_items: list[ContextItem]) -> str:
        """
        Format context items into a single deterministic string with clear delimiters.
        """
        if not context_items:
            return ""

        parts = []
        for item in context_items:
            source_ref = f"Source {item.rank}"
            if item.document_id:
                source_ref += f" (Document: {item.document_id})"

            parts.append(f"--- START {source_ref} ---")
            parts.append(item.text.strip())
            parts.append(f"--- END {source_ref} ---\n")

        return "\n".join(parts)
