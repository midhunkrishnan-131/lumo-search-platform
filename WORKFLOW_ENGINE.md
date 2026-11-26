# LUMO Workflow Engine & Request Router (Phase 27)

## Request Router ([`router.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/workflows/router.py))
`classify_and_plan()` deterministically maps requests and attached inputs to one of 9 intents:
`SEARCH`, `AI_SEARCH`, `RESEARCH`, `DOCUMENT_ANALYSIS`, `DATA_ANALYSIS`, `KNOWLEDGE_GRAPH`, `URL_VERIFICATION`, `FILE_ANALYSIS`, `MULTI_MODULE_WORKFLOW`.

## DAG Execution Engine ([`engine.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/workflows/engine.py))
- Executes steps in bounded topological waves (`ThreadPoolExecutor(max_workers=3)` for independent steps in the same wave).
- Tracks workflow statuses (`CREATED`, `PLANNING`, `READY`, `RUNNING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`).
- Polls `cancel_requested` between waves and marks dependent steps `SKIPPED` when upstream steps fail.
