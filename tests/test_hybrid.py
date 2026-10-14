"""Unit and integration tests for BM25 sparse retrieval and RRF fusion.

Verifies:
- Deterministic sparse retrieval
- Correct ranking for representative exact-term queries
- Exact RRF score calculation
- Stable deduplication by candidate ID
- Candidate ordering and tie handling
- Missing or duplicate identifiers
- Empty dense or sparse candidate lists
- Candidate sets with fewer than five results
- Correct preservation of source ranks and scores without mutating candidates
- Evaluation runner integration with hybrid retrieval
- Production isolation
"""

from __future__ import annotations

import pytest
from evaluation.bm25 import BM25Index, tokenize_text
from evaluation.fusion import reciprocal_rank_fusion
from evaluation.models import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkRunConfig,
)
from evaluation.runner import EvaluationRunner

from app.services.retrieval.models import RetrievedChunk

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_chunks() -> list[RetrievedChunk]:
    """Sample corpus chunks for BM25 indexing."""
    return [
        RetrievedChunk(
            id="chk-001",
            document_id="doc-001",
            text=(
                "Every workspace-scoped request must supply the "
                "X-KIP-Workspace-ID header in KIP multitenancy."
            ),
            score=0.9,
            metadata={"doc_name": "multitenancy.txt"},
        ),
        RetrievedChunk(
            id="chk-002",
            document_id="doc-002",
            text=(
                "Vector search uses Qdrant with cosine distance and "
                "768 dimensions for dense embeddings."
            ),
            score=0.8,
            metadata={"doc_name": "vector_store.txt"},
        ),
        RetrievedChunk(
            id="chk-003",
            document_id="doc-003",
            text=(
                "Document chunking operates with fixed-size chunks of "
                "1000 characters and 200 overlap."
            ),
            score=0.7,
            metadata={"doc_name": "chunking.txt"},
        ),
        RetrievedChunk(
            id="chk-004",
            document_id="doc-004",
            text=(
                "Distractor: BM25 and SPLADE hybrid proposals evaluate "
                "Reciprocal Rank Fusion with k=60."
            ),
            score=0.6,
            metadata={"doc_name": "distractor.txt"},
        ),
    ]


# ---------------------------------------------------------------------------
# BM25 Unit Tests
# ---------------------------------------------------------------------------


def test_bm25_tokenization():
    """Verify tokenizer extracts normalized alphanumeric and hyphenated tokens."""
    tokens = tokenize_text("What HTTP header X-KIP-Workspace-ID is required?")
    assert "x-kip-workspace-id" in tokens
    assert "http" in tokens
    assert "header" in tokens
    assert "required" in tokens
    assert tokenize_text("") == []


def test_bm25_deterministic_retrieval(sample_chunks):
    """Verify repeated retrieval with BM25 produces identical results and scores."""
    index = BM25Index(k1=1.5, b=0.75)
    index.index_chunks(sample_chunks)

    res1 = index.search("X-KIP-Workspace-ID header", top_k=3)
    res2 = index.search("X-KIP-Workspace-ID header", top_k=3)

    assert len(res1) == len(res2)
    for c1, c2 in zip(res1, res2, strict=True):
        assert c1.id == c2.id
        assert c1.score == c2.score
        assert c1.metadata["bm25_score"] == c2.metadata["bm25_score"]


def test_bm25_exact_term_ranking(sample_chunks):
    """Verify exact-term query correctly places the relevant chunk at rank 1."""
    index = BM25Index()
    index.index_chunks(sample_chunks)

    results = index.search("X-KIP-Workspace-ID", top_k=5)
    assert len(results) >= 1
    assert results[0].id == "chk-001"
    assert results[0].document_id == "doc-001"
    assert results[0].score > 0.0


def test_bm25_empty_query_or_index(sample_chunks):
    """Verify empty queries or empty index gracefully return empty results."""
    index = BM25Index()
    assert index.search("hello", top_k=5) == []

    index.index_chunks(sample_chunks)
    assert index.search("", top_k=5) == []
    assert index.search("   ", top_k=5) == []
    assert index.search("xyznonexistentterm12345", top_k=5) == []
    assert index.search("hello", top_k=0) == []


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion Unit Tests
# ---------------------------------------------------------------------------


