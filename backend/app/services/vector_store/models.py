"""Normalized vector storage domain models."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class StoredVector(BaseModel):
    """A normalized embedding record stored in the vector database."""

    id: str
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("vector")
    @classmethod
    def vector_must_not_be_empty(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("vector must not be empty")
        return value
