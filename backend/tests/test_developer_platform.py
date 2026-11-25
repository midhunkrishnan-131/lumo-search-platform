"""Deterministic tests for LUMO Phase 23: Intelligence API & Developer Platform."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.intelligence.security import redact_secrets
from app.main import create_app
from app.models.developer import ApiKey


@pytest.fixture()
def dev_client(tmp_path: Path):
    db_path = tmp_path / "dev_test.db"
    cfg = Settings(environment="test", database_url=f"sqlite:///{db_path}", local_only_ai=False)
    init_database(cfg.database_url)
    create_tables()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client
    dispose_database()


def test_developer_info_key_lifecycle_permissions_and_redaction(dev_client: TestClient):
    info = dev_client.get("/api/v1/developer/info")
    assert info.status_code == 200
    assert info.json()["api_version"] == "v1"
    assert "search:read" in info.json()["permissions"]

    # Create scoped key (search:read only)
    created = dev_client.post(
        "/api/v1/developer/keys",
        json={"name": "Search Client", "permissions": ["search:read"], "rate_limit_rpm": 5},
    )
    assert created.status_code == 201
    body = created.json()
    raw_key = body["raw_key"]
    key_id = body["key"]["id"]
    assert raw_key.startswith("lumo_pk_")

    # Listing keys never exposes raw_key or key_hash
    listed = dev_client.get("/api/v1/developer/keys")
    assert listed.status_code == 200
    assert raw_key not in listed.text
    assert "key_hash" not in listed.text

    # Redaction strips lumo_pk_ keys
    assert raw_key not in redact_secrets(f"Failed request with {raw_key}")

    # Authorized search succeeds with X-Request-ID
    ok_search = dev_client.get("/api/v1/search?q=LUMO&mode=classic", headers={"X-API-Key": raw_key})
    assert ok_search.status_code == 200
    assert "X-Request-ID" in ok_search.headers

    # Unauthorized namespace blocked with 403
    forbidden = dev_client.get("/api/v1/graph/stats", headers={"X-API-Key": raw_key})
    assert forbidden.status_code == 403

    # Rotate key -> old key becomes 401, new key works
    rot = dev_client.post(f"/api/v1/developer/keys/{key_id}/rotate")
    assert rot.status_code == 200
    new_key = rot.json()["raw_key"]
    new_id = rot.json()["key"]["id"]
    assert new_key != raw_key
    assert dev_client.get("/api/v1/search?q=LUMO", headers={"X-API-Key": raw_key}).status_code == 401
    assert dev_client.get("/api/v1/search?q=LUMO", headers={"X-API-Key": new_key}).status_code == 200

    # Revoke new key -> 401
    assert dev_client.post(f"/api/v1/developer/keys/{new_id}/revoke").status_code == 200
    assert dev_client.get("/api/v1/search?q=LUMO", headers={"X-API-Key": new_key}).status_code == 401


def test_per_key_rate_limit_expiration_and_usage_summary(dev_client: TestClient):
    created = dev_client.post(
        "/api/v1/developer/keys",
        json={"name": "Burst Test", "permissions": ["search:read"], "rate_limit_rpm": 5},
    ).json()
    raw_key = created["raw_key"]
    key_id = created["key"]["id"]

    # 5 allowed requests, 6th returns 429
    for _ in range(5):
        r = dev_client.get("/api/v1/search?q=LUMO", headers={"Authorization": f"Bearer {raw_key}"})
        assert r.status_code == 200
    rl = dev_client.get("/api/v1/search?q=LUMO", headers={"Authorization": f"Bearer {raw_key}"})
    assert rl.status_code == 429
    assert rl.headers.get("Retry-After") == "60"

    # Usage summary records requests & 429 without leaking raw key
    usage = dev_client.get("/api/v1/developer/usage").json()
    assert usage["total_requests"] >= 6
    assert usage["rate_limited_requests"] >= 1
    assert raw_key not in str(usage)

    # Expired key rejected with 401
    with get_session_factory()() as db:
        row = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    assert dev_client.get("/api/v1/search?q=LUMO", headers={"X-API-Key": raw_key}).status_code == 401


def test_python_sdk_import_and_error_class():
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from sdk.lumo_sdk import LumoApiError, LumoClient

    client = LumoClient("http://127.0.0.1:8000", api_key="lumo_pk_demo")
    assert client._headers()["X-API-Key"] == "lumo_pk_demo"
    err = LumoApiError(403, "Forbidden", "req-1")
    assert err.status_code == 403
