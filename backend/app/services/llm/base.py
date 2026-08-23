"""Provider-agnostic language model interface."""

from abc import ABC, abstractmethod

from app.services.llm.models import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Contract that every language model adapter must implement.

    Streaming is reserved for a later milestone and is not part of this contract.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier used for configuration and responses."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Invoke the configured model and return a normalized response."""
