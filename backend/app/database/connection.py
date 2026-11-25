"""PostgreSQL engine and session management.

Phase 1 prepares the connection only. It does not create tables.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import psycopg  # noqa: F401  # Confirms the Psycopg driver is installed.
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.logging import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all LUMO database models."""
    pass


_lock = threading.Lock()
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_database_url = ""


def database_target_label(database_url: str) -> str:
    """Return host, port, and database name without user or password."""
    if not database_url:
        return "not-configured"
    try:
        parsed = make_url(database_url)
    except Exception:
        return "unrecognized-database-target"
    host = parsed.host or "unknown-host"
    port = f":{parsed.port}" if parsed.port else ""
    database = f"/{parsed.database}" if parsed.database else ""
    return f"{host}{port}{database}"


def init_database(database_url: str) -> None:
    """Create a shared engine for the configured PostgreSQL URL."""
    global _engine, _session_factory, _database_url

    with _lock:
        if _engine is not None and _database_url == database_url:
            return
        _dispose_locked()
        _database_url = database_url.strip()
        if not _database_url:
            logger.warning("DATABASE_URL is empty. Database features are disabled.")
            return
        try:
            if _database_url.startswith("postgresql"):
                engine_kwargs = {
                    "pool_pre_ping": True,
                    "pool_size": 5,
                    "max_overflow": 5,
                    "pool_timeout": 30,
                    "connect_args": {"connect_timeout": 3},
                }
            else:
                engine_kwargs = {
                    "connect_args": {"check_same_thread": False},
                }

            _engine = create_engine(_database_url, **engine_kwargs)
            _session_factory = sessionmaker(
                bind=_engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
        except SQLAlchemyError as exc:
            _engine = None
            _session_factory = None
            logger.error(
                "Database engine was not created for %s (%s)",
                database_target_label(_database_url),
                type(exc).__name__,
            )
            return
        logger.info(
            "Database engine created for %s",
            database_target_label(_database_url),
        )


def dispose_database() -> None:
    """Close pooled connections during application shutdown."""
    with _lock:
        _dispose_locked()


def get_engine() -> Engine | None:
    """Return the shared engine, or None when the database is not configured."""
    with _lock:
        return _engine


def check_database_connection() -> bool:
    """Run SELECT 1. Failures are logged without credentials or driver text."""
    with _lock:
        engine = _engine
        target = database_target_label(_database_url) if _database_url else "not-configured"

    if engine is None:
        logger.warning("Database connection check skipped because no engine is configured.")
        return False

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error(
            "Database connection failed for %s (%s)",
            target,
            type(exc).__name__,
        )
        return False

    logger.info("Database connection succeeded for %s", target)
    return True


def get_session_factory() -> sessionmaker[Session] | None:
    """Return the active session factory or None if unconfigured."""
    with _lock:
        return _session_factory


def create_tables() -> None:
    """Create all registered database tables if engine is configured."""
    with _lock:
        engine = _engine
    if engine is not None:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables verified/created successfully.")
        except SQLAlchemyError as exc:
            logger.error("Failed to create database tables (%s)", type(exc).__name__)


def get_db() -> Iterator[Session]:
    """Yield a session, roll it back on error, and always close it."""
    with _lock:
        factory = _session_factory
    if factory is None:
        raise RuntimeError("Database is not configured.")

    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _dispose_locked() -> None:
    global _engine, _session_factory, _database_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _database_url = ""


if __name__ == "__main__":
    import sys
    from app.config import get_settings

    settings = get_settings()
    target = database_target_label(settings.database_url)
    print(f"Testing PostgreSQL connection to: {target} ...")
    if not settings.database_url:
        print("DATABASE_URL is not configured in .env. Database connection skipped.")
        sys.exit(0)

    init_database(settings.database_url)
    if check_database_connection():
        print("SUCCESS: Connected to PostgreSQL database successfully.")
        sys.exit(0)
    else:
        print("FAILED: Could not connect to PostgreSQL database.")
        print(" - Verify PostgreSQL service is running on Windows (e.g. Get-Service postgresql*).")
        print(" - Verify DATABASE_URL in backend/.env has the correct user, password, and port.")
        sys.exit(1)

