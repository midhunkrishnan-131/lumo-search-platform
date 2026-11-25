"""Shared fixtures for the LUMO backend tests."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import dispose_database
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="test",
        database_url="",
        log_level="WARNING",
        cors_origins="http://localhost:3000,http://127.0.0.1:3000",
        _env_file=None,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def lumo_logs(caplog: pytest.LogCaptureFixture):
    logger = logging.getLogger("lumo")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger="lumo")
    yield caplog
    logger.removeHandler(caplog.handler)


@pytest.fixture(autouse=True)
def reset_database():
    dispose_database()
    yield
    dispose_database()
