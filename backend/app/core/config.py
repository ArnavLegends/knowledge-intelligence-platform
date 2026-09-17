"""Application configuration loaded from environment variables and .env files."""

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


settings = Settings()
