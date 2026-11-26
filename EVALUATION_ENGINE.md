# LUMO Phase 25 — Intelligence Testing, Benchmarking & Evaluation Engine

## 1. Architecture
- **Datasets (`evaluation_datasets`)**: Versioned `JSON`, `JSONL`, and `CSV` test suites (capped at `200` cases and `5 MB` per upload; validated safely without executing dataset contents).
- **Benchmark Registry (`evaluation_benchmarks`)**: Configures target modules, supporting create, edit, clone, run, cancel, and delete:
  - `classic_search`, `semantic_search`, `hybrid_search`, `search_comparison`
  - `ai_search` (citation validity/coverage, deterministic reference-answer token F1/exact match, optional LLM judge)
  - `research_agent` (bounded research session completion, source discovery/diversity, citation validity/coverage, report completeness)
  - `knowledge_graph` (entity & exact/normalized relationship P/R/F1, evidence attribution rate)
  - `document_intelligence` (extraction & deterministic classification accuracy)
  - `data_intelligence` (`profile_dataset_file`, `generate_chart_data`, numeric tolerance, missingness)
  - `guardian` (`validate_guardian_url` SSRF/scheme rules + `FileSecurityAnalyzer` static inspection)
- **Metrics Engine ([`metrics.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/evaluation/metrics.py))**:
  - **IR Metrics**: `Precision@K`, `Recall@K`, `F1`, `MRR`, `MAP`, and graded `NDCG@K`.
  - **AI & Citation Metrics**: `citation_validity_rate`, `citation_coverage`, `hallucinated_citations`, `evaluate_reference_answer` (normalized exact match, token precision/recall/F1), and optional LLM judge scores (marked `is_estimate: true`).
  - **Graph, Data & Guardian Metrics**: `set_prf1`, `evaluate_relationships`, `evaluate_dataset_profile`, `evaluate_chart_output`, `evaluate_guardian_indicators`, and `numeric_within_tolerance`.
  - **Performance**: `avg_ms`, `median_ms`, `p95_ms`, `p99_ms`, `throughput_qps`, and OS-measured `memory_rss_mb` (returns `null` if unavailable, never fabricated).
- **Regression Engine (`compare_runs`)**: Compares baseline vs current runs and flags metric drops (`> regression_threshold`) or latency increases (`> latency_threshold_pct`).
- **Human Reviews (`evaluation_reviews`)**: Stores reviewer scores (1–5), status, and notes per run/case.

---

## 2. Benchmark & Dataset Workflow
1. **Import or Create a Dataset**: Upload `.json`, `.jsonl`, or `.csv` via `POST /api/v1/evaluation-datasets/import` or submit JSON cases via `POST /api/v1/evaluation-datasets`.
2. **Register a Benchmark**: `POST /api/v1/evaluations` with `target_module` and `dataset_id` (update via `PUT /api/v1/evaluations/{id}`, duplicate via `POST /api/v1/evaluations/{id}/clone`).
3. **Execute & Monitor**: `POST /api/v1/evaluations/{id}/run` (optionally passing `provider`, `model_name`, `k`, `use_llm_judge`, `judge_provider`, `judge_model`). Poll `GET /api/v1/evaluations/runs/{run_id}` or cancel active runs via `POST /api/v1/evaluations/runs/{run_id}/cancel` (persists partial results).
4. **Review, Compare & Export**: Add human reviews (`POST /api/v1/evaluations/runs/{run_id}/reviews`), run regression checks (`GET /api/v1/evaluations/compare`), and export CSV/JSON reports (`GET /api/v1/evaluations/runs/{run_id}/export?format=csv|json`).

---

## 3. Dashboard & APIs
- **UI**: [`evaluations.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/evaluations.html) + [`evaluations.js`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/js/evaluations.js)
- **APIs** ([`evaluation.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/api/routes/evaluation.py)):
  - `/api/v1/evaluation-datasets` (`GET`, `POST`, `POST /import`, `GET /{id}`, `DELETE /{id}`)
  - `/api/v1/evaluations` (`GET`, `POST`, `GET /{id}`, `PUT /{id}`, `POST /{id}/clone`, `DELETE /{id}`, `POST /{id}/run`)
  - `/api/v1/evaluations/runs` (`GET`, `GET /{id}`, `GET /{id}/results`, `GET /{id}/export?format=csv|json`, `POST /{id}/cancel`, `POST /{id}/reviews`, `GET /{id}/reviews`)
  - `/api/v1/evaluations/compare`

---

## 4. Provider Configuration & Troubleshooting
- Provider/model selection uses LUMO's configured `AIProviderRouter` (`auto` or a specific configured provider not blocked by local-only privacy mode).
- If an external provider key is not configured or local-only mode is active, `ai_search` / `research_agent` / `llm_judge` gracefully fall back or record an unavailable status without crashing.
- **Troubleshooting**:
  - `400 Unsupported dataset format`: Ensure the file ends in `.json`, `.jsonl`, or `.csv`, is non-empty, <= 5 MB, and <= 200 cases.
  - `400 Unsupported evaluation target_module`: Verify `target_module` matches one of the 10 supported targets listed above.

---

## 5. Limitations
- Token-overlap metrics (`token_f1`, `exact_match`) measure lexical overlap, not semantic equivalence.
- Automated citation checking verifies citation key validity against retrieved sources; semantic claim-entailment requires optional human review or a configured LLM judge (which is probabilistic and marked `is_estimate: true`).
- Real cloud AI evaluations consume provider quota and are never triggered automatically during `pytest`.
