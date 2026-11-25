"""Deterministic tests for LUMO Phase 22: External Integration Layer (mocked external services)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database.connection import create_tables, dispose_database, init_database
from app.integrations.adapters import RssAtomIntegration
from app.main import create_app


@pytest.fixture()
def int_client(tmp_path: Path):
    db_path = tmp_path / "int_test.db"
    cfg = Settings(environment="test", database_url=f"sqlite:///{db_path}", local_only_ai=False)
    init_database(cfg.database_url)
    create_tables()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client
    dispose_database()


_SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>LUMO Tech Feed</title>
    <item>
      <guid>item-1</guid>
      <title>FastAPI 1.0 Released</title>
      <link>https://example.com/fastapi-1</link>
      <description>FastAPI and PostgreSQL performance improvements.</description>
      <pubDate>2026-11-25</pubDate>
    </item>
  </channel>
</rss>"""


def test_registry_permissions_secrets_and_ssrf(int_client: TestClient):
    avail = int_client.get("/api/v1/integrations/available")
    assert avail.status_code == 200
    ids = {a["id"] for a in avail.json()}
    assert {"rss_atom", "github", "docs_site", "open_data", "public_api"} <= ids

    reg = int_client.get("/api/v1/integrations")
    assert reg.status_code == 200
    assert len(reg.json()) >= 5

    # Configure GitHub with secret token; token must NEVER be returned in JSON
    cfg_resp = int_client.post(
        "/api/v1/integrations/github/configure",
        json={"secret_token": "ghp_super_secret_token_12345", "permissions": ["read_external", "import_data"]},
    )
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["has_secret"] is True
    assert "ghp_super_secret" not in cfg_resp.text

    # Enable GitHub, then try syncing without 'sync_sources' permission -> 403
    int_client.post("/api/v1/integrations/github/enable")
    int_client.post(
        "/api/v1/integrations/github/sources",
        json={"name": "FastAPI", "source_url": "tiangolo/fastapi", "source_type": "github"},
    )
    denied = int_client.post("/api/v1/integrations/github/sync", json={})
    assert denied.status_code == 403

    # SSRF block on localhost feed source
    bad_src = int_client.post(
        "/api/v1/integrations/rss_atom/sources",
        json={"name": "Local Feed", "source_url": "http://127.0.0.1/feed.xml", "source_type": "rss_atom"},
    )
    assert bad_src.status_code == 400

    # XXE rejection in RSS parser
    with patch("app.integrations.adapters.safe_integration_fetch", return_value=(200, {}, b"<!DOCTYPE foo><rss/>", "https://example.com/rss")):
        with pytest.raises(ValueError, match="XXE"):
            RssAtomIntegration().fetch_data("https://example.com/rss", {})


def test_rss_sync_deduplication_workspace_graph_and_notifications(int_client: TestClient):
    int_client.post("/api/v1/integrations/rss_atom/enable")
    src = int_client.post(
        "/api/v1/integrations/rss_atom/sources",
        json={"name": "Tech Feed", "source_url": "https://example.com/feed.xml", "source_type": "rss_atom"},
    )
    assert src.status_code == 201
    src_id = src.json()["id"]

    with patch("app.integrations.adapters.safe_integration_fetch", return_value=(200, {}, _SAMPLE_RSS, "https://example.com/feed.xml")):
        # 1st sync imports 1 entry
        run1 = int_client.post("/api/v1/integrations/rss_atom/sync", json={})
        assert run1.status_code == 200
        assert run1.json()["imported_count"] == 1
        assert run1.json()["skipped_count"] == 0

        # 2nd sync deduplicates same entry
        run2 = int_client.post("/api/v1/integrations/rss_atom/sync", json={})
        assert run2.status_code == 200
        assert run2.json()["imported_count"] == 0
        assert run2.json()["skipped_count"] == 1

    # Workspace search finds imported entry
    ws = int_client.post("/api/v1/workspace/search", json={"query": "FastAPI", "mode": "keyword"})
    assert ws.status_code == 200
    assert ws.json()["total"] >= 1

    # Knowledge Graph updated
    assert int_client.get("/api/v1/graph/stats").json()["total_entities"] >= 1

    # Notification created
    notifs = int_client.get("/api/v1/dashboard/notifications").json()
    assert notifs["unread_count"] >= 1

    # Source monitoring pause/resume/delete & history
    assert int_client.post(f"/api/v1/integrations/sources/{src_id}/pause").json()["paused"] is True
    assert int_client.post(f"/api/v1/integrations/sources/{src_id}/resume").json()["paused"] is False
    assert len(int_client.get("/api/v1/integrations/rss_atom/history").json()) == 2
    assert len(int_client.get("/api/v1/integrations/rss_atom/records").json()) == 1
    assert int_client.delete(f"/api/v1/integrations/sources/{src_id}").status_code == 200


def test_github_and_public_api_adapters_mocked(int_client: TestClient):
    int_client.post("/api/v1/integrations/github/enable")
    int_client.post(
        "/api/v1/integrations/github/sources",
        json={"name": "LUMO Demo Repo", "source_url": "octocat/Hello-World", "source_type": "github"},
    )

    repo_json = json.dumps({"full_name": "octocat/Hello-World", "description": "Demo repo", "language": "Python", "stargazers_count": 42, "forks_count": 5, "topics": ["python"], "html_url": "https://github.com/octocat/Hello-World"}).encode()
    rel_json = json.dumps([{"id": 99, "tag_name": "v1.0.0", "name": "v1.0.0", "body": "Initial release", "html_url": "https://github.com/octocat/Hello-World/releases/tag/v1.0.0"}]).encode()

    with patch("app.integrations.adapters.safe_integration_fetch", side_effect=[(200, {}, repo_json, "https://api.github.com/repos/octocat/Hello-World"), (200, {}, rel_json, "https://api.github.com/repos/octocat/Hello-World/releases")]):
        run = int_client.post("/api/v1/integrations/github/sync", json={})
        assert run.status_code == 200
        assert run.json()["imported_count"] == 2
