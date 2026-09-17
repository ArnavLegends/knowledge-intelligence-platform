"""UTF-8 plain-text parser."""

from app.core.exceptions import DocumentParseError
from app.services.documents.parsers.base import DocumentParser, ParseResult


class TxtParser(DocumentParser):
    """Parses `.txt` files as UTF-8 text."""

    @property
    def name(self) -> str:
        return "txt"

    @property
    def extensions(self) -> tuple[str, ...]:
        return (".txt",)

    @property
    def media_types(self) -> tuple[str, ...]:
        return ("text/plain",)

    def parse(self, filename: str, content: bytes) -> ParseResult:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentParseError(
                "File could not be decoded as UTF-8 text."
            ) from exc

        text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
        return ParseResult(
            text=text,
            media_type="text/plain",
            metadata={
                "parser": self.name,
                "encoding": "utf-8",
                "filename": filename,
                "size_bytes": len(content),
            },
        )
