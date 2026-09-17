"""Document parser contract."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ParseResult(BaseModel):
    """Text and metadata extracted by a parser."""

    text: str
    media_type: str
    metadata: dict[str, str | int]


class DocumentParser(ABC):
    """Contract that every document parser must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable parser identifier."""

    @property
    @abstractmethod
    def extensions(self) -> tuple[str, ...]:
        """Filename extensions this parser accepts, including the leading dot."""

    @property
    @abstractmethod
    def media_types(self) -> tuple[str, ...]:
        """MIME types this parser accepts."""

    @abstractmethod
    def parse(self, filename: str, content: bytes) -> ParseResult:
        """Extract text from raw file bytes."""
