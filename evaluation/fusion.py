"""Reciprocal Rank Fusion (RRF) for hybrid retrieval evaluation.

Combines multiple ranked candidate lists (e.g. dense semantic search and
sparse lexical BM25 search) using standard Reciprocal Rank Fusion:

    RRF(d) = sum_{r in channels} (1 / (k + rank_r(d)))

Reference:
    Cormack, Clarke, and Büttcher. "Reciprocal rank fusion outperforms
    condorcet and individual rank learning methods." SIGIR 2009.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.retrieval.models import RetrievedChunk


def reciprocal_rank_fusion(
    channel_results: dict[str, Sequence[RetrievedChunk]],
    k: int = 60,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Fuse ranked candidate lists from multiple retrieval channels via RRF.

    Args:
        channel_results: Mapping of channel name (e.g. 'dense', 'sparse') to
            an ordered sequence of RetrievedChunk candidates. 1-indexed ranks
            are determined by each candidate's position in its sequence.
        k: Smoothing constant (default 60, standard in literature).
        top_k: Number of fused candidates to return.

    Returns:
        Deduplicated list of RetrievedChunk objects sorted descending by RRF score.
        Source ranks and raw scores are preserved in metadata.
    """
    if top_k <= 0 or not channel_results:
        return []

    # Map candidate_id -> accumulated RRF score and metadata
    # candidate_id priority: chunk.id if non-empty, else chunk.document_id
    candidate_scores: dict[str, float] = {}
    candidate_channel_ranks: dict[str, dict[str, int]] = {}
    candidate_channel_scores: dict[str, dict[str, float | None]] = {}
    candidate_objects: dict[str, RetrievedChunk] = {}

    for channel_name, candidates in channel_results.items():
        if not candidates:
            continue

        for rank, chunk in enumerate(candidates, start=1):
            cand_id = chunk.id or chunk.document_id or f"anon-{id(chunk)}"
            if not cand_id:
                continue

            rrf_contribution = 1.0 / (k + rank)
            candidate_scores[cand_id] = (
                candidate_scores.get(cand_id, 0.0) + rrf_contribution
            )

            if cand_id not in candidate_channel_ranks:
                candidate_channel_ranks[cand_id] = {}
                candidate_channel_scores[cand_id] = {}
                candidate_objects[cand_id] = chunk

            candidate_channel_ranks[cand_id][f"{channel_name}_rank"] = rank
            candidate_channel_scores[cand_id][f"{channel_name}_score"] = (
                float(chunk.score) if chunk.score is not None else None
            )

    if not candidate_scores:
        return []

    # Deterministic sorting:
    # Primary: -rrf_score
    # Secondary: lowest min-rank across any channel
    # Tertiary: candidate ID string for total reproducibility
    def sort_key(item: tuple[str, float]) -> tuple[float, int, str]:
        cand_id, score = item
        ranks = candidate_channel_ranks[cand_id].values()
        min_rank = min(ranks) if ranks else 999999
        return (-score, min_rank, cand_id)

    sorted_candidates = sorted(candidate_scores.items(), key=sort_key)

    fused_chunks: list[RetrievedChunk] = []
    for cand_id, rrf_score in sorted_candidates[:top_k]:
        base_chunk = candidate_objects[cand_id]
        meta = dict(base_chunk.metadata) if base_chunk.metadata else {}

        # Record fusion metadata
        meta["rrf_score"] = rrf_score
        meta.update(candidate_channel_ranks[cand_id])
        meta.update(candidate_channel_scores[cand_id])

        fused_chunks.append(
            RetrievedChunk(
                id=base_chunk.id,
                document_id=base_chunk.document_id,
                text=base_chunk.text,
                score=rrf_score,
                metadata=meta,
            )
        )

    return fused_chunks
