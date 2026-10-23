"""Workspace validation, authorization, and FastAPI dependencies."""

from __future__ import annotations

import hmac
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.core.config import Settings, get_settings
from app.core.workspace_registry import WorkspaceRegistry, get_workspace_registry

# Workspace identifier: 8 to 128 chars, alphanumeric plus - and _
_WORKSPACE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def validate_workspace_id(workspace_id: str | None) -> str:
    """Validate that workspace_id is provided, non-empty, and valid format.

    Rejects missing, empty, or malformed workspace identifiers.
    """
    if not workspace_id or not workspace_id.strip():
        raise HTTPException(
            status_code=400,
            detail="X-KIP-Workspace-ID header is required and cannot be empty.",
        )

    clean_id = workspace_id.strip()
    if not _WORKSPACE_ID_REGEX.match(clean_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid X-KIP-Workspace-ID format. Workspace identifier must be "
                "between 8 and 128 characters containing only alphanumeric "
                "characters, hyphens, or underscores."
            ),
        )

    return clean_id


def extract_bearer_token(auth_header: str | None) -> str | None:
    """Extract token string from Authorization: Bearer <token> header."""
    if not auth_header:
        return None
    parts = auth_header.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def get_workspace_id(
    settings: Annotated[Settings, Depends(get_settings)],
    registry: Annotated[WorkspaceRegistry, Depends(get_workspace_registry)],
    x_kip_workspace_id: Annotated[
        str | None,
        Header(
            alias="X-KIP-Workspace-ID",
            description="Public identifier for the tenant workspace.",
        ),
    ] = None,
    x_kip_workspace_token: Annotated[
        str | None,
        Header(
            alias="X-KIP-Workspace-Token",
            description="Secret bearer access token for the tenant workspace.",
        ),
    ] = None,
    authorization: Annotated[
        str | None,
        Header(
            alias="Authorization",
            description="Bearer access token for workspace authentication.",
        ),
    ] = None,
) -> str:
    """FastAPI dependency validating workspace identity and bearer authorization."""
    clean_id = validate_workspace_id(x_kip_workspace_id)
    active_settings = settings or get_settings()

    if not active_settings.workspace_auth_enforce:
        return clean_id

    # Resolve token from either X-KIP-Workspace-Token or Authorization: Bearer
    token = x_kip_workspace_token
    if not token and authorization:
        token = extract_bearer_token(authorization)

    if not token or not token.strip():
        raise HTTPException(
            status_code=401,
            detail=(
                "X-KIP-Workspace-Token header is required for workspace authentication."
            ),
        )

    active_registry = registry or get_workspace_registry()
    is_valid = active_registry.verify_token(clean_id, token)
    if not is_valid:
        raise HTTPException(
            status_code=403,
            detail=(
                "Forbidden: Invalid, unprovisioned, or revoked workspace credentials."
            ),
        )

    return clean_id


def require_admin_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_kip_admin_key: Annotated[
        str | None,
        Header(
            alias="X-KIP-Admin-Key",
            description="Administrative secret key for system management.",
        ),
    ] = None,
    authorization: Annotated[
        str | None,
        Header(
            alias="Authorization",
            description="Bearer administrative key.",
        ),
    ] = None,
) -> str:
    """FastAPI dependency requiring valid administrative authorization."""
    active_settings = settings or get_settings()
    if not active_settings.admin_api_key or not active_settings.admin_api_key.strip():
        raise HTTPException(
            status_code=403,
            detail="Administrative access is unconfigured on this server.",
        )

    admin_key = x_kip_admin_key
    if not admin_key and authorization:
        admin_key = extract_bearer_token(authorization)

    if not admin_key or not hmac.compare_digest(
        admin_key.strip(), active_settings.admin_api_key.strip()
    ):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid or missing administrative credentials.",
        )

    return admin_key
