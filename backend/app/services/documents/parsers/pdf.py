"""PDF document parser."""

import io

try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
except ImportError:
    PdfReader = None

from app.core.exceptions import DocumentParseError
from app.services.documents.parsers.base import DocumentParser, ParseResult


class PdfParser(DocumentParser):
    """Parses `.pdf` files extracting text using pypdf."""

    @property
    def name(self) -> str:
        return "pdf"

    @property
    def extensions(self) -> tuple[str, ...]:
        return (".pdf",)

    @property
    def media_types(self) -> tuple[str, ...]:
        return ("application/pdf",)

    def parse(self, filename: str, content: bytes) -> ParseResult:
        if PdfReader is None:
            raise DocumentParseError("PDF parsing requires the 'pypdf' package.")

        try:
            pdf = PdfReader(io.BytesIO(content))
        except (PdfReadError, Exception) as exc:
            raise DocumentParseError("Could not read PDF file.") from exc

        text_parts = []
        for page in pdf.pages:
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception:
                pass

        text = "\n\n".join(text_parts).strip()
        text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")

        metadata = {
            "parser": self.name,
            "filename": filename,
            "size_bytes": len(content),
            "pages": len(pdf.pages),
        }

        # Add optional PDF metadata if available
        if pdf.metadata:
            if pdf.metadata.title:
                metadata["title"] = pdf.metadata.title
            if pdf.metadata.author:
                metadata["author"] = pdf.metadata.author

        return ParseResult(
            text=text,
            media_type="application/pdf",
            metadata=metadata,
        )
