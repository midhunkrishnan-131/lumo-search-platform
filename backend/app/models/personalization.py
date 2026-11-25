"""SQLAlchemy models for LUMO Phase 17: Adaptive Intelligence & Personalization Engine."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)

from app.database.connection import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PersonalizationSettings(Base):
    """User-controlled opt-in settings for adaptive personalization."""

    __tablename__ = "personalization_settings"

    id = Column(String(32), primary_key=True, default="default")
    enabled = Column(Boolean, nullable=False, default=False)
    personalization_weight = Column(Float, nullable=False, default=0.25)
    preferred_search_mode = Column(String(32), nullable=False, default="hybrid")
    use_search_history = Column(Boolean, nullable=False, default=True)
    use_workspace_signals = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class UserInterest(Base):
    """Explicitly followed or excluded non-sensitive user topics."""

    __tablename__ = "user_interests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic = Column(String(160), nullable=False)
    normalized_topic = Column(String(160), nullable=False, unique=True, index=True)
    category = Column(String(64), nullable=False, default="Topic")
    weight = Column(Float, nullable=False, default=1.0)
    source = Column(String(32), nullable=False, default="explicit", index=True)  # explicit | followed | excluded
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class TopicProfile(Base):
    """Observed topic signals with frequency, recency, and signal classification."""

    __tablename__ = "topic_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic = Column(String(160), nullable=False)
    normalized_topic = Column(String(160), nullable=False, unique=True, index=True)
    frequency = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=False, default=0.5)
    recency_score = Column(Float, nullable=False, default=1.0)
    signal_kind = Column(String(32), nullable=False, default="curiosity")  # curiosity | repeated | explicit | rejected
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class SourcePreference(Base):
    """Domain-level user preference (separate from credibility/trustworthiness)."""

    __tablename__ = "source_preferences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain = Column(String(255), nullable=False, unique=True, index=True)
    preference = Column(String(32), nullable=False, default="preferred", index=True)  # preferred | excluded
    weight = Column(Float, nullable=False, default=1.0)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class PersonalizationFeedback(Base):
    """Explicit optional user feedback on search results, AI answers, reports, or sources."""

    __tablename__ = "personalization_feedback"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_type = Column(String(48), nullable=False, index=True)
    target_id = Column(String(255), nullable=False, index=True)
    target_url = Column(Text, nullable=True)
    topic = Column(String(160), nullable=True)
    feedback_type = Column(String(48), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
