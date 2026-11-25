"""SQLAlchemy model for Autonomous Research Sessions."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchSession(Base):
    """Stores full state, audit trail, evidence, and report for a bounded research session."""

    __tablename__ = "research_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic = Column(Text, nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    # States: pending, planning, researching, analyzing, generating_report, completed, failed, cancelled

    current_iteration = Column(Integer, nullable=False, default=0)
    max_iterations = Column(Integer, nullable=False, default=3)
    max_queries = Column(Integer, nullable=False, default=12)
    max_sources = Column(Integer, nullable=False, default=30)
    provider = Column(String(32), nullable=False, default="auto")

    # Structured audit trail and artifact storage
    plan = Column(JSON, nullable=False, default=dict)
    queries_executed = Column(JSON, nullable=False, default=list)
    sources = Column(JSON, nullable=False, default=list)
    findings = Column(JSON, nullable=False, default=list)
    report_markdown = Column(Text, nullable=False, default="")
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

