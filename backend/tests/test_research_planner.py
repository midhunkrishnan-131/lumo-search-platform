"""Unit tests for Research Planner."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.ai.base import AIProviderResponse
from app.research.planner import ResearchPlanner


def test_research_planner_ai_structured_response():
    planner = ResearchPlanner()

    mock_ai_output = json.dumps({
        "objectives": [
            "Analyze lexical BM25 precision and recall trade-offs",
            "Evaluate dense vector semantic search characteristics",
        ],
        "subquestions": [
            "How does BM25 perform on exact keywords?",
            "What are the latency trade-offs of vector search?",
        ],
        "initial_queries": [
            "lexical BM25 search precision",
            "dense vector retrieval latency",
        ],
        "expected_evidence": [
            "Empirical benchmark datasets",
            "Latency benchmarks",
        ],
    })

    ai_resp = AIProviderResponse(content=mock_ai_output, provider="gemini", model="gemini-2.5-flash")
    with patch.object(planner.router, "execute", return_value=(ai_resp, False, "gemini")):
        plan = planner.create_plan("How does hybrid search compare to lexical search?")

        assert len(plan.objectives) == 2
        assert len(plan.subquestions) == 2
        assert len(plan.initial_queries) == 2
        assert "lexical BM25 search precision" in plan.initial_queries


def test_research_planner_fallback_on_unparseable_ai():
    planner = ResearchPlanner()

    # When AI returns non-JSON or garbled response
    ai_resp = AIProviderResponse(content="Sorry, I cannot help with that.", provider="gemini", model="gemini-2.5-flash")
    with patch.object(planner.router, "execute", return_value=(ai_resp, False, "gemini")):
        plan = planner.create_plan("Quantum Computing Algorithms")

        assert len(plan.objectives) >= 3
        assert len(plan.subquestions) >= 3
        assert len(plan.initial_queries) >= 3
        assert any("Quantum Computing Algorithms" in q for q in plan.initial_queries)


def test_research_planner_fallback_on_ai_exception():
    planner = ResearchPlanner()

    with patch.object(planner.router, "execute", side_effect=RuntimeError("AI Router unreachable")):
        plan = planner.create_plan("Autonomous Robotics Navigation")

        assert len(plan.objectives) >= 3
        assert len(plan.subquestions) >= 3
        assert len(plan.initial_queries) >= 3
        assert any("Robotics" in q or "Navigation" in q for q in plan.initial_queries)


def test_research_planner_truncates_oversized_topic():
    planner = ResearchPlanner()
    giant_topic = "A" * 600

    plan = planner.create_plan(giant_topic)
    assert len(plan.topic) <= 300
