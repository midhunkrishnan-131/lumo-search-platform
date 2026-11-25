"""Streaming Spreadsheet & Structured Dataset Intelligence, Deterministic Data Analyst, and Chart Data Builder."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
from typing import Any, Iterator

from openpyxl import load_workbook

from app.core.logging import get_logger

logger = get_logger("intelligence.spreadsheet")

MAX_PROFILE_ROWS = 50_000
MAX_UNIQUE_TRACK = 10_000
MAX_DUPLICATE_HASH_TRACK = 50_000

_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$")


def _is_missing(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip().lower() in ("", "na", "n/a", "null", "none", "nan"):
        return True
    return False


def _try_float(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(val, str):
        s = val.strip().replace(",", "")
        if s.startswith("$"):
            s = s[1:]
        if not s:
            return None
        try:
            f = float(s)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except ValueError:
            return None
    return None


def _try_date(val: Any) -> str | None:
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, str):
        s = val.strip()
        if _DATE_RE.match(s):
            return s[:10]
    return None


def _iter_csv_rows(path: Path) -> tuple[list[str], Iterator[list[Any]]]:
    f = path.open("r", encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.reader(f)
    try:
        headers = next(reader)
    except StopIteration:
        f.close()
        return [], iter(())
    headers = [str(h).strip() or f"column_{i + 1}" for i, h in enumerate(headers)]

    def gen() -> Iterator[list[Any]]:
        try:
            for row in reader:
                yield row
        finally:
            f.close()

    return headers, gen()


def _iter_xlsx_rows(path: Path, sheet_name: str | None = None) -> tuple[list[str], list[str], str, Iterator[list[Any]]]:
    wb = load_workbook(filename=path, read_only=True, data_only=True)
    sheet_names = list(wb.sheetnames)
    active = sheet_name if (sheet_name and sheet_name in sheet_names) else (sheet_names[0] if sheet_names else "Sheet1")
    if not sheet_names:
        wb.close()
        return [], [], active, iter(())

    ws = wb[active]
    row_iter = ws.iter_rows(values_only=True)
    headers: list[str] = []
    for first_row in row_iter:
        if any(cell is not None for cell in first_row):
            headers = [str(c).strip() if c is not None else f"column_{i + 1}" for i, c in enumerate(first_row)]
            break

    if not headers:
        wb.close()
        return [], sheet_names, active, iter(())

    def gen() -> Iterator[list[Any]]:
        try:
            for row in row_iter:
                yield list(row)
        finally:
            wb.close()

    return headers, sheet_names, active, gen()


def _iter_json_rows(path: Path, file_type: str) -> tuple[list[str], Iterator[list[Any]]]:
    records: list[dict[str, Any]] = []
    if file_type == "jsonl":
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx >= MAX_PROFILE_ROWS:
                    break
                s = line.strip()
                if not s:
                    continue
                obj = json.loads(s)
                if isinstance(obj, dict):
                    records.append(obj)
                else:
                    records.append({"value": obj})
    else:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(raw, list):
            for item in raw[:MAX_PROFILE_ROWS]:
                records.append(item if isinstance(item, dict) else {"value": item})
        elif isinstance(raw, dict):
            # Support wrapper dicts like {"data": [...]} or single dict
            list_vals = [v for v in raw.values() if isinstance(v, list)]
            if list_vals and isinstance(list_vals[0], list):
                for item in list_vals[0][:MAX_PROFILE_ROWS]:
                    records.append(item if isinstance(item, dict) else {"value": item})
            else:
                records.append(raw)

    if not records:
        return [], iter(())

    headers: list[str] = []
    seen_h: set[str] = set()
    for rec in records[:200]:
        for k in rec.keys():
            ks = str(k)
            if ks not in seen_h:
                seen_h.add(ks)
                headers.append(ks)

    def gen() -> Iterator[list[Any]]:
        for rec in records:
            yield [rec.get(h) for h in headers]

    return headers, gen()


def stream_dataset_rows(
    path: Path, file_type: str, sheet_name: str | None = None
) -> tuple[list[str], list[str], str | None, Iterator[list[Any]]]:
    """Open a streaming iterator over CSV, XLSX, JSON, or JSONL rows."""
    ft = file_type.lower()
    if ft == "csv":
        headers, it = _iter_csv_rows(path)
        return headers, ["Sheet1"], None, it
    if ft == "xlsx":
        headers, sheets, active, it = _iter_xlsx_rows(path, sheet_name=sheet_name)
        return headers, sheets, active, it
    if ft in ("json", "jsonl"):
        headers, it = _iter_json_rows(path, ft)
        return headers, ["records"], None, it
    raise ValueError(f"Unsupported dataset format: {file_type}")


def profile_dataset_file(path: Path, file_type: str, sheet_name: str | None = None) -> dict[str, Any]:
    """Stream rows from dataset file and compute bounded schema, missing values, duplicates, and stats."""
    headers, sheet_names, active_sheet, row_iter = stream_dataset_rows(path, file_type, sheet_name=sheet_name)
    if not headers:
        return {
            "row_count": 0,
            "column_count": 0,
            "sheet_count": len(sheet_names) or 1,
            "sheet_names": sheet_names,
            "active_sheet": active_sheet,
            "columns": [],
            "profile": {
                "duplicate_rows": 0,
                "total_missing_cells": 0,
                "truncated_at_limit": False,
                "quality_observations": ["Dataset has no header columns or rows."],
            },
            "summary": "Empty dataset (0 rows, 0 columns).",
            "preview_text": "",
        }

    num_cols = len(headers)
    non_null = [0] * num_cols
    missing = [0] * num_cols
    num_vals: list[list[float]] = [[] for _ in range(num_cols)]
    date_vals: list[list[str]] = [[] for _ in range(num_cols)]
    cat_counters: list[Counter[str]] = [Counter() for _ in range(num_cols)]
    unique_sets: list[set[str]] = [set() for _ in range(num_cols)]
    samples: list[list[Any]] = [[] for _ in range(num_cols)]
    bool_counts = [0] * num_cols

    seen_row_hashes: set[str] = set()
    duplicate_rows = 0
    row_count = 0
    truncated = False
    preview_rows: list[str] = []

    for raw_row in row_iter:
        if row_count >= MAX_PROFILE_ROWS:
            truncated = True
            break
        row_count += 1
        padded = [raw_row[i] if i < len(raw_row) else None for i in range(num_cols)]

        # Duplicate detection via streaming row hash
        if len(seen_row_hashes) < MAX_DUPLICATE_HASH_TRACK:
            row_sig = hashlib.md5(
                "|".join("" if v is None else str(v).strip() for v in padded).encode("utf-8", errors="replace")
            ).hexdigest()
            if row_sig in seen_row_hashes:
                duplicate_rows += 1
            else:
                seen_row_hashes.add(row_sig)

        if len(preview_rows) < 12:
            preview_rows.append(", ".join(f"{headers[i]}={padded[i]}" for i in range(min(num_cols, 8))))

        for i, val in enumerate(padded):
            if _is_missing(val):
                missing[i] += 1
                continue
            non_null[i] += 1
            s_val = str(val).strip()
            if len(samples[i]) < 5 and s_val not in samples[i]:
                samples[i].append(s_val[:80])
            if len(unique_sets[i]) < MAX_UNIQUE_TRACK:
                unique_sets[i].add(s_val[:120])

            if isinstance(val, bool) or s_val.lower() in ("true", "false"):
                bool_counts[i] += 1
            f_val = _try_float(val)
            if f_val is not None:
                num_vals[i].append(f_val)
            d_val = _try_date(val)
            if d_val is not None:
                date_vals[i].append(d_val)
            if len(cat_counters[i]) < 2000:
                cat_counters[i][s_val[:80]] += 1

    columns_profile: list[dict[str, Any]] = []
    quality_obs: list[str] = []
    total_missing = sum(missing)

    for i, name in enumerate(headers):
        nn = non_null[i]
        miss = missing[i]
        miss_pct = round((miss / row_count) * 100, 2) if row_count > 0 else 0.0
        uniq = len(unique_sets[i])

        if nn == 0:
            inferred = "empty"
        elif bool_counts[i] == nn:
            inferred = "boolean"
        elif len(num_vals[i]) >= 0.85 * nn:
            all_ints = all(abs(x - round(x)) < 1e-9 for x in num_vals[i][:500])
            inferred = "integer" if all_ints else "numeric"
        elif len(date_vals[i]) >= 0.85 * nn:
            inferred = "date"
        elif uniq <= max(25, int(0.25 * max(nn, 1))):
            inferred = "categorical"
        else:
            inferred = "text"

        num_stats = None
        if num_vals[i] and inferred in ("numeric", "integer"):
            vals = num_vals[i]
            num_stats = {
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "mean": round(statistics.fmean(vals), 4),
                "median": round(statistics.median(vals), 4),
                "std": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
                "sum": round(sum(vals), 4),
            }

        top_cats = [
            {"value": k, "count": c}
            for k, c in cat_counters[i].most_common(8)
        ] if inferred in ("categorical", "boolean", "text") else []

        date_range = None
        if date_vals[i] and inferred == "date":
            date_range = {"min": min(date_vals[i]), "max": max(date_vals[i])}

        if miss_pct >= 20.0:
            quality_obs.append(f"Column '{name}' has {miss_pct}% missing values ({miss} rows).")

        columns_profile.append(
            {
                "name": name,
                "inferred_type": inferred,
                "non_null_count": nn,
                "missing_count": miss,
                "missing_pct": miss_pct,
                "unique_count": uniq,
                "sample_values": samples[i],
                "numeric_stats": num_stats,
                "top_categories": top_cats,
                "date_range": date_range,
            }
        )

    if duplicate_rows > 0:
        quality_obs.append(f"Detected {duplicate_rows} duplicate rows.")
    if not quality_obs:
        quality_obs.append("No major data quality issues detected in profiled rows.")
    if truncated:
        quality_obs.append(f"Profiling capped at {MAX_PROFILE_ROWS:,} rows for bounded memory usage.")

    numeric_cols = [c["name"] for c in columns_profile if c["inferred_type"] in ("numeric", "integer")]
    cat_cols = [c["name"] for c in columns_profile if c["inferred_type"] == "categorical"]
    summary = (
        f"{file_type.upper()} dataset with {row_count:,} rows and {num_cols} columns "
        f"({len(numeric_cols)} numeric, {len(cat_cols)} categorical). "
        f"Missing cells: {total_missing:,}; Duplicate rows: {duplicate_rows:,}."
    )

    return {
        "row_count": row_count,
        "column_count": num_cols,
        "sheet_count": len(sheet_names) or 1,
        "sheet_names": sheet_names,
        "active_sheet": active_sheet,
        "columns": columns_profile,
        "profile": {
            "duplicate_rows": duplicate_rows,
            "total_missing_cells": total_missing,
            "truncated_at_limit": truncated,
            "quality_observations": quality_obs,
        },
        "summary": summary,
        "preview_text": "\n".join(preview_rows),
    }


def compute_deterministic_analysis(
    path: Path | None,
    file_type: str,
    columns_json: list[dict[str, Any]],
    profile_json: dict[str, Any],
    row_count: int,
    question: str,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Perform strictly deterministic calculations on dataset values for AI Data Analyst."""
    q_lower = question.lower()
    col_map = {c["name"]: c for c in columns_json}
    mentioned_cols = [c["name"] for c in columns_json if c["name"].lower() in q_lower]

    findings: list[str] = []
    computed_metrics: dict[str, Any] = {
        "row_count": row_count,
        "column_count": len(columns_json),
        "total_missing_cells": profile_json.get("total_missing_cells", 0),
        "duplicate_rows": profile_json.get("duplicate_rows", 0),
    }

    # Missing values question
    if "missing" in q_lower or "null" in q_lower or "quality" in q_lower:
        miss_cols = [
            {"column": c["name"], "missing_count": c["missing_count"], "missing_pct": c["missing_pct"]}
            for c in columns_json
            if c.get("missing_count", 0) > 0
        ]
        computed_metrics["missing_by_column"] = miss_cols
        if miss_cols:
            findings.append(
                "Missing values found in: "
                + ", ".join(f"{m['column']} ({m['missing_count']} / {m['missing_pct']}%)" for m in miss_cols[:6])
            )
        else:
            findings.append("Zero missing values detected across all columns.")

    # Highest / category comparison
    if any(k in q_lower for k in ("highest", "top", "most", "category", "distribution", "compare")):
        cat_cols = [c for c in columns_json if c.get("top_categories")]
        target_cats = [col_map[n] for n in mentioned_cols if n in col_map and col_map[n].get("top_categories")] or cat_cols[:2]
        for cc in target_cats:
            top = cc["top_categories"][0]
            computed_metrics[f"top_{cc['name']}"] = cc["top_categories"][:5]
            findings.append(f"Top value in '{cc['name']}' is '{top['value']}' ({top['count']} rows).")

    # Numeric / trend / anomaly / outlier analysis
    num_cols = [c for c in columns_json if c.get("numeric_stats")]
    target_nums = [col_map[n] for n in mentioned_cols if n in col_map and col_map[n].get("numeric_stats")] or num_cols[:3]
    for nc in target_nums:
        st = nc["numeric_stats"]
        computed_metrics[f"stats_{nc['name']}"] = st
        findings.append(
            f"Column '{nc['name']}': min={st['min']}, max={st['max']}, mean={st['mean']}, median={st['median']}, sum={st['sum']}."
        )

    # Anomaly detection via IQR/Z-score on streaming data if requested and file exists
    if ("anomal" in q_lower or "outlier" in q_lower) and path and path.exists() and target_nums:
        col_name = target_nums[0]["name"]
        st = target_nums[0]["numeric_stats"]
        mean = st["mean"]
        std = st["std"]
        if std > 0:
            headers, _, _, row_iter = stream_dataset_rows(path, file_type, sheet_name=sheet_name)
            if col_name in headers:
                idx = headers.index(col_name)
                outliers: list[float] = []
                for r in row_iter:
                    if idx < len(r):
                        fv = _try_float(r[idx])
                        if fv is not None and abs(fv - mean) > 2.5 * std:
                            outliers.append(fv)
                            if len(outliers) >= 10:
                                break
                computed_metrics[f"outliers_{col_name}"] = outliers
                findings.append(
                    f"Detected {len(outliers)} values in '{col_name}' beyond 2.5 standard deviations from mean ({mean})."
                )

    if not findings:
        findings.extend(profile_json.get("quality_observations", []))

    return {
        "question": question,
        "mentioned_columns": mentioned_cols,
        "computed_metrics": computed_metrics,
        "deterministic_findings": findings,
    }


