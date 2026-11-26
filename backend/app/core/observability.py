"""Centralized API Observability, Request Metrics, and Error Classification for LUMO Phase 26."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import threading
import time
from typing import Any


class ErrorCategory:
    """Standardized application error categories."""

    VALIDATION = "validation_error"
    AUTHENTICATION = "authentication_error"
    AUTHORIZATION = "authorization_error"
    PROVIDER = "provider_error"
    DATABASE = "database_error"
    NETWORK = "network_error"
    TIMEOUT = "timeout_error"
    RESOURCE = "resource_error"
    INTERNAL = "internal_error"


def classify_http_status(status_code: int) -> str:
    """Map an HTTP status code to a standardized error category."""
    if status_code in (400, 422):
        return ErrorCategory.VALIDATION
    if status_code == 401:
        return ErrorCategory.AUTHENTICATION
    if status_code == 403:
        return ErrorCategory.AUTHORIZATION
    if status_code in (408, 504):
        return ErrorCategory.TIMEOUT
    if status_code in (404, 409, 413, 429):
        return ErrorCategory.RESOURCE
    if status_code in (502, 503):
        return ErrorCategory.PROVIDER
    return ErrorCategory.INTERNAL


def classify_exception(exc: Exception) -> str:
    """Classify an exception into a standardized error category without exposing internals."""
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return ErrorCategory.TIMEOUT
    if "auth" in name:
        return ErrorCategory.AUTHENTICATION
    if "permission" in name:
        return ErrorCategory.AUTHORIZATION
    if "aiprovider" in name or "ratelimit" in name:
        return ErrorCategory.PROVIDER
    if "sqlalchemy" in type(exc).__module__.lower() or "sqlite" in name or "database" in name:
        return ErrorCategory.DATABASE
    if "connection" in name or "network" in name or "httpx" in type(exc).__module__.lower():
        return ErrorCategory.NETWORK
    if "valueerror" in name or "validation" in name:
        return ErrorCategory.VALIDATION
    if "memory" in name or "oserror" in name:
        return ErrorCategory.RESOURCE
    return ErrorCategory.INTERNAL


class ObservabilityRegistry:
    """Thread-safe bounded in-memory store for API metrics, slow requests, and recent errors."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc)
        self._start_monotonic = time.monotonic()
        self.total_requests = 0
        self.total_errors = 0
        self.status_counts: dict[str, int] = defaultdict(int)
        self.endpoint_stats: dict[str, dict[str, Any]] = {}
        self.slow_requests: deque[dict[str, Any]] = deque(maxlen=30)
        self.recent_errors: deque[dict[str, Any]] = deque(maxlen=50)

    def uptime_seconds(self) -> float:
        return round(max(0.0, time.monotonic() - self._start_monotonic), 2)

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        elapsed_ms: float,
        request_id: str,
        slow_threshold_ms: float = 1000.0,
    ) -> None:
        key = f"{method.upper()} {path}"
        status_bucket = f"{status_code // 100}xx"
        with self._lock:
            self.total_requests += 1
            self.status_counts[status_bucket] += 1
            if status_code >= 500:
                self.total_errors += 1

            ep = self.endpoint_stats.get(key)
            if ep is None:
                ep = {
                    "count": 0,
                    "errors": 0,
                    "total_ms": 0.0,
                    "max_ms": 0.0,
                }
                self.endpoint_stats[key] = ep
            ep["count"] += 1
            if status_code >= 400:
                ep["errors"] += 1
            ep["total_ms"] += elapsed_ms
            if elapsed_ms > ep["max_ms"]:
                ep["max_ms"] = round(elapsed_ms, 2)

            if elapsed_ms >= slow_threshold_ms:
                self.slow_requests.appendleft({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "method": method.upper(),
                    "path": path,
                    "status_code": status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "request_id": request_id,
                })

    def record_error(
        self,
        category: str,
        error_type: str,
        path: str,
        method: str,
        request_id: str,
        status_code: int = 500,
    ) -> None:
        with self._lock:
            self.recent_errors.appendleft({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": category,
                "error_type": error_type,
                "method": method.upper(),
                "path": path,
                "status_code": status_code,
                "request_id": request_id,
            })

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            top_endpoints = sorted(
                (
                    {
                        "endpoint": k,
                        "count": v["count"],
                        "errors": v["errors"],
                        "avg_ms": round(v["total_ms"] / max(v["count"], 1), 2),
                        "max_ms": round(v["max_ms"], 2),
                    }
                    for k, v in self.endpoint_stats.items()
                ),
                key=lambda item: item["count"],
                reverse=True,
            )[:15]
            return {
                "started_at": self.started_at.isoformat(),
                "uptime_seconds": self.uptime_seconds(),
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "status_distribution": dict(self.status_counts),
                "top_endpoints": top_endpoints,
                "slow_requests": list(self.slow_requests)[:10],
                "recent_errors": list(self.recent_errors)[:15],
            }


observability_registry = ObservabilityRegistry()
