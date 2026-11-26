# LUMO Reranking Engine (Phase 29)

`rerank_candidates()` ([`reranker.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/retrieval/reranker.py)) reorders up to `max_candidates=50` results using normalized base score, query term coverage, exact phrase boost, and title boost, while enforcing `timeout_seconds` and `cancel_check`.