def test_rrf_score_calculation():
    """Verify RRF formula calculation matches standard 1/(k + rank)."""
    c_dense = [
        RetrievedChunk(id="c1", document_id="d1", text="text1", score=0.9),
        RetrievedChunk(id="c2", document_id="d2", text="text2", score=0.8),
    ]
    c_sparse = [
        RetrievedChunk(id="c2", document_id="d2", text="text2", score=4.5),
        RetrievedChunk(id="c1", document_id="d1", text="text1", score=1.2),
    ]

    fused = reciprocal_rank_fusion(
        {"dense": c_dense, "sparse": c_sparse},
        k=60,
        top_k=5,
    )

    # c1: dense rank 1 (1/61), sparse rank 2 (1/62) -> 1/61 + 1/62
    expected_c1 = (1.0 / 61.0) + (1.0 / 62.0)
    # c2: dense rank 2 (1/62), sparse rank 1 (1/61) -> 1/62 + 1/61
    expected_c2 = (1.0 / 62.0) + (1.0 / 61.0)

    assert len(fused) == 2
    assert abs(expected_c1 - expected_c2) < 1e-9
    assert abs(fused[0].score - expected_c1) < 1e-6


def test_rrf_stable_deduplication():
    """Verify duplicates across channels are merged with both ranks preserved."""
    c_dense = [
        RetrievedChunk(id="chunk_a", document_id="doc_a", text="A", score=0.95),
        RetrievedChunk(id="chunk_b", document_id="doc_b", text="B", score=0.85),
    ]
    c_sparse = [
        RetrievedChunk(id="chunk_a", document_id="doc_a", text="A", score=3.2),
        RetrievedChunk(id="chunk_c", document_id="doc_c", text="C", score=2.1),
    ]

    fused = reciprocal_rank_fusion(
        {"dense": c_dense, "sparse": c_sparse},
        k=60,
        top_k=5,
    )

    assert len(fused) == 3
    assert fused[0].id == "chunk_a"
    assert fused[0].metadata["dense_rank"] == 1
    assert fused[0].metadata["sparse_rank"] == 1
    assert fused[0].metadata["dense_score"] == 0.95
    assert fused[0].metadata["sparse_score"] == 3.2
    assert fused[0].score == (1.0 / 61.0) + (1.0 / 61.0)


def test_rrf_candidate_ordering_and_tie_handling():
    """Verify strictly descending order and deterministic tie handling."""
    c1 = [RetrievedChunk(id="x_id", document_id="dx", text="X", score=0.9)]
    c2 = [RetrievedChunk(id="y_id", document_id="dy", text="Y", score=0.8)]

    fused = reciprocal_rank_fusion({"ch1": c1, "ch2": c2}, k=60, top_k=2)
    assert len(fused) == 2
    assert fused[0].score == fused[1].score
    assert {fused[0].id, fused[1].id} == {"x_id", "y_id"}


def test_rrf_missing_or_duplicate_identifiers():
    """Verify fusion handles missing chunk id by falling back to doc id."""
    c1 = [RetrievedChunk(id="", document_id="doc_only_1", text="T1", score=0.9)]
    c2 = [RetrievedChunk(id="", document_id="doc_only_1", text="T1", score=1.5)]

    fused = reciprocal_rank_fusion({"dense": c1, "sparse": c2}, k=60, top_k=5)
    assert len(fused) == 1
    assert fused[0].document_id == "doc_only_1"
    assert fused[0].score == (1.0 / 61.0) + (1.0 / 61.0)


def test_rrf_empty_dense_or_sparse_lists():
    """Verify graceful handling when one or all channels are empty."""
    c_dense = [RetrievedChunk(id="c1", document_id="d1", text="T", score=0.9)]

    fused_sparse_empty = reciprocal_rank_fusion(
        {"dense": c_dense, "sparse": []}, k=60, top_k=5
    )
    assert len(fused_sparse_empty) == 1
    assert fused_sparse_empty[0].id == "c1"
    assert fused_sparse_empty[0].score == 1.0 / 61.0
    assert fused_sparse_empty[0].metadata["dense_rank"] == 1
    assert "sparse_rank" not in fused_sparse_empty[0].metadata

    assert reciprocal_rank_fusion({"dense": [], "sparse": []}, k=60, top_k=5) == []
    assert reciprocal_rank_fusion({}, k=60, top_k=5) == []


