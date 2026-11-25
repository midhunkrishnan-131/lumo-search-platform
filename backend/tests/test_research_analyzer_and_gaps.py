"""Unit tests for Evidence Analyzer and Gap Detector."""

import json
from unittest.mock import patch

import pytest

from app.ai.base import AIProviderResponse
from app.research.analyzer import EvidenceAnalyzer
from app.research.gaps import GapDetector
from app.schemas.research import ResearchEvidenceItem, ResearchFindingItem, ResearchPlan


@pytest.fixture
def sample_plan():
    return ResearchPlan(
        topic="Dense Retrieval Scaling",
        objectives=["Measure memory usage", "Benchmark query latency"],
        subquestions=[
            "What is the memory footprint of HNSW index?",
            "How does latency scale with corpus size?",
        ],
        initial_queries=["HNSW memory footprint", "vector latency scaling"],
        expected_evidence=["Memory benchmarks", "QPS vs corpus size graphs"],
    )


@pytest.fixture
def sample_sources():
    return [
        ResearchEvidenceItem(
            source_id="S1",
            document_id="doc-1",
            title="HNSW Vector Indexing Benchmarks",
            url="https://benchmark.org/hnsw",
            domain="benchmark.org",
            passage="HNSW requires approximately 1.5 KB to 2 KB RAM per 768-dim vector.",
            query="HNSW memory footprint",
            iteration=1,
            score=0.92,
        ),
        ResearchEvidenceItem(
            source_id="S2",
            document_id="doc-2",
            title="Vector Search at Billion Scale",
            url="https://scale.org/vectors",
            domain="scale.org",
            passage="Product Quantization compresses memory by 8x with minimal recall loss.",
            query="vector latency scaling",
            iteration=1,
            score=0.88,
        ),
    ]


def test_evidence_analyzer_ai_parsing(sample_plan, sample_sources):
    analyzer = EvidenceAnalyzer()

    mock_ai_output = json.dumps([
        {
            "kind": "Supported Finding",
            "text": "HNSW index memory footprint ranges from 1.5 KB to 2 KB per vector [S1].",
            "citations": ["S1"],
        },
        {
            "kind": "Contradiction Noted",
            "text": "Some systems use PQ quantization to reduce memory at the cost of recall [S2].",
            "citations": ["S2"],
        },
        {
            "kind": "Information Gap",
            "text": "Exact sub-millisecond latency trade-offs on CPU vs GPU are missing.",
            "citations": [],
        },
    ])

    ai_resp = AIProviderResponse(content=mock_ai_output, provider="gemini", model="gemini-2.5-flash")
    with patch.object(analyzer.router, "execute", return_value=(ai_resp, False, "gemini")):
        findings = analyzer.analyze(sample_plan, sample_sources)

        assert len(findings) == 3
        assert findings[0].kind == "Supported Finding"
        assert "S1" in findings[0].citations
        assert findings[2].kind == "Information Gap"


def test_evidence_analyzer_deterministic_fallback(sample_plan, sample_sources):
    analyzer = EvidenceAnalyzer()

    with patch.object(analyzer.router, "execute", side_effect=Exception("API failure")):
        findings = analyzer.analyze(sample_plan, sample_sources)

        assert len(findings) >= 2
        kinds = {f.kind for f in findings}
        assert "Supported Finding" in kinds


def test_gap_detector_generates_bounded_queries(sample_plan):
    detector = GapDetector()

    findings = [
        ResearchFindingItem(
            kind="Supported Finding",
            text="HNSW memory footprint is confirmed [S1].",
            citations=["S1"],
        ),
        ResearchFindingItem(
            kind="Information Gap",
            text="Missing specific empirical QPS and latency benchmarks on billion-scale collections.",
            citations=[],
        ),
    ]

    mock_ai_output = json.dumps([
        "billion scale vector QPS latency benchmarks",
        "HNSW memory footprint",  # Should be deduplicated against executed_queries
        "GPU accelerated vector search latency",
    ])

    ai_resp = AIProviderResponse(content=mock_ai_output, provider="gemini", model="gemini-2.5-flash")
    with patch.object(detector.router, "execute", return_value=(ai_resp, False, "gemini")):
        new_queries = detector.detect_gaps_and_queries(
            plan=sample_plan,
            findings=findings,
            executed_queries=["HNSW memory footprint"],
            max_new_queries=2,
        )

        assert len(new_queries) <= 2
        # Duplicated query must not appear
        assert "HNSW memory footprint" not in new_queries
        assert "billion scale vector QPS latency benchmarks" in new_queries


def test_gap_detector_returns_empty_when_no_gaps(sample_plan):
    detector = GapDetector()

    # All findings supported, no information gaps
    findings = [
        ResearchFindingItem(
            kind="Supported Finding",
            text="All aspects verified [S1, S2].",
            citations=["S1", "S2"],
        )
    ]

    new_queries = detector.detect_gaps_and_queries(
        plan=sample_plan,
        findings=findings,
        executed_queries=["q1", "q2"],
        max_new_queries=3,
    )

    assert new_queries == []
