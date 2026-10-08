"""Gemini adapter for the language model gateway."""

from google import genai
from google.genai import types

from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.services.llm.base import LLMProvider
from app.services.llm.models import LLMRequest, LLMResponse, LLMUsage

logger = get_logger("app.services.llm.providers.gemini")


class GeminiProvider(LLMProvider):
    """Invokes Gemini models and returns normalized results."""

    def __init__(self, api_key: str, model: str, client: object | None = None) -> None:
        if not api_key and client is None:
            raise LLMProviderError("LLM API key is not configured for Gemini.")
        self._model = model
        self._client = client or genai.Client(api_key=api_key)

    @property
    def name(self) -> str:
        return "gemini"

    def generate(self, request: LLMRequest) -> LLMResponse:
        contents, config = self._to_gemini_payload(request)
        model_name = request.model or self._model

        try:
            response = self._client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            logger.exception("Gemini provider request failed: %s", exc)
            exc_str = str(exc).lower()
            code_attr = getattr(exc, "code", None)

            # Check for rate limit / quota exhaustion
            if (
                code_attr == 429
                or "429" in exc_str
                or "resource_exhausted" in exc_str
                or "quota" in exc_str
                or "rate limit" in exc_str
            ):
                raise LLMProviderError(
                    "Language model provider quota or rate limit exceeded. Please wait a moment and try again."
                ) from None

            # Check for context length / request size constraints
            if (
                "context length" in exc_str
                or ("token" in exc_str and "exceed" in exc_str)
                or "request payload size" in exc_str
                or "too large" in exc_str
            ):
                raise LLMProviderError(
                    "Language model provider request rejected due to request size or context constraints."
                ) from None

            # Check for temporary service unavailability / timeout
            if (
                code_attr in (503, 504)
                or "503" in exc_str
                or "504" in exc_str
                or "unavailable" in exc_str
                or "deadline_exceeded" in exc_str
                or "timeout" in exc_str
            ):
                raise LLMProviderError(
                    "Language model provider is temporarily unavailable or timed out. Please try again shortly."
                ) from None

            raise LLMProviderError("Language model provider request failed.") from None

        try:
            content = response.text or ""
        except ValueError:
            # If the response doesn't have valid text (e.g., blocked),
            # response.text can raise ValueError.
            content = ""

        usage = None
        if response.usage_metadata is not None:
            usage = LLMUsage(
                prompt_tokens=response.usage_metadata.prompt_token_count,
                completion_tokens=response.usage_metadata.candidates_token_count,
                total_tokens=response.usage_metadata.total_token_count,
            )

        finish_reason = None
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = str(response.candidates[0].finish_reason.name)

        return LLMResponse(
            content=content,
            model=model_name,
            provider=self.name,
            usage=usage,
            finish_reason=finish_reason,
        )

    def _to_gemini_payload(
        self, request: LLMRequest
    ) -> tuple[list[types.Content], types.GenerateContentConfig]:
        """Translate the internal request into Gemini contents and config."""
        contents = []
        system_instruction = None

        for message in request.messages:
            if message.role == "system":
                # If there are multiple system messages, we combine them
                if system_instruction is None:
                    system_instruction = message.content
                else:
                    system_instruction += "\n" + message.content
            else:
                role = "model" if message.role == "assistant" else "user"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=message.content)],
                    )
                )

        config_args = {}
        if request.temperature is not None:
            config_args["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            config_args["max_output_tokens"] = request.max_output_tokens
        if system_instruction is not None:
            config_args["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_args)
        return contents, config
