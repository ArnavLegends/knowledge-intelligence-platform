"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.documents import router as documents_router
from app.api.v1.llm import router as llm_router

api_v1_router = APIRouter()
api_v1_router.include_router(llm_router)
api_v1_router.include_router(documents_router)
