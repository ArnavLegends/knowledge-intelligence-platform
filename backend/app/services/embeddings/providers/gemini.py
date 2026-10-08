"""Gemini embedding provider adapter."""

from google import genai
from google.genai import types

from app.core.exceptions import EmbeddingProviderError
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.models import Embedding, EmbeddingRequest


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Adapter for Google Gemini's embedding API with configurable dimensionality."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-2",
        output_dimensionality: int | None = None,
        client: object | None = None,
    ) -> None:
        if not api_key and client is None:
            raise EmbeddingProviderError(
                "Embedding API key is not configured for Gemini."
            )
        self._client = client or genai.Client(api_key=api_key)
        self._default_model = model
        self._output_dimensionality = output_dimensionality

    @property
    def name(self) -> str:
        return "gemini"

    def embed(self, request: EmbeddingRequest) -> list[Embedding]:
        model = request.model or self._default_model
        if not request.inputs:
            return []

        contents = [
            types.Content(parts=[types.Part.from_text(text=inp.text)])
            for inp in request.inputs
        ]

        embed_config = None
        if self._output_dimensionality:
            try:
                embed_config = types.EmbedContentConfig(
                    output_dimensionality=self._output_dimensionality
                )
            except Exception:
                embed_config = {"output_dimensionality": self._output_dimensionality}

        try:
            kwargs = {"model": model, "contents": contents}
            if embed_config is not None:
                kwargs["config"] = embed_config

            response = self._client.models.embed_content(**kwargs)
        except Exception as e:
            raise EmbeddingProviderError(f"Gemini embedding failed: {e}") from e

        if not response.embeddings or len(response.embeddings) != len(request.inputs):
            num_embeds = len(response.embeddings) if response.embeddings else 0
            raise EmbeddingProviderError(
                f"Gemini embedding returned incorrect number of results. "
                f"Expected {len(request.inputs)}, got {num_embeds}."
            )

        embeddings = []
        for i, item in enumerate(response.embeddings):
            inp = request.inputs[i]
            vector = item.values

            # Validate vector dimensionality if configured
            if (
                self._output_dimensionality
                and len(vector) != self._output_dimensionality
            ):
                raise EmbeddingProviderError(
                    f"Gemini embedding dimension mismatch: expected "
                    f"{self._output_dimensionality}, got {len(vector)}."
                )

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
