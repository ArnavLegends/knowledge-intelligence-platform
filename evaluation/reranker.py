"""Cross-encoder reranking implementation for evaluation pipelines.

Provides a lightweight, locally executed cross-encoder using ONNX Runtime
and Hugging Face Tokenizers. Evaluates query-candidate pairs jointly
through full multi-head self-attention ([CLS] query [SEP] candidate [SEP])
to output an unnormalized logit relevance score.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
Architecture: BERT 6-layer MiniLM distilled on MS MARCO passage ranking
Inference Engine: ONNX Runtime (CPUExecutionProvider)
Max Sequence Length: 512 tokens (query + candidate combined)

NOTE: Cross-encoder scores are raw unnormalized logits (higher = more relevant).
They are NOT probabilities and must not be interpreted as calibrated confidence.
"""

from __future__ import annotations

import logging
import pathlib
import time
from collections.abc import Sequence
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from app.services.retrieval.models import RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
MAX_SEQUENCE_LENGTH = 512


class RerankedChunk(BaseModel):
    """Represents a retrieved chunk after cross-encoder reranking.

    Preserves both the original dense candidate properties (dense score,
    dense rank) and the cross-encoder logit score.
    """

    id: str
    document_id: str | None = None
    text: str | None = None
    dense_score: float | None = None
    dense_rank: int
    rerank_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class CrossEncoderReranker:
    """Locally executed cross-encoder reranker using ONNX Runtime.

    Scores candidate passages for a query and sorts candidates in
    descending order of relevance.

    Args:
        model_name: HuggingFace repository ID.
        max_length: Maximum combined sequence length (default 512).
        onnx_model_path: Optional explicit filesystem path to model.onnx.
        tokenizer_path: Optional explicit filesystem path to tokenizer.json.
        session: Optional pre-initialized ONNX InferenceSession (for testing/mocking).
        tokenizer: Optional pre-initialized Tokenizer (for testing/mocking).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        max_length: int = MAX_SEQUENCE_LENGTH,
        onnx_model_path: str | pathlib.Path | None = None,
        tokenizer_path: str | pathlib.Path | None = None,
        session: Any | None = None,
        tokenizer: Any | None = None,
    ) -> None:
        self.model_name = model_name
        self.max_length = max_length
        self._cold_start_load_ms: float = 0.0

        if session is not None and tokenizer is not None:
            self._session = session
            self._tokenizer = tokenizer
            return

        t_start = time.perf_counter()
        self._tokenizer = self._load_tokenizer(tokenizer_path)
        self._session = self._load_session(onnx_model_path)
        self._cold_start_load_ms = (time.perf_counter() - t_start) * 1000

        logger.info(
            "CrossEncoderReranker loaded: model=%s in %.2f ms",
            self.model_name,
            self._cold_start_load_ms,
        )

    @property
    def cold_start_load_ms(self) -> float:
        """Wall-clock time in milliseconds spent loading the model and tokenizer."""
        return self._cold_start_load_ms

    def _load_tokenizer(self, custom_path: str | pathlib.Path | None) -> Any:
        from tokenizers import Tokenizer

        if custom_path:
            path = pathlib.Path(custom_path)
        else:
            from huggingface_hub import hf_hub_download

            path = pathlib.Path(
                hf_hub_download(repo_id=self.model_name, filename="tokenizer.json")
            )

        tokenizer = Tokenizer.from_file(str(path))
        tokenizer.enable_padding(direction="right", pad_id=0, pad_token="[PAD]")
        tokenizer.enable_truncation(max_length=self.max_length)
        return tokenizer

    def _load_session(self, custom_path: str | pathlib.Path | None) -> Any:
        import onnxruntime as ort

        if custom_path:
            path = pathlib.Path(custom_path)
        else:
            from huggingface_hub import hf_hub_download

            path = pathlib.Path(
                hf_hub_download(repo_id=self.model_name, filename="onnx/model.onnx")
            )

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 4
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        return ort.InferenceSession(
            str(path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )

    def score_pairs(
        self, pairs: Sequence[tuple[str, str]]
    ) -> tuple[list[float], float]:
        """Score a batch of (query, candidate_text) pairs.

        Returns:
            (scores, latency_ms) where scores is a list of raw float logits.
        """
        if not pairs:
            return [], 0.0

        t_start = time.perf_counter()

        # Tokenize pairs simultaneously
        encodings = self._tokenizer.encode_batch(list(pairs))

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        token_type_ids = np.array([e.type_ids for e in encodings], dtype=np.int64)

        inputs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }

        outputs = self._session.run(None, inputs)
        raw_logits = outputs[0].flatten().tolist()

        latency_ms = (time.perf_counter() - t_start) * 1000
        return [float(s) for s in raw_logits], latency_ms

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        top_k: int = 5,
    ) -> tuple[list[RerankedChunk], float]:
        """Rerank candidates for a query in descending order of relevance.

        Preserves original candidate properties and dense rank.
        Does not mutate the candidate objects.

        Args:
            query: User or benchmark query string.
            candidates: Sequence of dense RetrievedChunk candidates.
            top_k: Number of reranked candidates to return.

        Returns:
            (reranked_chunks, reranking_latency_ms)
        """
        if not candidates:
            return [], 0.0

        pairs = [(query, c.text or "") for c in candidates]
        scores, latency_ms = self.score_pairs(pairs)

        # Build RerankedChunk objects
        reranked_all: list[RerankedChunk] = []
        for idx, (candidate, score) in enumerate(
            zip(candidates, scores, strict=True), start=1
        ):
            meta = (
                candidate.metadata.copy()
                if hasattr(candidate, "metadata") and candidate.metadata
                else {}
            )
            reranked_all.append(
                RerankedChunk(
                    id=candidate.id,
                    document_id=candidate.document_id,
                    text=candidate.text,
                    dense_score=candidate.score,
                    dense_rank=idx,
                    rerank_score=score,
                    metadata=meta,
                )
            )

        # Sort descending by rerank_score, with dense_rank as deterministic tie-breaker
        reranked_all.sort(key=lambda x: (-x.rerank_score, x.dense_rank))

        return reranked_all[:top_k], latency_ms
