"""OpenAI embedding provider adapter."""

import openai
from openai import OpenAI

from app.core.exceptions import EmbeddingProviderError
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.models import Embedding, EmbeddingRequest


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Adapter for OpenAI's embedding API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._client = OpenAI(api_key=api_key)
        self._default_model = model

    @property
    def name(self) -> str:
        return "openai"

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        model = request.model or self._default_model

        texts = [inp.text for inp in request.inputs]

        try:
            response = self._client.embeddings.create(
                input=texts,
                model=model,
            )
        except openai.OpenAIError as e:
            raise EmbeddingProviderError(f"OpenAI embedding failed: {e}") from e

        # Ensure the response is ordered properly (OpenAI usually preserves order)
        # We sort by index just to be absolutely safe.
        data_sorted = sorted(response.data, key=lambda x: x.index)

        embeddings = []
        for i, item in enumerate(data_sorted):
            inp = request.inputs[i]
            vector = item.embedding
            embeddings.append(
                Embedding(
                    source_id=inp.source_id,
                    vector=vector,
                    dimensions=len(vector),
                    metadata=inp.metadata.copy(),
                    provider=self.name,
                    model=model,
                )
            )

        return embeddings
