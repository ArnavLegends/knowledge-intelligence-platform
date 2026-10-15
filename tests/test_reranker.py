"""Unit and integration tests for the evaluation-only cross-encoder reranker.

Tests:
- Candidate preservation and ID consistency
- Stable mapping of scores to query-candidate pairs
- Correct descending reranking order
- Handling of empty candidate lists
- Handling of fewer than 20 candidates (and fewer than top-k)
- Handling of malformed or missing candidate metadata
- Relevance metrics after reranking in EvaluationRunner
- No mutation of original candidate records
- No changes to production retrieval defaults
- Integration test with ONNX Runtime session
"""

from unittest.mock import MagicMock

import numpy as np
import pytest
from evaluation.models import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkRunConfig,
)
from evaluation.reranker import CrossEncoderReranker
from evaluation.runner import EvaluationRunner

from app.core.config import Settings
from app.services.retrieval.models import RetrievedChunk
from app.services.retrieval.service import RetrievalService

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    chunk_id: str,
    doc_id: str,
    text: str,
    score: float = 0.5,
    metadata: dict | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        document_id=doc_id,
        text=text,
        score=score,
        metadata=metadata if metadata is not None else {"source": "test"},
    )


def _make_mock_reranker(scores: list[float]) -> CrossEncoderReranker:
    """Creates a CrossEncoderReranker with mocked session and tokenizer."""
    mock_session = MagicMock()
    # ONNX output shape is (batch_size, 1)
    mock_session.run.return_value = [np.array([[s] for s in scores], dtype=np.float32)]

    mock_tokenizer = MagicMock()
    mock_encodings = [
        MagicMock(ids=[101, 102], attention_mask=[1, 1], type_ids=[0, 1])
        for _ in scores
    ]
    mock_tokenizer.encode_batch.return_value = mock_encodings

    return CrossEncoderReranker(
        model_name="mock-cross-encoder",
        session=mock_session,
        tokenizer=mock_tokenizer,
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_reranker_handles_empty_candidates():
    """Reranker must return empty list and zero latency when candidates list is empty."""
    reranker = _make_mock_reranker([])
    reranked, lat = reranker.rerank("What is KIP?", candidates=[], top_k=5)

    assert reranked == []
    assert lat == 0.0


def test_reranker_handles_fewer_than_top_k_candidates():
    """When candidate count is less than top_k, all candidates should be returned sorted."""
    candidates = [
        _make_candidate("c1", "d1", "Text 1", score=0.8),
        _make_candidate("c2", "d2", "Text 2", score=0.6),
    ]
    # Candidate 2 gets higher rerank score than candidate 1
    reranker = _make_mock_reranker([1.5, 4.2])
    reranked, lat = reranker.rerank("Query", candidates, top_k=5)

    assert len(reranked) == 2
    assert reranked[0].id == "c2"
    assert reranked[0].rerank_score == pytest.approx(4.2, abs=1e-4)
    assert reranked[1].id == "c1"
    assert reranked[1].rerank_score == pytest.approx(1.5, abs=1e-4)
    assert lat >= 0.0


def test_reranker_descending_order_and_score_mapping():
    """Candidates must be sorted strictly descending by rerank score."""
    candidates = [
        _make_candidate("c1", "d1", "Text 1", score=0.9),
        _make_candidate("c2", "d2", "Text 2", score=0.8),
        _make_candidate("c3", "d3", "Text 3", score=0.7),
        _make_candidate("c4", "d4", "Text 4", score=0.6),
    ]
    # Scores: c1=-1.0, c2=5.0, c3=2.0, c4=0.0
    reranker = _make_mock_reranker([-1.0, 5.0, 2.0, 0.0])
    reranked, _ = reranker.rerank("Query", candidates, top_k=3)

    assert len(reranked) == 3
    assert [c.id for c in reranked] == ["c2", "c3", "c4"]
    assert [c.rerank_score for c in reranked] == [
        pytest.approx(5.0),
        pytest.approx(2.0),
        pytest.approx(0.0),
    ]


def test_reranker_preserves_candidate_attributes_and_dense_rank():
    """RerankedChunk must preserve original dense candidate attributes and original rank."""
    candidates = [
        _make_candidate("c1", "d1", "Text 1", score=0.95, metadata={"k": "v1"}),
        _make_candidate("c2", "d2", "Text 2", score=0.45, metadata={"k": "v2"}),
    ]
    # Invert order
    reranker = _make_mock_reranker([0.1, 9.9])
    reranked, _ = reranker.rerank("Query", candidates, top_k=2)

    top = reranked[0]
    assert top.id == "c2"
    assert top.document_id == "d2"
    assert top.text == "Text 2"
    assert top.dense_score == 0.45
    assert top.dense_rank == 2  # Was position 2 in candidate list
    assert top.rerank_score == pytest.approx(9.9, abs=1e-4)
    assert top.metadata == {"k": "v2"}

    second = reranked[1]
    assert second.id == "c1"
    assert second.dense_score == 0.95
    assert second.dense_rank == 1  # Was position 1 in candidate list
    assert second.rerank_score == pytest.approx(0.1, abs=1e-4)


def test_reranker_does_not_mutate_original_candidates():
    """Reranking must not alter or mutate the original RetrievedChunk instances."""
    candidates = [
        _make_candidate(
            "c1", "d1", "Original text", score=0.75, metadata={"flag": True}
        )
    ]
    original_dict = {
        "id": candidates[0].id,
        "document_id": candidates[0].document_id,
        "text": candidates[0].text,
        "score": candidates[0].score,
        "metadata": candidates[0].metadata.copy(),
    }

    reranker = _make_mock_reranker([3.14])
    reranked, _ = reranker.rerank("Query", candidates, top_k=1)

    # Input record remains unmodified
    assert candidates[0].id == original_dict["id"]
    assert candidates[0].document_id == original_dict["document_id"]
    assert candidates[0].text == original_dict["text"]
    assert candidates[0].score == original_dict["score"]
    assert candidates[0].metadata == original_dict["metadata"]
    assert not hasattr(candidates[0], "rerank_score")


def test_reranker_handles_missing_or_malformed_metadata():
    """Reranker handles chunks with None text, None metadata, or None score gracefully."""
    chunk_empty = RetrievedChunk(
        id="c_none", document_id=None, text=None, score=None, metadata={}
    )
    chunk_normal = _make_candidate("c_norm", "d_norm", "Valid passage", score=0.5)

    reranker = _make_mock_reranker([-2.0, 1.0])
    reranked, _ = reranker.rerank("Query", [chunk_empty, chunk_normal], top_k=2)

    assert len(reranked) == 2
    assert reranked[0].id == "c_norm"
    assert reranked[1].id == "c_none"
    assert reranked[1].text is None
    assert reranked[1].dense_score is None


def test_reranker_stable_tie_breaking_by_dense_rank():
    """Ties in rerank score must be broken deterministically by dense_rank."""
    candidates = [
        _make_candidate("c1", "d1", "Text 1", score=0.9),
        _make_candidate("c2", "d2", "Text 2", score=0.8),
        _make_candidate("c3", "d3", "Text 3", score=0.7),
    ]
    # Identical cross-encoder score for all
    reranker = _make_mock_reranker([2.5, 2.5, 2.5])
    reranked, _ = reranker.rerank("Query", candidates, top_k=3)

    # Must preserve dense_rank order: c1 (dense 1), c2 (dense 2), c3 (dense 3)
    assert [c.id for c in reranked] == ["c1", "c2", "c3"]


def test_evaluation_runner_two_stage_retrieval_and_metrics():
    """EvaluationRunner with reranker must execute Stage A candidates and Stage B reranking."""
    # Create 4 candidates: target is at position 4 in candidate retrieval (Hit@1=0, Hit@3=0 in candidate stage)
    candidates = [
        _make_candidate("c1", "d_distractor1", "Distractor 1", score=0.95),
        _make_candidate("c2", "d_distractor2", "Distractor 2", score=0.90),
        _make_candidate("c3", "d_distractor3", "Distractor 3", score=0.85),
        _make_candidate("c4", "d_target", "Relevant target text", score=0.80),
    ]

    mock_retrieval = MagicMock()
    mock_retrieval.search.return_value = candidates

    # Reranker elevates candidate 4 to position 1
    mock_reranker = _make_mock_reranker([0.1, 0.2, 0.3, 9.5])

    config = BenchmarkRunConfig(
        benchmark_version="v1.2-rerank-test",
        evaluation_workspace_id="test-ws",
        llm_provider="none",
        llm_model="none",
        embedding_provider="gemini",
        embedding_model="gemini-embedding-2",
        retrieval_top_k=3,
        chunk_size=1000,
        chunk_overlap=200,
    )

    dataset = BenchmarkDataset(
        version="v1.2-test",
        cases=[
            BenchmarkCase(
                id="test-001",
                question="What is the target?",
                expected_document_ids=["d_target"],
                expected_chunk_ids=["c4"],
            )
        ],
    )

    runner = EvaluationRunner(
        rag_service=None,
        retrieval_service=mock_retrieval,
        config=config,
        reranker=mock_reranker,
        candidate_top_k=4,
    )

    result = runner.evaluate_dataset(dataset)

    assert result.total_cases == 1
    cr = result.case_results[0]
    ret = cr.retrieval

    # Candidate metrics
    assert ret.candidate_count == 4
    assert ret.candidate_hit_at_20 is True
    assert ret.candidate_doc_ids == [
        "d_distractor1",
        "d_distractor2",
        "d_distractor3",
        "d_target",
    ] or set(ret.candidate_doc_ids) == {
        "d_distractor1",
        "d_distractor2",
        "d_distractor3",
        "d_target",
    }

    # Final reranked metrics: target chunk c4 was elevated to rank 1
    assert ret.hit is True
    assert ret.hit_at_1 is True
    assert ret.hit_at_3 is True
    assert ret.reciprocal_rank == 1.0
    assert ret.retrieved_chunk_ids[0] == "c4"
    assert ret.reranking_latency_ms is not None
    assert ret.reranking_latency_ms >= 0.0

    # Aggregate result metrics
    assert result.hit_rate_at_1 == 1.0
    assert result.mean_reciprocal_rank == 1.0
    assert result.candidate_hit_rate_at_20 == 1.0


def test_production_retrieval_defaults_unmodified():
    """Production RetrievalService and Settings must not have reranking enabled by default."""
    s = Settings()
    # RetrievalService search does not take or use reranker
    rs = RetrievalService(settings=s)
    assert not hasattr(rs, "_reranker")
    assert not hasattr(s, "reranker_model")


def test_live_onnx_reranker_inference():
    """Verify live cross-encoder/ms-marco-MiniLM-L-6-v2 ONNX model on realistic inputs."""
    # This tests the real ONNX runtime session and tokenizer downloaded in Stage 1
    reranker = CrossEncoderReranker()
    assert reranker.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert reranker.cold_start_load_ms >= 0.0

    query = "What is the capital of France?"
    candidates = [
        _make_candidate("c1", "d1", "Berlin is the capital of Germany.", score=0.8),
        _make_candidate("c2", "d2", "Paris is the capital of France.", score=0.7),
        _make_candidate("c3", "d3", "Madrid is the capital of Spain.", score=0.6),
    ]

    reranked, lat = reranker.rerank(query, candidates, top_k=3)

    assert len(reranked) == 3
    # Paris should be rank 1 with highest score
    assert reranked[0].id == "c2"
    assert reranked[0].document_id == "d2"
    assert reranked[0].rerank_score > reranked[1].rerank_score
    assert reranked[0].rerank_score > reranked[2].rerank_score
    assert lat > 0.0
