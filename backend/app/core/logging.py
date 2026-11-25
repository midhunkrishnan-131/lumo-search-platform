"""Logging setup that keeps credentials out of rendered log lines."""

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


class RedactingFormatter(logging.Formatter):
    """Render log records with URL passwords and API credentials replaced."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        rendered = _CREDENTIAL_IN_URL.sub(r"\1***@", rendered)
        for pat in _API_KEY_PATTERNS:
            if pat.groups >= 1 and ("key=" in pat.pattern or "Bearer" in pat.pattern):
                rendered = pat.sub(r"\1[REDACTED]", rendered)
            else:
                rendered = pat.sub("[REDACTED]", rendered)
        return rendered


def setup_logging(level_name: str) -> None:
    """Configure the LUMO logger once and redact secrets in its output."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if not any(getattr(handler, "_lumo_handler", False) for handler in logger.handlers):
        fmt = RedactingFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(fmt)
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
            file_handler.setFormatter(fmt)
            file_handler._lumo_handler = True  # type: ignore[attr-defined]
            logger.addHandler(file_handler)
        except OSError:
            pass

    # Driver and pool loggers can include a full connection URL. Keep them quiet.
    logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)
    logging.getLogger("psycopg").setLevel(logging.CRITICAL)


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the lumo namespace."""
    suffix = name.strip(".")
    if not suffix:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}")
