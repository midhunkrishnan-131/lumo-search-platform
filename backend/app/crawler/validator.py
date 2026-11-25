"""URL validation, normalization, and SSRF defense module.

Enforces strict boundary checks on web addresses:
- Allows HTTP and HTTPS only.
- Rejects localhost, loopback, private, link-local, multicast, and reserved IP ranges.
- Restricts destination ports to standard web ports (80, 443) by default.
- Performs DNS resolution to prevent DNS rebinding to internal infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.core.logging import get_logger

logger = get_logger("crawler.validator")

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}

# Prohibited internal or special-purpose hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "loopback",
    "internal",
    "local",
    "home",
    "lan",
    "corp",
    "metadata.google.internal",
    "metadata.aws.internal",
    "instance-data",
}

# Special-purpose IP networks that must be strictly rejected
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),         # Private RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Address / Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-Local
    ipaddress.ip_network("172.16.0.0/12"),      # Private RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),     # Private RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),      # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("fc00::/7"),           # Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-Local
    ipaddress.ip_network("ff00::/8"),           # Multicast
]


@dataclass
class ValidationResult:
    """Outcome of URL validation and SSRF screening."""
    is_valid: bool
    normalized_url: str = ""
    error: str | None = None
    resolved_ips: list[str] = field(default_factory=list)


def is_prohibited_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address belongs to any prohibited or private range."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        if is_prohibited_ip(ip.ipv4_mapped):
            return True

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    for network in PROHIBITED_NETWORKS:
        if ip in network:
            return True

    return False


def normalize_url(url: str) -> str:
    """Produce a canonical normalized form for deduplication and storage."""
    url = url.strip()
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Drop explicit standard ports
    if ":" in netloc:
        host, _, port = netloc.partition(":")
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = parsed.path or "/"
    # Clean up double slashes in path
    while "//" in path:
        path = path.replace("//", "/")

    # Normalize query string (sorted keys, drop fragments)
    query = ""
    if parsed.query:
        sorted_params = sorted(parse_qsl(parsed.query, keep_blank_values=True))
        query = urlencode(sorted_params)

    return urlunparse((scheme, netloc, path, "", query, ""))


def validate_and_screen_url(
    url: str,
    resolve_dns: bool = True,
    allowed_schemes: set[str] | None = None,
    allowed_ports: set[int] | None = None,
) -> ValidationResult:
    """Validate URL syntax, scheme, port, hostname, and resolve DNS for SSRF check."""
    if allowed_schemes is None:
        allowed_schemes = ALLOWED_SCHEMES
    if allowed_ports is None:
        allowed_ports = ALLOWED_PORTS

    if not url or not isinstance(url, str):
        return ValidationResult(is_valid=False, error="URL must not be empty.")

    url = url.strip()
    if len(url) > 2048:
        return ValidationResult(is_valid=False, error="URL exceeds maximum length of 2048 characters.")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        return ValidationResult(is_valid=False, error=f"Malformed URL: {exc}")

    # 1. Scheme check
    scheme = parsed.scheme.lower()
    if not scheme:
        return ValidationResult(is_valid=False, error="Missing URL scheme (e.g. http:// or https://).")
    if scheme not in allowed_schemes:
        return ValidationResult(
            is_valid=False,
            error=f"Unsupported scheme '{scheme}'. Only HTTP and HTTPS are permitted.",
        )

    if parsed.username or parsed.password:
        return ValidationResult(
            is_valid=False,
            error="URLs with embedded user credentials (user:pass@host) are rejected.",
        )

    # 2. Hostname check
    hostname = parsed.hostname
    if not hostname:
        return ValidationResult(is_valid=False, error="URL does not contain a valid hostname.")

    hostname_lower = hostname.lower()

    # Reject internal/special domain patterns
    if (
        hostname_lower in BLOCKED_HOSTNAMES
        or hostname_lower.endswith(".localhost")
        or hostname_lower.endswith(".local")
        or hostname_lower.endswith(".internal")
        or hostname_lower.endswith(".lan")
    ):
        return ValidationResult(
            is_valid=False,
            error=f"Access to internal hostname '{hostname}' is prohibited.",
        )

    # 3. Port check
    port = parsed.port or (443 if scheme == "https" else 80)
    if port not in allowed_ports:
        return ValidationResult(
            is_valid=False,
            error=f"Port {port} is not allowed. Only ports {sorted(allowed_ports)} are permitted.",
        )

    normalized = normalize_url(url)
    resolved_ips: list[str] = []

    # 4. IP check (direct IP literal or DNS resolution)
    # Check if host is direct IP address literal
    try:
        direct_ip = ipaddress.ip_address(hostname_lower)
        if is_prohibited_ip(direct_ip):
            return ValidationResult(
                is_valid=False,
                normalized_url=normalized,
                error=f"Access to prohibited IP address '{direct_ip}' is blocked.",
                resolved_ips=[str(direct_ip)],
            )
        resolved_ips.append(str(direct_ip))
    except ValueError:
        # Host is a domain name, resolve via DNS
        if resolve_dns:
            try:
                addr_info = socket.getaddrinfo(
                    hostname_lower,
                    port,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as exc:
                return ValidationResult(
                    is_valid=False,
                    normalized_url=normalized,
                    error=f"DNS resolution failed for '{hostname}': {exc}",
                )
            except Exception as exc:
                return ValidationResult(
                    is_valid=False,
                    normalized_url=normalized,
                    error=f"DNS lookup error for '{hostname}': {exc}",
                )

            for item in addr_info:
                sockaddr = item[4]
                ip_str = sockaddr[0]
                try:
                    ip_obj = ipaddress.ip_address(ip_str)
                    if is_prohibited_ip(ip_obj):
                        return ValidationResult(
                            is_valid=False,
                            normalized_url=normalized,
                            error=f"Domain '{hostname}' resolves to prohibited internal address '{ip_str}'.",
                            resolved_ips=resolved_ips + [ip_str],
                        )
                    if ip_str not in resolved_ips:
                        resolved_ips.append(ip_str)
                except ValueError:
                    continue

            if not resolved_ips:
                return ValidationResult(
                    is_valid=False,
                    normalized_url=normalized,
                    error=f"Domain '{hostname}' has no routable IP addresses.",
                )

    return ValidationResult(
        is_valid=True,
        normalized_url=normalized,
        resolved_ips=resolved_ips,
    )
