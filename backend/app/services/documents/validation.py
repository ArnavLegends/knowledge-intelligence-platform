"""Upload validation for the document ingestion pipeline."""

import re
from pathlib import Path

from app.core.exceptions import DocumentValidationError

# Maximum filename length (POSIX filesystem limit)
_MAX_FILENAME_BYTES = 255

# Control characters (0x00–0x1F and 0x7F), including null byte
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def normalize_filename(filename: str | None) -> str:
    """Return a safe basename for an uploaded file.

    Rejects:
    - None or blank input
    - Null bytes and ASCII control characters
    - Filenames that resolve to '.' or '..'
    - Names exceeding 255 bytes when encoded as UTF-8
    """
    if filename is None or not filename.strip():
        raise DocumentValidationError("A valid filename is required.")

    if _CONTROL_CHAR_RE.search(filename):
        raise DocumentValidationError(
            "Filename contains invalid characters (null bytes or control characters)."
        )

    name = Path(filename).name.strip()
    if not name or name in {".", ".."}:
        raise DocumentValidationError("Invalid filename.")

    if len(name.encode("utf-8")) > _MAX_FILENAME_BYTES:
        raise DocumentValidationError(
            f"Filename exceeds the maximum allowed length of "
            f"{_MAX_FILENAME_BYTES} bytes."
        )

    return name


def validate_upload(filename: str | None, content: bytes, max_bytes: int) -> str:
    """Validate filename and payload size. Returns the normalized filename."""
    safe_name = normalize_filename(filename)
    if len(content) == 0:
        raise DocumentValidationError("Uploaded file is empty.")
    if len(content) > max_bytes:
        raise DocumentValidationError("Uploaded file exceeds the maximum allowed size.")
    return safe_name
