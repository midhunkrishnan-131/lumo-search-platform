"""Guardian URL Validator: SSRF prevention, scheme enforcement, and safe DNS pre-resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import re
import socket
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.crawler.validator import BLOCKED_HOSTNAMES, is_prohibited_ip, normalize_url

logger = get_logger("guardian.validator")

ALLOWED_GUARDIAN_SCHEMES = {"http", "https"}


@dataclass
class GuardianUrlValidationResult:
    """Outcome of defensive URL validation."""

    is_valid: bool
    normalized_url: str = ""
    scheme: str = ""
    hostname: str = ""
    port: int = 80
    resolved_ips: list[str] = field(default_factory=list)
    is_blocked: bool = False
    error: str | None = None


def validate_guardian_url(url: str, resolve_dns: bool = True) -> GuardianUrlValidationResult:
    """Strictly validate and normalize a candidate URL for defensive security analysis."""
    clean_url = (url or "").strip()
    if not clean_url:
        return GuardianUrlValidationResult(is_valid=False, error="URL cannot be empty.")

    try:
        parsed = urlparse(clean_url)
    except Exception as exc:
        return GuardianUrlValidationResult(is_valid=False, error=f"Malformed URL: {exc}")

    # 1. Scheme check
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_GUARDIAN_SCHEMES:
        return GuardianUrlValidationResult(
            is_valid=False,
            is_blocked=True,
            error=f"Unsupported scheme '{scheme}'. Only HTTP and HTTPS are permitted for security analysis.",
        )

    # 2. Reject embedded credentials (user:pass@host)
    if parsed.username or parsed.password:
        return GuardianUrlValidationResult(
            is_valid=False,
            is_blocked=True,
            error="URLs with embedded user credentials (user:pass@host) are rejected for safety.",
        )

    # 3. Hostname checks
    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return GuardianUrlValidationResult(is_valid=False, error="URL hostname cannot be empty.")

    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".internal") or hostname.endswith(".local"):
        return GuardianUrlValidationResult(
            is_valid=False,
            is_blocked=True,
            hostname=hostname,
            error=f"Prohibited internal hostname '{hostname}'. Requests to internal/local names are strictly blocked.",
        )

    port = parsed.port or (443 if scheme == "https" else 80)
    normalized = normalize_url(clean_url)

    # 4. Check if hostname is directly an IP literal
    resolved_ips: list[str] = []
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if is_prohibited_ip(ip_obj):
            return GuardianUrlValidationResult(
                is_valid=False,
                is_blocked=True,
                hostname=hostname,
                resolved_ips=[str(ip_obj)],
                error=f"Blocked destination IP address '{ip_obj}' belongs to a private, loopback, or reserved range.",
            )
        resolved_ips.append(str(ip_obj))
    except ValueError:
        # Hostname is a domain name, proceed to safe DNS resolution if enabled
        if resolve_dns:
            try:
                addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
                for item in addr_info:
                    ip_str = item[4][0]
                    ip_obj = ipaddress.ip_address(ip_str)
                    if is_prohibited_ip(ip_obj):
                        logger.warning("SSRF blocked: '%s' resolved to protected IP %s", hostname, ip_str)
                        return GuardianUrlValidationResult(
                            is_valid=False,
                            is_blocked=True,
                            hostname=hostname,
                            resolved_ips=[ip_str],
                            error=f"SSRF blocked: Domain '{hostname}' resolved to prohibited IP '{ip_str}'.",
                        )
                    if ip_str not in resolved_ips:
                        resolved_ips.append(ip_str)
            except (socket.gaierror, socket.herror) as exc:
                # DNS resolution failure does not crash the validator; it is captured as unresolvable
                logger.debug("DNS resolution failed for %s: %s", hostname, exc)

    return GuardianUrlValidationResult(
        is_valid=True,
        normalized_url=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        resolved_ips=resolved_ips,
    )
