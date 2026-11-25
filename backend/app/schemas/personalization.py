"""Pydantic schemas for LUMO Phase 17: Adaptive Intelligence & Personalization Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PersonalizationSettingsSchema(BaseModel):
    enabled: bool = False
    personalization_weight: float = Field(0.25, ge=0.0, le=0.5)
    preferred_search_mode: Literal["classic", "semantic", "hybrid", "ai"] = "hybrid"
    use_search_history: bool = True
    use_workspace_signals: bool = True

    model_config = {"from_attributes": True}


class PersonalizationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    personalization_weight: float | None = Field(None, ge=0.0, le=0.5)
    preferred_search_mode: Literal["classic", "semantic", "hybrid", "ai"] | None = None
    use_search_history: bool | None = None
    use_workspace_signals: bool | None = None


class UserInterestCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=160)
    category: str = Field("Topic", max_length=64)
    weight: float = Field(1.0, ge=0.1, le=2.0)
    source: Literal["explicit", "followed", "excluded"] = "explicit"


class UserInterestResponse(BaseModel):
    id: str
    topic: str
    normalized_topic: str
    category: str
    weight: float
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicProfileResponse(BaseModel):
    id: str
    topic: str
    normalized_topic: str
    frequency: int
    confidence: float
    recency_score: float
    signal_kind: str
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class SourcePreferenceCreate(BaseModel):
    domain: str = Field(..., min_length=1, max_length=255)
    preference: Literal["preferred", "excluded"] = "preferred"
    weight: float = Field(1.0, ge=0.1, le=2.0)
    note: str | None = Field(None, max_length=500)


class SourcePreferenceResponse(BaseModel):
    id: str
    domain: str
    preference: str
    weight: float
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


FeedbackTargetType = Literal["search_result", "ai_answer", "research_report", "recommendation", "source"]
FeedbackKind = Literal[
    "relevant",
    "not_relevant",
    "helpful",
    "not_helpful",
    "prefer_source",
    "avoid_source",
    "follow_topic",
    "hide_topic",
]


class FeedbackCreate(BaseModel):
    target_type: FeedbackTargetType
    target_id: str = Field(..., min_length=1, max_length=255)
    target_url: str | None = Field(None, max_length=2048)
    topic: str | None = Field(None, max_length=160)
    feedback_type: FeedbackKind


class FeedbackResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    target_url: str | None = None
    topic: str | None = None
    feedback_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RecommendationItem(BaseModel):
    kind: str  # "topic", "research_topic", "workspace_item", "indexed_document", "graph_entity"
    id: str
    title: str
    url: str | None = None
    reason: str
    signals: list[str] = Field(default_factory=list)
    score: float = 0.0


class PersonalizationStatusResponse(BaseModel):
    enabled: bool
    personalization_weight: float
    interests_count: int
    topics_count: int
    preferred_sources_count: int
    excluded_sources_count: int
    feedback_count: int


class PersonalizationProfileResponse(BaseModel):
    settings: PersonalizationSettingsSchema
    interests: list[UserInterestResponse] = Field(default_factory=list)
    topics: list[TopicProfileResponse] = Field(default_factory=list)
    sources: list[SourcePreferenceResponse] = Field(default_factory=list)
    recent_feedback: list[FeedbackResponse] = Field(default_factory=list)
