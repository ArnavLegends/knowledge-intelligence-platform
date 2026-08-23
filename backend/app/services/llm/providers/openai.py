"""OpenAI adapter for the language model gateway."""

from openai import OpenAI

from app.core.exceptions import LLMProviderError
from app.core.logging import get_logger
from app.services.llm.base import LLMProvider
from app.services.llm.models import LLMRequest, LLMResponse, LLMUsage

logger = get_logger("app.services.llm.providers.openai")


class OpenAIProvider(LLMProvider):
    """Invokes OpenAI chat completions and returns normalized results."""

    def __init__(self, api_key: str, model: str, client: object | None = None) -> None:
        if not api_key and client is None:
            raise LLMProviderError("LLM API key is not configured.")
        self._model = model
        self._client = client or OpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return "openai"

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._model
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]

        try:
            completion = self._client.chat.completions.create(
                model=model,
                messages=messages,
            )
        except LLMProviderError:
            raise
        except Exception:
            logger.exception("OpenAI provider request failed")
            raise LLMProviderError("Language model provider request failed.") from None

        if not completion.choices:
            raise LLMProviderError("Language model provider returned no choices.")

        message = completion.choices[0].message
        content = message.content or ""

        usage = None
        if completion.usage is not None:
            usage = LLMUsage(
                prompt_tokens=getattr(completion.usage, "prompt_tokens", None),
                completion_tokens=getattr(completion.usage, "completion_tokens", None),
                total_tokens=getattr(completion.usage, "total_tokens", None),
            )

        return LLMResponse(
            content=content,
            model=completion.model or model,
            provider=self.name,
            usage=usage,
        )
