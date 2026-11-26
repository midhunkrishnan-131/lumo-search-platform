"""Database models for LUMO Phase 27: Unified Intelligence Workspace & Orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.connection import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntelligenceWorkflow(Base):
    """Persisted multi-module intelligence workflow plan, execution state, and unified results."""

    __tablename__ = "intelligence_workflows"

    id = Column(String(36), primary_key=True)
    owner_id = Column(String(128), nullable=False, default="local", index=True)
    title = Column(String(255), nullable=False)
    user_request = Column(Text, nullable=False, default="")
    intent = Column(String(64), nullable=False, index=True)
    selected_modules_json = Column(JSON, nullable=False, default=list)
    plan_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="CREATED", index=True)
    progress = Column(Float, nullable=False, default=0.0)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    summary = Column(Text, nullable=True)
    results_json = Column(JSON, nullable=False, default=dict)
    sources_json = Column(JSON, nullable=False, default=list)
    disagreements_json = Column(JSON, nullable=False, default=list)
    errors_json = Column(JSON, nullable=False, default=list)
    execution_metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    steps = relationship(
        "IntelligenceWorkflowStep",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="IntelligenceWorkflowStep.created_at.asc()",
    )


class IntelligenceWorkflowStep(Base):
    """Individual module step inside an IntelligenceWorkflow DAG."""

    __tablename__ = "intelligence_workflow_steps"

    id = Column(String(36), primary_key=True)
    workflow_id = Column(
        String(36),
        ForeignKey("intelligence_workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_key = Column(String(64), nullable=False)
    module_name = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    depends_on_json = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="PENDING")
    output_ref_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    workflow = relationship("IntelligenceWorkflow", back_populates="steps")
