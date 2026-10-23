"""Persistent source-document file storage subsystem."""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from pathlib import Path

from app.core.config import settings as default_settings

logger = logging.getLogger(__name__)


class LocalDocumentStorage:
    """Safe, atomic, workspace-scoped local file storage for raw uploaded documents."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        raw_path = base_dir or default_settings.document_storage_dir
        self._base_dir = Path(raw_path).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(
        self, workspace_id: str, document_id: str, filename: str
    ) -> Path:
        """Resolve and validate target file path resides strictly within base_dir."""
        for part in (workspace_id, document_id, filename):
            if not part or ".." in part:
                raise ValueError(f"Path traversal sequence detected in '{part}'.")

        if "/" in filename or "\\" in filename:
            raise ValueError(
                f"Path traversal characters detected in filename '{filename}'."
            )

        clean_ws = Path(workspace_id).name
        clean_doc = Path(document_id).name
        clean_file = Path(filename).name

        target_dir = (self._base_dir / clean_ws / clean_doc).resolve()
        target_path = (target_dir / clean_file).resolve()

        if not target_path.is_relative_to(self._base_dir):
            raise ValueError(
                f"Path traversal detected: path '{target_path}' escapes base directory."
            )

        return target_path

    def save_file(
        self,
        workspace_id: str,
        document_id: str,
        filename: str,
        content: bytes,
    ) -> str:
        """Atomically persist raw document bytes to disk.

        Writes to a temporary file in the target directory and renames atomically,
        preventing partial or corrupted files from being exposed on interrupted writes.
        Returns the relative path to base_dir as a string.
        """
        target_path = self._resolve_safe_path(workspace_id, document_id, filename)
        target_dir = target_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        temp_name = f".tmp_{uuid.uuid4().hex}_{target_path.name}"
        temp_path = target_dir / temp_name

        try:
            with open(temp_path, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace on modern operating systems
            temp_path.replace(target_path)
            logger.debug(
                "Persisted source document: workspace=%s doc=%s bytes=%d",
                workspace_id[:8],
                document_id[:8],
                len(content),
            )
            return str(target_path.relative_to(self._base_dir))
        except Exception:
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()
            raise

    def read_file(
        self,
        workspace_id: str,
        document_id: str,
        filename: str,
    ) -> bytes:
        """Read and return raw bytes of stored document."""
        target_path = self._resolve_safe_path(workspace_id, document_id, filename)
        if not target_path.exists():
            raise FileNotFoundError(
                f"Stored document file not found: "
                f"{workspace_id}/{document_id}/{filename}"
            )
        return target_path.read_bytes()

    def file_exists(
        self,
        workspace_id: str,
        document_id: str,
        filename: str,
    ) -> bool:
        """Check if stored document file exists on disk."""
        try:
            target_path = self._resolve_safe_path(workspace_id, document_id, filename)
            return target_path.is_file()
        except ValueError:
            return False

    def delete_file(
        self,
        workspace_id: str,
        document_id: str,
        filename: str,
    ) -> bool:
        """Delete stored file and prune empty parent directories."""
        try:
            target_path = self._resolve_safe_path(workspace_id, document_id, filename)
            if not target_path.exists():
                return False
            target_path.unlink()
            # Prune empty doc dir if empty
            parent_doc_dir = target_path.parent
            if parent_doc_dir.exists() and not any(parent_doc_dir.iterdir()):
                parent_doc_dir.rmdir()
            return True
        except Exception as e:
            logger.warning("Error deleting stored file: %s", e)
            return False


_default_storage: LocalDocumentStorage | None = None


def get_document_storage() -> LocalDocumentStorage:
    """Return singleton LocalDocumentStorage."""
    global _default_storage  # noqa: PLW0603
    if _default_storage is None:
        _default_storage = LocalDocumentStorage()
    return _default_storage
