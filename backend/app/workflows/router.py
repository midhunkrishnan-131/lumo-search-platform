"""Deterministic Request Router & Workflow DAG Planner for LUMO Phase 27."""

from __future__ import annotations

import re
from typing import Any


class WorkflowIntent:
    SEARCH = "SEARCH"
    AI_SEARCH = "AI_SEARCH"
    RESEARCH = "RESEARCH"
    DOCUMENT_ANALYSIS = "DOCUMENT_ANALYSIS"
    DATA_ANALYSIS = "DATA_ANALYSIS"
    KNOWLEDGE_GRAPH = "KNOWLEDGE_GRAPH"
    URL_VERIFICATION = "URL_VERIFICATION"
    FILE_ANALYSIS = "FILE_ANALYSIS"
    MULTI_MODULE_WORKFLOW = "MULTI_MODULE_WORKFLOW"


VALID_INTENTS = {
    WorkflowIntent.SEARCH,
    WorkflowIntent.AI_SEARCH,
    WorkflowIntent.RESEARCH,
    WorkflowIntent.DOCUMENT_ANALYSIS,
    WorkflowIntent.DATA_ANALYSIS,
    WorkflowIntent.KNOWLEDGE_GRAPH,
    WorkflowIntent.URL_VERIFICATION,
    WorkflowIntent.FILE_ANALYSIS,
    WorkflowIntent.MULTI_MODULE_WORKFLOW,
}

SUPPORTED_MODULES = {
    "search",
    "ai_search",
    "research_agent",
    "document_intelligence",
    "data_intelligence",
    "knowledge_graph",
    "guardian_url",
    "guardian_file",
    "evaluation",
}


