"""Administrative workspace management and provisioning endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.workspace import require_admin_key
from app.core.workspace_registry import (
    WorkspaceRegistry,
    get_workspace_registry,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceProvisionRequest(BaseModel):
    """Payload for provisioning a new tenant workspace."""

    name: str = Field(..., min_length=1, max_length=128, description="Workspace name")
    workspace_id: str | None = Field(
        default=None,
        description=(
            "Optional explicit workspace identifier (8-128 chars [A-Za-z0-9_-])"
        ),
    )


class WorkspaceProvisionResponse(BaseModel):
    """Response containing provisioned workspace metadata and secret token."""

    workspace_id: str
    name: str
    token: str = Field(
        ...,
        description=(
            "Secret bearer access token. Save this securely; it is shown only once."
        ),
    )
    created_at: str
    message: str = (
        "Workspace provisioned successfully. Store the access token securely."
    )


class WorkspaceItem(BaseModel):
    """Metadata for a registered tenant workspace."""

    workspace_id: str
    name: str
    created_at: str
    revoked_at: str | None = None
    is_active: bool


class WorkspaceRevokeResponse(BaseModel):
    """Response returned upon workspace revocation."""

    workspace_id: str
    revoked: bool
    message: str


@router.post("", response_model=WorkspaceProvisionResponse)
def provision_workspace(
    payload: WorkspaceProvisionRequest,
    _admin_key: Annotated[str, Depends(require_admin_key)],
    registry: Annotated[WorkspaceRegistry, Depends(get_workspace_registry)],
) -> WorkspaceProvisionResponse:
    """Provision a new workspace and generate its secret bearer token.

    Requires administrative authentication via X-KIP-Admin-Key.
    """
    try:
        metadata, secret_token = registry.create_workspace(
            name=payload.name,
            workspace_id=payload.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return WorkspaceProvisionResponse(
        workspace_id=metadata["workspace_id"],
        name=metadata["name"],
        token=secret_token,
        created_at=metadata["created_at"],
    )


@router.get("", response_model=list[WorkspaceItem])
def list_workspaces(
    _admin_key: Annotated[str, Depends(require_admin_key)],
    registry: Annotated[WorkspaceRegistry, Depends(get_workspace_registry)],
) -> list[WorkspaceItem]:
    """List all registered workspaces.

    Requires administrative authentication via X-KIP-Admin-Key.
    Secret tokens are never returned.
    """
    workspaces = registry.list_workspaces()
    return [WorkspaceItem(**ws) for ws in workspaces]


@router.post("/{workspace_id}/revoke", response_model=WorkspaceRevokeResponse)
def revoke_workspace(
    workspace_id: str,
    _admin_key: Annotated[str, Depends(require_admin_key)],
    registry: Annotated[WorkspaceRegistry, Depends(get_workspace_registry)],
) -> WorkspaceRevokeResponse:
    """Revoke credentials for a workspace and deactivate access.

    Requires administrative authentication via X-KIP-Admin-Key.
    """
    revoked = registry.revoke_workspace(workspace_id)
    if not revoked:
        raise HTTPException(
            status_code=404,
            detail=f"Active workspace '{workspace_id}' not found.",
        )

    return WorkspaceRevokeResponse(
        workspace_id=workspace_id,
        revoked=True,
        message=f"Workspace '{workspace_id}' has been revoked successfully.",
    )
