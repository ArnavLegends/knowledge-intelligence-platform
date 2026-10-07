"""Workspace validation and FastAPI dependency."""

import re
from typing import Annotated

from fastapi import Header, HTTPException

# High-entropy token or identifier: 8 to 128 chars, alphanumeric plus - and _
_WORKSPACE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def validate_workspace_id(workspace_id: str | None) -> str:
    """Validate that workspace_id is provided, non-empty, and valid format.

    Rejects missing, empty, or malformed workspace identifiers.
    Never exposes or logs the full raw workspace token.
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


def get_workspace_id(
    x_kip_workspace_id: Annotated[
        str | None,
        Header(
            alias="X-KIP-Workspace-ID",
            description="Private workspace token identifying tenant workspace.",
        ),
    ] = None,
) -> str:
    """FastAPI dependency that extracts and validates the workspace identifier."""
    return validate_workspace_id(x_kip_workspace_id)
