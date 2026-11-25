"""Research Session Manager: Lifecycle, background thread execution, and CRUD."""

from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import get_logger
from app.database.connection import get_session_factory
from app.models.research import ResearchSession
from app.research.controller import ResearchController

logger = get_logger("research.manager")


class ResearchSessionManager:
    """Manages creation, execution, cancellation, and retrieval of research sessions."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def create_session(
        self,
        db: Session,
        topic: str,
        max_iterations: int | None = None,
        max_queries: int | None = None,
        max_sources: int | None = None,
        provider: str | None = None,
    ) -> ResearchSession:
        """Create a new research session record in pending status."""
        safe_iterations = max(1, min(max_iterations or self.settings.research_max_iterations, 5))
        safe_queries = max(1, min(max_queries or self.settings.research_max_queries, 25))
        safe_sources = max(1, min(max_sources or self.settings.research_max_sources, 50))
        selected_provider = provider or "auto"

        session = ResearchSession(
            id=str(uuid4()),
            topic=topic.strip(),
            status="pending",
            provider=selected_provider,
            max_iterations=safe_iterations,
            max_queries=safe_queries,
            max_sources=safe_sources,
            current_iteration=0,
            plan={},
            queries_executed=[],
            sources=[],
            findings=[],
            report_markdown="",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info("Created research session %s for topic '%s'", session.id, session.topic)
        return session

    def start_session(self, session_id: str, background: bool = True) -> ResearchSession | None:
        """Start execution of an existing pending research session."""
        factory = get_session_factory()
        if not factory:
            logger.error("Cannot start session %s: Database session factory not available", session_id)
            return None

        with factory() as db:
            session = db.query(ResearchSession).filter(ResearchSession.id == session_id).first()
            if not session:
                logger.error("Session %s not found for start", session_id)
                return None
            if session.status != "pending":
                logger.warning("Session %s already in status '%s'", session_id, session.status)
                return session

        if background:
            thread = threading.Thread(
                target=self._run_session_worker,
                args=(session_id,),
                name=f"research-{session_id[:8]}",
                daemon=True,
            )
            thread.start()
            logger.info("Launched background thread for research session %s", session_id)
            # Re-fetch from DB to return
            with factory() as db:
                return db.query(ResearchSession).filter(ResearchSession.id == session_id).first()
        else:
            # Synchronous execution (useful for unit tests)
            with factory() as db:
                controller = ResearchController(session_id=session_id, db=db)
                return controller.run()

    def _run_session_worker(self, session_id: str) -> None:
        """Background thread target that instantiates a controller and runs the research pipeline."""
        factory = get_session_factory()
        if not factory:
            logger.error("Worker failed: database session factory unavailable")
            return

        with factory() as db:
            try:
                controller = ResearchController(session_id=session_id, db=db)
                controller.run()
            except Exception as exc:
                logger.error("Unhandled error in research session worker %s: %s", session_id, exc, exc_info=True)

    def cancel_session(self, session_id: str, db: Session) -> ResearchSession | None:
        """Mark a research session as cancelled so its loop terminates gracefully."""
        session = db.query(ResearchSession).filter(ResearchSession.id == session_id).first()
        if not session:
            return None

        if session.status not in {"completed", "failed", "cancelled"}:
            session.status = "cancelled"
            db.commit()
            db.refresh(session)
            logger.info("Cancelled research session %s", session_id)

        return session

    def get_session(self, session_id: str, db: Session) -> ResearchSession | None:
        """Fetch session by ID."""
        return db.query(ResearchSession).filter(ResearchSession.id == session_id).first()

    def list_sessions(
        self,
        db: Session,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ResearchSession], int]:
        """Return paginated list of research sessions and total count, ordered by creation time descending."""
        query = db.query(ResearchSession).order_by(ResearchSession.created_at.desc())
        total = query.count()
        sessions = query.offset(offset).limit(limit).all()
        return sessions, total

    def delete_session(self, session_id: str, db: Session) -> bool:
        """Delete a research session from database."""
        session = db.query(ResearchSession).filter(ResearchSession.id == session_id).first()
        if not session:
            return False
        db.delete(session)
        db.commit()
        logger.info("Deleted research session %s", session_id)
        return True


research_manager = ResearchSessionManager()
