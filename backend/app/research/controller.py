"""Research Controller: Orchestrates the bounded multi-step autonomous research loop."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.research import ResearchSession
from app.research.analyzer import EvidenceAnalyzer
from app.research.evidence import EvidenceCollector
from app.research.executor import ResearchExecutor
from app.research.gaps import GapDetector
from app.research.planner import ResearchPlanner
from app.research.reporter import ResearchReportGenerator
from app.schemas.research import ResearchFindingItem, ResearchPlan

logger = get_logger("research.controller")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchController:
    """Manages the full lifecycle and bounded execution loop of an autonomous research session."""

    def __init__(
        self,
        session_id: str,
        db: Session,
        planner: ResearchPlanner | None = None,
        analyzer: EvidenceAnalyzer | None = None,
        gap_detector: GapDetector | None = None,
        reporter: ResearchReportGenerator | None = None,
    ) -> None:
        self.session_id = session_id
        self.db = db
        self.planner = planner or ResearchPlanner()
        self.analyzer = analyzer or EvidenceAnalyzer()
        self.gap_detector = gap_detector or GapDetector()
        self.reporter = reporter or ResearchReportGenerator()

    def run(self) -> ResearchSession:
        """Execute the end-to-end bounded research workflow."""
        session = self.db.query(ResearchSession).filter(ResearchSession.id == self.session_id).first()
        if not session:
            raise ValueError(f"Research session {self.session_id} not found")

        if session.status in {"completed", "cancelled", "failed"}:
            return session

        logger.info("Starting autonomous research session %s ('%s')", session.id, session.topic)

        try:
            # Step 1: Planning Phase
            if self._is_cancelled(session):
                return session

            session.status = "planning"
            self.db.commit()

            plan = self.planner.create_plan(topic=session.topic, provider=session.provider)
            session.plan = plan.model_dump()
            self.db.commit()

            # Step 2: Initialize Execution & Evidence Collection
            executor = ResearchExecutor(self.db)
            collector = EvidenceCollector(max_sources=session.max_sources)
            all_findings: list[ResearchFindingItem] = []
            queries_history: list[dict[str, Any]] = []

            pending_queries = list(plan.initial_queries)

            # Step 3: Bounded Research Loop
            for iteration in range(1, session.max_iterations + 1):
                if self._is_cancelled(session):
                    return session

                session.current_iteration = iteration
                session.status = "researching"
                self.db.commit()

                # Execute queries for current iteration (bounded by max_queries)
                for q in pending_queries:
                    if self._is_cancelled(session):
                        return session
                    if len(queries_history) >= session.max_queries:
                        logger.info("Reached maximum research query cap (%d)", session.max_queries)
                        break

                    results = executor.execute_query(q, iteration=iteration, limit=5)
                    queries_history.append({
                        "query": q,
                        "iteration": iteration,
                        "results_count": len(results),
                        "timestamp": utc_now().isoformat(),
                    })

                    new_evidence = collector.collect(results, query=q, iteration=iteration, db=self.db)
                    logger.debug("Iteration %d, query '%s' yielded %d new sources", iteration, q, len(new_evidence))

                # Update live sources & queries in database for progress polling
                session.queries_executed = queries_history
                session.sources = [s.model_dump() for s in collector.get_all_sources()]
                self.db.commit()

                # Evidence Analysis Phase
                if self._is_cancelled(session):
                    return session

                session.status = "analyzing"
                self.db.commit()

                all_findings = self.analyzer.analyze(
                    plan=plan,
                    sources=collector.get_all_sources(),
                    provider=session.provider,
                )
                session.findings = [f.model_dump() for f in all_findings]
                self.db.commit()

                # Gap Detection & Next Iteration Planning
                if iteration < session.max_iterations and len(queries_history) < session.max_queries:
                    remaining_budget = session.max_queries - len(queries_history)
                    new_queries = self.gap_detector.detect_gaps_and_queries(
                        plan=plan,
                        findings=all_findings,
                        executed_queries=executor.executed_queries,
                        max_new_queries=min(3, remaining_budget),
                        provider=session.provider,
                    )
                    if new_queries:
                        pending_queries = new_queries
                    else:
                        logger.info("No further research gaps identified; completing loop early at iteration %d", iteration)
                        break
                else:
                    break

            # Step 4: Report Generation Phase
            if self._is_cancelled(session):
                return session

            session.status = "generating_report"
            self.db.commit()

            report_md = self.reporter.generate_report(
                plan=plan,
                sources=collector.get_all_sources(),
                findings=all_findings,
                provider=session.provider,
            )

            # Step 5: Mark Completed
            session.report_markdown = report_md
            session.status = "completed"
            session.completed_at = utc_now()
            self.db.commit()
            logger.info("Autonomous research session %s completed successfully", session.id)

        except Exception as exc:
            logger.error("Research session %s failed: %s", session.id, exc, exc_info=True)
            session.status = "failed"
            session.error_message = str(exc)
            self.db.commit()

        return session

    def _is_cancelled(self, session: ResearchSession) -> bool:
        self.db.refresh(session)
        if session.status == "cancelled":
            logger.info("Research session %s was cancelled by user", session.id)
            return True
        return False
