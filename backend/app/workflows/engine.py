"""Controlled Workflow Planner & DAG Execution Engine for LUMO Phase 27."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import time
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.ai.orchestrator import AISearchOrchestrator
from app.core.logging import get_logger
from app.graph.extractor import EntityExtractor
from app.graph.relationships import RelationshipExtractor
from app.guardian.file_analyzer import FileSecurityAnalyzer
from app.guardian.validator import validate_guardian_url
from app.intelligence.classifier import classify_content_deterministic
from app.intelligence.spreadsheet import generate_chart_data, profile_dataset_file
from app.models.workflow import IntelligenceWorkflow, IntelligenceWorkflowStep
from app.processor.extractor import extract_document_data
from app.research.manager import research_manager
from app.schemas.ai import AISearchRequest
from app.schemas.workflow import WorkflowCreateRequest, WorkflowExecuteRequest
from app.search.engine import ClassicSearchEngine
from app.search.hybrid import HybridSearchOrchestrator
from app.semantic.search import SemanticSearchEngine
from app.workflows.context import (
    CrossModuleContext,
    deduplicate_sources,
    detect_disagreements_and_gaps,
    make_source_record,
)
from app.workflows.router import classify_and_plan

logger = get_logger("workflows.engine")
MAX_WORKFLOW_BYTES = 2 * 1024 * 1024


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowManager:
    """Coordinates workflow planning, controlled DAG execution, cancellation, history, and export."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_and_plan(self, payload: WorkflowCreateRequest, owner_id: str = "local") -> IntelligenceWorkflow:
        plan = classify_and_plan(
            payload.user_request,
            inputs=payload.inputs,
            preferred_intent=payload.preferred_intent,
            allowed_modules=payload.allowed_modules,
        )
        title = (payload.title or "").strip() or payload.user_request.strip()[:90]
        wf = IntelligenceWorkflow(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            title=title,
            user_request=payload.user_request.strip(),
            intent=plan["intent"],
            selected_modules_json=plan["selected_modules"],
            plan_json={
                "steps": plan["steps"],
                "missing_inputs": plan["missing_inputs"],
                "extracted_urls": plan["extracted_urls"],
                "inputs": payload.inputs,
            },
            status="READY" if plan["ready"] else "PLANNING",
            progress=0.0,
        )
        self.db.add(wf)
        for s in plan["steps"]:
            self.db.add(
                IntelligenceWorkflowStep(
                    id=str(uuid.uuid4()),
                    workflow_id=wf.id,
                    step_key=s["step_key"],
                    module_name=s["module_name"],
                    title=s["title"],
                    depends_on_json=s["depends_on"],
                    status="PENDING",
                )
            )
        self.db.commit()
        self.db.refresh(wf)
        return wf

    def list_workflows(
        self,
        owner_id: str = "local",
        intent: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 40,
    ) -> list[IntelligenceWorkflow]:
        query = self.db.query(IntelligenceWorkflow).filter(IntelligenceWorkflow.owner_id == owner_id)
        if intent:
            query = query.filter(IntelligenceWorkflow.intent == intent)
        if status:
            query = query.filter(IntelligenceWorkflow.status == status)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(
                (IntelligenceWorkflow.title.ilike(like)) | (IntelligenceWorkflow.user_request.ilike(like))
            )
        return query.order_by(IntelligenceWorkflow.created_at.desc()).limit(limit).all()

    def get_workflow(self, workflow_id: str, owner_id: str = "local") -> IntelligenceWorkflow:
        wf = (
            self.db.query(IntelligenceWorkflow)
            .filter(IntelligenceWorkflow.id == workflow_id, IntelligenceWorkflow.owner_id == owner_id)
            .first()
        )
        if not wf:
            raise ValueError("Workflow not found.")
        return wf

    def delete_workflow(self, workflow_id: str, owner_id: str = "local") -> bool:
        wf = (
            self.db.query(IntelligenceWorkflow)
            .filter(IntelligenceWorkflow.id == workflow_id, IntelligenceWorkflow.owner_id == owner_id)
            .first()
        )
        if not wf:
            return False
        self.db.delete(wf)
        self.db.commit()
        return True

    def cancel_workflow(self, workflow_id: str, owner_id: str = "local") -> IntelligenceWorkflow:
        wf = self.get_workflow(workflow_id, owner_id=owner_id)
        if wf.status in ("COMPLETED", "FAILED", "CANCELLED"):
            return wf
        wf.cancel_requested = True
        for st in wf.steps:
            if st.status == "PENDING":
                st.status = "CANCELLED"
        if wf.status in ("CREATED", "PLANNING", "READY"):
            wf.status = "CANCELLED"
            wf.completed_at = utc_now()
        self.db.commit()
        self.db.refresh(wf)
        return wf

    def _is_cancelled(self, workflow_id: str) -> bool:
        self.db.expire_all()
        row = self.db.query(IntelligenceWorkflow.cancel_requested).filter(IntelligenceWorkflow.id == workflow_id).first()
        return bool(row and row[0])

    def _run_step(
        self,
        step: IntelligenceWorkflowStep,
        wf: IntelligenceWorkflow,
        params: WorkflowExecuteRequest,
        inputs: dict[str, Any],
        extracted_urls: list[str],
        ctx: CrossModuleContext,
        db_session: Session | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Execute one bounded module step using existing LUMO engines (no autonomous loops)."""
        db = db_session or self.db
        mod = step.module_name
        sources: list[dict[str, Any]] = []
        q = wf.user_request

        if mod == "search":
            mode = (params.search_mode or "hybrid").lower()
            if mode == "classic":
                res = ClassicSearchEngine(db).search(query=q, page=1, per_page=5)
            elif mode == "semantic":
                res = SemanticSearchEngine(db).search(query=q, page=1, per_page=5)
            else:
                res, _, _ = HybridSearchOrchestrator(db).search(query=q, page=1, per_page=5)
            hits = [
                {
                    "id": getattr(r, "id", getattr(r, "document_id", "")),
                    "url": getattr(r, "url", ""),
                    "title": getattr(r, "title", ""),
                    "snippet": getattr(r, "snippet", ""),
                    "score": getattr(r, "score", 0.0),
                }
                for r in res.results
            ]
            for idx, h in enumerate(hits, start=1):
                sources.append(
                    make_source_record(
                        url=h.get("url", ""),
                        title=h.get("title", ""),
                        module="search",
                        source_type="indexed_document",
                        relevance=h.get("score"),
                        citation_id=f"S{idx}",
                        excerpt=h.get("snippet", ""),
                    )
                )
            ctx.add_text("search", "\n".join(f"{h.get('title')}: {h.get('snippet')}" for h in hits))
            return {"mode": mode, "total": len(hits), "results": hits}, sources

        if mod == "ai_search":
            orch = AISearchOrchestrator(db)
            ai_res = orch.search(
                AISearchRequest(
                    query=q,
                    search_mode="hybrid",
                    provider=params.provider,
                    model=params.model_name,
                    max_sources=5,
                )
            )
            cids = [s.source_id for s in (ai_res.sources or [])]
            for s in (ai_res.sources or []):
                sources.append(
                    make_source_record(
                        url=s.url,
                        title=s.title,
                        module="ai_search",
                        source_type="ai_source",
                        citation_id=s.source_id,
                        excerpt=s.snippet,
                    )
                )
            ctx.add_text("ai_search", ai_res.answer or "")
            return {
                "status": ai_res.status,
                "answer": ai_res.answer,
                "citations": cids,
                "provider": getattr(ai_res, "provider_used", params.provider),
                "is_ai_generated": True,
            }, sources

        if mod == "research_agent":
            session = research_manager.create_session(
                db=db,
                topic=q,
                max_iterations=1,
                max_queries=3,
                max_sources=5,
                provider=params.provider,
            )
            finished = research_manager.start_session(session.id, background=False) or session
            report = getattr(finished, "report", None) or {}
            srcs_list = getattr(finished, "sources", None) or []
            for s in srcs_list[:10]:
                if isinstance(s, dict):
                    sources.append(
                        make_source_record(
                            url=str(s.get("url") or ""),
                            title=str(s.get("title") or ""),
                            module="research_agent",
                            source_type="research_source",
                            citation_id=s.get("source_id"),
                            excerpt=str(s.get("passage") or s.get("snippet") or ""),
                        )
                    )
            summary_txt = str(report.get("executive_summary") or getattr(finished, "topic", q) or "")
            ctx.add_text("research_agent", summary_txt)
            return {
                "session_id": finished.id,
                "status": finished.status,
                "executive_summary": summary_txt,
                "key_findings": report.get("key_findings", []),
                "sources_count": len(srcs_list),
            }, sources

        if mod == "document_intelligence":
            html = str(inputs.get("html") or "")
            text = str(inputs.get("document_text") or "")
            title = str(inputs.get("document_title") or "")
            if html:
                ext = extract_document_data(html, "https://workspace.local/doc")
                text = ext.main_content
                title = title or ext.title
            cat, conf, _ = classify_content_deterministic(title, text, str(inputs.get("file_type") or "txt"))
            ctx.add_text("document_intelligence", f"{title}\n{text}")
            return {
                "title": title or "Uploaded Document",
                "category": cat,
                "confidence": conf,
                "char_count": len(text),
                "excerpt": text[:400],
            }, sources

        if mod == "data_intelligence":
            file_type = "json" if inputs.get("json_content") is not None else "csv"
            raw_text = (
                inputs.get("json_content")
                if isinstance(inputs.get("json_content"), str)
                else json.dumps(inputs["json_content"])
                if inputs.get("json_content") is not None
                else str(inputs.get("csv_content") or "")
            )
            raw_bytes = raw_text.encode("utf-8", errors="replace")
            if len(raw_bytes) > MAX_WORKFLOW_BYTES:
                raise ValueError("Dataset exceeds 2 MB workflow limit.")
            with tempfile.TemporaryDirectory(prefix="lumo_wf_data_") as tmpdir:
                tmp_path = Path(tmpdir) / f"dataset.{file_type}"
                tmp_path.write_bytes(raw_bytes)
                profile = profile_dataset_file(tmp_path, file_type)
                chart = None
                try:
                    chart = generate_chart_data(tmp_path, file_type, profile.get("columns", []))
                except ValueError:
                    chart = None
            ctx.add_text("data_intelligence", str(profile.get("summary") or ""))
            return {"profile": profile, "chart": chart}, sources

        if mod == "knowledge_graph":
            source_text = str(inputs.get("document_text") or "") or ctx.get_combined_text() or q
            ent_ext = EntityExtractor()
            rel_ext = RelationshipExtractor()
            entities = ent_ext.extract(source_text[:6000])
            rels = rel_ext.extract(source_text[:6000], entities)
            return {
                "entities": [{"name": e.name, "type": e.entity_type} for e in entities[:20]],
                "relationships": [
                    {"source": r.source_name, "type": r.relationship_type, "target": r.target_name, "snippet": r.snippet}
                    for r in rels[:20]
                ],
            }, sources

        if mod == "guardian_url":
            url_results = []
            for u in extracted_urls[:10]:
                v = validate_guardian_url(u, resolve_dns=False)
                url_results.append({
                    "url": u,
                    "is_valid": v.is_valid,
                    "is_blocked": v.is_blocked,
                    "error": v.error,
                    "scheme": v.scheme,
                    "hostname": v.hostname,
                })
                sources.append(
                    make_source_record(
                        url=u,
                        title=v.hostname or u,
                        module="guardian_url",
                        source_type="submitted_url",
                        verification_status="blocked" if v.is_blocked else ("verified" if v.is_valid else "unverified"),
                    )
                )
            return {"urls": url_results}, sources

        if mod == "guardian_file":
            filename = str(inputs.get("filename") or "upload.bin")
            if inputs.get("file_bytes_b64") is not None:
                raw_bytes = base64.b64decode(str(inputs["file_bytes_b64"]))
            else:
                raw_bytes = str(inputs.get("file_text") or "").encode("utf-8", errors="replace")
            if len(raw_bytes) > MAX_WORKFLOW_BYTES:
                raise ValueError("File exceeds 2 MB workflow limit.")
            analyzer = FileSecurityAnalyzer()
            hashes, fmt, mime, findings, features, fsize = analyzer.analyze_file_stream(io.BytesIO(raw_bytes), filename)
            return {
                "filename": filename,
                "size_bytes": fsize,
                "detected_format": fmt,
                "detected_mime": mime,
                "sha256": hashes.get("sha256"),
                "findings": [{"name": f.name, "severity": f.severity, "description": f.description} for f in findings],
                "static_features": features,
            }, sources

        raise ValueError(f"Unsupported workflow module '{mod}'.")

    def execute_workflow(
        self,
        workflow_id: str,
        owner_id: str = "local",
        payload: WorkflowExecuteRequest | None = None,
    ) -> IntelligenceWorkflow:
        """Execute planned DAG steps in dependency waves with parallel wave execution and cancellation."""
        wf = self.get_workflow(workflow_id, owner_id=owner_id)
        if wf.status == "RUNNING":
            raise ValueError("Workflow is already running.")
        if wf.status in ("COMPLETED", "CANCELLED"):
            raise ValueError(f"Workflow in status '{wf.status}' cannot be re-executed.")

        params = payload or WorkflowExecuteRequest()
        plan = wf.plan_json or {}
        inputs = dict(plan.get("inputs") or {})
        extracted_urls = list(plan.get("extracted_urls") or [])

        wf.status = "RUNNING"
        wf.started_at = utc_now()
        wf.cancel_requested = False
        self.db.commit()

        ctx = CrossModuleContext()
        if inputs.get("knowledge_collection_id") or inputs.get("knowledge_item_ids"):
            from app.knowledge_hub.service import KnowledgeHubService
            from app.schemas.knowledge_hub import KnowledgeContextRequest

            k_ctx = KnowledgeHubService(self.db).build_knowledge_context(
                KnowledgeContextRequest(
                    query=wf.user_request,
                    collection_id=inputs.get("knowledge_collection_id"),
                    item_ids=list(inputs.get("knowledge_item_ids") or []),
                ),
                owner_id=owner_id,
            )
            if k_ctx.get("context_text"):
                ctx.add_text("knowledge_hub", k_ctx["context_text"])
        results: dict[str, Any] = dict(wf.results_json or {})
        all_sources: list[dict[str, Any]] = list(wf.sources_json or [])
        errors: list[dict[str, Any]] = []
        module_durations: dict[str, float] = {}

        steps_by_key = {s.step_key: s for s in wf.steps}
        completed_keys = {k for k, s in steps_by_key.items() if s.status == "COMPLETED"}

        # Bounded topological wave loop (max iterations = len(steps) + 1)
        for _ in range(len(steps_by_key) + 1):
            if self._is_cancelled(wf.id):
                wf.status = "CANCELLED"
                break

            ready_steps = [
                s for s in wf.steps
                if s.status == "PENDING"
                and all(dep in completed_keys for dep in (s.depends_on_json or []))
            ]
            if not ready_steps:
                break

            # Mark wave steps RUNNING
            for s in ready_steps:
                s.status = "RUNNING"
                s.started_at = utc_now()
            self.db.commit()

            def _exec_one(st: IntelligenceWorkflowStep, use_thread_session: bool = False) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]], str | None, float]:
                t0 = time.perf_counter()
                thread_db: Session | None = None
                try:
                    if use_thread_session:
                        from app.database.connection import get_session_factory
                        factory = get_session_factory()
                        if factory is not None:
                            thread_db = factory()
                    out, srcs = self._run_step(st, wf, params, inputs, extracted_urls, ctx, db_session=thread_db)
                    return st.step_key, out, srcs, None, round((time.perf_counter() - t0) * 1000, 2)
                except Exception as exc:
                    return st.step_key, None, [], f"{type(exc).__name__}: {exc}", round((time.perf_counter() - t0) * 1000, 2)
                finally:
                    if thread_db is not None:
                        thread_db.close()

            wave_results: list[tuple[str, dict[str, Any] | None, list[dict[str, Any]], str | None, float]] = []
            if len(ready_steps) > 1:
                # Parallel execution for independent steps in the same wave (each with isolated DB session)
                with ThreadPoolExecutor(max_workers=min(3, len(ready_steps))) as pool:
                    futs = [pool.submit(_exec_one, st, True) for st in ready_steps]
                    for fut in as_completed(futs):
                        wave_results.append(fut.result())
            else:
                wave_results.append(_exec_one(ready_steps[0], False))

            for key, out, srcs, err, dur in wave_results:
                st = steps_by_key[key]
                st.duration_ms = dur
                st.completed_at = utc_now()
                module_durations[st.module_name] = dur
                if err:
                    st.status = "FAILED"
                    st.error_message = err
                    errors.append({"step_key": key, "module": st.module_name, "error": err})
                else:
                    st.status = "COMPLETED"
                    st.output_ref_json = out or {}
                    results[st.module_name] = out
                    all_sources.extend(srcs)
                    completed_keys.add(key)

            done_count = sum(1 for s in wf.steps if s.status in ("COMPLETED", "FAILED", "CANCELLED", "SKIPPED"))
            wf.progress = round(done_count / max(len(wf.steps), 1), 2)
            self.db.commit()

        # Skip any remaining PENDING steps whose dependencies failed
        for s in wf.steps:
            if s.status == "PENDING":
                s.status = "CANCELLED" if wf.cancel_requested else "SKIPPED"

        deduped_sources, dup_count = deduplicate_sources(all_sources)
        ai_cits = (results.get("ai_search") or {}).get("citations") if isinstance(results.get("ai_search"), dict) else None
        g_urls = (results.get("guardian_url") or {}).get("urls") if isinstance(results.get("guardian_url"), dict) else None
        disagreements = detect_disagreements_and_gaps(deduped_sources, guardian_urls=g_urls, citations=ai_cits)

        comp_cnt = sum(1 for s in wf.steps if s.status == "COMPLETED")
        fail_cnt = sum(1 for s in wf.steps if s.status == "FAILED")

        if wf.cancel_requested:
            wf.status = "CANCELLED"
        elif fail_cnt == 0 and comp_cnt == len(wf.steps):
            wf.status = "COMPLETED"
        elif comp_cnt > 0:
            wf.status = "PARTIALLY_COMPLETED"
        else:
            wf.status = "FAILED"

        wf.results_json = results
        wf.sources_json = deduped_sources
        wf.disagreements_json = disagreements
        wf.errors_json = errors
        wf.summary = (
            f"Executed {comp_cnt}/{len(wf.steps)} steps for intent '{wf.intent}'. "
            f"Collected {len(deduped_sources)} unique sources ({dup_count} duplicates removed)."
        )
        wf.execution_metadata_json = {
            "module_durations_ms": module_durations,
            "duplicate_sources_removed": dup_count,
            "limitations": [
                "External URLs are validated statically without fetching arbitrary remote pages.",
                "AI synthesis is separated from retrieved sources and requires a configured provider.",
            ],
        }
        wf.completed_at = utc_now()
        self.db.commit()
        self.db.refresh(wf)
        return wf

    def retry_failed_steps(self, workflow_id: str, owner_id: str = "local") -> IntelligenceWorkflow:
        wf = self.get_workflow(workflow_id, owner_id=owner_id)
        failed_steps = [s for s in wf.steps if s.status in ("FAILED", "SKIPPED")]
        if not failed_steps:
            return wf
        for s in failed_steps:
            s.status = "PENDING"
            s.error_message = None
        wf.status = "READY"
        self.db.commit()
        return self.execute_workflow(workflow_id, owner_id=owner_id)

    def export_workflow(self, workflow_id: str, owner_id: str = "local", fmt: str = "json") -> tuple[str, str]:
        wf = self.get_workflow(workflow_id, owner_id=owner_id)
        if fmt.lower() == "markdown":
            lines = [
                f"# LUMO Workflow Report: {wf.title}",
                f"- **ID**: `{wf.id}`",
                f"- **Intent**: `{wf.intent}` | **Status**: `{wf.status}`",
                f"- **Modules**: {', '.join(wf.selected_modules_json or [])}",
                "",
                "## Summary",
                wf.summary or "No summary available.",
                "",
                "## Sources",
            ]
            for s in (wf.sources_json or []):
                lines.append(f"- [{s.get('title')}]({s.get('url')}) (`{s.get('module')}`, status: `{s.get('verification_status')}`)")
            if not (wf.sources_json or []):
                lines.append("- None")
            lines.extend(["", "## Structured Results", "```json", json.dumps(wf.results_json or {}, indent=2), "```"])
            return "\n".join(lines), "text/markdown"

        payload = {
            "id": wf.id,
            "title": wf.title,
            "user_request": wf.user_request,
            "intent": wf.intent,
            "status": wf.status,
            "summary": wf.summary,
            "results": wf.results_json,
            "sources": wf.sources_json,
            "disagreements": wf.disagreements_json,
            "errors": wf.errors_json,
            "execution_metadata": wf.execution_metadata_json,
        }
        return json.dumps(payload, indent=2), "application/json"
