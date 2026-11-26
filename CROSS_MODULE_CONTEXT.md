# LUMO Cross-Module Context (Phase 27)

`CrossModuleContext` ([`context.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/workflows/context.py)) passes bounded outputs between workflow steps:
- Enforces `MAX_CONTEXT_CHARS = 8000` across combined module outputs.
- Sanitizes all external document, dataset, and search snippets via `PromptSanitizer._sanitize_for_prompt()` so untrusted content cannot override system instructions.
- Allows downstream steps (such as `knowledge_graph`) to consume upstream text from `search`, `research_agent`, `document_intelligence`, and `data_intelligence`.
