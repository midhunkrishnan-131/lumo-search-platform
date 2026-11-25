"""Personalization Service managing opt-in profiles, signals, feedback, and search reranking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.personalization import (
    PersonalizationFeedback,
    PersonalizationSettings,
    SourcePreference,
    TopicProfile,
    UserInterest,
)
from app.personalization.discovery import DiscoveryEngine
from app.personalization.ranking import AdaptiveRanker, RankedResultAdjustment
from app.personalization.topics import extract_safe_topics, is_sensitive_topic, normalize_topic
from app.schemas.personalization import (
    FeedbackCreate,
    FeedbackResponse,
    PersonalizationProfileResponse,
    PersonalizationSettingsSchema,
    PersonalizationSettingsUpdate,
    PersonalizationStatusResponse,
    RecommendationItem,
    SourcePreferenceCreate,
    SourcePreferenceResponse,
    TopicProfileResponse,
    UserInterestCreate,
    UserInterestResponse,
)

logger = get_logger("personalization.service")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PersonalizationService:
    """Coordinates user-controlled adaptive intelligence and privacy-preserving ranking."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.ranker = AdaptiveRanker()

    def get_or_create_settings(self) -> PersonalizationSettings:
        row = self.db.query(PersonalizationSettings).filter(PersonalizationSettings.id == "default").first()
        if not row:
            row = PersonalizationSettings(id="default", enabled=False, personalization_weight=0.25)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        return row

    def update_settings(self, payload: PersonalizationSettingsUpdate) -> PersonalizationSettingsSchema:
        row = self.get_or_create_settings()
        if payload.enabled is not None:
            row.enabled = payload.enabled
        if payload.personalization_weight is not None:
            row.personalization_weight = payload.personalization_weight
        if payload.preferred_search_mode is not None:
            row.preferred_search_mode = payload.preferred_search_mode
        if payload.use_search_history is not None:
            row.use_search_history = payload.use_search_history
        if payload.use_workspace_signals is not None:
            row.use_workspace_signals = payload.use_workspace_signals
        row.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(row)
        return PersonalizationSettingsSchema.model_validate(row)

    def get_status(self) -> PersonalizationStatusResponse:
        s = self.get_or_create_settings()
        return PersonalizationStatusResponse(
            enabled=s.enabled,
            personalization_weight=s.personalization_weight,
            interests_count=self.db.query(func.count(UserInterest.id)).scalar() or 0,
            topics_count=self.db.query(func.count(TopicProfile.id)).scalar() or 0,
            preferred_sources_count=(
                self.db.query(func.count(SourcePreference.id))
                .filter(SourcePreference.preference == "preferred")
                .scalar()
                or 0
            ),
            excluded_sources_count=(
                self.db.query(func.count(SourcePreference.id))
                .filter(SourcePreference.preference == "excluded")
                .scalar()
                or 0
            ),
            feedback_count=self.db.query(func.count(PersonalizationFeedback.id)).scalar() or 0,
        )

    def get_profile(self) -> PersonalizationProfileResponse:
        s = self.get_or_create_settings()
        return PersonalizationProfileResponse(
            settings=PersonalizationSettingsSchema.model_validate(s),
            interests=self.list_interests(),
            topics=self.list_topics(),
            sources=self.list_sources(),
            recent_feedback=self.list_feedback(limit=20),
        )

    # --- Interests ---

    def list_interests(self) -> list[UserInterestResponse]:
        rows = self.db.query(UserInterest).order_by(UserInterest.weight.desc(), UserInterest.topic.asc()).all()
        return [UserInterestResponse.model_validate(r) for r in rows]

    def add_interest(self, payload: UserInterestCreate) -> UserInterestResponse:
        if is_sensitive_topic(payload.topic):
            raise ValueError("Sensitive personal attributes cannot be stored as personalization interests.")
        norm = normalize_topic(payload.topic)
        existing = self.db.query(UserInterest).filter(UserInterest.normalized_topic == norm).first()
        if existing:
            existing.topic = payload.topic.strip()
            existing.category = payload.category
            existing.weight = payload.weight
            existing.source = payload.source
            existing.updated_at = utc_now()
            self.db.commit()
            self.db.refresh(existing)
            return UserInterestResponse.model_validate(existing)

        row = UserInterest(
            id=str(uuid.uuid4()),
            topic=payload.topic.strip(),
            normalized_topic=norm,
            category=payload.category,
            weight=payload.weight,
            source=payload.source,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return UserInterestResponse.model_validate(row)

    def delete_interest(self, interest_id: str) -> bool:
        row = self.db.query(UserInterest).filter(UserInterest.id == interest_id).first()
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # --- Topics ---

    def list_topics(self, limit: int = 50) -> list[TopicProfileResponse]:
        rows = (
            self.db.query(TopicProfile)
            .order_by(TopicProfile.frequency.desc(), TopicProfile.last_seen_at.desc())
            .limit(limit)
            .all()
        )
        return [TopicProfileResponse.model_validate(r) for r in rows]

    def delete_topic(self, topic_id: str) -> bool:
        row = self.db.query(TopicProfile).filter(TopicProfile.id == topic_id).first()
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def record_search_signal(self, query: str, privacy_disabled: bool = False) -> None:
        """Extract non-sensitive topics from search queries only if personalization & history are enabled."""
        if privacy_disabled or not query.strip():
            return
        s = self.get_or_create_settings()
        if not s.enabled or not s.use_search_history:
            return

        topics = extract_safe_topics(query, max_topics=3)
        if not topics:
            cleaned_q = " ".join(query.strip().split())
            if 2 <= len(cleaned_q) <= 80 and len(cleaned_q.split()) <= 4 and not is_sensitive_topic(cleaned_q):
                topics = [cleaned_q]
        now = utc_now()
        for t in topics:
            norm = normalize_topic(t)
            if not norm:
                continue
            existing = self.db.query(TopicProfile).filter(TopicProfile.normalized_topic == norm).first()
            if existing:
                existing.frequency += 1
                existing.last_seen_at = now
                existing.recency_score = 1.0
                if existing.frequency >= 3 and existing.signal_kind == "curiosity":
                    existing.signal_kind = "repeated"
                    existing.confidence = min(0.85, 0.4 + 0.1 * existing.frequency)
            else:
                self.db.add(
                    TopicProfile(
                        id=str(uuid.uuid4()),
                        topic=t,
                        normalized_topic=norm,
                        frequency=1,
                        confidence=0.35,
                        recency_score=1.0,
                        signal_kind="curiosity",
                        last_seen_at=now,
                    )
                )
        self.db.commit()

    # --- Source Preferences ---

    def list_sources(self) -> list[SourcePreferenceResponse]:
        rows = self.db.query(SourcePreference).order_by(SourcePreference.domain.asc()).all()
        return [SourcePreferenceResponse.model_validate(r) for r in rows]

    def add_source_preference(self, payload: SourcePreferenceCreate) -> SourcePreferenceResponse:
        raw_dom = payload.domain.strip().lower()
        if "://" in raw_dom:
            raw_dom = urlparse(raw_dom).netloc.lower()
        raw_dom = raw_dom.split("/")[0].strip()
        if not raw_dom:
            raise ValueError("Invalid domain.")

        existing = self.db.query(SourcePreference).filter(SourcePreference.domain == raw_dom).first()
        if existing:
            existing.preference = payload.preference
            existing.weight = payload.weight
            existing.note = payload.note
            existing.updated_at = utc_now()
            self.db.commit()
            self.db.refresh(existing)
            return SourcePreferenceResponse.model_validate(existing)

        row = SourcePreference(
            id=str(uuid.uuid4()),
            domain=raw_dom,
            preference=payload.preference,
            weight=payload.weight,
            note=payload.note,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return SourcePreferenceResponse.model_validate(row)

    def delete_source_preference(self, source_id: str) -> bool:
        row = self.db.query(SourcePreference).filter(SourcePreference.id == source_id).first()
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # --- Feedback ---

    def list_feedback(self, limit: int = 30) -> list[FeedbackResponse]:
        rows = (
            self.db.query(PersonalizationFeedback)
            .order_by(PersonalizationFeedback.created_at.desc())
            .limit(limit)
            .all()
        )
        return [FeedbackResponse.model_validate(r) for r in rows]

    def record_feedback(self, payload: FeedbackCreate) -> FeedbackResponse:
        fb = PersonalizationFeedback(
            id=str(uuid.uuid4()),
            target_type=payload.target_type,
            target_id=payload.target_id,
            target_url=payload.target_url,
            topic=payload.topic,
            feedback_type=payload.feedback_type,
        )
        self.db.add(fb)

        # Propagate explicit source/topic feedback
        if payload.feedback_type in ("prefer_source", "avoid_source") and payload.target_url:
            dom = urlparse(payload.target_url).netloc.lower() or payload.target_url.lower()
            if dom:
                pref_kind = "preferred" if payload.feedback_type == "prefer_source" else "excluded"
                self.add_source_preference(SourcePreferenceCreate(domain=dom, preference=pref_kind))

        if payload.feedback_type in ("follow_topic", "hide_topic") and payload.topic:
            if not is_sensitive_topic(payload.topic):
                src_kind = "followed" if payload.feedback_type == "follow_topic" else "excluded"
                self.add_interest(UserInterestCreate(topic=payload.topic, source=src_kind))

        self.db.commit()
        self.db.refresh(fb)
        return FeedbackResponse.model_validate(fb)

    def delete_feedback(self, feedback_id: str) -> bool:
        row = self.db.query(PersonalizationFeedback).filter(PersonalizationFeedback.id == feedback_id).first()
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    # --- Discovery & Search Integration ---

    def get_recommendations(self, limit: int = 12) -> list[RecommendationItem]:
        s = self.get_or_create_settings()
        if not s.enabled:
            return []
        return DiscoveryEngine(self.db).get_recommendations(limit=limit)

    def rerank_search_results(
        self, results: list[Any]
    ) -> tuple[list[Any], list[RankedResultAdjustment], bool]:
        s = self.get_or_create_settings()
        if not s.enabled or not results:
            return results, [], False

        interests = [
            {"topic": r.topic, "weight": r.weight, "source": r.source}
            for r in self.db.query(UserInterest).all()
        ]
        topics = [
            {"topic": r.topic, "confidence": r.confidence, "signal_kind": r.signal_kind}
            for r in self.db.query(TopicProfile).all()
        ]
        source_prefs = [
            {"domain": r.domain, "preference": r.preference, "weight": r.weight}
            for r in self.db.query(SourcePreference).all()
        ]
        feedback_items = [
            {"target_url": r.target_url, "feedback_type": r.feedback_type}
            for r in self.db.query(PersonalizationFeedback).limit(100).all()
        ]

        reranked, adjustments = self.ranker.rerank(
            results=results,
            enabled=s.enabled,
            personalization_weight=s.personalization_weight,
            interests=interests,
            topics=topics,
            source_prefs=source_prefs,
            feedback_items=feedback_items,
        )
        return reranked, adjustments, True

    def reset_all(self) -> None:
        """Delete all personalization profile data and disable personalization."""
        self.db.query(UserInterest).delete()
        self.db.query(TopicProfile).delete()
        self.db.query(SourcePreference).delete()
        self.db.query(PersonalizationFeedback).delete()
        s = self.get_or_create_settings()
        s.enabled = False
        s.personalization_weight = 0.25
        s.updated_at = utc_now()
        self.db.commit()
