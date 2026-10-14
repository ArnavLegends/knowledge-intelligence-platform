"""Deterministic sentence-boundary chunker for document segmentation.

Implements semantic text chunking based on sentence boundaries with deterministic
rules for:
- Terminal punctuation splitting (. ! ?)
- Target chunk size accumulation
- Oversized sentence handling
- Short trailing fragment merging
- Sentence overlap within document boundaries
- Zero cross-document overlap carryover
"""

from __future__ import annotations

import re

from app.core.exceptions import ChunkingError
from app.services.chunking.chunkers.base import DocumentChunker


class SentenceBoundaryChunker(DocumentChunker):
    """Chunks text along natural sentence boundaries into coherent segments.

    Args:
        target_chunk_size: Preferred maximum character length per chunk (default 400).
        min_chunk_size: Minimum character length for standalone chunks (default 150).
            Fragments shorter than this are merged into the preceding chunk.
        overlap_sentences: Number of trailing sentences from previous chunk to
            carry forward as overlap context (default 1).
    """

    def __init__(
        self,
        target_chunk_size: int = 400,
        min_chunk_size: int = 150,
        overlap_sentences: int = 1,
    ) -> None:
        if target_chunk_size <= 0:
            raise ChunkingError("target_chunk_size must be strictly greater than 0")
        if min_chunk_size <= 0:
            raise ChunkingError("min_chunk_size must be strictly greater than 0")
        if min_chunk_size > target_chunk_size:
            raise ChunkingError("min_chunk_size cannot exceed target_chunk_size")
        if overlap_sentences < 0:
            raise ChunkingError("overlap_sentences must be non-negative")

        self.target_chunk_size = target_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_sentences = overlap_sentences

    def chunk(self, text: str) -> list[str]:
        """Convert a source string into ordered, sentence-aligned chunks.

        Follows deterministic rules:
        1. Empty/whitespace input returns an empty list.
        2. Text <= target_chunk_size returns [text.strip()].
        3. Sentences are split on terminal punctuation (. ! ?) followed by whitespace.
        4. Sentences exceeding target_chunk_size are deterministically sliced.
        5. Trailing fragments < min_chunk_size are merged into the preceding chunk
           if combined length <= target_chunk_size * 1.5, else emitted as a chunk.
        6. Overlap is strictly internal to the provided text (zero cross-doc leak).
        """
        if not text or not text.strip():
            return []

        cleaned_text = text.strip()
        if len(cleaned_text) <= self.target_chunk_size:
            return [cleaned_text]

        # 1. Deterministic sentence tokenization
        # Split on whitespace immediately following terminal punctuation (. ! ?)
        raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned_text)
        sentences: list[str] = [s.strip() for s in raw_sentences if s.strip()]

        # If no punctuation or regex produced only 1 sentence that exceeds target
        if len(sentences) <= 1:
            return self._slice_oversized_unit(cleaned_text)

        chunks: list[str] = []
        current_sentences: list[str] = []
        current_len = 0

        for sentence in sentences:
            # Handle individual sentences that exceed target_chunk_size
            if len(sentence) > self.target_chunk_size:
                if current_sentences:
                    chunk_text = " ".join(current_sentences).strip()
                    if chunk_text:
                        chunks.append(chunk_text)
                    current_sentences = []
                    current_len = 0

                oversized_slices = self._slice_oversized_unit(sentence)
                for s in oversized_slices:
                    if s.strip():
                        chunks.append(s.strip())
                continue

            # Calculate prospective length if sentence is added
            prospective_len = (
                current_len + len(sentence) + (1 if current_sentences else 0)
            )

            if prospective_len <= self.target_chunk_size:
                current_sentences.append(sentence)
                current_len = prospective_len
            else:
                # Buffer has enough content to form a chunk
                if current_sentences:
                    chunk_text = " ".join(current_sentences).strip()
                    chunks.append(chunk_text)

                    # Prepare overlap from trailing sentences
                    if self.overlap_sentences > 0:
                        overlap_pool = current_sentences[-self.overlap_sentences :]
                        current_sentences = list(overlap_pool)
                        current_len = sum(len(s) for s in current_sentences) + max(
                            0, len(current_sentences) - 1
                        )
                    else:
                        current_sentences = []
                        current_len = 0

                # Append current sentence
                current_sentences.append(sentence)
                current_len += len(sentence) + (1 if len(current_sentences) > 1 else 0)

        # 2. Handle trailing buffer
        if current_sentences:
            trailing_text = " ".join(current_sentences).strip()
            if trailing_text:
                # Check if trailing text is an orphan fragment
                if len(trailing_text) < self.min_chunk_size and chunks:
                    last_chunk = chunks[-1]
                    max_merged_len = int(self.target_chunk_size * 1.5)
                    # Deduplicate any overlap sentence already present in last_chunk
                    if trailing_text not in last_chunk:
                        candidate_merge = f"{last_chunk} {trailing_text}".strip()
                        if len(candidate_merge) <= max_merged_len:
                            chunks[-1] = candidate_merge
                        else:
                            chunks.append(trailing_text)
                else:
                    # Avoid emitting exact duplicate of preceding chunk
                    if not chunks or trailing_text != chunks[-1]:
                        chunks.append(trailing_text)

        return chunks

    def _slice_oversized_unit(self, text: str) -> list[str]:
        """Deterministically slice text exceeding target size into overlapping chunks.
        """
        slices: list[str] = []
        step = max(50, self.target_chunk_size - self.min_chunk_size)
        for i in range(0, len(text), step):
            slice_text = text[i : i + self.target_chunk_size].strip()
            if slice_text:
                slices.append(slice_text)
            if i + self.target_chunk_size >= len(text):
                break
        return slices
