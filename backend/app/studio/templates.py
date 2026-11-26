"""Editable structured document templates for LUMO Intelligence Studio (Phase 30)."""

from __future__ import annotations

import uuid
from typing import Any

STUDIO_TEMPLATES: dict[str, dict[str, Any]] = {
    "research_report": {
        "id": "research_report",
        "name": "Research Report",
        "sections": [
            "Research Objective",
            "Methodology",
            "Findings",
            "Analysis",
            "Evidence",
            "Limitations",
        ],
    },
    "technical_report": {
        "id": "technical_report",
        "name": "Technical Report",
        "sections": [
            "Overview",
            "Problem",
            "Architecture",
            "Methodology",
            "Technical Findings",
            "Implementation Details",
            "Risks",
            "Recommendations",
        ],
    },
    "business_intelligence": {
        "id": "business_intelligence",
        "name": "Business Intelligence Report",
        "sections": [
            "Business Context",
            "Data Overview",
            "Key Findings",
            "Trends",
            "Insights",
            "Recommendations",
            "Limitations",
        ],
    },
    "data_analysis": {
        "id": "data_analysis",
        "name": "Data Analysis Report",
        "sections": [
            "Dataset Overview",
            "Data Quality",
            "Methodology",
            "Statistical Findings",
            "Visualizations",
            "Interpretation",
            "Limitations",
        ],
    },
    "briefing": {
        "id": "briefing",
        "name": "Briefing",
        "sections": [
            "Overview",
            "Key Points",
            "Important Evidence",
            "Implications",
            "Recommended Next Steps",
        ],
    },
    "custom": {
        "id": "custom",
        "name": "Custom Document",
        "sections": [
            "Section 1",
        ],
    },
}


def build_template_sections(template_id: str) -> list[dict[str, Any]]:
    tpl = STUDIO_TEMPLATES.get(template_id, STUDIO_TEMPLATES["custom"])
    return [
        {
            "id": str(uuid.uuid4())[:8],
            "title": sec_title,
            "paragraphs": [],
            "bullets": [],
            "tables": [],
            "quotations": [],
            "notes": "",
            "is_ai_generated": False,
        }
        for sec_title in tpl["sections"]
    ]
