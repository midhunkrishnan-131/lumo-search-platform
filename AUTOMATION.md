# LUMO Intelligence Automation Engine (Phase 16)

The Intelligence Automation Engine (`lumo-frontend/automation.html`, `/api/v1/automations/*`) enables recurring, event-driven, and manual intelligence workflows built on top of LUMO's existing Search, AI Router, Knowledge Graph, and Personal Workspace.

---

## 1. Architecture

- **Persistent Models (`backend/app/models/automation.py`)**:
  - `automations`: Workflow definitions, triggers, validated steps, quotas (`max_executions_per_day`, `timeout_seconds`, `max_retries`), and `next_run_at`.
  - `automation_executions`: Per-run status (`pending`, `queued`, `running`, `completed`, `failed`, `cancelled`), `context_data` (including Research Monitor `seen_urls`), and `workspace_item_id`.
  - `automation_execution_steps`: Step-by-step execution logs with duration and error info.
  - `automation_notifications`: Internal notifications for completed runs, failures, and newly detected information.
- **Execution Engine (`backend/app/automation/engine.py`)**:
  - Bounded `ThreadPoolExecutor(max_workers=2)` for local Windows hardware.
  - Background scheduler checks due `scheduled` automations every 30 seconds.
  - Startup recovery (`recover_interrupted_executions`) marks any orphaned `running`/`queued` runs from a prior crash as `failed`.

---

## 2. Triggers & Conditions

- **Manual**: Triggered via UI or `POST /api/v1/automations/{id}/run`.
- **Scheduled**: `hourly`, `daily`, `weekly`, `monthly`, or `custom` (`interval_minutes`).
- **Event-Based**: `document_indexed`, `workspace_saved`, `research_completed`, `collection_updated`, `page_crawled`, `entity_detected`.
- **Declarative Conditions (`backend/app/automation/conditions.py`)**:
  - `results_exist`, `min_count`, `keyword_present`, `new_info_detected`, `topic_relevant` (no `eval()` or arbitrary code execution).

---

## 3. Built-In Templates

1. **Research Monitor**: Hybrid search $\rightarrow$ `new_info_detected` condition $\rightarrow$ Report $\rightarrow$ Save to Workspace $\rightarrow$ Notification.
2. **Daily Knowledge Brief**: Recent documents & workspace items $\rightarrow$ Summarize $\rightarrow$ Save to Workspace.
3. **Document Intelligence**: `document_indexed` event $\rightarrow$ Entity extraction $\rightarrow$ Summarize $\rightarrow$ Assign tags $\rightarrow$ Save.
4. **Research Collection Builder**: Topic search $\rightarrow$ Summarize $\rightarrow$ Save to Collection.
5. **Knowledge Update Monitor**: Scheduled search $\rightarrow$ Compare with previous run $\rightarrow$ Update report.
6. **Learning Assistant**: Search topic/docs $\rightarrow$ Study notes, FAQs & Quiz $\rightarrow$ Save to Workspace.

---

## 4. Security & Resource Controls

- Strict Pydantic `Literal` validation on all step types (`StepType`) and trigger types (`TriggerType`).
- Zero arbitrary Python/shell execution inside workflows.
- Daily execution quotas (`max_executions_per_day`), overlapping run prevention, timeouts, and cooperative cancellation.

---

## 5. Testing

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_automation.py -v
```
