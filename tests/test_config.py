"""Application configuration tests."""

from app.core.config import Settings


def test_settings_default_values() -> None:
    settings = Settings()
    assert settings.app_name == "Knowledge Intelligence Platform"
    assert settings.app_version == "0.2.0"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.log_level == "INFO"


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
        "APP_NAME=From Env File\n"
        "APP_VERSION=1.2.3\n"
        "ENVIRONMENT=staging\n"
        "DEBUG=true\n",
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
