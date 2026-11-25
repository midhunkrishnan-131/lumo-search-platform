"""AI Search Orchestrator combining Hybrid Search, Context Building, Provider Routing, and Citation Validation."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.ai.base import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from app.ai.citations import CitationValidator
from app.ai.context import ContextBuilder
from app.ai.prompts import AI_SEARCH_SYSTEM_PROMPT, build_user_prompt
from app.ai.router import AIProviderRouter, ai_provider_router
from app.core.logging import get_logger
from app.schemas.ai import AISearchRequest, AISearchResponse
from app.search.hybrid import HybridSearchOrchestrator

logger = get_logger("ai.orchestrator")


class AISearchOrchestrator:
    """End-to-end coordinator for Grounded AI Search and Research queries."""

    def __init__(
        self,
        db: Session,
        router: AIProviderRouter | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.db = db
        self.router = router or ai_provider_router
        self.context_builder = context_builder or ContextBuilder()
        self.hybrid_orchestrator = HybridSearchOrchestrator(db)

    def search(self, request: AISearchRequest) -> AISearchResponse:
        """Execute end-to-end RAG pipeline for the given query.

        Args:
            request: Validated AISearchRequest.

        Returns:
            AISearchResponse with grounded answer, verified citations, and execution telemetry.
        """
        start_time = time.perf_counter()
        query = (request.query or "").strip()

        # Step 1: Validate Query
        if not query:
            return AISearchResponse(
                query="",
                answer="Please provide a valid question to search.",
                report="Please provide a valid question to search.",
                citations=[],
                sources=[],
                provider="none",
                model="none",
                status="insufficient_evidence",
                execution_metadata={"duration_ms": 0.0},
            )

        # Step 2: Evidence Retrieval via Hybrid Search
        t_retrieval_start = time.perf_counter()
        search_set, degraded, search_meta = self.hybrid_orchestrator.search(
            query=query,
            page=1,
            per_page=request.page_size,
            domain=request.domain,
            language=request.language,
        )
        retrieval_ms = round((time.perf_counter() - t_retrieval_start) * 1000, 2)

        # Step 3: Context Building & Injection Sanitization
        context_result = self.context_builder.build_context(search_set.results, query=query, db=self.db)

        # Step 4: Check Evidence Sufficiency
        if not context_result.has_sufficient_evidence:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            insufficient_msg = (
                "Based on the documents currently indexed in LUMO, there is insufficient evidence "
                "to answer this question accurately."
            )
            return AISearchResponse(
                query=query,
                answer=insufficient_msg,
                report=insufficient_msg,
                citations=[],
                sources=[],
                provider="none",
                model="none",
                fallback_used=False,
                status="insufficient_evidence",
                execution_metadata={
                    "retrieval_duration_ms": retrieval_ms,
                    "total_duration_ms": elapsed_ms,
                    "hybrid_retrieved": len(search_set.results),
                    "search_degraded": degraded,
                },
            )

        # Step 5: Grounded Answer Generation via Provider Router
        system_prompt = AI_SEARCH_SYSTEM_PROMPT
        user_prompt = build_user_prompt(query, context_result.formatted_context)

        t_gen_start = time.perf_counter()
        try:
            ai_resp, fallback_used, active_provider = self.router.execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                requested_provider=request.provider,
            )
            generation_ms = round((time.perf_counter() - t_gen_start) * 1000, 2)
        except AIProviderAuthError as exc:
            logger.warning("AI provider authentication failure: %s", exc)
            err_msg = f"AI Search unavailable: {exc}"
            return self._build_error_response(query, err_msg, "auth_error", start_time, retrieval_ms)
        except AIProviderRateLimitError as exc:
            logger.warning("AI provider rate limit: %s", exc)
            err_msg = "AI Search rate limit reached. Please try again in a few moments."
            return self._build_error_response(query, err_msg, "rate_limited", start_time, retrieval_ms)
        except AIProviderTimeoutError as exc:
            logger.warning("AI provider timeout: %s", exc)
            err_msg = "AI provider timed out while generating an answer."
            return self._build_error_response(query, err_msg, "timeout", start_time, retrieval_ms)
        except AIProviderUnavailableError as exc:
            logger.warning("AI provider unavailable: %s", exc)
            err_msg = f"AI provider unavailable: {exc}"
            return self._build_error_response(query, err_msg, "unavailable", start_time, retrieval_ms)
        except AIProviderError as exc:
            logger.warning("AI provider error: %s", exc)
            err_msg = f"AI provider error: {exc}"
            return self._build_error_response(query, err_msg, "provider_error", start_time, retrieval_ms)
        except Exception as exc:
            logger.error("Unexpected error in AI generation: %s", exc, exc_info=True)
            err_msg = "An unexpected error occurred during AI search generation."
            return self._build_error_response(query, err_msg, "internal_error", start_time, retrieval_ms)

        # Step 6: Citation Validation & Extraction
        validator = CitationValidator(context_result.source_map)
        cleaned_answer, verified_citations, all_sources = validator.validate_and_extract(ai_resp.content)

        # Step 7: Build Report Markdown (for research interface compatibility)
        report_sections = [cleaned_answer]
        if verified_citations:
            report_sections.append("\n\n### Verified Sources & Citations")
            for c in verified_citations:
                report_sections.append(f"- **{c.citation_id}** [{c.title}]({c.url}) ({c.domain})")
        report_text = "\n".join(report_sections)

        total_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return AISearchResponse(
            query=query,
            answer=cleaned_answer,
            report=report_text,
            citations=verified_citations,
            sources=all_sources,
            provider=active_provider,
            model=ai_resp.model,
            fallback_used=fallback_used,
            status="success",
            execution_metadata={
                "retrieval_duration_ms": retrieval_ms,
                "generation_duration_ms": generation_ms,
                "total_duration_ms": total_ms,
                "prompt_tokens": ai_resp.prompt_tokens,
                "completion_tokens": ai_resp.completion_tokens,
                "total_tokens": ai_resp.total_tokens,
                "sources_retrieved": len(search_set.results),
                "sources_used_in_context": len(context_result.sources),
                "citations_count": len(verified_citations),
                "search_degraded": degraded,
            },
        )

    def _build_error_response(
        self,
        query: str,
        message: str,
        status: str,
        start_time: float,
        retrieval_ms: float,
    ) -> AISearchResponse:
        total_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return AISearchResponse(
            query=query,
            answer=message,
            report=message,
            citations=[],
            sources=[],
            provider="none",
            model="none",
            fallback_used=False,
            status=status,
            execution_metadata={
                "retrieval_duration_ms": retrieval_ms,
                "total_duration_ms": total_ms,
                "error": message,
            },
        )
