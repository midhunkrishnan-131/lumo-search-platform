"""Safe database schema version tracking and non-destructive migration helper."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, inspect, text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.connection import Base, create_tables, get_engine

logger = get_logger("ops.migrations")

CURRENT_SCHEMA_VERSION = 24
SCHEMA_HISTORY: list[tuple[int, str]] = [
    (1, "Core crawl, document, search, and history tables"),
    (14, "Personal Workspace tables"),
    (16, "Intelligence Automation Engine tables"),
    (17, "Adaptive Personalization tables"),
    (18, "Universal Data Intelligence tables"),
    (21, "Operational schema_migrations version tracking"),
    (22, "External Integration Layer tables"),
    (23, "Developer Platform API keys and usage tracking tables"),
    (24, "Intelligence Evaluation & Benchmarking tables"),
]


class SchemaMigration(Base):
    """Tracks applied non-destructive schema versions."""

    __tablename__ = "schema_migrations"

    version = Column(Integer, primary_key=True)
    description = Column(String(255), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


def get_migration_status(db: Session | None = None) -> dict[str, Any]:
    """Inspect current database tables and applied schema_migrations without modifying data."""
    engine = get_engine()
    if engine is None:
        return {"status": "FAILED", "current_version": 0, "target_version": CURRENT_SCHEMA_VERSION, "tables_count": 0}

    insp = inspect(engine)
    tables = insp.get_table_names()
    applied: list[dict[str, Any]] = []
    if "schema_migrations" in tables:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT version, description, applied_at FROM schema_migrations ORDER BY version ASC")).fetchall()
            applied = [{"version": r[0], "description": r[1], "applied_at": str(r[2])} for r in rows]

    cur_ver = max((a["version"] for a in applied), default=0)
    return {
        "status": "READY" if cur_ver >= CURRENT_SCHEMA_VERSION else "WARNING",
        "current_version": cur_ver,
        "target_version": CURRENT_SCHEMA_VERSION,
        "tables_count": len(tables),
        "applied_migrations": applied,
    }


def apply_safe_migrations() -> dict[str, Any]:
    """Create missing tables and record schema version entries non-destructively."""
    engine = get_engine()
    if engine is None:
        raise RuntimeError("Database engine is not initialized.")

    # Never drops or alters existing user data; only creates missing tables
    create_tables()
    insp = inspect(engine)
    if "schema_migrations" not in insp.get_table_names():
        SchemaMigration.__table__.create(bind=engine, checkfirst=True)

    with engine.begin() as conn:
        existing = {
            r[0] for r in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()
        }
        now = datetime.now(timezone.utc)
        for ver, desc in SCHEMA_HISTORY:
            if ver not in existing:
                conn.execute(
                    text(
                        "INSERT INTO schema_migrations (version, description, applied_at) "
                        "VALUES (:v, :d, :ts)"
                    ),
                    {"v": ver, "d": desc, "ts": now},
                )
    logger.info("Safe schema migration check completed (version=%d)", CURRENT_SCHEMA_VERSION)
    return get_migration_status()
