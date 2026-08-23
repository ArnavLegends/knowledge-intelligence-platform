"""Normalized request and response models for the LLM gateway."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

LLMRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    """A single provider-agnostic chat message."""

    role: LLMRole
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class LLMRequest(BaseModel):
    """Provider-agnostic generation request consumed by the LLM manager."""

    messages: list[LLMMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("model must not be blank")
        return value


class LLMUsage(BaseModel):
    """Token usage reported by a provider, when available."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMResponse(BaseModel):
    """Normalized generation result returned to application code."""

    content: str
    model: str
    provider: str
    usage: LLMUsage | None = None
