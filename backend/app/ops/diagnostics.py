"""Deployment & Dependency Diagnostics Engine for LUMO Phase 21."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import shutil
import sys
from typing import Any
import urllib.request

from app.config import Settings, get_settings
from app.database.connection import check_database_connection, get_engine
from app.ops.migrations import get_migration_status

REQUIRED_PACKAGES = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "psycopg",
    "pydantic",
    "httpx",
    "pypdf",
    "openpyxl",
    "qdrant_client",
    "sentence_transformers",
]


def run_deployment_diagnostics(settings: Settings | None = None) -> dict[str, Any]:
    """Check Python, packages, DB, migrations, Qdrant, Ollama, AI providers, disk, and directories."""
    cfg = settings or get_settings()
    backend_dir = Path(__file__).resolve().parents[2]
    repo_root = backend_dir.parent
    frontend_dir = repo_root / "lumo-frontend"

    checks: list[dict[str, Any]] = []

    # 1. Python & venv
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    checks.append({
        "component": "python_runtime",
        "status": "READY" if sys.version_info >= (3, 11) else "WARNING",
        "detail": f"Python {py_ver} ({'venv active' if in_venv else 'system python'})",
    })

    # 2. Required dependencies
    missing_pkgs = [p for p in REQUIRED_PACKAGES if importlib.util.find_spec(p) is None]
    checks.append({
        "component": "python_dependencies",
        "status": "READY" if not missing_pkgs else "FAILED",
        "detail": "All core packages installed." if not missing_pkgs else f"Missing: {', '.join(missing_pkgs)}",
    })

    # 3. Database connectivity & dialect
    db_ok = check_database_connection()
    eng = get_engine()
    dialect = eng.dialect.name if eng is not None else "none"
    checks.append({
        "component": "database",
        "status": "READY" if db_ok else "FAILED",
        "detail": f"Connected ({dialect})" if db_ok else "Database unavailable",
    })

    # 4. Schema & migrations
    mig = get_migration_status() if db_ok else {"status": "FAILED", "current_version": 0, "target_version": 21}
    checks.append({
        "component": "database_migrations",
        "status": mig["status"],
        "detail": f"Schema v{mig['current_version']}/{mig['target_version']} ({mig.get('tables_count', 0)} tables)",
    })

    # 5. Qdrant configuration & storage
    qdrant_path = (backend_dir / cfg.qdrant_storage_path).resolve() if not Path(cfg.qdrant_storage_path).is_absolute() else Path(cfg.qdrant_storage_path)
    qdrant_ok = qdrant_path.exists() or bool(cfg.qdrant_url)
    checks.append({
        "component": "qdrant_vector_store",
        "status": "READY" if qdrant_ok else "NOT CONFIGURED",
        "detail": f"Collection '{cfg.qdrant_collection_name}' (local={qdrant_path.exists()})",
    })

    # 6. Ollama (Optional)
    if not cfg.ollama_enabled:
        checks.append({
            "component": "ollama_local_ai",
            "status": "OPTIONAL",
            "detail": "Disabled in configuration (OLLAMA_ENABLED=false)",
        })
    else:
        ollama_up = False
        try:
            with urllib.request.urlopen(f"{cfg.ollama_base_url.rstrip('/')}/api/tags", timeout=1.5) as r:
                ollama_up = r.status == 200
        except Exception:
            ollama_up = False
        checks.append({
            "component": "ollama_local_ai",
            "status": "READY" if ollama_up else "WARNING",
            "detail": f"Reachable at {cfg.ollama_base_url}" if ollama_up else "Enabled but not reachable",
        })

    # 7. Cloud AI Providers (Optional, key-safe)
    has_gem = bool(cfg.gemini_api_key.strip())
    has_grok = bool(cfg.grok_api_key.strip())
    if cfg.local_only_ai:
        ai_status = "OPTIONAL"
        ai_detail = "Local-Only AI privacy mode active (cloud providers blocked)"
    elif has_gem or has_grok:
        ai_status = "READY"
        ai_detail = f"Configured: {', '.join([p for p, ok in (('gemini', has_gem), ('grok', has_grok)) if ok])}"
    else:
        ai_status = "NOT CONFIGURED"
        ai_detail = "No cloud AI keys configured; deterministic/local fallbacks active"
    checks.append({"component": "ai_providers", "status": ai_status, "detail": ai_detail})

    # 8. Frontend & Writable Storage
    fe_ok = (frontend_dir / "index.html").exists() and (frontend_dir / "command-center.html").exists()
    checks.append({
        "component": "frontend_assets",
        "status": "READY" if fe_ok else "FAILED",
        "detail": str(frontend_dir) if fe_ok else "Frontend HTML assets missing",
    })

    data_dir = backend_dir / "data"
    logs_dir = backend_dir / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    writable = os.access(data_dir, os.W_OK) and os.access(logs_dir, os.W_OK)
    disk = shutil.disk_usage(backend_dir)
    free_gb = round(disk.free / (1024 ** 3), 2)
    checks.append({
        "component": "storage_and_disk",
        "status": "READY" if (writable and free_gb >= 1.0) else ("WARNING" if writable else "FAILED"),
        "detail": f"Free disk: {free_gb} GB | data/ & logs/ writable: {writable}",
    })

    statuses = {c["status"] for c in checks}
    overall = "FAILED" if "FAILED" in statuses else ("WARNING" if "WARNING" in statuses else "READY")

    return {
        "overall_status": overall,
        "version": cfg.app_version,
        "environment": cfg.environment,
        "free_disk_gb": free_gb,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
