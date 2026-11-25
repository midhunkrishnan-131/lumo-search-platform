"""Developer Platform service: API key lifecycle, granular permissions, per-key rate limiting, and usage logs."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import threading
import time
from typing import Any
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.developer import ApiKey, ApiUsageLog
from app.schemas.developer import ApiKeyCreateRequest, ApiUsageSummaryResponse

API_PERMISSIONS: dict[str, str] = {
    "search:read": "Execute Classic, Semantic, and Hybrid Search queries.",
    "ai:execute": "Run AI Search, summarization, and grounded AI generation.",
    "research:read": "Read research sessions, status, and reports.",
    "research:write": "Create and cancel Autonomous Research Agent sessions.",
    "documents:read": "Read indexed documents and metadata.",
    "documents:write": "Import and process documents.",
    "data_intelligence:read": "Read datasets, profiles, and intelligence reports.",
    "data_intelligence:write": "Import datasets, analyze data, and generate visualizations.",
    "graph:read": "Query Knowledge Graph entities, relationships, and neighborhoods.",
    "guardian:execute": "Run Download Guardian URL/file analyses and read reports.",
    "workspace:read": "Read Personal Workspace items, notes, collections, and search.",
    "workspace:write": "Create or modify Personal Workspace items and notes.",
    "integrations:read": "List external integrations, sources, and sync history.",
    "integrations:sync": "Configure, test, and synchronize external integrations.",
    "automation:read": "List automations, execution history, and notifications.",
    "automation:execute": "Create, trigger, pause, or resume automations.",
    "system:read": "Read system diagnostics, health, and release metadata.",
}

_KEY_RATE_LOCK = threading.Lock()
_KEY_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_raw_api_key() -> tuple[str, str, str]:
    """Return (raw_key, key_prefix, key_hash)."""
    token = secrets.token_urlsafe(32)
    raw = f"lumo_pk_{token}"
    prefix = raw[:16]
    return raw, prefix, hash_api_key(raw)


def resolve_required_permission(method: str, path: str) -> str | None:
    """Map an API route and HTTP method to its required granular permission."""
    is_write = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
    if path.startswith("/api/v1/search"):
        return "search:read"
    if path.startswith("/api/v1/ai"):
        return "ai:execute"
    if path.startswith("/api/v1/research"):
        return "research:write" if is_write else "research:read"
    if path.startswith("/api/v1/documents"):
        return "documents:write" if is_write else "documents:read"
    if path.startswith("/api/v1/intelligence"):
        return "data_intelligence:write" if is_write else "data_intelligence:read"
    if path.startswith("/api/v1/graph"):
        return "graph:read"
    if path.startswith("/api/v1/guardian"):
        return "guardian:execute"
    if path.startswith("/api/v1/workspace"):
        # Search POST is a read operation
        if path.rstrip("/") == "/api/v1/workspace/search":
            return "workspace:read"
        return "workspace:write" if is_write else "workspace:read"
    if path.startswith("/api/v1/integrations"):
        return "integrations:sync" if is_write else "integrations:read"
    if path.startswith("/api/v1/automations") or path.startswith("/api/v1/executions") or path.startswith("/api/v1/notifications"):
        return "automation:execute" if is_write else "automation:read"
    if path.startswith("/api/v1/dashboard") or path.startswith("/api/v1/ops") or path.startswith("/api/v1/evaluations") or path.startswith("/api/v1/evaluation-datasets"):
        return "system:read"
    if path.startswith("/api/v1/developer/info"):
        return "system:read"
    return None


def check_key_rate_limit(key_id: str, limit_rpm: int) -> bool:
    """Return True if within per-key rate limit, False if exceeded."""
    now = time.monotonic()
    with _KEY_RATE_LOCK:
        q = _KEY_RATE_BUCKETS[key_id]
        while q and (now - q[0]) > 60.0:
            q.popleft()
        if len(q) >= max(limit_rpm, 1):
            return False
        q.append(now)
        return True


class DeveloperPlatformService:
    """Manages developer API keys, validation, permission checks, and usage telemetry."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_key(self, payload: ApiKeyCreateRequest) -> tuple[ApiKey, str]:
        invalid = [p for p in payload.permissions if p not in API_PERMISSIONS]
        if invalid:
            raise ValueError(f"Unsupported permission(s): {', '.join(invalid)}")
        raw_key, prefix, key_hash = generate_raw_api_key()
        expires_at = (
            utc_now() + timedelta(days=payload.expires_in_days)
            if payload.expires_in_days
            else None
        )
        row = ApiKey(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            key_prefix=prefix,
            key_hash=key_hash,
            permissions_json=list(dict.fromkeys(payload.permissions)),
            rate_limit_rpm=payload.rate_limit_rpm,
            is_active=True,
            expires_at=expires_at,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row, raw_key

    def list_keys(self) -> list[ApiKey]:
        return self.db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()

    def revoke_key(self, key_id: str) -> ApiKey:
        row = self.db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not row:
            raise ValueError("API key not found.")
        row.is_active = False
        row.revoked_at = utc_now()
        self.db.commit()
        self.db.refresh(row)
        return row

    def rotate_key(self, key_id: str) -> tuple[ApiKey, str]:
        old = self.revoke_key(key_id)
        raw_key, prefix, key_hash = generate_raw_api_key()
        new_row = ApiKey(
            id=str(uuid.uuid4()),
            name=old.name,
            key_prefix=prefix,
            key_hash=key_hash,
            permissions_json=list(old.permissions_json or []),
            rate_limit_rpm=old.rate_limit_rpm,
            is_active=True,
            expires_at=old.expires_at,
        )
        self.db.add(new_row)
        self.db.commit()
        self.db.refresh(new_row)
        return new_row, raw_key

    def delete_key(self, key_id: str) -> bool:
        row = self.db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def validate_raw_key(self, raw_key: str) -> ApiKey:
        row = self.db.query(ApiKey).filter(ApiKey.key_hash == hash_api_key(raw_key)).first()
        if not row:
            raise PermissionError("Invalid API key.")
        if not row.is_active or row.revoked_at is not None:
            raise PermissionError("API key has been revoked.")
        if row.expires_at is not None:
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if utc_now() >= exp:
                raise PermissionError("API key has expired.")
        row.last_used_at = utc_now()
        self.db.commit()
        return row

    def record_usage(
        self,
        api_key: ApiKey | None,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: int,
        rate_limited: bool = False,
    ) -> None:
        self.db.add(
            ApiUsageLog(
                id=str(uuid.uuid4()),
                api_key_id=api_key.id if api_key else None,
                key_prefix=api_key.key_prefix if api_key else None,
                endpoint=endpoint[:255],
                method=method[:12],
                status_code=status_code,
                duration_ms=max(0, duration_ms),
                rate_limited=rate_limited,
            )
        )
        self.db.commit()

    def get_usage_summary(self, limit: int = 30) -> ApiUsageSummaryResponse:
        total = self.db.query(func.count(ApiUsageLog.id)).scalar() or 0
        success = (
            self.db.query(func.count(ApiUsageLog.id))
            .filter(ApiUsageLog.status_code >= 200, ApiUsageLog.status_code < 400)
            .scalar()
            or 0
        )
        failed = (
            self.db.query(func.count(ApiUsageLog.id))
            .filter(ApiUsageLog.status_code >= 400)
            .scalar()
            or 0
        )
        rate_limited = (
            self.db.query(func.count(ApiUsageLog.id))
            .filter(ApiUsageLog.rate_limited == True)  # noqa: E712
            .scalar()
            or 0
        )
        ep_rows = (
            self.db.query(ApiUsageLog.endpoint, func.count(ApiUsageLog.id))
            .group_by(ApiUsageLog.endpoint)
            .order_by(func.count(ApiUsageLog.id).desc())
            .limit(12)
            .all()
        )
        recent = (
            self.db.query(ApiUsageLog)
            .order_by(ApiUsageLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return ApiUsageSummaryResponse(
            total_requests=total,
            successful_requests=success,
            failed_requests=failed,
            rate_limited_requests=rate_limited,
            by_endpoint=[{"endpoint": ep, "count": cnt} for ep, cnt in ep_rows],
            recent=recent,
        )
