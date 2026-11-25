"""Phase 21: Deployment, Migration, Backup, Restore & Operational Diagnostics tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.database.connection import create_tables, dispose_database, get_session_factory, init_database
from app.main import create_app
from app.models.workspace import WorkspaceItem
from app.ops.backup import create_backup, prune_backups, restore_backup, verify_backup
from app.ops.diagnostics import run_deployment_diagnostics
from app.ops.migrations import CURRENT_SCHEMA_VERSION, apply_safe_migrations, get_migration_status


@pytest.fixture()
def ops_env(tmp_path: Path):
    db_path = tmp_path / "ops_test.db"
    backups_dir = tmp_path / "backups"
    cfg = Settings(
        environment="test",
        database_url=f"sqlite:///{db_path}",
        ollama_enabled=False,
        local_only_ai=False,
    )
    init_database(cfg.database_url)
    create_tables()
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client, cfg, backups_dir, db_path
    dispose_database()


def test_diagnostics_and_optional_ollama_handling(ops_env):
    client, cfg, _, _ = ops_env
    apply_safe_migrations()

    diag = run_deployment_diagnostics(cfg)
    assert diag["overall_status"] in ("READY", "WARNING")
    by_comp = {c["component"]: c for c in diag["checks"]}
    assert by_comp["database"]["status"] == "READY"
    assert by_comp["ollama_local_ai"]["status"] == "OPTIONAL"

    resp = client.get("/api/v1/ops/diagnostics")
    assert resp.status_code == 200
    rel = client.get("/api/v1/ops/release")
    assert rel.status_code == 200
    assert rel.json()["schema_version"] == CURRENT_SCHEMA_VERSION


def test_safe_migrations_preserve_user_data(ops_env):
    _, _, _, _ = ops_env
    factory = get_session_factory()
    with factory() as db:
        db.add(
            WorkspaceItem(
                id="ops-ws-keep",
                title="Preserve Me",
                content="Important user data",
                source_type="document",
                content_hash="hkeep1",
            )
        )
        db.commit()

    st = apply_safe_migrations()
    assert st["status"] == "READY"
    assert st["current_version"] == CURRENT_SCHEMA_VERSION

    with factory() as db:
        row = db.query(WorkspaceItem).filter(WorkspaceItem.id == "ops-ws-keep").first()
        assert row is not None
        assert row.title == "Preserve Me"


def test_backup_verify_tamper_prune_and_confirmed_restore(ops_env):
    client, cfg, backups_dir, _ = ops_env
    apply_safe_migrations()

    # Seed data before backup
    factory = get_session_factory()
    with factory() as db:
        db.add(
            WorkspaceItem(
                id="ops-ws-bkp",
                title="Backed Up Item",
                content="Snapshot content",
                source_type="document",
                content_hash="hbkp1",
            )
        )
        db.commit()

    m1 = create_backup(label="test1", settings=cfg, backups_root=backups_dir)
    assert m1["file_count"] >= 1
    ver1 = verify_backup(m1["backup_id"], backups_root=backups_dir)
    assert ver1["valid"] is True

    # Restore without confirmation must fail
    with pytest.raises(ValueError, match="confirmation"):
        restore_backup(m1["backup_id"], confirm=False, settings=cfg, backups_root=backups_dir)

    # Modify DB after backup, then restore with confirm=True
    with factory() as db:
        db.query(WorkspaceItem).filter(WorkspaceItem.id == "ops-ws-bkp").delete()
        db.commit()

    res = restore_backup(m1["backup_id"], confirm=True, settings=cfg, backups_root=backups_dir)
    assert res["restored_backup_id"] == m1["backup_id"]
    assert res["safety_backup_id"]

    with get_session_factory()() as db:
        restored = db.query(WorkspaceItem).filter(WorkspaceItem.id == "ops-ws-bkp").first()
        assert restored is not None

    # Retention validation
    with pytest.raises(ValueError, match="at least 1"):
        prune_backups(keep=0, backups_root=backups_dir)
    pruned = prune_backups(keep=1, backups_root=backups_dir)
    assert pruned["kept"] == 1

    # Tamper detection
    m2 = create_backup(label="tamper", settings=cfg, backups_root=backups_dir)
    b_db = backups_dir / m2["backup_id"] / "database" / "lumo.db"
    b_db.write_bytes(b"corrupted")
    tamper_ver = verify_backup(m2["backup_id"], backups_root=backups_dir)
    assert tamper_ver["valid"] is False
    assert "database/lumo.db" in tamper_ver["checksum_mismatches"]
