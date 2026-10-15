"""Isolated deterministic BM25Okapi index for KIP retrieval evaluation.

Provides an in-memory lexical retrieval index using standard Robertson-Spärck Jones
BM25Okapi scoring with Lucene smoothing to guarantee non-negative IDFs.

Implementation features:
- Deterministic text normalization and tokenization.
- No external heavy dependencies (uses standard library math and re).
- Scored chunks returned as standard RetrievedChunk objects.
- Completely isolated from production vector stores and databases.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

from app.services.retrieval.models import RetrievedChunk


def tokenize_text(text: str) -> list[str]:
    """Tokenize text into normalized lowercase alphanumeric terms.

    Extracts terms preserving internal hyphens/underscores (e.g. 'x-kip-workspace-id')
    and alphanumeric words.
    """
    if not text:
        return []
    return re.findall(r"\b[a-zA-Z0-9_\-]+\b|\b\w+\b", text.lower())


class BM25Document:
    """Internal indexed representation of a chunk/document for BM25."""

    __slots__ = ("id", "document_id", "text", "metadata", "tokens", "length", "tf")

    def __init__(
        self,
        id: str,
        document_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.document_id = document_id
        self.text = text
        self.metadata = metadata or {}
        self.tokens = tokenize_text(text)
        self.length = len(self.tokens)
        self.tf = Counter(self.tokens)


class BM25Index:
    """In-memory BM25Okapi index over a collection of chunks.

    Args:
        k1: Term frequency saturation parameter (default 1.5).
        b: Document length normalization parameter (default 0.75).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.documents: list[BM25Document] = []
        self.doc_frequencies: Counter[str] = Counter()
        self.avg_doc_len: float = 0.0
        self.num_docs: int = 0
        self._idf_cache: dict[str, float] = {}

    def index_chunks(self, chunks: Sequence[Any]) -> None:
        """Build the BM25 index from a collection of chunks or documents.

        Accepts any sequence of objects with `id`, `document_id`, `text`
        (and optionally `metadata`).
        """
        self.documents = []
        self.doc_frequencies = Counter()
        self._idf_cache = {}

        total_tokens = 0
        for chunk in chunks:
            chunk_id = getattr(chunk, "id", "") or ""
            doc_id = getattr(chunk, "document_id", "") or ""
            text = getattr(chunk, "text", "") or ""
            metadata = getattr(chunk, "metadata", None)

            doc = BM25Document(
                id=chunk_id,
                document_id=doc_id,
                text=text,
                metadata=metadata,
            )
            self.documents.append(doc)
            total_tokens += doc.length

            # Document frequency counts unique terms per document
            for term in set(doc.tokens):
                self.doc_frequencies[term] += 1

        self.num_docs = len(self.documents)
        self.avg_doc_len = (total_tokens / self.num_docs) if self.num_docs > 0 else 0.0

    def idf(self, term: str) -> float:
        """Calculate Robertson-Spärck Jones IDF with Lucene smoothing.

        IDF(t) = ln(1.0 + (N - n(t) + 0.5) / (n(t) + 0.5))
        Guarantees non-negative IDF for all terms even when n(t) > N/2.
        """
        if term in self._idf_cache:
            return self._idf_cache[term]

        n_q = self.doc_frequencies.get(term, 0)
        val = math.log(1.0 + (self.num_docs - n_q + 0.5) / (n_q + 0.5))
        self._idf_cache[term] = val
        return val

    def search(
        self,
        query: str,
        top_k: int = 20,
    ) -> list[RetrievedChunk]:
        """Perform BM25 retrieval for query text.

        Args:
            query: User search query string.
            top_k: Maximum number of candidates to return.

        Returns:
            Ranked list of RetrievedChunk objects in descending order of BM25 score.
        """
        if not query or not query.strip() or not self.documents or top_k <= 0:
            return []

        query_tokens = tokenize_text(query)
        if not query_tokens:
            return []

        # Filter query tokens to those present in the corpus vocabulary
        active_tokens = [t for t in query_tokens if t in self.doc_frequencies]
        if not active_tokens:
            # Query terms don't appear in corpus at all
            return []

        scored_docs: list[tuple[float, BM25Document]] = []
        k1 = self.k1
        b = self.b
        avgdl = self.avg_doc_len if self.avg_doc_len > 0 else 1.0

        for doc in self.documents:
            score = 0.0
            doc_len = doc.length
            len_norm = 1.0 - b + b * (doc_len / avgdl)

            for term in active_tokens:
                f_q = doc.tf.get(term, 0)
                if f_q == 0:
                    continue
                idf_val = self.idf(term)
                term_score = idf_val * ((f_q * (k1 + 1.0)) / (f_q + k1 * len_norm))
                score += term_score

            if score > 0.0:
                scored_docs.append((score, doc))

        # Sort descending by score; break ties deterministically by chunk id
        scored_docs.sort(key=lambda item: (-item[0], item[1].id))

        results: list[RetrievedChunk] = []
        for score, doc in scored_docs[:top_k]:
            meta = dict(doc.metadata) if doc.metadata else {}
            meta["bm25_score"] = score
            results.append(
                RetrievedChunk(
                    id=doc.id,
                    document_id=doc.document_id,
                    text=doc.text,
                    score=score,
                    metadata=meta,
                )
            )

        return results
