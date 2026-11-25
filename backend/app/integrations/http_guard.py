"""SSRF-safe HTTP client, rate limiter, and secret sealing for Phase 22 Integrations."""

from __future__ import annotations

import base64
from collections import defaultdict, deque
import hashlib
import hmac
import threading
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.logging import get_logger
from app.crawler.validator import validate_and_screen_url
from app.intelligence.security import redact_secrets

logger = get_logger("integrations.http")

MAX_INTEGRATION_BYTES = 5 * 1024 * 1024  # 5 MB response cap
MAX_REDIRECTS = 5
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)

# Local symmetric key derivation for at-rest token obfuscation in SQLite/PostgreSQL
_LOCAL_SEAL_SEED = hashlib.sha256(b"lumo-local-integration-seal-v1").digest()


def seal_secret(plaintext: str) -> str:
    """Seal an integration API token before DB storage (never stored as raw JSON config)."""
    raw = plaintext.encode("utf-8")
    stream = hashlib.sha256(_LOCAL_SEAL_SEED + len(raw).to_bytes(4, "big")).digest()
    xored = bytes(b ^ stream[i % len(stream)] for i, b in enumerate(raw))
    mac = hmac.new(_LOCAL_SEAL_SEED, xored, hashlib.sha256).digest()[:12]
    return base64.urlsafe_b64encode(mac + xored).decode("ascii")


def unseal_secret(sealed: str | None) -> str | None:
    if not sealed:
        return None
    try:
        blob = base64.urlsafe_b64decode(sealed.encode("ascii"))
        mac, xored = blob[:12], blob[12:]
        expected = hmac.new(_LOCAL_SEAL_SEED, xored, hashlib.sha256).digest()[:12]
        if not hmac.compare_digest(mac, expected):
            return None
        stream = hashlib.sha256(_LOCAL_SEAL_SEED + len(xored).to_bytes(4, "big")).digest()
        return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(xored)).decode("utf-8")
    except Exception:
        return None


def _check_rate_limit(integration_id: str, rpm: int = 30) -> None:
    now = time.monotonic()
    with _RATE_LOCK:
        q = _RATE_BUCKETS[integration_id]
        while q and (now - q[0]) > 60.0:
            q.popleft()
        if len(q) >= max(rpm, 1):
            raise RuntimeError(f"Rate limit exceeded for integration '{integration_id}' ({rpm} req/min).")
        q.append(now)


def safe_integration_fetch(
    url: str,
    integration_id: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 12.0,
    max_bytes: int = MAX_INTEGRATION_BYTES,
    rate_limit_rpm: int = 30,
) -> tuple[int, dict[str, str], bytes, str]:
    """Fetch external URL with per-hop SSRF screening, redirect checks, size caps, and retries."""
    _check_rate_limit(integration_id, rpm=rate_limit_rpm)
    req_headers = {"User-Agent": "LUMO-Integration-Client/1.0", **(headers or {})}
    current_url = url

    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                target = current_url
                for hop in range(MAX_REDIRECTS + 1):
                    val = validate_and_screen_url(target)
                    if not val.is_valid:
                        raise ValueError(f"SSRF guard blocked '{target}': {val.error}")

                    resp = client.get(target, headers=req_headers, params=params if hop == 0 else None)
                    if resp.is_redirect:
                        loc = resp.headers.get("location")
                        if not loc:
                            raise ValueError("Redirect response missing Location header.")
                        target = urljoin(target, loc)
                        continue

                    if resp.status_code in (429, 503) and attempt == 0:
                        time.sleep(0.5)
                        break

                    if len(resp.content) > max_bytes:
                        raise ValueError(f"Response exceeds {max_bytes // (1024 * 1024)} MB safety limit.")

                    resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                    return resp.status_code, resp_headers, resp.content, target
                else:
                    raise ValueError(f"Exceeded maximum redirects ({MAX_REDIRECTS}).")
        except httpx.RequestError as exc:
            if attempt == 1:
                raise RuntimeError(f"Network error ({type(exc).__name__}): {redact_secrets(str(exc))}") from exc
            time.sleep(0.3)

    raise RuntimeError("External request failed after retry.")
