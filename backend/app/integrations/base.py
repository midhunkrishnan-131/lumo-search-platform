"""Standardized External Integration contract and normalized data model (Phase 22)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from typing import Any

ALLOWED_PERMISSIONS = frozenset({
    "read_external",
    "import_data",
    "write_workspace",
    "create_notifications",
    "sync_sources",
    "access_config",
})


def compute_normalized_hash(title: str, content: str, url: str | None = None) -> str:
    payload = re.sub(r"\s+", " ", f"{title or ''}|{url or ''}|{content or ''}".strip())
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class NormalizedItem:
    """Standard LUMO representation for any external integration record."""

    external_id: str
    integration_id: str
    source_type: str
    title: str
    content: str
    description: str = ""
    url: str | None = None
    author: str | None = None
    published_at: str | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    tags: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    source_attribution: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = compute_normalized_hash(self.title, self.content, self.url)


class BaseIntegration(ABC):
    """Unified contract every LUMO external integration adapter implements."""

    integration_id: str = ""
    name: str = ""
    category: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: list[str] = []
    default_permissions: list[str] = ["read_external", "import_data", "write_workspace", "sync_sources"]
    config_fields: list[dict[str, Any]] = []

    def initialize(self, config: dict[str, Any], secret: str | None = None) -> None:
        self.config = dict(config or {})
        self.secret = secret

    @abstractmethod
    def validate_configuration(self, config: dict[str, Any], secret: str | None = None) -> tuple[bool, str | None]:
        """Validate adapter configuration without making destructive changes."""

    @abstractmethod
    def test_connection(self, config: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
        """Perform a lightweight read-only connectivity check."""

    @abstractmethod
    def fetch_data(
        self,
        source_url: str,
        config: dict[str, Any],
        secret: str | None = None,
        max_items: int = 15,
    ) -> list[dict[str, Any]]:
        """Fetch raw untrusted records from the external source."""

    @abstractmethod
    def normalize_data(self, raw_items: list[dict[str, Any]], source_url: str) -> list[NormalizedItem]:
        """Convert raw records into standardized NormalizedItem objects."""

    def import_data(self, items: list[NormalizedItem]) -> list[NormalizedItem]:
        """Hook for adapter-level post-normalization filtering before DB persistence."""
        return items

    def get_status(self) -> dict[str, Any]:
        return {
            "id": self.integration_id,
            "name": self.name,
            "category": self.category,
            "version": self.version,
        }

    def shutdown(self) -> None:
        return None
