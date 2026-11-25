"""Timestamped Backup, Integrity Verification, Retention, and Confirmed Restore for LUMO Phase 21."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import time
from typing import Any

from sqlalchemy.engine.url import make_url

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.database.connection import dispose_database, get_engine, init_database

logger = get_logger("ops.backup")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_backups_root(settings: Settings | None = None) -> Path:
    backend_dir = Path(__file__).resolve().parents[2]
    root = backend_dir.parent / "backups"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _backup_database(db_dir: Path, settings: Settings) -> tuple[str, str]:
    """Safely back up SQLite (via sqlite3.backup API) or PostgreSQL (via pg_dump)."""
    db_dir.mkdir(parents=True, exist_ok=True)
    url = (settings.database_url or "").strip()
    if not url or url.startswith("sqlite"):
        eng = get_engine()
        db_file = Path(eng.url.database) if (eng and eng.url.database and eng.url.database != ":memory:") else (Path(__file__).resolve().parents[2] / "lumo.db")
        if not db_file.is_absolute():
            db_file = Path(__file__).resolve().parents[2] / db_file
        target = db_dir / "lumo.db"
        if db_file.exists():
            src = sqlite3.connect(str(db_file))
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        return "sqlite", target.name

    # PostgreSQL via pg_dump
    parsed = make_url(url)
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError("pg_dump executable not found on PATH for PostgreSQL backup.")
    target = db_dir / "lumo_pg.sql"
    env = {"PGPASSWORD": parsed.password or ""}
    cmd = [
        pg_dump,
        "-h", parsed.host or "127.0.0.1",
        "-p", str(parsed.port or 5432),
        "-U", parsed.username or "postgres",
        "-F", "p",
        "-f", str(target),
        parsed.database or "lumo",
    ]
    proc = subprocess.run(cmd, env={**__import__("os").environ, **env}, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed with exit code {proc.returncode}")
    return "postgresql", target.name


def create_backup(label: str = "manual", settings: Settings | None = None, backups_root: Path | None = None) -> dict[str, Any]:
    """Create a timestamped backup with SHA-256 manifest across DB, documents, and vector store."""
    cfg = settings or get_settings()
    backend_dir = Path(__file__).resolve().parents[2]
    root = backups_root or get_backups_root(cfg)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S_%f")
    backup_dir = root / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_dir = backup_dir / "database"
    docs_dir = backup_dir / "documents"
    vec_dir = backup_dir / "vector_store"
    docs_dir.mkdir(parents=True, exist_ok=True)
    vec_dir.mkdir(parents=True, exist_ok=True)

    dialect, db_artifact = _backup_database(db_dir, cfg)

    # Copy backend/data/ (ingested datasets, workspace files)
    src_data = backend_dir / "data"
    if src_data.exists():
        shutil.copytree(src_data, docs_dir, dirs_exist_ok=True)

    # Copy embedded qdrant_storage if present
    q_path = Path(cfg.qdrant_storage_path)
    if not q_path.is_absolute():
        q_path = (backend_dir / q_path).resolve()
    if q_path.exists() and q_path.is_dir():
        shutil.copytree(q_path, vec_dir, dirs_exist_ok=True)

    checksums: dict[str, str] = {}
    total_bytes = 0
    for f in sorted(backup_dir.rglob("*")):
        if f.is_file() and f.name != "manifest.json":
            rel = f.relative_to(backup_dir).as_posix()
            checksums[rel] = _sha256_file(f)
            total_bytes += f.stat().st_size

    manifest = {
        "backup_id": stamp,
        "label": label,
        "lumo_version": cfg.app_version,
        "environment": cfg.environment,
        "database_dialect": dialect,
        "database_artifact": db_artifact,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(checksums),
        "total_bytes": total_bytes,
        "checksums": checksums,
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Created LUMO backup '%s' (%d files, %d bytes)", stamp, len(checksums), total_bytes)
    return manifest


def verify_backup(backup_id: str, backups_root: Path | None = None) -> dict[str, Any]:
    """Verify backup manifest existence and SHA-256 integrity of every file."""
    root = backups_root or get_backups_root()
    bdir = (root / Path(backup_id).name).resolve()
    if not bdir.exists() or not (bdir / "manifest.json").exists():
        return {"backup_id": backup_id, "valid": False, "error": "Backup or manifest.json not found."}

    manifest = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
    checksums = manifest.get("checksums", {})
    mismatches: list[str] = []
    missing: list[str] = []
    for rel, expected in checksums.items():
        fpath = bdir / rel
        if not fpath.exists():
            missing.append(rel)
        elif _sha256_file(fpath) != expected:
            mismatches.append(rel)

    valid = not mismatches and not missing
    return {
        "backup_id": backup_id,
        "valid": valid,
        "file_count": len(checksums),
        "missing_files": missing,
        "checksum_mismatches": mismatches,
        "manifest": manifest,
    }


def list_backups(backups_root: Path | None = None) -> list[dict[str, Any]]:
    root = backups_root or get_backups_root()
    items: list[dict[str, Any]] = []
    for d in sorted(root.iterdir(), reverse=True):
        if d.is_dir() and (d / "manifest.json").exists():
            try:
                m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
                items.append({
                    "backup_id": m.get("backup_id", d.name),
                    "label": m.get("label", "manual"),
                    "lumo_version": m.get("lumo_version"),
                    "database_dialect": m.get("database_dialect"),
                    "file_count": m.get("file_count", 0),
                    "total_bytes": m.get("total_bytes", 0),
                    "created_at": m.get("created_at"),
                })
            except Exception:
                continue
    return items


def _rmtree_force(target: Path) -> None:
    def _onexc(func, path, exc):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            time.sleep(0.05)
            func(path)

    shutil.rmtree(target, onexc=_onexc)


def prune_backups(keep: int = 5, backups_root: Path | None = None) -> dict[str, Any]:
    """Delete oldest verified backups beyond retention count (minimum keep=1)."""
    if keep < 1:
        raise ValueError("Retention 'keep' must be at least 1.")
    all_b = list_backups(backups_root=backups_root)
    root = backups_root or get_backups_root()
    deleted: list[str] = []
    for b in all_b[keep:]:
        target = (root / Path(b["backup_id"]).name).resolve()
        if root.resolve() in target.parents and target.exists():
            _rmtree_force(target)
            deleted.append(b["backup_id"])
    return {"kept": min(len(all_b), keep), "deleted": deleted}


def restore_backup(
    backup_id: str,
    confirm: bool = False,
    settings: Settings | None = None,
    backups_root: Path | None = None,
) -> dict[str, Any]:
    """Restore a verified backup only with explicit confirm=True, creating a pre-restore safety backup first."""
    if not confirm:
        raise ValueError("Restore requires explicit confirmation (confirm=True).")

    cfg = settings or get_settings()
    root = backups_root or get_backups_root(cfg)
    ver = verify_backup(backup_id, backups_root=root)
    if not ver["valid"]:
        raise ValueError(f"Backup integrity check failed: {ver.get('error') or ver.get('checksum_mismatches')}")

    manifest = ver["manifest"]
    bdir = (root / Path(backup_id).name).resolve()
    safety = create_backup(label=f"pre_restore_{backup_id}", settings=cfg, backups_root=root)

    backend_dir = Path(__file__).resolve().parents[2]
    dialect = manifest.get("database_dialect")
    db_file_src = bdir / "database" / manifest.get("database_artifact", "lumo.db")

    if dialect == "sqlite" and db_file_src.exists():
        eng = get_engine()
        target_db = Path(eng.url.database) if (eng and eng.url.database and eng.url.database != ":memory:") else (backend_dir / "lumo.db")
        if not target_db.is_absolute():
            target_db = backend_dir / target_db
        dispose_database()
        shutil.copy2(db_file_src, target_db)
        init_database(cfg.database_url or f"sqlite:///{target_db}")

    docs_src = bdir / "documents"
    if docs_src.exists():
        shutil.copytree(docs_src, backend_dir / "data", dirs_exist_ok=True)

    logger.info("Restored LUMO backup '%s' (safety backup: '%s')", backup_id, safety["backup_id"])
    return {
        "restored_backup_id": backup_id,
        "safety_backup_id": safety["backup_id"],
        "database_dialect": dialect,
        "restored_at": datetime.now(timezone.utc).isoformat(),
    }
