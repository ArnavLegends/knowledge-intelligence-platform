"""FastAPI application entry point for the Knowledge Intelligence Platform."""

from fastapi import FastAPI

API_VERSION = "0.2.0"

app = FastAPI(
    title="Knowledge Intelligence Platform",
    description=(
        "A production-grade AI Knowledge Intelligence Platform for RAG, "
        "Agentic AI, and Knowledge Graphs."
    ),
    version=API_VERSION,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a simple health status for operational monitoring."""
    return {"status": "healthy"}
