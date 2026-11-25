# LUMO Phase 17 — Adaptive Intelligence & Personalization Engine

LUMO's **Adaptive Intelligence & Personalization Engine** improves search relevance, knowledge discovery, and research workflows using **user-controlled, transparent, opt-in preference signals** stored locally in LUMO's database.

---

## 1. Core Principles

- **Explicit Opt-In (`enabled = False` by default)**: Personalization is disabled until the user explicitly enables it. Disabling personalization restores the exact baseline search ranking.
- **No Sensitive Trait Profiling**: `is_sensitive_topic()` rejects sensitive personal attributes (religion, political affiliation, sexual orientation, gender identity, medical/health conditions, ethnicity, race) from ever being stored as interests or learned topics.
- **Bounded Relevance Adjustment**: Personalization adjusts scores within a strict `[-0.35, +0.35] * weight` delta (`AdaptiveRanker.MAX_DELTA = 0.35`) so user preferences refine ordering without overwhelming core query relevance.
- **Explainable & Inspectable**: Every personalized result includes `personalization_delta`, `personalization_reason`, and `applied_signals` metadata; every recommendation carries a grounded `reason`.
- **Full User Control & Reset**: Users can inspect, add, edit, or delete individual interests, learned topics, source preferences, and feedback signals, or wipe all personalization data via `POST /api/v1/personalization/reset`.

---

## 2. Architecture

### Backend Modules (`backend/app/personalization/`)
- **`topics.py`**: Topic normalization (`normalize_topic`), sensitive-trait blocklist (`is_sensitive_topic`), and safe entity/topic extraction (`extract_safe_topics`) reusing LUMO's `EntityExtractor`.
- **`ranking.py`**: `AdaptiveRanker.rerank()` applies bounded score adjustments based on preferred/excluded domains, followed/excluded interests, learned topics, and direct item/source feedback.
- **`discovery.py`**: `DiscoveryEngine.get_recommendations()` generates grounded recommendations from Knowledge Graph entities, Personal Workspace items, and indexed Documents matching the user's interests/topics.
- **`service.py`**: `PersonalizationService` coordinates settings, interests, topic learning (`record_search_signal`), domain preferences, feedback propagation, search reranking (`rerank_search_results`), and full reset (`reset_all`).

### Database Models (`backend/app/models/personalization.py`)
- `personalization_settings`: Global opt-in flag (`enabled`), `personalization_weight`, `preferred_search_mode`, `use_search_history`, `use_workspace_signals`.
- `user_interests`: Explicit or workspace-derived interests (`status`: `followed` | `excluded`, `weight`).
- `topic_profiles`: Learned non-sensitive topics (`frequency`, `confidence`, `recency_score`, `signal_kind`: `curiosity` | `repeated`).
- `source_preferences`: Domain-level boost/demote preferences (`preference`: `preferred` | `excluded`, `weight`).
- `personalization_feedback`: Explicit item/source feedback (`more_like_this`, `less_like_this`, `prefer_source`, `exclude_source`).

### API Endpoints (`/api/v1/personalization/*`)
- `GET /status` — Current opt-in status, weight, and signal counts.
- `GET /profile` — Full transparent profile (settings, interests, topics, source preferences, recent feedback).
- `PUT /settings` — Update opt-in toggle, personalization weight, and signal toggles.
- `POST /interests` / `DELETE /interests/{id}` — Follow/exclude topics or remove interests (rejects sensitive traits with HTTP `400`).
- `GET /topics` / `DELETE /topics/{id}` — Inspect or delete learned topics.
- `POST /sources` / `DELETE /sources/{id}` — Prefer or exclude domains.
- `POST /feedback` / `DELETE /feedback/{id}` — Submit or undo explicit relevance feedback.
- `GET /recommendations` — Fetch grounded Knowledge Graph / Workspace / Document recommendations.
- `GET /activity` — Inspect learned topics and recent feedback signals.
- `POST /reset` — Delete all interests, learned topics, source preferences, and feedback, and disable personalization.

### Frontend (`lumo-frontend/`)
- `personalization.html` & `js/personalization.js`: Adaptive Intelligence & Personalization Dashboard integrated into `ADVANCED_MODULES` in `js/ui-shell.js` and `js/api.js`.

---

## 3. Search Integration

`GET /api/v1/search` checks `PersonalizationService(db)`:
1. When `privacy_active` is `False` and personalization + `use_search_history` are enabled, non-sensitive topics are recorded via `record_search_signal()`.
2. When `enabled=True`, `rerank_search_results()` applies `AdaptiveRanker` to the retrieved candidate list and attaches `execution_metadata.personalized = True`.
3. When `enabled=False`, search results are returned unmodified with `execution_metadata.personalized = False`.

---

## 4. Testing

Run the deterministic Phase 17 test suite (no external paid API calls):

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_personalization.py -v
```

Coverage includes:
- Opt-in disabled default (`enabled=False`)
- Sensitive trait rejection (`400`) on interest creation
- `POST /reset` clearing profile data and resetting opt-in state
- `AdaptiveRanker` delta bounds (`<= 0.35 * weight`) and baseline preservation when disabled
- `GET /api/v1/search` integration, topic recording, grounded `DiscoveryEngine` recommendations, and feedback deletion
