"""DOCX document parser."""

import io

try:
    import docx
except ImportError:
    docx = None

from app.core.exceptions import DocumentParseError
from app.services.documents.parsers.base import DocumentParser, ParseResult


class DocxParser(DocumentParser):
    """Parses `.docx` files extracting text using python-docx."""

    @property
    def name(self) -> str:
        return "docx"

    @property
    def extensions(self) -> tuple[str, ...]:
        return (".docx",)

    @property
    def media_types(self) -> tuple[str, ...]:
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def parse(self, filename: str, content: bytes) -> ParseResult:
        if docx is None:
            raise DocumentParseError("DOCX parsing requires the 'python-docx' package.")

        try:
            doc = docx.Document(io.BytesIO(content))
        except Exception as exc:
            raise DocumentParseError("Could not read DOCX file.") from exc

        text_parts = [para.text for para in doc.paragraphs if para.text]
        text = "\n\n".join(text_parts).strip()
        text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")

        metadata = {
            "parser": self.name,
            "filename": filename,
            "size_bytes": len(content),
        }

        if getattr(doc.core_properties, "title", None):
            metadata["title"] = doc.core_properties.title
        if getattr(doc.core_properties, "author", None):
            metadata["author"] = doc.core_properties.author

        return ParseResult(
            text=text,
            media_type=self.media_types[0],
            metadata=metadata,
        )
