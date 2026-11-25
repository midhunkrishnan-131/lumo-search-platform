"""Tests for LUMO Phase 17: Adaptive Intelligence & Personalization Engine."""

from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.document import Document
from app.models.graph import Entity
from app.personalization.ranking import AdaptiveRanker


@pytest.fixture
def pers_client(tmp_path) -> Generator[TestClient, None, None]:
    db_file = tmp_path / "pers_test.db"
    settings = Settings(
        app_name="LUMO",
        app_version="0.1.0",
        environment="test",
        database_url=f"sqlite:///{db_file}",
        log_level="WARNING",
        cors_origins="http://127.0.0.1:3000",
        _env_file=None,
    )
    init_database(settings.database_url)
    create_tables()

    with TestClient(create_app(settings)) as client:
        yield client

    dispose_database()


def test_opt_in_default_sensitive_trait_rejection_and_reset(pers_client: TestClient):
    # Default is disabled (opt-in)
    st = pers_client.get("/api/v1/personalization/status").json()
    assert st["enabled"] is False

    # Sensitive traits must be rejected
    for bad_topic in ("religious affiliation", "political party", "medical diagnosis"):
        resp = pers_client.post(
            "/api/v1/personalization/interests",
            json={"topic": bad_topic, "source": "explicit"},
        )
        assert resp.status_code == 400

    # Valid non-sensitive topic accepted
    ok_resp = pers_client.post(
        "/api/v1/personalization/interests",
        json={"topic": "Python Development", "source": "explicit", "weight": 1.2},
    )
    assert ok_resp.status_code == 201
    interest_id = ok_resp.json()["id"]

    # Enable personalization
    upd = pers_client.put("/api/v1/personalization/settings", json={"enabled": True, "personalization_weight": 0.3})
    assert upd.status_code == 200
    assert upd.json()["enabled"] is True

    # Delete single interest
    assert pers_client.delete(f"/api/v1/personalization/interests/{interest_id}").status_code == 204

    # Reset deletes everything and disables personalization
    pers_client.post(
        "/api/v1/personalization/sources",
        json={"domain": "docs.python.org", "preference": "preferred"},
    )
    reset_resp = pers_client.post("/api/v1/personalization/reset")
    assert reset_resp.status_code == 200

    after = pers_client.get("/api/v1/personalization/status").json()
    assert after["enabled"] is False
    assert after["preferred_sources_count"] == 0
    assert after["interests_count"] == 0


def test_adaptive_ranker_bounds_explainability_and_disabled_baseline():
    class DummyRes:
        def __init__(self, id, title, url, score):
            self.id = id
            self.title = title
            self.url = url
            self.domain = url.split("/")[2]
            self.score = score
            self.snippet = title

    items = [
        DummyRes("1", "Generic Blog", "https://blog.example.com/1", 1.0),
        DummyRes("2", "Python FastAPI Docs", "https://docs.python.org/2", 0.95),
    ]
    ranker = AdaptiveRanker()

    # Disabled: preserves exact baseline order
    out_off, adj_off = ranker.rerank(
        results=items,
        enabled=False,
        personalization_weight=0.5,
        interests=[{"topic": "Python", "source": "explicit", "weight": 1.5}],
        topics=[],
        source_prefs=[{"domain": "docs.python.org", "preference": "preferred", "weight": 1.5}],
        feedback_items=[],
    )
    assert [x.id for x in out_off] == ["1", "2"]
    assert adj_off == []

    # Enabled: boosts preferred domain + followed topic within strict bounds
    out_on, adj_on = ranker.rerank(
        results=items,
        enabled=True,
        personalization_weight=0.5,
        interests=[{"topic": "Python", "source": "explicit", "weight": 1.5}],
        topics=[],
        source_prefs=[{"domain": "docs.python.org", "preference": "preferred", "weight": 1.5}],
        feedback_items=[],
    )
    assert [x.id for x in out_on] == ["2", "1"]
    top_adj = next(a for a in adj_on if a.item_id == "2")
    assert "preferred_source" in top_adj.applied_signals
    assert "Matches preferred source" in top_adj.explanation
    # Bound check: adjusted_score <= original_score * (1 + 0.35 * 0.5)
    assert top_adj.adjusted_score <= round(0.95 * (1.0 + 0.35 * 0.5), 6)


def test_search_integration_discovery_and_feedback(pers_client: TestClient):
    # Seed indexed documents and Knowledge Graph entity
    factory = get_session_factory()
    with factory() as db:
        db.add(
            Document(
                id="doc-p1",
                url="https://generic.example.com/a",
                title="Python Overview",
                main_content="Python overview for general programming.",
                content_hash="hp1",
                extraction_status="completed",
                is_duplicate=False,
            )
        )
        db.add(
            Document(
                id="doc-p2",
                url="https://docs.python.org/b",
                title="Python Guide",
                main_content="Python guide for web backends.",
                content_hash="hp2",
                extraction_status="completed",
                is_duplicate=False,
            )
        )
        db.add(
            Entity(
                id="ent-py",
                name="Python",
                normalized_name="python",
                entity_type="Technology",
                confidence=1.0,
                extraction_method="rule_based",
            )
        )
        db.commit()

    # Baseline search when disabled
    base_res = pers_client.get("/api/v1/search?q=Python&mode=classic").json()
    assert base_res["execution_metadata"].get("personalized") is False

    # Enable personalization & prefer docs.python.org via feedback
    pers_client.put("/api/v1/personalization/settings", json={"enabled": True, "personalization_weight": 0.4})
    fb = pers_client.post(
        "/api/v1/personalization/feedback",
        json={
            "target_type": "source",
            "target_id": "docs.python.org",
            "target_url": "https://docs.python.org/b",
            "topic": "Python",
            "feedback_type": "prefer_source",
        },
    )
    assert fb.status_code == 201
    fb_id = fb.json()["id"]

    # Search now records topic signal & marks personalized=True
    pers_res = pers_client.get("/api/v1/search?q=Python&mode=classic").json()
    assert pers_res["execution_metadata"].get("personalized") is True
    assert len(pers_client.get("/api/v1/personalization/topics").json()) >= 1

    # Grounded discovery recommendations
    recs = pers_client.get("/api/v1/personalization/recommendations").json()
    assert len(recs) >= 1
    assert any("Knowledge Graph" in r["reason"] or "Indexed in LUMO" in r["reason"] for r in recs)

    # Delete feedback
    assert pers_client.delete(f"/api/v1/personalization/feedback/{fb_id}").status_code == 204
