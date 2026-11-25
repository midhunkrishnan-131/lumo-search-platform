"""Citation registry and validator for autonomous research reports."""

from __future__ import annotations

import re
from typing import Any

from app.schemas.research import ResearchEvidenceItem


class ResearchCitationRegistry:
    """Manages session-scoped source mappings and validates markdown report citations."""

    def __init__(self, sources: list[ResearchEvidenceItem] | None = None) -> None:
        self.sources_map: dict[str, ResearchEvidenceItem] = {
            s.source_id: s for s in (sources or [])
        }

    def register(self, document_id: str, url: str, title: str, passage: str) -> str:
        """Register a new source and assign the next sequential [S1] key."""
        next_idx = len(self.sources_map) + 1
        source_id = f"S{next_idx}"
        item = ResearchEvidenceItem(
            source_id=source_id,
            document_id=document_id,
            title=title,
            url=url,
            domain=url.split("//")[-1].split("/")[0],
            passage=passage,
            query="",
            iteration=1,
            score=1.0,
        )
        self.sources_map[source_id] = item
        return source_id

    def get_registered_keys(self) -> list[str]:
        return list(self.sources_map.keys())

    def strip_hallucinated_citations(self, text: str) -> str:
        """Remove any [S...] tokens that are not registered in sources_map."""
        if not text:
            return ""
        cited_keys = set(re.findall(r"\[S(\d+)\]", text))
        cleaned = text
        for k in sorted(cited_keys, key=lambda x: int(x)):
            token = f"S{k}"
            if token not in self.sources_map:
                cleaned = cleaned.replace(f"[{token}]", "")
        return re.sub(r" {2,}", " ", cleaned).strip()

    def validate_report(self, report_markdown: str) -> str:
        """Scan report for citation tokens like [S1], strip invalid citations, and append verified references."""
        if not report_markdown:
            return ""

        # Find all cited keys: [S1], [S2]
        cited_keys = set(re.findall(r"\[S(\d+)\]", report_markdown))

        # Identify invalid/hallucinated citations not in sources_map
        valid_sources: list[ResearchEvidenceItem] = []
        invalid_keys: set[str] = set()

        for k in sorted(cited_keys, key=lambda x: int(x)):
            token = f"S{k}"
            if token in self.sources_map:
                valid_sources.append(self.sources_map[token])
            else:
                invalid_keys.add(f"[S{k}]")

        # Strip invalid citations from markdown
        cleaned_report = report_markdown
        for bad_token in invalid_keys:
            cleaned_report = cleaned_report.replace(bad_token, "")

        # Clean double spaces
        cleaned_report = re.sub(r" {2,}", " ", cleaned_report)

        # Check if References section already exists; if not, append verified references
        if "## References" not in cleaned_report and "### References" not in cleaned_report:
            ref_lines = ["\n\n## References"]
            # Prioritize sources that were actively cited
            used_sources = valid_sources if valid_sources else list(self.sources_map.values())
            for src in used_sources:
                ref_lines.append(f"- **[{src.source_id}]** [{src.title}]({src.url}) — *{src.domain}*")
            cleaned_report += "\n".join(ref_lines)

        return cleaned_report.strip()
