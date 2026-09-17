"""Upload validation for the document ingestion pipeline."""

from pathlib import Path

from app.core.exceptions import DocumentValidationError


def normalize_filename(filename: str | None) -> str:
    """Return a safe basename for an uploaded file."""
    if filename is None or not filename.strip():
        raise DocumentValidationError("A valid filename is required.")

    name = Path(filename).name.strip()
    if not name or name in {".", ".."}:
        raise DocumentValidationError("Invalid filename.")
    return name


def validate_upload(filename: str | None, content: bytes, max_bytes: int) -> str:
    """Validate filename and payload size. Returns the normalized filename."""
    safe_name = normalize_filename(filename)
    if len(content) == 0:
        raise DocumentValidationError("Uploaded file is empty.")
    if len(content) > max_bytes:
        raise DocumentValidationError("Uploaded file exceeds the maximum allowed size.")
    return safe_name
