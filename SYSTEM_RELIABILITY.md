# LUMO System Reliability (Phase 26)

## Architecture Overview
- **Startup Validation**: `validate_startup_config()` checks `LOG_FORMAT`, `AI_REQUEST_TIMEOUT`, `SLOW_REQUEST_THRESHOLD_MS`, `AI_MAX_RETRIES`, and production security/database settings on boot.
- **Database Fallback & Recovery**: Primary DB failure in non-test environments falls back safely to local SQLite (`lumo.db`), runs non-destructive schema migrations (`apply_safe_migrations()`), and recovers interrupted background jobs (`automation_manager`, `UniversalIngestionPipeline`, `EvaluationManager.recover_interrupted_runs`).
- **Graceful Shutdown**: Stops the automation scheduler and disposes database connection pools cleanly in `_lifespan`.
- **Resource Guards**: Bounded file upload limits (`5 MB` datasets, `25 MB` Guardian, `2 MB` synthetic eval fixtures), temporary file cleanup via `tempfile.TemporaryDirectory`, and rate limiting.