def suggest_charts(columns_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suggest appropriate chart configurations based on profiled column types."""
    suggestions: list[dict[str, Any]] = []
    num_cols = [c["name"] for c in columns_json if c.get("inferred_type") in ("numeric", "integer")]
    cat_cols = [c["name"] for c in columns_json if c.get("inferred_type") == "categorical"]
    date_cols = [c["name"] for c in columns_json if c.get("inferred_type") == "date"]

    if cat_cols and num_cols:
        suggestions.append(
            {
                "chart_type": "bar",
                "title": f"{num_cols[0]} by {cat_cols[0]}",
                "x_column": cat_cols[0],
                "y_column": num_cols[0],
                "reason": "Compares numeric totals across categorical groups.",
            }
        )
    if date_cols and num_cols:
        suggestions.append(
            {
                "chart_type": "line",
                "title": f"{num_cols[0]} over {date_cols[0]}",
                "x_column": date_cols[0],
                "y_column": num_cols[0],
                "reason": "Shows trend progression across dates.",
            }
        )
    if cat_cols:
        suggestions.append(
            {
                "chart_type": "pie",
                "title": f"Distribution of {cat_cols[0]}",
                "x_column": cat_cols[0],
                "y_column": None,
                "reason": "Displays category share breakdown.",
            }
        )
    if num_cols:
        suggestions.append(
            {
                "chart_type": "histogram",
                "title": f"Distribution of {num_cols[0]}",
                "x_column": num_cols[0],
                "y_column": None,
                "reason": "Shows frequency distribution of numeric values.",
            }
        )
    if len(num_cols) >= 2:
        suggestions.append(
            {
                "chart_type": "scatter",
                "title": f"{num_cols[1]} vs {num_cols[0]}",
                "x_column": num_cols[0],
                "y_column": num_cols[1],
                "reason": "Explores correlation between two numeric columns.",
            }
        )
    return suggestions


def generate_chart_data(
    path: Path,
    file_type: str,
    columns_json: list[dict[str, Any]],
    chart_type: str | None = None,
    x_column: str | None = None,
    y_column: str | None = None,
    limit: int = 20,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Generate validated chart data directly from actual dataset rows."""
    suggestions = suggest_charts(columns_json)
    if not chart_type:
        if suggestions:
            chart_type = suggestions[0]["chart_type"]
            x_column = x_column or suggestions[0]["x_column"]
            y_column = y_column or suggestions[0]["y_column"]
        else:
            chart_type = "bar"

    headers, _, _, row_iter = stream_dataset_rows(path, file_type, sheet_name=sheet_name)
    if not headers:
        raise ValueError("Dataset contains no columns to visualize.")

    if not x_column or x_column not in headers:
        x_column = headers[0]
    if y_column and y_column not in headers:
        y_column = None

    x_idx = headers.index(x_column)
    y_idx = headers.index(y_column) if y_column else None

    labels: list[str] = []
    values: list[float] = []
    points: list[dict[str, float]] = []

    if chart_type == "histogram":
        raw_nums: list[float] = []
        for idx, r in enumerate(row_iter):
            if idx >= MAX_PROFILE_ROWS:
                break
            if x_idx < len(r):
                fv = _try_float(r[x_idx])
                if fv is not None:
                    raw_nums.append(fv)
        if not raw_nums:
            raise ValueError(f"Column '{x_column}' has no numeric values for a histogram.")
        lo, hi = min(raw_nums), max(raw_nums)
        bins = min(max(limit, 5), 15)
        span = (hi - lo) or 1.0
        step = span / bins
        counts = [0] * bins
        for v in raw_nums:
            b = min(bins - 1, int((v - lo) / step))
            counts[b] += 1
        for b in range(bins):
            b_start = round(lo + b * step, 2)
            b_end = round(lo + (b + 1) * step, 2)
            labels.append(f"{b_start}-{b_end}")
            values.append(float(counts[b]))
        return {
            "chart_type": "histogram",
            "title": f"Histogram of {x_column}",
            "x_label": x_column,
            "y_label": "Frequency",
            "labels": labels,
            "values": values,
            "points": [],
            "suggestions": suggestions,
        }

    if chart_type == "scatter":
        if y_idx is None:
            num_cols = [c["name"] for c in columns_json if c.get("inferred_type") in ("numeric", "integer") and c["name"] != x_column]
            if not num_cols:
                raise ValueError("Scatter plot requires two numeric columns.")
            y_column = num_cols[0]
            y_idx = headers.index(y_column)
        for idx, r in enumerate(row_iter):
            if idx >= MAX_PROFILE_ROWS or len(points) >= max(limit * 5, 100):
                break
            if x_idx < len(r) and y_idx < len(r):
                fx = _try_float(r[x_idx])
                fy = _try_float(r[y_idx])
                if fx is not None and fy is not None:
                    points.append({"x": fx, "y": fy})
        return {
            "chart_type": "scatter",
            "title": f"{y_column} vs {x_column}",
            "x_label": x_column,
            "y_label": y_column or "Y",
            "labels": [],
            "values": [],
            "points": points,
            "suggestions": suggestions,
        }

    # Bar / Line / Pie: aggregate counts or sum of y_column grouped by x_column
    agg: dict[str, float] = {}
    for idx, r in enumerate(row_iter):
        if idx >= MAX_PROFILE_ROWS:
            break
        if x_idx >= len(r) or _is_missing(r[x_idx]):
            continue
        key = str(r[x_idx]).strip()[:60]
        if y_idx is not None and y_idx < len(r):
            fv = _try_float(r[y_idx])
            if fv is not None:
                agg[key] = agg.get(key, 0.0) + fv
        else:
            agg[key] = agg.get(key, 0.0) + 1.0

    items = list(agg.items())
    if chart_type in ("bar", "pie"):
        items.sort(key=lambda kv: kv[1], reverse=True)
    else:
        items.sort(key=lambda kv: kv[0])
    items = items[:limit]
    labels = [k for k, _ in items]
    values = [round(v, 4) for _, v in items]

    return {
        "chart_type": chart_type,
        "title": f"{y_column or 'Count'} by {x_column}",
        "x_label": x_column,
        "y_label": y_column or "Count",
        "labels": labels,
        "values": values,
        "points": [],
        "suggestions": suggestions,
    }
