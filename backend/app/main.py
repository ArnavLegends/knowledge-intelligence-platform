"""FastAPI application entry point for the Knowledge Intelligence Platform."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application services on startup."""
    setup_logging()
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "A production-grade AI Knowledge Intelligence Platform for RAG, "
        "Agentic AI, and Knowledge Graphs."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a simple health status for operational monitoring."""
    return {"status": "healthy"}
