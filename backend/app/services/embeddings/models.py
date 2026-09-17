"""Normalized embedding request and response models."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class EmbeddingInput(BaseModel):
    """A single text input to be embedded."""

    source_id: str
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingRequest(BaseModel):
    """Provider-agnostic embedding request."""

    model: str | None = None
    inputs: list[EmbeddingInput] = Field(min_length=1)

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("model must not be blank")
        return value


class Embedding(BaseModel):
    """A single normalized embedding vector."""

    source_id: str
    vector: list[float]
    dimensions: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    model: str | None = None

    @field_validator("vector")
    @classmethod
    def vector_must_not_be_empty(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("vector must not be empty")
        return value

    @field_validator("dimensions")
    @classmethod
    def dimensions_must_match_vector(cls, value: int, info) -> int:
        if "vector" in info.data and value != len(info.data["vector"]):
            raise ValueError("dimensions must match vector length")
        return value
