"""SQLAlchemy model for Download Guardian security analyses."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GuardianAnalysis(Base):
    """Stores full audit trail, static inspection findings, and risk reports for URLs and files."""

    __tablename__ = "guardian_analyses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    analysis_type = Column(String(16), nullable=False, index=True)  # 'url' | 'file'
    target = Column(Text, nullable=False, index=True)  # Normalized URL or filename
    target_identifier = Column(String(64), nullable=True, index=True)  # SHA-256 or Domain

    risk_level = Column(String(20), nullable=False, default="Unknown", index=True)
    # Informational, Low, Medium, High, Critical, Unknown
    risk_score = Column(Integer, nullable=False, default=0)

    # Structured findings: list of dicts with name, description, severity, evidence, recommendation
    findings = Column(JSON, nullable=False, default=list)

    # Detailed metadata (URL structure, redirects, domain, TLS cert / File hashes, magic signature, static characteristics)
    target_metadata = Column(JSON, nullable=False, default=dict)

    # External reputation lookup (if opted in)
    reputation = Column(JSON, nullable=False, default=dict)

    # Optional plain-English AI explanation of findings
    ai_explanation = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default="completed", index=True)  # completed, failed, blocked
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    @property
    def findings_count(self) -> int:
        return len(self.findings or [])
