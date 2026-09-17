"""Application-facing language model service."""

from app.services.llm.manager import LLMManager
from app.services.llm.models import LLMRequest, LLMResponse


class LLMService:
    """Application boundary for language model generation.

    FastAPI routes and future orchestrators should depend on this service
    rather than on LLMManager or provider adapters.
    """

    def __init__(self, manager: LLMManager | None = None) -> None:
        self._manager = manager or LLMManager()

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a completion through the configured provider gateway."""
        return self._manager.generate(request)


def get_llm_service() -> LLMService:
    """FastAPI dependency that constructs the application LLM service."""
    return LLMService()
