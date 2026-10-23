"""SQLite document metadata and versioned lifecycle store."""

import logging
import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings as default_settings

logger = logging.getLogger(__name__)


class DocumentMetadataStore:
    """Thread-safe persistent store.

    Manages document metadata, versions, and lifecycle.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or default_settings.workspace_db_path
        self._lock = threading.Lock()
        self._ensure_storage()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_storage(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    active_version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    file_path TEXT,
                    chunks_indexed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (document_id, workspace_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_ws_status
                ON documents (workspace_id, status)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_versions (
                    version_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    chunks_indexed INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (document_id, workspace_id)
                        REFERENCES documents (document_id, workspace_id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_versions_doc
                ON document_versions (document_id, workspace_id, version_number)
                """
            )

    def record_document(
        self,
        document_id: str,
        workspace_id: str,
        filename: str,
        content_hash: str,
        media_type: str,
        size_bytes: int,
        chunks_indexed: int = 0,
        file_path: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        """Record or update an active document and initialize version 1."""
        now_iso = datetime.now(UTC).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT document_id, active_version FROM documents
                WHERE document_id = ? AND workspace_id = ?
                """,
                (document_id, workspace_id),
            )
            existing = cursor.fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE documents
                    SET filename = ?, content_hash = ?, media_type = ?,
                        size_bytes = ?, chunks_indexed = ?, file_path = ?,
                        status = ?, updated_at = ?
                    WHERE document_id = ? AND workspace_id = ?
                    """,
                    (
                        filename,
                        content_hash,
                        media_type,
                        size_bytes,
                        chunks_indexed,
                        file_path,
                        status,
                        now_iso,
                        document_id,
                        workspace_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO documents (
                        document_id, workspace_id, filename, content_hash,
                        media_type, size_bytes, active_version, status,
                        file_path, chunks_indexed, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        workspace_id,
                        filename,
                        content_hash,
                        media_type,
                        size_bytes,
                        status,
                        file_path,
                        chunks_indexed,
                        now_iso,
                        now_iso,
                    ),
                )
                # Insert initial version 1
                version_id = f"ver_{uuid.uuid4().hex}"
                conn.execute(
                    """
                    INSERT INTO document_versions (
                        version_id, document_id, workspace_id, version_number,
                        content_hash, filename, file_path, media_type,
                        size_bytes, chunks_indexed, status, created_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 'active', ?)
                    """,
                    (
                        version_id,
                        document_id,
                        workspace_id,
                        content_hash,
                        filename,
                        file_path,
                        media_type,
                        size_bytes,
                        chunks_indexed,
                        now_iso,
                    ),
                )

        return self.get_document(document_id, workspace_id)  # type: ignore

    def create_replacement_version(
        self,
        document_id: str,
        workspace_id: str,
        filename: str,
        content_hash: str,
        media_type: str,
        size_bytes: int,
        chunks_indexed: int,
        file_path: str | None = None,
    ) -> int:
        """Create new version for document, marking previous versions superseded."""
        now_iso = datetime.now(UTC).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT active_version FROM documents
                WHERE document_id = ? AND workspace_id = ?
                """,
                (document_id, workspace_id),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(
                    f"Document '{document_id}' not found in workspace '{workspace_id}'."
                )

            new_version = row["active_version"] + 1

            # Mark old versions as superseded
            conn.execute(
                """
                UPDATE document_versions
                SET status = 'superseded'
                WHERE document_id = ? AND workspace_id = ? AND status = 'active'
                """,
                (document_id, workspace_id),
            )

            # Insert new active version
            version_id = f"ver_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO document_versions (
                    version_id, document_id, workspace_id, version_number,
                    content_hash, filename, file_path, media_type,
                    size_bytes, chunks_indexed, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    version_id,
                    document_id,
                    workspace_id,
                    new_version,
                    content_hash,
                    filename,
                    file_path,
                    media_type,
                    size_bytes,
                    chunks_indexed,
                    now_iso,
                ),
            )

            # Update document master record
            conn.execute(
                """
                UPDATE documents
                SET filename = ?, content_hash = ?, media_type = ?,
                    size_bytes = ?, active_version = ?, status = 'active',
                    file_path = ?, chunks_indexed = ?, updated_at = ?
                WHERE document_id = ? AND workspace_id = ?
                """,
                (
                    filename,
                    content_hash,
                    media_type,
                    size_bytes,
                    new_version,
                    file_path,
                    chunks_indexed,
                    now_iso,
                    document_id,
                    workspace_id,
                ),
            )

            return new_version

    def get_document(
        self, document_id: str, workspace_id: str
    ) -> dict[str, Any] | None:
        """Retrieve single document record."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT document_id, workspace_id, filename, content_hash,
                       media_type, size_bytes, active_version, status,
                       file_path, chunks_indexed, created_at, updated_at
                FROM documents
                WHERE document_id = ? AND workspace_id = ?
                """,
                (document_id, workspace_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_documents(
        self, workspace_id: str, status: str | None = "active"
    ) -> list[dict[str, Any]]:
        """List documents in workspace filtered by status (default 'active')."""
        with self._lock, self._get_connection() as conn:
            if status:
                cursor = conn.execute(
                    """
                    SELECT document_id, workspace_id, filename, content_hash,
                           media_type, size_bytes, active_version, status,
                           file_path, chunks_indexed, created_at, updated_at
                    FROM documents
                    WHERE workspace_id = ? AND status = ?
                    ORDER BY updated_at DESC
                    """,
                    (workspace_id, status),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT document_id, workspace_id, filename, content_hash,
                           media_type, size_bytes, active_version, status,
                           file_path, chunks_indexed, created_at, updated_at
                    FROM documents
                    WHERE workspace_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (workspace_id,),
                )
            return [dict(r) for r in cursor.fetchall()]

    def list_versions(
        self, document_id: str, workspace_id: str
    ) -> list[dict[str, Any]]:
        """List all version history records for a document."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT version_id, document_id, workspace_id, version_number,
                       content_hash, filename, file_path, media_type,
                       size_bytes, chunks_indexed, status, created_at
                FROM document_versions
                WHERE document_id = ? AND workspace_id = ?
                ORDER BY version_number DESC
                """,
                (document_id, workspace_id),
            )
            return [dict(r) for r in cursor.fetchall()]

    def set_status(self, document_id: str, workspace_id: str, status: str) -> bool:
        """Update lifecycle status of a document.

        Status options: 'pending', 'active', 'deleting', 'deleted', 'failed'.
        """
        now_iso = datetime.now(UTC).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE documents
                SET status = ?, updated_at = ?
                WHERE document_id = ? AND workspace_id = ?
                """,
                (status, now_iso, document_id, workspace_id),
            )
            return cursor.rowcount > 0

    def delete_document(
        self, document_id: str, workspace_id: str, hard_delete: bool = False
    ) -> bool:
        """Mark document deleted (or hard delete if specified)."""
        now_iso = datetime.now(UTC).isoformat()
        with self._lock, self._get_connection() as conn:
            if hard_delete:
                cursor = conn.execute(
                    """
                    DELETE FROM documents
                    WHERE document_id = ? AND workspace_id = ?
                    """,
                    (document_id, workspace_id),
                )
                return cursor.rowcount > 0

            cursor = conn.execute(
                """
                UPDATE documents
                SET status = 'deleted', updated_at = ?
                WHERE document_id = ? AND workspace_id = ? AND status != 'deleted'
                """,
                (now_iso, document_id, workspace_id),
            )
            return cursor.rowcount > 0

    def get_active_document_ids(self, workspace_id: str) -> set[str]:
        """Return set of document IDs currently in 'active' status for workspace."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT document_id FROM documents
                WHERE workspace_id = ? AND status = 'active'
                """,
                (workspace_id,),
            )
            return {row["document_id"] for row in cursor.fetchall()}

    def has_documents(self, workspace_id: str) -> bool:
        """Return True if metadata store has any document records for this workspace."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM documents WHERE workspace_id = ? LIMIT 1",
                (workspace_id,),
            )
            return cursor.fetchone() is not None


_default_store: DocumentMetadataStore | None = None


def get_document_metadata_store() -> DocumentMetadataStore:
    """Return singleton DocumentMetadataStore."""
    global _default_store  # noqa: PLW0603
    if _default_store is None:
        _default_store = DocumentMetadataStore()
    return _default_store
