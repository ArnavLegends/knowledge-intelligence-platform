"""Versioned language model HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.schemas import GenerateRequest, GenerateResponse
from app.core.config import Settings, get_settings
from app.core.workspace import require_admin_key
from app.services.llm.service import LLMService, get_llm_service

router = APIRouter(prefix="/llm", tags=["llm"])


def verify_direct_llm_access(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.enable_direct_llm_endpoint:
        raise HTTPException(
            status_code=403,
            detail=(
                "Direct LLM generation endpoint is disabled by policy. "
                "Enable 'enable_direct_llm_endpoint' and provide valid "
                "administrative credentials."
            ),
        )


@router.post("/generate", response_model=GenerateResponse)
def generate(
    _disabled_check: Annotated[None, Depends(verify_direct_llm_access)],
    _admin_key: Annotated[str, Depends(require_admin_key)],
    payload: GenerateRequest,
    service: Annotated[LLMService, Depends(get_llm_service)],
) -> GenerateResponse:
    """Generate a completion through the application LLM service.

    SECURED DEVELOPMENT ENDPOINT: Disabled by default. When enabled via
    settings.enable_direct_llm_endpoint, requires administrative authorization.
    """
    return GenerateResponse.from_internal(service.generate(payload.to_internal()))
