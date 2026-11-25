"""SQLAlchemy models for LUMO Phase 23: Intelligence API & Developer Platform."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(Base):
    """Hashed developer API credential with granular permissions, expiration, and per-key rate limits."""

    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(160), nullable=False)
    key_prefix = Column(String(24), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    permissions_json = Column(JSON, nullable=False, default=list)
    rate_limit_rpm = Column(Integer, nullable=False, default=60)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)


class ApiUsageLog(Base):
    """Privacy-safe API usage telemetry (never stores raw keys or request/document bodies)."""

    __tablename__ = "api_usage_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id = Column(
        String(36),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    key_prefix = Column(String(24), nullable=True)
    endpoint = Column(String(255), nullable=False, index=True)
    method = Column(String(12), nullable=False)
    status_code = Column(Integer, nullable=False, index=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    rate_limited = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    __table_args__ = (
        Index("ix_api_usage_key_created", "api_key_id", "created_at"),
    )
