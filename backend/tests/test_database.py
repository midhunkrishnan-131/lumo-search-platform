"""Database session and connectivity tests."""

import pytest

from app.config import Settings
from app.database.connection import (
    check_database_connection,
    database_target_label,
    get_db,
    init_database,
)
from app.main import create_app


def test_database_target_hides_credentials():
    label = database_target_label(
        "postgresql+psycopg://lumo_user:super-secret-password@localhost:5432/lumo"
    )

    assert label == "localhost:5432/lumo"
    assert "super-secret-password" not in label
    assert "lumo_user" not in label


def test_connection_failure_is_safe(lumo_logs: pytest.LogCaptureFixture):
    database_url = "postgresql+psycopg://lumo_user:super-secret-password@127.0.0.1:1/lumo"

    init_database(database_url)
    assert check_database_connection() is False
    assert "Database connection failed" in lumo_logs.text
    assert "super-secret-password" not in lumo_logs.text
    assert "lumo_user" not in lumo_logs.text


def test_startup_logs_do_not_include_password(lumo_logs: pytest.LogCaptureFixture):
    from fastapi.testclient import TestClient
    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://lumo_user:super-secret-password@127.0.0.1:1/lumo",
        log_level="INFO",
        cors_origins="http://localhost:3000",
        _env_file=None,
    )

    with TestClient(create_app(settings)):
        pass

    assert "Application startup" in lumo_logs.text
    assert "super-secret-password" not in lumo_logs.text


def test_get_db_requires_configuration():
    with pytest.raises(RuntimeError, match="not configured"):
        next(get_db())


def test_get_db_closes_session_and_rolls_back_on_error():
    init_database("postgresql+psycopg://lumo_user:change-me@127.0.0.1:1/lumo")
    generator = get_db()
    session = next(generator)
    events = {"rollback": False, "close": False}
    original_rollback = session.rollback
    original_close = session.close

    def spy_rollback() -> None:
        events["rollback"] = True
        original_rollback()

    def spy_close() -> None:
        events["close"] = True
        original_close()

    session.rollback = spy_rollback  # type: ignore[method-assign]
    session.close = spy_close  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom"):
        generator.throw(RuntimeError("boom"))

    assert events == {"rollback": True, "close": True}


def test_successful_connection_check(monkeypatch: pytest.MonkeyPatch):
    class FakeConnection:
        def execute(self, statement):
            assert str(statement) == "SELECT 1"
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeEngine:
        def connect(self):
            return FakeConnection()

        def dispose(self) -> None:
            return None

    monkeypatch.setattr("app.database.connection._engine", FakeEngine())
    monkeypatch.setattr(
        "app.database.connection._database_url",
        "postgresql+psycopg://lumo_user:secret@localhost:5432/lumo",
    )

    assert check_database_connection() is True
