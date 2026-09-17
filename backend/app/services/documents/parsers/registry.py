"""Parser registry for document ingestion."""

from pathlib import Path

from app.core.exceptions import UnsupportedFormatError
from app.services.documents.parsers.base import DocumentParser
from app.services.documents.parsers.txt import TxtParser


class ParserRegistry:
    """Selects a parser from filename extension or media type."""

    def __init__(self) -> None:
        self._by_extension: dict[str, DocumentParser] = {}
        self._by_media_type: dict[str, DocumentParser] = {}

    def register(self, parser: DocumentParser) -> None:
        for extension in parser.extensions:
            self._by_extension[extension.lower()] = parser
        for media_type in parser.media_types:
            self._by_media_type[media_type.lower()] = parser

    def select(self, filename: str, media_type: str | None = None) -> DocumentParser:
        extension = Path(filename).suffix.lower()
        parser = self._by_extension.get(extension)
        if parser is None and media_type:
            parser = self._by_media_type.get(media_type.split(";")[0].strip().lower())
        if parser is None:
            raise UnsupportedFormatError("Unsupported document format.")
        return parser


def build_default_registry() -> ParserRegistry:
    """Return a registry with the parsers available in this milestone."""
    registry = ParserRegistry()
    registry.register(TxtParser())
    return registry
