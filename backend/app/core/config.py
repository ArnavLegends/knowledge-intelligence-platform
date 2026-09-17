"""Application configuration loaded from environment variables and .env files."""

from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings for the Knowledge Intelligence Platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Knowledge Intelligence Platform"
    app_version: str = "0.2.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    max_upload_bytes: int = 2_097_152
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    vector_store_provider: str = "chroma"
    vector_store_collection: str = "knowledge_base"
    vector_store_persist_directory: str = "./.chroma_data"
    retrieval_default_top_k: int = 5
    retrieval_default_threshold: float | None = None
    rag_prompt_version: str = "v1"
    rag_empty_context_message: str = (
        "I could not find relevant information in the knowledge "
        "base to answer your question."
    )

    @model_validator(mode="after")
    def validate_chunking(self) -> Self:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be strictly greater than 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")
        return self


settings = Settings()


def get_settings() -> Settings:
    return settings
