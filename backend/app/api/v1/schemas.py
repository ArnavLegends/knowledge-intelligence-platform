"""HTTP schemas for the versioned LLM API.

These models are independent of provider SDKs. They map to internal
LLMRequest / LLMResponse values at the application boundary.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMUsage

APIRole = Literal["system", "user", "assistant"]


class GenerateMessage(BaseModel):
    """A single chat message in an HTTP generate request."""

    role: APIRole
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class GenerateRequest(BaseModel):
    """Application request body for POST /api/v1/llm/generate."""

    messages: list[GenerateMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)

    def to_internal(self) -> LLMRequest:
        """Convert the HTTP payload into the internal LLM request contract."""
        return LLMRequest(
            messages=[
                LLMMessage(role=message.role, content=message.content)
                for message in self.messages
            ],
            model=self.model,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )


class GenerateUsage(BaseModel):
    """Token usage included in an HTTP generate response, when available."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @classmethod
    def from_internal(cls, usage: LLMUsage | None) -> "GenerateUsage | None":
        if usage is None:
            return None
        return cls(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )


class GenerateResponse(BaseModel):
    """Application response body for POST /api/v1/llm/generate."""

    content: str
    model: str
    provider: str
    usage: GenerateUsage | None = None
    finish_reason: str | None = None

    @classmethod
    def from_internal(cls, response: LLMResponse) -> "GenerateResponse":
        return cls(
            content=response.content,
            model=response.model,
            provider=response.provider,
            usage=GenerateUsage.from_internal(response.usage),
            finish_reason=response.finish_reason,
        )
