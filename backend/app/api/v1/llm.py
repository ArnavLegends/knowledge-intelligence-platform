"""Versioned language model HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.schemas import GenerateRequest, GenerateResponse
from app.services.llm.service import LLMService, get_llm_service

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/generate", response_model=GenerateResponse)
def generate(
    payload: GenerateRequest,
    service: Annotated[LLMService, Depends(get_llm_service)],
) -> GenerateResponse:
    """Generate a completion through the application LLM service."""
    return GenerateResponse.from_internal(service.generate(payload.to_internal()))
