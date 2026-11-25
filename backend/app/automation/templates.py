"""Reusable workflow templates for LUMO Phase 16 Intelligence Automation Engine."""

from __future__ import annotations

from app.schemas.automation import AutomationTemplateResponse, WorkflowStepSchema

AUTOMATION_TEMPLATES: list[AutomationTemplateResponse] = [
    AutomationTemplateResponse(
        id="research_monitor",
        name="Research Monitor",
        description="Monitor a topic, retrieve new sources, compare against previous runs, and save a grounded update report.",
        workflow_type="research_monitor",
        trigger_type="scheduled",
        trigger_config={"interval": "daily", "topic": "Hybrid Search & RAG", "max_sources": 6},
        steps=[
            WorkflowStepSchema(id="step-search", type="hybrid_search", config={"query": "Hybrid Search", "limit": 6}),
            WorkflowStepSchema(id="step-cond", type="condition", config={"condition_type": "new_info_detected"}),
            WorkflowStepSchema(id="step-report", type="report_generate", config={"title_prefix": "Research Monitor Update"}),
            WorkflowStepSchema(id="step-save", type="workspace_save", config={"source_type": "research_report", "tags": ["monitor"]}),
            WorkflowStepSchema(id="step-notify", type="notification", config={"event_type": "new_info_detected"}),
        ],
    ),
    AutomationTemplateResponse(
        id="daily_brief",
        name="Daily Knowledge Brief",
        description="Retrieve recent indexed documents and saved workspace research, summarize key points, and save a daily brief.",
        workflow_type="daily_brief",
        trigger_type="scheduled",
        trigger_config={"interval": "daily"},
        steps=[
            WorkflowStepSchema(id="step-search", type="search", config={"query": "", "limit": 6, "include_workspace": True}),
            WorkflowStepSchema(id="step-summarize", type="ai_summarize", config={"instruction": "Create a concise daily knowledge brief from the retrieved items."}),
            WorkflowStepSchema(id="step-save", type="workspace_save", config={"source_type": "research_report", "tags": ["daily-brief"]}),
            WorkflowStepSchema(id="step-notify", type="notification", config={"event_type": "completed"}),
        ],
    ),
    AutomationTemplateResponse(
        id="document_intelligence",
        name="Document Intelligence",
        description="Automatically analyze newly indexed documents, summarize content, extract topics, and assign tags.",
        workflow_type="document_intelligence",
        trigger_type="event",
        trigger_config={"event_name": "document_indexed"},
        steps=[
            WorkflowStepSchema(id="step-analyze", type="document_analysis", config={}),
            WorkflowStepSchema(id="step-summarize", type="ai_summarize", config={"instruction": "Summarize key points and extracted entities."}),
            WorkflowStepSchema(id="step-tags", type="tag_assign", config={"tags": ["auto-analyzed"]}),
            WorkflowStepSchema(id="step-save", type="workspace_save", config={"source_type": "document_import", "tags": ["doc-intelligence"]}),
        ],
    ),
    AutomationTemplateResponse(
        id="collection_builder",
        name="Research Collection Builder",
        description="Search a selected topic, analyze retrieved sources, summarize findings, and save to a target collection.",
        workflow_type="collection_builder",
        trigger_type="manual",
        trigger_config={"topic": "Knowledge Graphs"},
        steps=[
            WorkflowStepSchema(id="step-search", type="hybrid_search", config={"query": "Knowledge Graphs", "limit": 8}),
            WorkflowStepSchema(id="step-cond", type="condition", config={"condition_type": "results_exist"}),
            WorkflowStepSchema(id="step-summarize", type="ai_summarize", config={"instruction": "Synthesize a structured collection overview."}),
            WorkflowStepSchema(id="step-save", type="workspace_save", config={"source_type": "research_report", "tags": ["collection-builder"]}),
        ],
    ),
    AutomationTemplateResponse(
        id="knowledge_update",
        name="Knowledge Update Monitor",
        description="Check for new information on a topic, compare with existing workspace knowledge, and report changes.",
        workflow_type="knowledge_update",
        trigger_type="scheduled",
        trigger_config={"interval": "weekly", "topic": "AI Security"},
        steps=[
            WorkflowStepSchema(id="step-search", type="hybrid_search", config={"query": "AI Security", "limit": 6}),
            WorkflowStepSchema(id="step-cond", type="condition", config={"condition_type": "new_info_detected"}),
            WorkflowStepSchema(id="step-report", type="report_generate", config={"title_prefix": "Knowledge Update"}),
            WorkflowStepSchema(id="step-save", type="workspace_save", config={"source_type": "research_report", "tags": ["knowledge-update"]}),
        ],
    ),
    AutomationTemplateResponse(
        id="learning_assistant",
        name="Learning Assistant",
        description="Generate structured study notes, FAQs, and a quick quiz from selected workspace documents or a topic.",
        workflow_type="learning_assistant",
        trigger_type="manual",
        trigger_config={"topic": "Python"},
        steps=[
            WorkflowStepSchema(id="step-search", type="search", config={"query": "Python", "limit": 5, "include_workspace": True}),
            WorkflowStepSchema(id="step-study", type="ai_summarize", config={"instruction": "Generate structured study notes, 3 FAQs, and a 3-question quiz with answers."}),
            WorkflowStepSchema(id="step-save", type="workspace_save", config={"source_type": "note", "tags": ["study-notes"]}),
        ],
    ),
]
