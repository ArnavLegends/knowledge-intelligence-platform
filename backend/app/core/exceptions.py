"""Application exception hierarchy and FastAPI exception handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("app.core.exceptions")


class AppException(Exception):
    """Base application error with a stable code, message, and HTTP status."""

    code = "application_error"
    status_code = 500

    def __init__(
        self,
        message: str = "An application error occurred.",
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.status_code = status_code if status_code is not None else self.status_code


class BadRequestError(AppException):
    """Raised when a request is invalid."""

    code = "bad_request"
    status_code = 400

    def __init__(self, message: str = "Invalid request.") -> None:
        super().__init__(message)


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    code = "not_found"
    status_code = 404

    def __init__(self, message: str = "Resource not found.") -> None:
        super().__init__(message)


class LLMProviderError(AppException):
    """Raised when a language model provider request fails."""

    code = "llm_provider_error"
    status_code = 503

    def __init__(
        self, message: str = "Language model provider request failed."
    ) -> None:
        super().__init__(message)


class DocumentValidationError(AppException):
    """Raised when an uploaded document fails validation."""

    code = "invalid_document"
    status_code = 400

    def __init__(self, message: str = "Invalid document upload.") -> None:
        super().__init__(message)


class UnsupportedFormatError(AppException):
    """Raised when no parser is registered for the uploaded format."""

    code = "unsupported_format"
    status_code = 415

    def __init__(self, message: str = "Unsupported document format.") -> None:
        super().__init__(message)


class DocumentParseError(AppException):
    """Raised when a supported document cannot be parsed."""

    code = "document_parse_error"
    status_code = 400

    def __init__(self, message: str = "Document could not be parsed.") -> None:
        super().__init__(message)


class ChunkingError(AppException):
    """Raised when chunking configuration or execution fails at runtime."""

    code = "chunking_error"
    status_code = 500

    def __init__(self, message: str = "Chunking failed.") -> None:
        super().__init__(message)


class EmbeddingProviderError(AppException):
    """Raised when an embedding provider request fails."""

    code = "embedding_provider_error"
    status_code = 503

    def __init__(self, message: str = "Embedding provider request failed.") -> None:
        super().__init__(message)


class VectorStoreError(AppException):
    """Raised when a vector storage operation fails."""

    code = "vector_store_error"
    status_code = 500

    def __init__(self, message: str = "Vector storage operation failed.") -> None:
        super().__init__(message)


class RetrievalError(AppException):
    """Raised when a retrieval operation fails."""

    code = "retrieval_error"
    status_code = 500

    def __init__(self, message: str = "Retrieval operation failed.") -> None:
        super().__init__(message)


def error_payload(code: str, message: str) -> dict[str, dict[str, str]]:
    """Return the standard API error body."""
    return {"error": {"code": code, "message": message}}


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Return a consistent JSON error for known application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected errors and return a generic 500 response."""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=error_payload("internal_error", "An unexpected error occurred."),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach application and unhandled exception handlers to a FastAPI app."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
