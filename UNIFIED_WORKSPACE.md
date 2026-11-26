# LUMO Unified Intelligence Workspace (Phase 27)

## Overview
The Unified Intelligence Workspace ([`workspace-hub.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/workspace-hub.html) + [`workspace-hub.js`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/js/workspace-hub.js)) connects Search, AI Search, Research Agent, Document Intelligence, Universal Data Intelligence, Knowledge Graph, and Download Guardian into a single user-controlled workflow.

## User Control Model
1. **Plan First**: Submitting a request calls `POST /api/v1/workflows`, classifying intent and displaying the planned modules and dependency steps without silently launching expensive operations.
2. **Explicit Execution**: Clicking **Execute Workflow** triggers `POST /api/v1/workflows/{id}/execute`.
3. **Control & Recovery**: Users can cancel (`POST .../cancel`), retry failed steps (`POST .../retry`), inspect per-section results, filter workflow history, and export Markdown or JSON reports.
