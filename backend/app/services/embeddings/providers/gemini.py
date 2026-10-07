"""Gemini embedding provider adapter."""

from google import genai

from app.core.exceptions import EmbeddingProviderError
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.models import Embedding, EmbeddingRequest


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Adapter for Google Gemini's embedding API."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-004",
        client: object | None = None,
    ) -> None:
        if not api_key and client is None:
            raise EmbeddingProviderError(
                "Embedding API key is not configured for Gemini."
            )
        self._client = client or genai.Client(api_key=api_key)
        self._default_model = model

    @property
    def name(self) -> str:
        return "gemini"

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        model = request.model or self._default_model
        texts = [inp.text for inp in request.inputs]

        if not texts:
            return []

        try:
            # Generate embeddings for the list of texts
            response = self._client.models.embed_content(
                model=model,
                contents=texts,
            )
        except Exception as e:
            raise EmbeddingProviderError(f"Gemini embedding failed: {e}") from e

        # Ensure we have the same number of embeddings as inputs
        if not response.embeddings or len(response.embeddings) != len(texts):
            num_embeds = len(response.embeddings) if response.embeddings else 0
            raise EmbeddingProviderError(
                f"Gemini embedding returned incorrect number of results. "
                f"Expected {len(texts)}, got {num_embeds}."
            )

        embeddings = []
        for i, item in enumerate(response.embeddings):
            inp = request.inputs[i]
            vector = item.values
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
