"""Application configuration tests."""

from app.core.config import Settings


def test_settings_default_values(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.app_name == "Knowledge Intelligence Platform"
    assert settings.app_version == "1.3.0"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.llm_provider == "openai"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.llm_api_key == ""
    assert settings.max_upload_bytes == 2_097_152


def test_settings_load_from_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test Platform")
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DEBUG", "true")

    settings = Settings()

    assert settings.app_name == "Test Platform"
    assert settings.app_version == "9.9.9"
    assert settings.environment == "testing"
    assert settings.debug is True


def test_settings_load_from_env_file(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_NAME=From Env File\nAPP_VERSION=1.2.3\nENVIRONMENT=staging\nDEBUG=true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.app_name == "From Env File"
    assert settings.app_version == "1.2.3"
    assert settings.environment == "staging"
    assert settings.debug is True


def test_fastapi_app_uses_settings() -> None:
    from app.core.config import settings
    from app.main import app

    assert app.title == settings.app_name
    assert app.version == settings.app_version


def test_fastapi_openapi_version_is_1_3_0() -> None:
    """Ensure the OpenAPI schema version reflects the configured application version."""
    from app.main import app

    openapi_schema = app.openapi()
    schema_version = openapi_schema.get("info", {}).get("version")
    assert openapi_schema["info"]["version"] == "1.3.0", (
        f"Expected OpenAPI info.version '1.3.0', got '{schema_version}'. "
        "Update app_version in backend/app/core/config.py."
    )
