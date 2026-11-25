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
