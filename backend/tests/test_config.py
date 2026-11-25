"""Configuration loading tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.core.logging import RedactingFormatter


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_NAME", "LUMO")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "LUMO"
    assert settings.app_version == "0.1.0"
    assert settings.environment == "test"
    assert settings.database_url == ""
    assert settings.log_level == "DEBUG"
    assert settings.cors_origin_list == ["http://localhost:3000"]
    get_settings.cache_clear()


def test_settings_load_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in (
        "APP_NAME",
        "APP_VERSION",
        "ENVIRONMENT",
        "DATABASE_URL",
        "LOG_LEVEL",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_NAME=LUMO",
                "APP_VERSION=0.9.9",
                "ENVIRONMENT=development",
                "DATABASE_URL=postgresql+psycopg://lumo_user:from-file@localhost:5432/lumo",
                "LOG_LEVEL=ERROR",
                "CORS_ORIGINS=http://127.0.0.1:3000",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_version == "0.9.9"
    assert settings.log_level == "ERROR"
    assert settings.database_url.endswith("@localhost:5432/lumo")
    assert settings.cors_origin_list == ["http://127.0.0.1:3000"]


def test_example_env_file_has_no_wildcard_cors():
    example = Path(__file__).resolve().parents[1] / ".env.example"
    text = example.read_text(encoding="utf-8")

    assert "APP_NAME=LUMO" in text
    assert "postgresql+psycopg://" in text
    assert "CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500" in text
    assert "*" not in text.split("CORS_ORIGINS=", 1)[1].splitlines()[0]


def test_wildcard_cors_is_rejected():
    with pytest.raises(ValidationError):
        Settings(environment="production", cors_origins="*", _env_file=None)


def test_non_psycopg_database_url_is_rejected():
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://lumo_user:change-me@localhost:5432/lumo",
            _env_file=None,
        )


def test_log_formatter_redacts_url_passwords():
    import logging

    formatter = RedactingFormatter("%(message)s")
    log_record = logging.LogRecord(
        name="lumo.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="connecting to postgresql+psycopg://lumo_user:super-secret-password@localhost:5432/lumo",
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(log_record)

    assert "super-secret-password" not in rendered
    assert "***@" in rendered
