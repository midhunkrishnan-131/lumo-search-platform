# LUMO Phase 25 — Intelligence Testing, Benchmarking & Evaluation Engine

## 1. Architecture
- **Datasets (`evaluation_datasets`)**: Versioned `JSON`, `JSONL`, and `CSV` test suites (capped at `200` cases / `5 MB` per upload, never executed).
- **Benchmark Registry (`evaluation_benchmarks`)**: Configures target modules (`classic_search`, `semantic_search`, `hybrid_search`, `search_comparison`, `ai_search`, `knowledge_graph`, `document_intelligence`, `data_intelligence`, `guardian`), supporting create, edit, clone, run, cancel, and delete.
- **Metrics Engine ([`metrics.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/evaluation/metrics.py))**:
  - **IR Metrics**: `Precision@K`, `Recall@K`, `F1`, `MRR`, `MAP`, and graded `NDCG@K`.
  - **Citation Metrics**: `citation_validity_rate`, `citation_coverage`, and `hallucinated_citations`.
  - **Graph & Data Metrics**: `set_prf1` (Entity Precision/Recall/F1) and `numeric_within_tolerance`.
  - **Performance**: `avg_ms`, `median_ms`, `p95_ms`, `p99_ms`, `throughput_qps`, and OS-measured `memory_rss_mb` (returns `null` if unavailable, never fabricated).
- **Regression Engine (`compare_runs`)**: Compares baseline vs current runs and flags metric drops (`> regression_threshold`) or latency increases (`> latency_threshold_pct`).
- **Human Reviews (`evaluation_reviews`)**: Stores reviewer scores (1–5) and notes per run/case.

---

## 2. Dashboard & APIs
- **UI**: [`evaluations.html`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/lumo-frontend/evaluations.html)
- **APIs**:
  - `/api/v1/evaluation-datasets` (`GET`, `POST`, `POST /import`, `GET /{id}`, `DELETE /{id}`)
  - `/api/v1/evaluations` (`GET`, `POST`, `GET /{id}`, `PUT /{id}`, `POST /{id}/clone`, `DELETE /{id}`, `POST /{id}/run`)
  - `/api/v1/evaluations/runs` (`GET`, `GET /{id}`, `GET /{id}/results`, `GET /{id}/export?format=csv|json`, `POST /{id}/cancel`, `POST /{id}/reviews`)
  - `/api/v1/evaluations/compare`

---

## 3. Limitations
- Automated citation checking verifies citation key validity against retrieved sources; semantic claim-entailment requires optional human review or a configured evaluator model (which itself is probabilistic).
- Real cloud AI evaluations consume provider quota and are never triggered automatically during `pytest`.
