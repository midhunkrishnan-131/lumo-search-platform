"""LUMO FastAPI application."""

import hmac
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.health import (
    HealthResponse,
    ReadinessResponse,
    health_payload,
    readiness_payload,
    router as health_router,
)
from app.api.routes.crawler import router as crawler_router
from app.api.routes.documents import router as documents_router
from app.api.routes.search import router as search_router
from app.api.routes.history import router as history_router
from app.api.routes.semantic import router as semantic_router
from app.api.routes.ai_search import router as ai_search_router
from app.api.routes.research import router as research_router
from app.api.routes.guardian import router as guardian_router
from app.api.routes.graph import router as graph_router
from app.api.routes.workspace import router as workspace_router
from app.api.routes.extension import router as extension_router
from app.api.routes.local_ai import router as local_ai_router
from app.api.routes.automation import (
    automations_router,
    executions_router,
    notifications_router,
)
from app.api.routes.personalization import router as personalization_router
from app.api.routes.intelligence import router as intelligence_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.ops import router as ops_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.developer import router as developer_router
from app.api.routes.evaluation import benchmarks_router as eval_benchmarks_router, datasets_router as eval_datasets_router
from app.api.routes.workflows import router as workflows_router
from app.api.routes.knowledge_hub import router as knowledge_hub_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.studio import router as studio_router
from app.automation.engine import automation_manager
from app.developer.service import (
    DeveloperPlatformService,
    check_key_rate_limit,
    resolve_required_permission,
)
from app.evaluation.runner import EvaluationManager
from app.intelligence.ingestion import UniversalIngestionPipeline
from app.ops.migrations import apply_safe_migrations
from app.config import Settings, get_settings, validate_startup_config
from app.core.logging import get_logger, reset_request_context, set_request_context, setup_logging
from app.core.observability import (
    ErrorCategory,
    classify_exception,
    classify_http_status,
    observability_registry,
)
from app.database.connection import (
    check_database_connection,
    create_tables,
    dispose_database,
    init_database,
)

