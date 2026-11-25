"""Central Integration Manager coordinating registration, permissions, sync, and monitoring."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.ai.context import ContextBuilder
from app.ai.router import AIProviderRouter
from app.core.logging import get_logger
from app.crawler.validator import validate_and_screen_url
from app.graph.extractor import EntityExtractor
from app.graph.service import invalidate_graph_cache
from app.integrations.adapters import BUILTIN_ADAPTERS
from app.integrations.base import ALLOWED_PERMISSIONS, BaseIntegration, NormalizedItem
from app.integrations.http_guard import seal_secret, unseal_secret
from app.intelligence.security import redact_secrets
from app.models.automation import AutomationNotification
from app.models.graph import Entity
from app.models.integrations import (
    IntegrationImportRecord,
    IntegrationRecord,
    IntegrationSource,
    IntegrationSyncRun,
)
from app.models.workspace import WorkspaceItem
from app.schemas.integrations import (
    IntegrationCatalogItem,
    IntegrationConfigureRequest,
    IntegrationSourceCreate,
)

logger = get_logger("integrations.manager")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationManager:
    """Manages integration registry, permissions, sources, sync runs, and unified imports."""

    def __init__(self, db: Session, ai_router: AIProviderRouter | None = None) -> None:
        self.db = db
        self.ai_router = ai_router or AIProviderRouter()
        self.entity_extractor = EntityExtractor()
        self.sanitizer = ContextBuilder()

    def ensure_registered(self) -> None:
        """Idempotently register all built-in adapters in the integrations table."""
        existing = {r.id for r in self.db.query(IntegrationRecord.id).all()}
        added = False
        for adapter in BUILTIN_ADAPTERS.values():
            if adapter.integration_id not in existing:
                self.db.add(
                    IntegrationRecord(
                        id=adapter.integration_id,
                        name=adapter.name,
                        category=adapter.category,
                        description=adapter.description,
                        version=adapter.version,
                        enabled=False,
                        status="not_configured",
                        connection_status="unknown",
                        permissions_json=list(adapter.default_permissions),
                        config_json={},
                    )
                )
                added = True
        if added:
            self.db.commit()

    def list_available_catalog(self) -> list[IntegrationCatalogItem]:
        return [
            IntegrationCatalogItem(
                id=a.integration_id,
                name=a.name,
                category=a.category,
                description=a.description,
                version=a.version,
                capabilities=list(a.capabilities),
                default_permissions=list(a.default_permissions),
                config_fields=list(a.config_fields),
            )
            for a in BUILTIN_ADAPTERS.values()
        ]

    def list_integrations(self) -> list[IntegrationRecord]:
        self.ensure_registered()
        return self.db.query(IntegrationRecord).order_by(IntegrationRecord.category.asc(), IntegrationRecord.name.asc()).all()

    def get_integration(self, integration_id: str) -> IntegrationRecord:
        self.ensure_registered()
        rec = self.db.query(IntegrationRecord).filter(IntegrationRecord.id == integration_id).first()
        if not rec:
            raise ValueError(f"Integration '{integration_id}' not found.")
        return rec

    def _get_adapter(self, integration_id: str) -> BaseIntegration:
        adapter = BUILTIN_ADAPTERS.get(integration_id)
        if not adapter:
            raise ValueError(f"No adapter registered for '{integration_id}'.")
        return adapter

    def _require_permission(self, rec: IntegrationRecord, perm: str) -> None:
        granted = set(rec.permissions_json or [])
        if perm not in granted:
            raise PermissionError(f"Integration '{rec.id}' lacks required permission '{perm}'.")

    def enable_integration(self, integration_id: str) -> IntegrationRecord:
        rec = self.get_integration(integration_id)
        rec.enabled = True
        if rec.status == "disabled":
            rec.status = "configured"
        rec.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def disable_integration(self, integration_id: str) -> IntegrationRecord:
        rec = self.get_integration(integration_id)
        rec.enabled = False
        rec.status = "disabled"
        rec.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def configure_integration(self, integration_id: str, payload: IntegrationConfigureRequest) -> IntegrationRecord:
        rec = self.get_integration(integration_id)
        adapter = self._get_adapter(integration_id)

        merged_cfg = {**(rec.config_json or {}), **(payload.config or {})}
        secret = None if payload.clear_secret else (
            payload.secret_token if payload.secret_token else unseal_secret(rec.secret_encrypted)
        )
        ok, err = adapter.validate_configuration(merged_cfg, secret=secret)
        if not ok:
            raise ValueError(err or "Invalid integration configuration.")

        if payload.permissions is not None:
            invalid_p = [p for p in payload.permissions if p not in ALLOWED_PERMISSIONS]
            if invalid_p:
                raise ValueError(f"Invalid permissions: {', '.join(invalid_p)}")
            rec.permissions_json = list(dict.fromkeys(payload.permissions))

        if payload.sync_frequency_minutes is not None:
            rec.sync_frequency_minutes = payload.sync_frequency_minutes

        if payload.clear_secret:
            rec.secret_encrypted = None
            rec.has_secret = False
        elif payload.secret_token:
            rec.secret_encrypted = seal_secret(payload.secret_token)
            rec.has_secret = True

        rec.config_json = merged_cfg
        rec.status = "configured" if rec.enabled else "not_configured"
        rec.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def test_connection(self, integration_id: str) -> dict[str, Any]:
        rec = self.get_integration(integration_id)
        adapter = self._get_adapter(integration_id)
        secret = unseal_secret(rec.secret_encrypted)
        try:
            res = adapter.test_connection(rec.config_json or {}, secret=secret)
            rec.connection_status = "connected" if res.get("ok") else "failed"
            rec.last_sync_error = None if res.get("ok") else str(res.get("detail", "Connection failed"))
            self.db.commit()
            return {"integration_id": integration_id, **res}
        except Exception as exc:
            msg = redact_secrets(str(exc))
            rec.connection_status = "failed"
            rec.last_sync_error = msg[:500]
            self.db.commit()
            return {"integration_id": integration_id, "ok": False, "detail": msg}

    # --- Source Monitoring ---

    def list_sources(self, integration_id: str) -> list[IntegrationSource]:
        self.get_integration(integration_id)
        return (
            self.db.query(IntegrationSource)
            .filter(IntegrationSource.integration_id == integration_id)
            .order_by(IntegrationSource.created_at.desc())
            .all()
        )

    def add_source(self, integration_id: str, payload: IntegrationSourceCreate) -> IntegrationSource:
        self.get_integration(integration_id)
        src_url = payload.source_url.strip()
        if integration_id != "github" or "://" in src_url:
            v = validate_and_screen_url(src_url, resolve_dns=False)
            if not v.is_valid:
                raise ValueError(f"Invalid source URL: {v.error}")
        src = IntegrationSource(
            id=str(uuid.uuid4()),
            integration_id=integration_id,
            name=payload.name.strip(),
            source_url=src_url,
            source_type=payload.source_type,
            monitored=payload.monitored,
            paused=False,
            sync_frequency_minutes=payload.sync_frequency_minutes,
            config_json=payload.config_json,
        )
        self.db.add(src)
        self.db.commit()
        self.db.refresh(src)
        return src

    def set_source_paused(self, source_id: str, paused: bool) -> IntegrationSource:
        src = self.db.query(IntegrationSource).filter(IntegrationSource.id == source_id).first()
        if not src:
            raise ValueError("Source not found.")
        src.paused = paused
        src.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(src)
        return src

    def delete_source(self, source_id: str) -> bool:
        src = self.db.query(IntegrationSource).filter(IntegrationSource.id == source_id).first()
        if not src:
            return False
        self.db.delete(src)
        self.db.commit()
        return True

    # --- Synchronization & Unified Import Pipeline ---

    def _link_entities(self, item: NormalizedItem) -> None:
        ents = self.entity_extractor.extract(f"{item.title}\n{item.content[:8000]}", max_entities=12)
        for ent in ents:
            existing = self.db.query(Entity).filter(Entity.normalized_name == ent.normalized_name).first()
            if not existing:
                self.db.add(
                    Entity(
                        id=str(uuid.uuid4()),
                        name=ent.name,
                        normalized_name=ent.normalized_name,
                        entity_type=ent.entity_type,
                        confidence=ent.confidence,
                        extraction_method=f"integration:{item.integration_id}",
                    )
                )
        if ents:
            invalidate_graph_cache()

    def _notify(self, rec: IntegrationRecord, title: str, message: str, event_type: str = "integration_update") -> None:
        if "create_notifications" not in (rec.permissions_json or []):
            return
        self.db.add(
            AutomationNotification(
                id=str(uuid.uuid4()),
                event_type=event_type,
                title=title[:255],
                message=message[:1000],
                is_read=False,
            )
        )

    def sync_integration(
        self,
        integration_id: str,
        source_id: str | None = None,
        summarize_with_ai: bool = False,
        ai_provider: str = "auto",
        max_items: int = 15,
        trigger_mode: str = "manual",
    ) -> IntegrationSyncRun:
        rec = self.get_integration(integration_id)
        if not rec.enabled:
            raise ValueError(f"Integration '{integration_id}' is disabled. Enable it before syncing.")

        self._require_permission(rec, "read_external")
        self._require_permission(rec, "sync_sources")
        self._require_permission(rec, "import_data")

        adapter = self._get_adapter(integration_id)
        secret = unseal_secret(rec.secret_encrypted)
        adapter.initialize(rec.config_json or {}, secret=secret)

        # Resolve target sources
        if source_id:
            sources = self.db.query(IntegrationSource).filter(
                IntegrationSource.id == source_id,
                IntegrationSource.integration_id == integration_id,
            ).all()
            if not sources:
                raise ValueError("Specified source not found for this integration.")
        else:
            sources = self.db.query(IntegrationSource).filter(
                IntegrationSource.integration_id == integration_id,
                IntegrationSource.paused == False,  # noqa: E712
            ).all()

        if not sources:
            fallback_url = (rec.config_json or {}).get("default_feed_url") or (rec.config_json or {}).get("default_repo")
            if not fallback_url:
                raise ValueError("No active sources configured for this integration.")
            sources = [
                IntegrationSource(
                    id="",
                    integration_id=integration_id,
                    name=str(fallback_url),
                    source_url=str(fallback_url),
                    source_type="default",
                )
            ]

        t0 = time.perf_counter()
        run = IntegrationSyncRun(
            id=str(uuid.uuid4()),
            integration_id=integration_id,
            source_id=source_id,
            trigger_mode=trigger_mode,
            status="running",
            started_at=utc_now(),
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        imported = 0
        skipped = 0
        failed = 0
        can_write_ws = "write_workspace" in (rec.permissions_json or [])

        try:
            for src in sources:
                try:
                    raw = adapter.fetch_data(src.source_url, rec.config_json or {}, secret=secret, max_items=max_items)
                    norm_items = adapter.import_data(adapter.normalize_data(raw, src.source_url))

                    for item in norm_items:
                        dup = (
                            self.db.query(IntegrationImportRecord)
                            .filter(
                                IntegrationImportRecord.integration_id == integration_id,
                                IntegrationImportRecord.content_hash == item.content_hash,
                            )
                            .first()
                        )
                        if dup:
                            skipped += 1
                            continue

                        summary_text = item.description or item.content[:240]
                        if summarize_with_ai and item.content.strip():
                            try:
                                safe_txt = self.sanitizer._sanitize_for_prompt(item.content[:4000])
                                ai_resp, _, _ = self.ai_router.execute(
                                    system_prompt="Summarize this untrusted external item in 2 concise sentences.",
                                    user_prompt=f"Title: {item.title}\nContent:\n{safe_txt}",
                                    requested_provider=ai_provider,
                                    timeout=15.0,
                                )
                                summary_text = ai_resp.content
                            except Exception:
                                pass

                        ws_item_id = None
                        if can_write_ws:
                            ws_item = WorkspaceItem(
                                id=str(uuid.uuid4()),
                                title=item.title,
                                content=item.content,
                                summary=summary_text,
                                source_type=item.source_type,
                                source_url=item.url,
                                content_hash=item.content_hash,
                                metadata_json={
                                    "integration_id": integration_id,
                                    "source_attribution": item.source_attribution,
                                    "author": item.author,
                                    "published_at": item.published_at,
                                    "tags": item.tags,
                                },
                            )
                            self.db.add(ws_item)
                            self.db.flush()
                            ws_item_id = ws_item.id

                        self._link_entities(item)

                        self.db.add(
                            IntegrationImportRecord(
                                id=str(uuid.uuid4()),
                                integration_id=integration_id,
                                source_id=src.id or None,
                                external_id=item.external_id[:255] if item.external_id else None,
                                content_hash=item.content_hash,
                                title=item.title,
                                url=item.url,
                                workspace_item_id=ws_item_id,
                            )
                        )
                        imported += 1

                    if src.id:
                        src.last_synced_at = utc_now()
                        src.last_error = None
                        if norm_items:
                            src.last_item_hash = norm_items[0].content_hash
                except Exception as src_exc:
                    failed += 1
                    err_msg = redact_secrets(str(src_exc))[:500]
                    if src.id:
                        src.last_error = err_msg

            run.imported_count = imported
            run.skipped_count = skipped
            run.failed_count = failed
            run.duration_ms = int((time.perf_counter() - t0) * 1000)
            run.status = "completed" if (failed == 0 or imported > 0) else "failed"
            run.completed_at = utc_now()

            rec.last_sync_at = utc_now()
            rec.connection_status = "connected" if failed == 0 else rec.connection_status
            rec.last_sync_error = None if failed == 0 else f"{failed} source(s) failed during sync."
            rec.status = "configured"

            if imported > 0:
                self._notify(
                    rec,
                    f"{rec.name}: {imported} new item(s) imported",
                    f"Synchronized {imported} new, {skipped} duplicate skipped.",
                    event_type="integration_sync",
                )
            elif failed > 0:
                self._notify(
                    rec,
                    f"{rec.name}: Sync error",
                    f"{failed} source(s) failed during synchronization.",
                    event_type="integration_error",
                )

            self.db.commit()
            self.db.refresh(run)
            return run
        except Exception as exc:
            self.db.rollback()
            err = redact_secrets(str(exc))[:1000]
            run.status = "failed"
            run.error_message = err
            run.duration_ms = int((time.perf_counter() - t0) * 1000)
            run.completed_at = utc_now()
            rec.last_sync_error = err
            rec.connection_status = "failed"
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            raise
