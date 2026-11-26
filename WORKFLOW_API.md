# LUMO Workflow API Reference (Phase 27)

Implemented in [`workflows.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/api/routes/workflows.py).

- `POST /api/v1/workflows`: Create & plan a workflow (`WorkflowCreateRequest`). Requires `workflows:execute`.
- `GET /api/v1/workflows`: List workflows for the current `X-LUMO-Owner` (supports `intent`, `status`, `q`, `limit`). Requires `workflows:read`.
- `GET /api/v1/workflows/{id}`: Retrieve workflow plan, steps, results, sources, and disagreements. Requires `workflows:read`.
- `POST /api/v1/workflows/{id}/execute`: Execute a planned workflow (`WorkflowExecuteRequest`). Requires `workflows:execute`.
- `POST /api/v1/workflows/{id}/cancel`: Cancel a pending or running workflow. Requires `workflows:execute`.
- `POST /api/v1/workflows/{id}/retry`: Retry eligible failed/skipped steps. Requires `workflows:execute`.
- `GET /api/v1/workflows/{id}/export?format=json|markdown`: Export report without secrets. Requires `workflows:read`.
- `DELETE /api/v1/workflows/{id}`: Delete an owned workflow. Requires `workflows:execute`.