def _extract_urls(text: str, inputs: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    if isinstance(inputs.get("urls"), list):
        urls.extend(str(u).strip() for u in inputs["urls"] if str(u).strip())
    if inputs.get("url"):
        urls.append(str(inputs["url"]).strip())
    for m in re.findall(r"https?://[^\s<>'\"`]+", text or ""):
        if m not in urls:
            urls.append(m)
    return urls[:10]


def classify_and_plan(
    user_request: str,
    inputs: dict[str, Any] | None = None,
    preferred_intent: str | None = None,
    allowed_modules: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministically classify user intent, validate required inputs, and build a bounded DAG plan."""
    inp = dict(inputs or {})
    q = (user_request or "").strip()
    q_low = q.lower()
    urls = _extract_urls(q, inp)

    has_file = bool(inp.get("file_bytes_b64") is not None or inp.get("file_text") is not None or inp.get("filename"))
    has_dataset = bool(inp.get("csv_content") is not None or inp.get("json_content") is not None)
    has_doc = bool(inp.get("document_text") or inp.get("html"))

    # Determine intent deterministically
    intent = preferred_intent if preferred_intent in VALID_INTENTS else None
    if intent is None:
        multi_signals = sum([
            bool(urls),
            has_file,
            has_dataset,
            has_doc,
            any(k in q_low for k in ("research", "investigate", "compare", "verify", "report", "analyze and")),
        ])
        if has_file and has_doc:
            intent = WorkflowIntent.MULTI_MODULE_WORKFLOW
        elif has_file:
            intent = WorkflowIntent.FILE_ANALYSIS
        elif has_dataset:
            intent = WorkflowIntent.DATA_ANALYSIS
        elif has_doc and any(k in q_low for k in ("graph", "relationship", "entity", "entities", "extract")):
            intent = WorkflowIntent.MULTI_MODULE_WORKFLOW
        elif has_doc:
            intent = WorkflowIntent.DOCUMENT_ANALYSIS
        elif urls and any(k in q_low for k in ("research", "search", "summarize", "document", "investigate")):
            intent = WorkflowIntent.MULTI_MODULE_WORKFLOW
        elif urls or any(k in q_low for k in ("verify url", "check url", "safe url", "ssrf", "guardian")):
            intent = WorkflowIntent.URL_VERIFICATION
        elif any(k in q_low for k in ("research", "investigate", "deep dive", "comprehensive report")):
            intent = WorkflowIntent.MULTI_MODULE_WORKFLOW if multi_signals >= 2 else WorkflowIntent.RESEARCH
        elif any(k in q_low for k in ("relationship", "knowledge graph", "entities", "connected to")):
            intent = WorkflowIntent.KNOWLEDGE_GRAPH
        elif q.endswith("?") or any(q_low.startswith(p) for p in ("what ", "why ", "how ", "explain ", "summarize ")):
            intent = WorkflowIntent.AI_SEARCH
        else:
            intent = WorkflowIntent.SEARCH

    # Build steps DAG based on intent & inputs
    steps: list[dict[str, Any]] = []
    missing_inputs: list[str] = []

    if intent == WorkflowIntent.SEARCH:
        steps.append({"step_key": "search", "module_name": "search", "title": "Execute Hybrid/Classic Search", "depends_on": []})
    elif intent == WorkflowIntent.AI_SEARCH:
        steps.append({"step_key": "search", "module_name": "search", "title": "Retrieve Relevant Sources", "depends_on": []})
        steps.append({"step_key": "ai_search", "module_name": "ai_search", "title": "Synthesize Grounded Answer", "depends_on": ["search"]})
    elif intent == WorkflowIntent.RESEARCH:
        steps.append({"step_key": "search", "module_name": "search", "title": "Collect Initial Sources", "depends_on": []})
        steps.append({"step_key": "research_agent", "module_name": "research_agent", "title": "Run Bounded Research Investigation", "depends_on": ["search"]})
        steps.append({"step_key": "knowledge_graph", "module_name": "knowledge_graph", "title": "Extract Entities & Relationships", "depends_on": ["research_agent"]})
    elif intent == WorkflowIntent.DOCUMENT_ANALYSIS:
        if not has_doc and not q:
            missing_inputs.append("document_text or html")
        steps.append({"step_key": "document_intelligence", "module_name": "document_intelligence", "title": "Extract & Classify Document Content", "depends_on": []})
        steps.append({"step_key": "knowledge_graph", "module_name": "knowledge_graph", "title": "Extract Entities & Relationships", "depends_on": ["document_intelligence"]})
    elif intent == WorkflowIntent.DATA_ANALYSIS:
        if not has_dataset:
            missing_inputs.append("csv_content or json_content")
        steps.append({"step_key": "data_intelligence", "module_name": "data_intelligence", "title": "Profile Dataset & Generate Chart Data", "depends_on": []})
    elif intent == WorkflowIntent.KNOWLEDGE_GRAPH:
        steps.append({"step_key": "knowledge_graph", "module_name": "knowledge_graph", "title": "Extract & Query Knowledge Graph", "depends_on": []})
    elif intent == WorkflowIntent.URL_VERIFICATION:
        if not urls:
            missing_inputs.append("url or urls")
        steps.append({"step_key": "guardian_url", "module_name": "guardian_url", "title": "Verify URL Security & SSRF Rules", "depends_on": []})
    elif intent == WorkflowIntent.FILE_ANALYSIS:
        if not has_file:
            missing_inputs.append("filename with file_bytes_b64 or file_text")
        steps.append({"step_key": "guardian_file", "module_name": "guardian_file", "title": "Static File Security Inspection", "depends_on": []})
    else:
        # MULTI_MODULE_WORKFLOW: compose available steps cleanly with parallel wave 0 where independent
        if urls:
            steps.append({"step_key": "guardian_url", "module_name": "guardian_url", "title": "Verify Submitted URLs", "depends_on": []})
        if has_file:
            steps.append({"step_key": "guardian_file", "module_name": "guardian_file", "title": "Static File Security Inspection", "depends_on": []})
        if has_doc:
            steps.append({"step_key": "document_intelligence", "module_name": "document_intelligence", "title": "Extract Document Structure", "depends_on": []})
        if has_dataset:
            steps.append({"step_key": "data_intelligence", "module_name": "data_intelligence", "title": "Profile & Analyze Dataset", "depends_on": []})
        steps.append({"step_key": "search", "module_name": "search", "title": "Search Indexed Knowledge", "depends_on": []})

        kg_deps = [s["step_key"] for s in steps if s["module_name"] in ("document_intelligence", "search")]
        if any(k in q_low for k in ("research", "investigate", "report")):
            steps.append({"step_key": "research_agent", "module_name": "research_agent", "title": "Run Bounded Research Investigation", "depends_on": ["search"]})
            kg_deps = ["research_agent"]
        steps.append({"step_key": "knowledge_graph", "module_name": "knowledge_graph", "title": "Extract Knowledge Graph Context", "depends_on": kg_deps})

    # Respect module allowlist if provided
    if allowed_modules is not None:
        allow_set = {m.strip().lower() for m in allowed_modules if m.strip()}
        steps = [s for s in steps if s["module_name"] in allow_set]
        valid_keys = {s["step_key"] for s in steps}
        for s in steps:
            s["depends_on"] = [d for d in s["depends_on"] if d in valid_keys]

    selected_modules = []
    for s in steps:
        if s["module_name"] not in selected_modules:
            selected_modules.append(s["module_name"])

    return {
        "intent": intent,
        "selected_modules": selected_modules,
        "steps": steps,
        "missing_inputs": missing_inputs,
        "extracted_urls": urls,
        "ready": len(missing_inputs) == 0 and len(steps) > 0,
    }
