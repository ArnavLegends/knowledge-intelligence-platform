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


settings = Settings()
