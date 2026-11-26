"""Objective evaluation metrics for Search, AI Citations, Knowledge Graph, Data, and Latency."""

from __future__ import annotations

import math
import re
import statistics
import sys
from typing import Any

_CITE_RE = re.compile(r"\[([A-Za-z]?\d+)\]")


def get_process_memory_mb() -> float | None:
    """Measure current process RSS memory in MB using OS APIs; return None if unavailable."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            hproc = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(hproc, ctypes.byref(counters), counters.cb):
                return round(counters.WorkingSetSize / (1024 * 1024), 2)
        except Exception:
            return None
    return None


def precision_at_k(retrieved: list[str], relevant_grades: dict[str, float], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    hits = sum(1 for doc_id in top if relevant_grades.get(doc_id, 0.0) > 0)
    return round(hits / len(top), 4)


def recall_at_k(retrieved: list[str], relevant_grades: dict[str, float], k: int) -> float:
    pos = {doc_id for doc_id, g in relevant_grades.items() if g > 0}
    if not pos:
        return 0.0
    hits = sum(1 for doc_id in retrieved[:k] if doc_id in pos)
    return round(hits / len(pos), 4)


def f1_score(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round((2 * precision * recall) / (precision + recall), 4)


def reciprocal_rank(retrieved: list[str], relevant_grades: dict[str, float]) -> float:
    for idx, doc_id in enumerate(retrieved, start=1):
        if relevant_grades.get(doc_id, 0.0) > 0:
            return round(1.0 / idx, 4)
    return 0.0


def average_precision(retrieved: list[str], relevant_grades: dict[str, float]) -> float:
    pos = {doc_id for doc_id, g in relevant_grades.items() if g > 0}
    if not pos:
        return 0.0
    hits = 0
    sum_prec = 0.0
    for idx, doc_id in enumerate(retrieved, start=1):
        if doc_id in pos:
            hits += 1
            sum_prec += hits / idx
    return round(sum_prec / len(pos), 4)


def ndcg_at_k(retrieved: list[str], relevant_grades: dict[str, float], k: int) -> float:
    """Normalized Discounted Cumulative Gain supporting graded relevance."""
    if k <= 0:
        return 0.0
    dcg = 0.0
    for idx, doc_id in enumerate(retrieved[:k], start=1):
        rel = max(0.0, float(relevant_grades.get(doc_id, 0.0)))
        if rel > 0:
            dcg += (2 ** rel - 1.0) / math.log2(idx + 1)

    ideal_rels = sorted((max(0.0, float(g)) for g in relevant_grades.values() if g > 0), reverse=True)[:k]
    idcg = sum((2 ** rel - 1.0) / math.log2(idx + 1) for idx, rel in enumerate(ideal_rels, start=1))
    if idcg == 0.0:
        return 0.0
    return round(dcg / idcg, 4)


def evaluate_citations(answer_text: str, valid_keys: set[str]) -> dict[str, Any]:
    """Check inline citations [1], [S1], [W1] against valid retrieved source keys."""
    found = _CITE_RE.findall(answer_text or "")
    unique_found = list(dict.fromkeys(found))
    if not unique_found:
        return {
            "citations_found": 0,
            "citation_validity_rate": 0.0 if valid_keys else 1.0,
            "citation_coverage": 0.0,
            "hallucinated_citations": [],
        }
    valid_hits = [c for c in unique_found if c in valid_keys]
    bad_hits = [c for c in unique_found if c not in valid_keys]
    validity = round(len(valid_hits) / len(unique_found), 4)
    coverage = round(len(valid_hits) / len(valid_keys), 4) if valid_keys else 0.0
    return {
        "citations_found": len(unique_found),
        "citation_validity_rate": validity,
        "citation_coverage": coverage,
        "hallucinated_citations": bad_hits,
    }


def set_prf1(predicted: set[str], expected: set[str]) -> dict[str, float]:
    """Compute Precision, Recall, F1 over normalized string sets (e.g. KG entities/relationships)."""
    if not predicted and not expected:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not predicted or not expected:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = len(predicted & expected)
    p = round(tp / len(predicted), 4)
    r = round(tp / len(expected), 4)
    return {"precision": p, "recall": r, "f1": f1_score(p, r)}


def numeric_within_tolerance(actual: float, expected: float, rel_tol: float = 0.02) -> bool:
    if expected == 0:
        return abs(actual) <= rel_tol
    return abs(actual - expected) <= abs(expected) * rel_tol


def latency_stats(durations_ms: list[float]) -> dict[str, Any]:
    if not durations_ms:
        return {"avg_ms": 0.0, "median_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "throughput_qps": 0.0}
    ordered = sorted(durations_ms)
    n = len(ordered)
    avg = round(statistics.fmean(ordered), 2)
    med = round(statistics.median(ordered), 2)
    p95 = round(ordered[min(n - 1, int(math.ceil(0.95 * n)) - 1)], 2)
    p99 = round(ordered[min(n - 1, int(math.ceil(0.99 * n)) - 1)], 2)
    total_sec = sum(ordered) / 1000.0
    qps = round(n / total_sec, 2) if total_sec > 0 else 0.0
    return {
        "avg_ms": avg,
        "median_ms": med,
        "p95_ms": p95,
        "p99_ms": p99,
        "throughput_qps": qps,
    }


def _normalize_tokens(text: str) -> tuple[str, list[str]]:
    cleaned = _CITE_RE.sub(" ", text or "")
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, cleaned.split() if cleaned else []


def evaluate_reference_answer(predicted: str, reference: str | None) -> dict[str, Any] | None:
    """Compute normalized exact match and multiset token P/R/F1 against a reference answer."""
    if reference is None or not str(reference).strip():
        return None
    norm_pred, pred_toks = _normalize_tokens(predicted)
    norm_ref, ref_toks = _normalize_tokens(str(reference))
    if not pred_toks or not ref_toks:
        return {
            "exact_match": 1.0 if (norm_pred == norm_ref and norm_ref != "") else 0.0,
            "token_precision": 0.0,
            "token_recall": 0.0,
            "token_f1": 0.0,
        }
    from collections import Counter

    pc = Counter(pred_toks)
    rc = Counter(ref_toks)
    overlap = sum((pc & rc).values())
    p = round(overlap / len(pred_toks), 4)
    r = round(overlap / len(ref_toks), 4)
    return {
        "exact_match": 1.0 if norm_pred == norm_ref else 0.0,
        "token_precision": p,
        "token_recall": r,
        "token_f1": f1_score(p, r),
    }


def evaluate_relationships(
    predicted_rels: list[Any],
    expected_rels: list[dict[str, Any]] | None,
    source_text: str = "",
) -> dict[str, Any]:
    """Evaluate extracted KG relationships using exact & normalized matching plus snippet evidence."""
    from app.graph.normalizer import normalize_entity_name

    # Evidence attribution check: does snippet appear in source_text?
    src_lower = (source_text or "").lower()
    if predicted_rels:
        ev_hits = sum(
            1 for r in predicted_rels
            if getattr(r, "snippet", "") and getattr(r, "snippet", "").strip().lower() in src_lower
        )
        evidence_rate: float | None = round(ev_hits / len(predicted_rels), 4)
    else:
        evidence_rate = None

    if expected_rels is None:
        return {"exact": None, "normalized": None, "evidence_attribution_rate": evidence_rate}

    pred_exact = {
        f"{getattr(r, 'source_name', '').strip()}|{getattr(r, 'relationship_type', '').strip().upper()}|{getattr(r, 'target_name', '').strip()}"
        for r in predicted_rels
    }
    exp_exact = {
        f"{str(e.get('source', '')).strip()}|{str(e.get('type', '')).strip().upper()}|{str(e.get('target', '')).strip()}"
        for e in expected_rels
        if isinstance(e, dict)
    }

    pred_norm = {
        f"{normalize_entity_name(getattr(r, 'source_name', ''))}|{getattr(r, 'relationship_type', '').strip().upper()}|{normalize_entity_name(getattr(r, 'target_name', ''))}"
        for r in predicted_rels
    }
    exp_norm = {
        f"{normalize_entity_name(str(e.get('source', '')))}|{str(e.get('type', '')).strip().upper()}|{normalize_entity_name(str(e.get('target', '')))}"
        for e in expected_rels
        if isinstance(e, dict)
    }

    return {
        "exact": set_prf1(pred_exact, exp_exact),
        "normalized": set_prf1(pred_norm, exp_norm),
        "evidence_attribution_rate": evidence_rate,
    }


def evaluate_dataset_profile(
    actual: dict[str, Any],
    expected: dict[str, Any],
    rel_tol: float = 0.01,
) -> dict[str, Any]:
    """Compare profile_dataset_file output against expected schema, missingness, and numeric stats."""
    checks_total = 0
    checks_passed = 0
    details: dict[str, bool] = {}

    def _record(name: str, ok: bool) -> None:
        nonlocal checks_total, checks_passed
        checks_total += 1
        if ok:
            checks_passed += 1
        details[name] = ok

    if "row_count" in expected:
        _record("row_count", actual.get("row_count") == expected["row_count"])
    if "column_count" in expected:
        _record("column_count", actual.get("column_count") == expected["column_count"])

    cols_by_name = {c.get("name"): c for c in (actual.get("columns") or []) if isinstance(c, dict)}
    if "column_names" in expected:
        actual_names = [c.get("name") for c in (actual.get("columns") or []) if isinstance(c, dict)]
        _record("column_names", actual_names == list(expected["column_names"]))

    if "column_types" in expected and isinstance(expected["column_types"], dict):
        for col_name, exp_type in expected["column_types"].items():
            col = cols_by_name.get(col_name)
            _record(f"type:{col_name}", bool(col and col.get("inferred_type") == exp_type))

    profile_meta = actual.get("profile") or {}
    if "total_missing_cells" in expected:
        _record("total_missing_cells", profile_meta.get("total_missing_cells") == expected["total_missing_cells"])
    if "duplicate_rows" in expected:
        _record("duplicate_rows", profile_meta.get("duplicate_rows") == expected["duplicate_rows"])

    if "missing_values" in expected and isinstance(expected["missing_values"], dict):
        for col_name, exp_miss in expected["missing_values"].items():
            col = cols_by_name.get(col_name)
            _record(f"missing:{col_name}", bool(col and col.get("missing_count") == exp_miss))

    if "numeric_stats" in expected and isinstance(expected["numeric_stats"], dict):
        for col_name, stat_map in expected["numeric_stats"].items():
            col = cols_by_name.get(col_name) or {}
            stats = col.get("numeric_stats") or {}
            for stat_k, exp_v in (stat_map or {}).items():
                act_v = stats.get(stat_k)
                ok = act_v is not None and numeric_within_tolerance(float(act_v), float(exp_v), rel_tol=rel_tol)
                _record(f"stat:{col_name}.{stat_k}", ok)

    if "categorical_stats" in expected and isinstance(expected["categorical_stats"], dict):
        for col_name, exp_top in expected["categorical_stats"].items():
            col = cols_by_name.get(col_name) or {}
            top_cats = col.get("top_categories") or []
            top_val = top_cats[0].get("value") if top_cats else None
            _record(f"cat:{col_name}", top_val == exp_top)

    if "quality_indicators" in expected and isinstance(expected["quality_indicators"], list):
        obs_text = " ".join(str(o) for o in (profile_meta.get("quality_observations") or [])).lower()
        for idx, ind in enumerate(expected["quality_indicators"]):
            _record(f"quality:{idx}", str(ind).lower() in obs_text)

    return {
        "passed": checks_total > 0 and checks_passed == checks_total,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "details": details,
    }


def evaluate_chart_output(
    actual: dict[str, Any],
    expected: dict[str, Any],
    rel_tol: float = 0.01,
) -> dict[str, Any]:
    """Validate generate_chart_data output schema, labels, values, and point counts."""
    checks_total = 0
    checks_passed = 0
    details: dict[str, bool] = {}

    def _record(name: str, ok: bool) -> None:
        nonlocal checks_total, checks_passed
        checks_total += 1
        if ok:
            checks_passed += 1
        details[name] = ok

    has_schema = (
        isinstance(actual, dict)
        and "chart_type" in actual
        and isinstance(actual.get("labels"), list)
        and isinstance(actual.get("values"), list)
        and isinstance(actual.get("points"), list)
    )
    _record("schema_valid", has_schema)

    if "chart_type" in expected:
        _record("chart_type", actual.get("chart_type") == expected["chart_type"])
    if "x_label" in expected:
        _record("x_label", actual.get("x_label") == expected["x_label"])
    if "y_label" in expected:
        _record("y_label", actual.get("y_label") == expected["y_label"])
    if "labels" in expected:
        _record("labels", actual.get("labels") == list(expected["labels"]))
    if "min_labels" in expected:
        _record("min_labels", len(actual.get("labels") or []) >= int(expected["min_labels"]))
    if "values" in expected:
        act_vals = actual.get("values") or []
        exp_vals = list(expected["values"])
        vals_ok = len(act_vals) == len(exp_vals) and all(
            numeric_within_tolerance(float(a), float(e), rel_tol=rel_tol)
            for a, e in zip(act_vals, exp_vals)
        )
        _record("values", vals_ok)
    if "points_count" in expected:
        _record("points_count", len(actual.get("points") or []) == int(expected["points_count"]))

    return {
        "passed": checks_total > 0 and checks_passed == checks_total,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "details": details,
    }


def evaluate_guardian_indicators(
    actual_texts: list[str],
    expected_indicators: list[str] | None = None,
    forbidden_indicators: list[str] | None = None,
) -> dict[str, Any]:
    """Check expected and forbidden indicator substrings against Guardian findings/errors."""
    haystack = " | ".join(str(t) for t in actual_texts if t).lower()
    matched: list[str] = []
    missing: list[str] = []
    unexpected: list[str] = []

    for ind in (expected_indicators or []):
        if str(ind).lower() in haystack:
            matched.append(str(ind))
        else:
            missing.append(str(ind))

    for forb in (forbidden_indicators or []):
        if str(forb).lower() in haystack:
            unexpected.append(str(forb))

    return {
        "passed": len(missing) == 0 and len(unexpected) == 0,
        "matched": matched,
        "missing": missing,
        "unexpected": unexpected,
    }
