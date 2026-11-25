"""Phase 20: Platform Security, Reliability & Hardening verification tests."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.ai.router import AIProviderRouter
from app.ai.base import AIProviderError
from app.config import Settings
from app.core.logging import RedactingFormatter
from app.crawler.validator import validate_and_screen_url
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.guardian.validator import validate_guardian_url
from app.intelligence.ingestion import UniversalIngestionPipeline
from app.main import create_app
from app.models.intelligence import UniversalImportJob
from app.workspace.importer import WorkspaceImporter


@pytest.fixture()
def sec_client(tmp_path: Path):
    db_path = tmp_path / "sec_test.db"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_path}",
        api_auth_token="lumo-test-secret-token",
        rate_limit_per_minute=3,
        local_only_ai=True,
    )
    init_database(cfg.database_url)
    create_tables()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client
    dispose_database()


def test_security_headers_auth_boundary_and_rate_limit(sec_client: TestClient):
    # Health endpoint is exempt from API token and still returns security headers
    h = sec_client.get("/api/v1/health")
    assert h.status_code == 200
    assert h.headers["X-Content-Type-Options"] == "nosniff"
    assert h.headers["X-Frame-Options"] == "DENY"
    assert h.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    # Protected endpoints require token when api_auth_token is configured
    unauth = sec_client.get("/api/v1/dashboard/overview")
    assert unauth.status_code == 401

    bad_tok = sec_client.get("/api/v1/dashboard/overview", headers={"Authorization": "Bearer wrong"})
    assert bad_tok.status_code == 401

    ok_tok = sec_client.get("/api/v1/dashboard/overview", headers={"Authorization": "Bearer lumo-test-secret-token"})
    assert ok_tok.status_code == 200

    # Rate limit enforcement (limit=3/min)
    hdrs = {"X-LUMO-Token": "lumo-test-secret-token", "X-Enforce-Rate-Limit": "true"}
    for _ in range(3):
        r = sec_client.get("/api/v1/dashboard/integrity", headers=hdrs)
        assert r.status_code == 200
    blocked = sec_client.get("/api/v1/dashboard/integrity", headers=hdrs)
    assert blocked.status_code == 429


def test_ssrf_ipv4_mapped_ipv6_and_metadata_blocking():
    blocked_urls = [
        "http://127.0.0.1/admin",
        "http://[::ffff:127.0.0.1]/admin",
        "http://[::ffff:169.254.169.254]/latest/meta-data/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "http://user:pass@example.com/",
    ]
    for url in blocked_urls:
        c_res = validate_and_screen_url(url, resolve_dns=False)
        assert c_res.is_valid is False, f"Crawler failed to block: {url}"
        g_res = validate_guardian_url(url, resolve_dns=False)
        assert g_res.is_valid is False, f"Guardian failed to block: {url}"


def test_workspace_upload_signature_and_path_traversal():
    imp = WorkspaceImporter()
    with pytest.raises(ValueError, match="PDF signature"):
        imp.import_bytes("../../evil.pdf", b"not-a-pdf")
    with pytest.raises(ValueError, match="DOCX signature"):
        imp.import_bytes("fake.docx", b"not-a-zip")
    with pytest.raises(ValueError, match="Unsupported file type"):
        imp.import_bytes("payload.exe", b"MZ...")


def test_log_redacting_formatter_and_local_only_ai():
    fmt = RedactingFormatter("%(message)s")
    rec = logging.LogRecord(
        name="lumo.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Calling https://user:superpass@db.local and https://generativelanguage.googleapis.com?key=AQ.SecretTest123456789012345 with grok_abc12345678901234567890 and Bearer tok12345",
        args=(),
        exc_info=None,
    )
    rendered = fmt.format(rec)
    assert "superpass" not in rendered
    assert "AQ.SecretTest" not in rendered
    assert "grok_abc" not in rendered
    assert "tok12345" not in rendered

    router = AIProviderRouter(local_only_mode=True)
    with pytest.raises(AIProviderError, match="Local-Only Privacy Mode"):
        router.execute("sys", "user", requested_provider="gemini")
    with pytest.raises(AIProviderError, match="Local-Only Privacy Mode"):
        router.execute("sys", "user", requested_provider="grok")


def test_restart_recovery_and_integrity_endpoint(sec_client: TestClient):
    factory = get_session_factory()
    with factory() as db:
        db.add(
            UniversalImportJob(
                id="stuck-job-1",
                source_kind="file",
                format_type="pdf",
                status="extracting",
                current_stage="content_extraction",
                progress_pct=35,
            )
        )
        db.commit()
        recovered = UniversalIngestionPipeline.recover_interrupted_jobs(db)
        assert recovered == 1

    hdrs = {"Authorization": "Bearer lumo-test-secret-token"}
    integ = sec_client.get("/api/v1/dashboard/integrity", headers=hdrs)
    assert integ.status_code == 200
    assert integ.json()["status"] == "consistent"
