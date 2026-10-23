"""SQLite-backed workspace registry with hashed token storage and revocation."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

_WORKSPACE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def hash_token(token: str) -> str:
    """Compute deterministic SHA-256 hex digest of access token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class WorkspaceRegistry:
    """Thread-safe persistent registry managing tenant workspaces and credentials."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.workspace_db_path
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
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workspaces_active
                ON workspaces (workspace_id, is_active)
                """
            )

    def create_workspace(
        self,
        name: str,
        workspace_id: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Provision a new workspace, generate a secret token, and persist hashed token.

        Returns (metadata_dict, secret_token). The raw secret token is returned
        only once and never stored in plaintext.
        """
        clean_name = name.strip() if name else "Unnamed Workspace"
        if not clean_name:
            clean_name = "Unnamed Workspace"

        if workspace_id is not None and workspace_id.strip():
            candidate_id = workspace_id.strip()
            if not _WORKSPACE_ID_REGEX.match(candidate_id):
                raise ValueError(
                    "Invalid workspace_id format. Must be 8-128 chars [A-Za-z0-9_-]."
                )
        else:
            candidate_id = f"ws_{secrets.token_hex(12)}"

        secret_token = f"kip_sec_{secrets.token_urlsafe(32)}"
        token_digest = hash_token(secret_token)
        now_iso = datetime.now(UTC).isoformat()

        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT workspace_id FROM workspaces WHERE workspace_id = ?",
                (candidate_id,),
            )
            if cursor.fetchone():
                raise ValueError(f"Workspace '{candidate_id}' already exists.")

            conn.execute(
                """
                INSERT INTO workspaces
                    (workspace_id, name, token_hash, created_at, revoked_at, is_active)
                VALUES (?, ?, ?, ?, NULL, 1)
                """,
                (candidate_id, clean_name, token_digest, now_iso),
            )

        metadata = {
            "workspace_id": candidate_id,
            "name": clean_name,
            "created_at": now_iso,
            "is_active": True,
        }
        return metadata, secret_token

    def verify_token(self, workspace_id: str, token: str | None) -> bool:
        """Verify that token matches the stored token hash for an active workspace."""
        if not workspace_id or not token:
            return False

        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT token_hash, is_active
                FROM workspaces
                WHERE workspace_id = ?
                """,
                (workspace_id.strip(),),
            )
            row = cursor.fetchone()

        if not row or not row["is_active"]:
            return False

        presented_hash = hash_token(token.strip())
        return hmac.compare_digest(row["token_hash"], presented_hash)

    def revoke_workspace(self, workspace_id: str) -> bool:
        """Revoke a workspace's credentials and deactivate access.

        Returns True if revoked, False if workspace does not exist.
        """
        now_iso = datetime.now(UTC).isoformat()
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE workspaces
                SET is_active = 0, revoked_at = ?
                WHERE workspace_id = ? AND is_active = 1
                """,
                (now_iso, workspace_id.strip()),
            )
            return cursor.rowcount > 0

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        """Retrieve workspace record metadata (without token hash)."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT workspace_id, name, created_at, revoked_at, is_active
                FROM workspaces
                WHERE workspace_id = ?
                """,
                (workspace_id.strip(),),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "workspace_id": row["workspace_id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "revoked_at": row["revoked_at"],
            "is_active": bool(row["is_active"]),
        }

    def list_workspaces(self) -> list[dict[str, Any]]:
        """List all registered workspaces."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT workspace_id, name, created_at, revoked_at, is_active
                FROM workspaces
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()

        return [
            {
                "workspace_id": r["workspace_id"],
                "name": r["name"],
                "created_at": r["created_at"],
                "revoked_at": r["revoked_at"],
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]


_default_registry: WorkspaceRegistry | None = None


def get_workspace_registry() -> WorkspaceRegistry:
    """Return singleton workspace registry."""
    global _default_registry  # noqa: PLW0603
    if _default_registry is None:
        _default_registry = WorkspaceRegistry()
    return _default_registry
