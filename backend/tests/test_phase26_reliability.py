"""Tests for LUMO Phase 26: Observability, Health, Error Handling, Resilience, and Config."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.ai.base import (
    AIProviderAuthError,
    AIProviderResponse,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    BaseAIProvider,
)
from app.ai.router import AIProviderRouter
from app.config import Settings, validate_startup_config
from app.core.logging import StructuredJsonFormatter, reset_request_context, set_request_context
from app.database.connection import get_session_factory
from app.evaluation.runner import EvaluationManager
from app.main import create_app
from app.models.evaluation import EvaluationBenchmark, EvaluationRun


@pytest.fixture()
def p26_client(tmp_path: Path):
    db_file = tmp_path / "phase26_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_file.as_posix()}",
        log_level="INFO",
        log_format="text",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client


def test_logging_sanitization_json_format_and_correlation():
    fmt = StructuredJsonFormatter()
    tokens = set_request_context("req-123", "corr-456")
    try:
        rec = logging.LogRecord(
            name="lumo.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Connect postgresql://user:supersecret@localhost/db key=AIzaSyDummyKey12345678901234567890 Bearer tok12345",
            args=(),
            exc_info=None,
        )
        rec.error_class = "database_error"
        rendered = json.loads(fmt.format(rec))
        assert rendered["request_id"] == "req-123"
        assert rendered["correlation_id"] == "corr-456"
        assert rendered["error_class"] == "database_error"
        assert "supersecret" not in rendered["message"]
        assert "AIzaSyDummyKey12345678901234567890" not in rendered["message"]
        assert "tok12345" not in rendered["message"]
    finally:
        reset_request_context(tokens)


def test_health_diagnostics_system_info_and_standardized_errors(p26_client: TestClient):
    for ep in ("/health", "/health/live", "/health/ready", "/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready"):
        r = p26_client.get(ep, headers={"X-Request-ID": "trace-abc", "X-Correlation-ID": "corr-xyz"})
        assert r.status_code == 200
        assert r.headers.get("X-Request-ID") == "trace-abc"
        assert r.headers.get("X-Correlation-ID") == "corr-xyz"

    diag = p26_client.get("/api/v1/health/diagnostics")
    assert diag.status_code == 200
    d_body = diag.json()
    assert "uptime_seconds" in d_body
    assert "background_jobs" in d_body
    assert "observability" in d_body
    assert "circuit_breakers" in d_body["ai_providers"]

    info = p26_client.get("/api/v1/system/info")
    assert info.status_code == 200
    i_body = info.json()
    assert i_body["phase"] == "26"
    assert "evaluation_engine" in i_body["enabled_modules"]
    assert "gemini_api_key" not in json.dumps(i_body)

    # Standardized 404 resource_error & 422 validation_error
    r404 = p26_client.get("/api/v1/evaluations/does-not-exist")
    assert r404.status_code == 404
    assert r404.json()["error_category"] == "resource_error"
    assert "request_id" in r404.json()


def test_system_info_auth_protection(tmp_path: Path):
    db_file = tmp_path / "phase26_auth.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_file.as_posix()}",
        api_auth_token="secret-token-26",
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        unauth = client.get("/api/v1/system/info")
        assert unauth.status_code == 401
        assert unauth.json()["error_category"] == "authentication_error"
        auth = client.get("/api/v1/system/info", headers={"X-LUMO-Token": "secret-token-26"})
        assert auth.status_code == 200


class _FlakyProvider(BaseAIProvider):
    def __init__(self, mode: str = "timeout") -> None:
        self.calls = 0
        self.mode = mode

    def is_configured(self) -> bool:
        return True

    def generate_grounded_answer(self, system_prompt: str, user_prompt: str, model: str | None = None, timeout: float | None = None) -> AIProviderResponse:
        self.calls += 1
        if self.mode == "auth":
            raise AIProviderAuthError("bad key", provider="gemini")
        if self.mode == "recover_on_second" and self.calls >= 2:
            return AIProviderResponse(content="ok", model=model or "m", provider="gemini")
        raise AIProviderTimeoutError("timed out", provider="gemini")


def test_provider_retry_and_circuit_breaker():
    # 1. Recovers on retry
    p_rec = _FlakyProvider(mode="recover_on_second")
    router = AIProviderRouter(
        providers={"gemini": p_rec},
        primary_provider="gemini",
        local_only_mode=False,
        max_retries=1,
        retry_backoff_seconds=0.0,
        circuit_breaker_threshold=3,
    )
    resp, fb, active = router.execute("sys", "usr")
    assert resp.content == "ok" and fb is False and active == "gemini"
    assert p_rec.calls == 2

    # 2. Never retries auth errors
    p_auth = _FlakyProvider(mode="auth")
    r_auth = AIProviderRouter(providers={"gemini": p_auth}, primary_provider="gemini", local_only_mode=False, max_retries=3, retry_backoff_seconds=0.0)
    with pytest.raises(AIProviderAuthError):
        r_auth.execute("sys", "usr")
    assert p_auth.calls == 1

    # 3. Circuit breaker opens after threshold
    p_down = _FlakyProvider(mode="timeout")
    r_cb = AIProviderRouter(
        providers={"gemini": p_down},
        primary_provider="gemini",
        local_only_mode=False,
        max_retries=0,
        circuit_breaker_threshold=2,
        circuit_breaker_cooldown_seconds=60.0,
    )
    for _ in range(2):
        with pytest.raises(AIProviderTimeoutError):
            r_cb.execute("sys", "usr")
    with pytest.raises(AIProviderUnavailableError):
        r_cb.execute("sys", "usr")
    assert r_cb.get_status()["providers"]["gemini"]["circuit_state"] == "open"


def test_stuck_evaluation_run_recovery_and_config_validation(p26_client: TestClient):
    with get_session_factory()() as db:
        bm = EvaluationBenchmark(id="bm-stuck", name="Stuck BM", category="guardian", target_module="guardian", status="running")
        db.add(bm)
        db.add(EvaluationRun(id="run-stuck", benchmark_id="bm-stuck", target_module="guardian", status="running"))
        db.commit()

        recovered = EvaluationManager.recover_interrupted_runs(db)
        assert recovered >= 1
        refreshed = db.query(EvaluationRun).filter(EvaluationRun.id == "run-stuck").first()
        assert refreshed is not None and refreshed.status == "failed"

    cfg_bad = Settings(environment="production", api_auth_token="", ai_request_timeout=0.0, log_format="invalid")
    rep = validate_startup_config(cfg_bad)
    assert len(rep["warnings"]) >= 2
    assert len(rep["errors"]) >= 1
