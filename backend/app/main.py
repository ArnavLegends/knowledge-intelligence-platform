"""FastAPI application entry point for the Knowledge Intelligence Platform."""

from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description=(
        "A production-grade AI Knowledge Intelligence Platform for RAG, "
        "Agentic AI, and Knowledge Graphs."
    ),
    version=settings.app_version,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a simple health status for operational monitoring."""
    return {"status": "healthy"}