logger = get_logger("app")
access_logger = get_logger("access")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    setup_logging(settings.log_level, log_format=settings.log_format, environment=settings.environment)
    cfg_report = validate_startup_config(settings)
    for w in cfg_report["warnings"]:
        logger.warning("Startup config warning: %s", w)
    for e in cfg_report["errors"]:
        logger.error("Startup config error: %s", e)
    logger.info(
        "Application startup: %s version %s (%s)",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
    init_database(settings.database_url)
    if check_database_connection():
        logger.info("Database connection status: available")
        create_tables()
    elif settings.environment != "test":
        logger.warning(
            "Primary database connection unavailable for '%s'. Falling back to SQLite local database.",
            settings.database_url,
        )
        init_database("sqlite:///lumo.db")
        if check_database_connection():
            logger.info("SQLite local database active: lumo.db")
            create_tables()
    else:
        logger.warning("Database connection status: unavailable")

    if settings.environment != "test" and check_database_connection():
        apply_safe_migrations()

    if settings.environment != "test":
        from app.database.connection import get_session_factory
        factory = get_session_factory()
        if factory is not None:
            with factory() as db:
                automation_manager.recover_interrupted_executions(db)
                UniversalIngestionPipeline.recover_interrupted_jobs(db)
                recovered_evals = EvaluationManager.recover_interrupted_runs(db)
                if recovered_evals:
                    logger.warning("Recovered %d interrupted evaluation run(s) on startup", recovered_evals)
        automation_manager.start_scheduler()

    yield
    automation_manager.stop_scheduler()
    logger.info("Application shutdown started")
    try:
        dispose_database()
    except Exception as exc:
        logger.error("Database shutdown failed (%s)", type(exc).__name__)
    logger.info("Application shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with configuration, logging, routes, and safe errors."""
    cfg = settings or get_settings()
    setup_logging(cfg.log_level, log_format=cfg.log_format, environment=cfg.environment)

    app = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        description=(
            "Local API foundation for LUMO. Health responses do not include "
            "credentials or infrastructure details."
        ),
        lifespan=_lifespan,
        debug=False,
        docs_url=None if cfg.is_production else "/docs",
        redoc_url=None if cfg.is_production else "/redoc",
        openapi_url=None if cfg.is_production else "/openapi.json",
        openapi_tags=[
            {
                "name": "system",
                "description": "Liveness and readiness checks.",
            }
        ],
    )
    app.state.settings = cfg

    _rate_lock = threading.Lock()
    _rate_buckets: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def security_and_rate_guard(request: Request, call_next):
        path = request.url.path
        started = time.perf_counter()
        req_id = request.headers.get("X-Request-ID") or str(__import__("uuid").uuid4())
        corr_id = request.headers.get("X-Correlation-ID") or req_id
        request.state.request_id = req_id
        request.state.correlation_id = corr_id
        ctx_tokens = set_request_context(req_id, corr_id)
        try:
            # Developer API Key authentication & permission check (when X-API-Key or Bearer lumo_pk_... is supplied)
            x_api_key = request.headers.get("X-API-Key", "").strip()
            auth_hdr = request.headers.get("Authorization", "")
            bearer_val = auth_hdr[7:].strip() if auth_hdr.lower().startswith("bearer ") else ""
            dev_raw_key = x_api_key or (bearer_val if bearer_val.startswith("lumo_pk_") else "")
            dev_key_obj = None

            if dev_raw_key and path.startswith("/api/v1") and request.method != "OPTIONS":
                from app.database.connection import get_session_factory
                factory = get_session_factory()
                if factory is not None:
                    with factory() as db:
                        dev_svc = DeveloperPlatformService(db)
                        try:
                            dev_key_obj = dev_svc.validate_raw_key(dev_raw_key)
                        except PermissionError as exc:
                            dev_svc.record_usage(None, path, request.method, 401, 0, rate_limited=False)
                            return JSONResponse(status_code=401, content={"detail": str(exc), "error_category": ErrorCategory.AUTHENTICATION, "request_id": req_id})

                        req_perm = resolve_required_permission(request.method, path)
                        if req_perm and req_perm not in (dev_key_obj.permissions_json or []):
                            dev_svc.record_usage(dev_key_obj, path, request.method, 403, 0, rate_limited=False)
                            return JSONResponse(
                                status_code=403,
                                content={"detail": f"API key lacks required permission '{req_perm}'.", "error_category": ErrorCategory.AUTHORIZATION, "request_id": req_id},
                            )

                        if not check_key_rate_limit(dev_key_obj.id, dev_key_obj.rate_limit_rpm):
                            dev_svc.record_usage(dev_key_obj, path, request.method, 429, 0, rate_limited=True)
                            return JSONResponse(
                                status_code=429,
                                headers={"Retry-After": "60"},
                                content={"detail": "API key rate limit exceeded.", "error_category": ErrorCategory.RESOURCE, "request_id": req_id},
                            )

            # Optional API token boundary for LAN/non-localhost deployments
            expected_token = (cfg.api_auth_token or "").strip()
            if (
                expected_token
                and dev_key_obj is None
                and request.method != "OPTIONS"
                and path.startswith("/api/v1")
                and path not in ("/api/v1/health", "/api/v1/ready", "/api/v1/health/live", "/api/v1/health/ready")
            ):
                x_tok = request.headers.get("X-LUMO-Token", "")
                supplied = bearer_val or x_tok.strip()
                if not supplied or not hmac.compare_digest(supplied, expected_token):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Unauthorized: invalid or missing API token.", "error_category": ErrorCategory.AUTHENTICATION, "request_id": req_id},
                    )

            # Sliding-window per-client rate limiter (disabled in test unless X-Enforce-Rate-Limit=true)
            enforce_rl = cfg.rate_limit_per_minute > 0 and (
                cfg.environment != "test" or request.headers.get("X-Enforce-Rate-Limit") == "true"
            )
            if enforce_rl and path.startswith("/api/v1"):
                client_ip = request.client.host if request.client else "local"
                now = time.monotonic()
                with _rate_lock:
                    q = _rate_buckets[client_ip]
                    while q and (now - q[0]) > 60.0:
                        q.popleft()
                    if len(q) >= cfg.rate_limit_per_minute:
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Rate limit exceeded. Please slow down requests.", "error_category": ErrorCategory.RESOURCE, "request_id": req_id},
                        )
                    q.append(now)

            response = await call_next(request)
            if dev_key_obj is not None:
                from app.database.connection import get_session_factory
                factory = get_session_factory()
                if factory is not None:
                    with factory() as db:
                        DeveloperPlatformService(db).record_usage(
                            dev_key_obj,
                            path,
                            request.method,
                            response.status_code,
                            int((time.perf_counter() - started) * 1000),
                            rate_limited=False,
                        )
            response.headers.setdefault("X-Request-ID", req_id)
            response.headers.setdefault("X-Correlation-ID", corr_id)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
            return response
        finally:
            reset_request_context(ctx_tokens)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        req_id = getattr(request.state, "request_id", request.headers.get("X-Request-ID") or "-")
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            err_cat = classify_exception(exc)
            observability_registry.record_request(
                request.method,
                request.url.path,
                500,
                elapsed_ms,
                req_id,
                slow_threshold_ms=cfg.slow_request_threshold_ms,
            )
            observability_registry.record_error(
                err_cat, type(exc).__name__, request.url.path, request.method, req_id, 500
            )
            access_logger.error(
                "%s %s failed after %.1f ms",
                request.method,
                request.url.path,
                elapsed_ms,
                extra={"error_class": err_cat},
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        observability_registry.record_request(
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            req_id,
            slow_threshold_ms=cfg.slow_request_threshold_ms,
        )
        if response.status_code >= 500:
            observability_registry.record_error(
                classify_http_status(response.status_code),
                f"HTTP_{response.status_code}",
                request.url.path,
                request.method,
                req_id,
                response.status_code,
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if elapsed_ms >= cfg.slow_request_threshold_ms:
            access_logger.warning(
                "Slow request: %s %s -> %s (%.1f ms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        else:
            access_logger.info(
                "%s %s -> %s (%.1f ms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        req_id = getattr(request.state, "request_id", "-")
        cat = classify_http_status(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail, "error_category": cat, "request_id": req_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "-")
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed.",
                "error_category": ErrorCategory.VALIDATION,
                "request_id": req_id,
                "errors": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "-")
        cat = classify_exception(exc)
        observability_registry.record_error(
            cat, type(exc).__name__, request.url.path, request.method, req_id, 500
        )
        logger.error(
            "Unhandled %s on %s %s",
            type(exc).__name__,
            request.method,
            request.url.path,
            exc_info=True,
            extra={"error_class": cat},
        )
        return JSONResponse(
            status_code=500,
            headers={"X-Error-Category": cat, "X-Request-ID": req_id},
            content={"detail": "Internal server error"},
        )

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(health_router)
    api_v1.include_router(crawler_router)
    api_v1.include_router(documents_router)
    api_v1.include_router(search_router)
    api_v1.include_router(history_router)
    api_v1.include_router(semantic_router)
    api_v1.include_router(ai_search_router)
    api_v1.include_router(research_router)
    api_v1.include_router(guardian_router)
    api_v1.include_router(graph_router)
    api_v1.include_router(workspace_router)
    api_v1.include_router(extension_router)
    api_v1.include_router(local_ai_router)
    api_v1.include_router(automations_router)
    api_v1.include_router(executions_router)
    api_v1.include_router(notifications_router)
    api_v1.include_router(personalization_router)
    api_v1.include_router(intelligence_router)
    api_v1.include_router(dashboard_router)
    api_v1.include_router(ops_router)
    api_v1.include_router(integrations_router)
    api_v1.include_router(developer_router)
    api_v1.include_router(eval_benchmarks_router)
    api_v1.include_router(eval_datasets_router)
    api_v1.include_router(workflows_router)
    api_v1.include_router(knowledge_hub_router)
    api_v1.include_router(retrieval_router)
    api_v1.include_router(studio_router)
    app.include_router(api_v1)

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Liveness alias",
    )
    def health_alias(request: Request) -> HealthResponse:
        """Match the existing settings page, which calls GET /health."""
        return health_payload(request.app.state.settings)

    @app.get(
        "/health/live",
        response_model=HealthResponse,
        tags=["system"],
        summary="Root Liveness Probe",
    )
    def root_health_live(request: Request) -> HealthResponse:
        return health_payload(request.app.state.settings)

    @app.get(
        "/health/ready",
        response_model=ReadinessResponse,
        tags=["system"],
        summary="Root Readiness Probe",
        responses={503: {"model": ReadinessResponse}},
    )
    def root_health_ready(request: Request, response: Response) -> ReadinessResponse:
        payload = readiness_payload(request.app.state.settings)
        if payload.status != "ready":
            response.status_code = 503
        return payload

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_origin_regex=r"^(chrome-extension|moz-extension|extension)://[a-zA-Z0-9_-]+$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "Authorization", "X-API-Key", "X-LUMO-Token", "X-LUMO-Owner", "X-Request-ID", "X-Correlation-ID", "X-History-Disabled"],
    )
    return app


app = create_app()
