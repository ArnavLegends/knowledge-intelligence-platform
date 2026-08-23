"""Normalized request and response models for the LLM gateway."""

from typing import Literal

from pydantic import BaseModel, Field

LLMRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    """A single chat message sent to a language model."""

    role: LLMRole
    content: str


class LLMRequest(BaseModel):
    """Provider-agnostic generation request."""

    messages: list[LLMMessage] = Field(min_length=1)
    model: str | None = None


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
