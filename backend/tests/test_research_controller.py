"""Unit tests for Research Controller execution loop and bounded limits."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.models.research import ResearchSession
from app.research.controller import ResearchController
from app.schemas.research import ResearchFindingItem, ResearchPlan
from app.search.engine import SearchResult


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        yield session


def test_research_controller_full_loop(test_db):
    session = ResearchSession(
        id="session-test-1",
        topic="Neural Search Reranking",
        status="pending",
        max_iterations=2,
        max_queries=4,
        max_sources=5,
    )
    test_db.add(session)
    test_db.commit()

    # Mock planner
    mock_planner = MagicMock()
    mock_planner.create_plan.return_value = ResearchPlan(
        topic="Neural Search Reranking",
        objectives=["Evaluate cross-encoders"],
        subquestions=["How accurate are cross-encoders?"],
        initial_queries=["cross-encoder reranking"],
        expected_evidence=["NDCG benchmarks"],
    )

    # Mock analyzer
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = [
        ResearchFindingItem(
            kind="Supported Finding",
            text="Cross-encoders boost NDCG@10 by 15% [S1].",
            citations=["S1"],
        )
    ]

    # Mock gap detector (returns empty so terminates after 1 iteration)
    mock_gaps = MagicMock()
    mock_gaps.detect_gaps_and_queries.return_value = []

    # Mock reporter
    mock_reporter = MagicMock()
    mock_reporter.generate_report.return_value = "# Neural Search Report\n\nCross-encoders boost accuracy [S1]."

    controller = ResearchController(
        session_id=session.id,
        db=test_db,
        planner=mock_planner,
        analyzer=mock_analyzer,
        gap_detector=mock_gaps,
        reporter=mock_reporter,
    )

    with patch("app.research.controller.ResearchExecutor") as MockExecutor:
        executor_instance = MockExecutor.return_value
        executor_instance.executed_queries = ["cross-encoder reranking"]
        executor_instance.execute_query.return_value = [
            SearchResult(
                id="doc-rerank-1",
                url="https://rerank.org",
                domain="rerank.org",
                title="Reranking Paper",
                description="",
                snippet="Cross-encoders improve NDCG@10 significantly.",
                score=0.95,
                sources=["hybrid"],
            )
        ]

        completed = controller.run()

        assert completed.status == "completed"
        assert completed.report_markdown.startswith("# Neural Search Report")
        assert len(completed.sources) >= 1
        assert completed.completed_at is not None


def test_research_controller_graceful_cancellation(test_db):
    session = ResearchSession(
        id="session-test-cancel",
        topic="Cancelled Investigation",
        status="pending",
        max_iterations=3,
        max_queries=10,
        max_sources=10,
    )
    test_db.add(session)
    test_db.commit()

    controller = ResearchController(session_id=session.id, db=test_db)

    # Mark session cancelled before/during run
    session.status = "cancelled"
    test_db.commit()

    result = controller.run()
    assert result.status == "cancelled"
