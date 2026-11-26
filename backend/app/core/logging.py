"""Centralized logging setup with secret redaction, correlation IDs, and optional JSON output."""

from __future__ import annotations

import contextvars
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from typing import Final

_CREDENTIAL_IN_URL: Final[re.Pattern[str]] = re.compile(r"(://[^:/\s]+:)[^@/\s]+@")
_API_KEY_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(AIza[0-9A-Za-z_-]{20,})"),
    re.compile(r"(AQ\.[0-9A-Za-z_-]{20,})"),
    re.compile(r"(grok_[0-9A-Za-z_]{20,})"),
    re.compile(r"(xai-[0-9A-Za-z_-]{20,})"),
    re.compile(r"(lumo_pk_[0-9A-Za-z_-]{16,})"),
    re.compile(r"([?&]key=)[^&\s]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[0-9A-Za-z._-]+", re.IGNORECASE),
)
_LOGGER_NAME: Final[str] = "lumo"

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("lumo_request_id", default="-")
_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("lumo_correlation_id", default="-")


def set_request_context(request_id: str, correlation_id: str | None = None) -> tuple[contextvars.Token[str], contextvars.Token[str]]:
    """Bind request_id and correlation_id to the current async/thread context."""
    t1 = _request_id_var.set(request_id or "-")
    t2 = _correlation_id_var.set(correlation_id or request_id or "-")
    return t1, t2


def reset_request_context(tokens: tuple[contextvars.Token[str], contextvars.Token[str]]) -> None:
    _request_id_var.reset(tokens[0])
    _correlation_id_var.reset(tokens[1])


def get_request_context() -> dict[str, str]:
    return {
        "request_id": _request_id_var.get(),
        "correlation_id": _correlation_id_var.get(),
    }


def redact_secrets(text: str) -> str:
    """Strip passwords in URLs, API keys, and Bearer tokens from log strings."""
    rendered = _CREDENTIAL_IN_URL.sub(r"\1***@", text)
    for pat in _API_KEY_PATTERNS:
        if pat.groups >= 1 and ("key=" in pat.pattern or "Bearer" in pat.pattern):
            rendered = pat.sub(r"\1[REDACTED]", rendered)
        else:
            rendered = pat.sub("[REDACTED]", rendered)
    return rendered


class RedactingFormatter(logging.Formatter):
    """Render plain-text log records with correlation IDs and secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_request_context()
        record.request_id = getattr(record, "request_id", ctx["request_id"])
        record.correlation_id = getattr(record, "correlation_id", ctx["correlation_id"])
        return redact_secrets(super().format(record))


class StructuredJsonFormatter(logging.Formatter):
    """Render structured JSON log lines with correlation IDs and secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_request_context()
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "request_id": getattr(record, "request_id", ctx["request_id"]),
            "correlation_id": getattr(record, "correlation_id", ctx["correlation_id"]),
            "message": redact_secrets(record.getMessage()),
        }
        error_class = getattr(record, "error_class", None)
        if error_class:
            payload["error_class"] = error_class
        if record.exc_info:
            payload["stack_trace"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level_name: str, log_format: str = "auto", environment: str = "development") -> None:
    """Configure the LUMO logger with rotation, correlation IDs, and secret redaction."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    resolved_fmt = log_format.lower().strip()
    if resolved_fmt == "auto":
        resolved_fmt = "json" if environment.lower().strip() == "production" else "text"

    formatter: logging.Formatter = (
        StructuredJsonFormatter()
        if resolved_fmt == "json"
        else RedactingFormatter("%(asctime)s | %(levelname)s | %(name)s | req=%(request_id)s | %(message)s")
    )

    if not any(getattr(handler, "_lumo_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler._lumo_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

        try:
            log_dir = Path(__file__).resolve().parents[2] / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_dir / "lumo.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler._lumo_handler = True  # type: ignore[attr-defined]
            logger.addHandler(file_handler)
        except OSError:
            pass
    else:
        for handler in logger.handlers:
            if getattr(handler, "_lumo_handler", False):
                handler.setFormatter(formatter)

    # Driver and pool loggers can include a full connection URL. Keep them quiet.
    logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)
    logging.getLogger("psycopg").setLevel(logging.CRITICAL)


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the lumo namespace."""
    suffix = name.strip(".")
    if not suffix:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}")