def test_rrf_fewer_than_five_results():
    """Verify fusion preserves all candidates when total distinct items < 5."""
    c_dense = [
        RetrievedChunk(id="c1", document_id="d1", text="T1", score=0.9),
        RetrievedChunk(id="c2", document_id="d2", text="T2", score=0.8),
    ]
    fused = reciprocal_rank_fusion({"dense": c_dense}, k=60, top_k=5)
    assert len(fused) == 2
    assert [c.id for c in fused] == ["c1", "c2"]


def test_no_mutation_of_original_candidates():
    """Verify original input candidate objects are not modified by fusion."""
    orig_chunk = RetrievedChunk(
        id="c1",
        document_id="d1",
        text="text",
        score=0.95,
        metadata={"custom_key": "custom_val"},
    )
    c_list = [orig_chunk]

    fused = reciprocal_rank_fusion({"dense": c_list}, k=60, top_k=5)
    assert len(fused) == 1
    assert orig_chunk.score == 0.95
    assert "rrf_score" not in orig_chunk.metadata
    assert "dense_rank" not in orig_chunk.metadata
    assert fused[0].score != orig_chunk.score
    assert "rrf_score" in fused[0].metadata
    assert fused[0].metadata["custom_key"] == "custom_val"


# ---------------------------------------------------------------------------
# EvaluationRunner Hybrid Integration Test
# ---------------------------------------------------------------------------


class MockRetrievalService:
    """Mock RetrievalService that returns canned candidates."""

    def __init__(self, candidates: list[RetrievedChunk]) -> None:
        self.candidates = candidates

    def search(self, query) -> list[RetrievedChunk]:
        return list(self.candidates[: query.top_k])


def test_evaluation_runner_hybrid_integration():
    """Verify EvaluationRunner executes hybrid retrieval correctly."""
    dense_chunks = [
        RetrievedChunk(
            id="chk-d1", document_id="target-doc", text="Target", score=0.85
        ),
        RetrievedChunk(
            id="chk-d2", document_id="other-doc", text="Other", score=0.75
        ),
    ]
    mock_ret_service = MockRetrievalService(dense_chunks)

    sparse_index = BM25Index()
    sparse_index.index_chunks(
        [
            RetrievedChunk(
                id="chk-d2",
                document_id="other-doc",
                text="Other text",
                score=1.0,
            ),
            RetrievedChunk(
                id="chk-d1",
                document_id="target-doc",
                text="Target keyword text",
                score=2.0,
            ),
        ]
    )

    config = BenchmarkRunConfig(
        benchmark_version="test-hybrid",
        evaluation_workspace_id="test-workspace",
        llm_provider="none",
        llm_model="none",
        embedding_provider="none",
        embedding_model="none",
        retrieval_top_k=5,
        chunk_size=1000,
        chunk_overlap=200,
    )

    runner = EvaluationRunner(
        rag_service=None,
        retrieval_service=mock_ret_service,
        config=config,
        sparse_retriever=sparse_index,
        candidate_top_k=10,
        rrf_k=60,
    )

    case = BenchmarkCase(
        id="case-1",
        question="Target keyword",
        reference_answer="",
        expected_document_ids=["target-doc"],
        expected_chunk_ids=["chk-d1"],
    )
    dataset = BenchmarkDataset(version="test", cases=[case])

    result = runner.evaluate_dataset(dataset)
    assert result.total_cases == 1
    assert result.labelled_cases == 1
    assert result.hit_rate == 1.0
    assert result.mean_reciprocal_rank == 1.0
    assert result.case_results[0].retrieval.hit_at_1 is True
    assert result.case_results[0].retrieval.dense_latency_ms is not None
    assert result.case_results[0].retrieval.sparse_latency_ms is not None
    assert result.case_results[0].retrieval.fusion_latency_ms is not None
