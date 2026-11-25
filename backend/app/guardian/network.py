"""Guardian Network Inspector: Safe redirect tracing, DNS verification, and TLS certificate metadata."""

from __future__ import annotations

from datetime import datetime, timezone
import socket
import ssl
from typing import Any
from urllib.parse import urljoin, urlparse

import urllib3
from urllib3.util import parse_url

from app.config import get_settings
from app.core.logging import get_logger
from app.guardian.validator import validate_guardian_url
from app.schemas.guardian import GuardianFinding

logger = get_logger("guardian.network")


class SafeNetworkInspector:
    """Safely probes HTTP/HTTPS redirect chains and TLS certificates with strict per-hop SSRF validation."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def inspect_url(
        self,
        initial_url: str,
        max_redirects: int | None = None,
        timeout: float | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[GuardianFinding]]:
        """Trace redirects safely and inspect domain & TLS metadata.

        Returns:
            Tuple of (redirect_chain, domain_info, network_findings)
        """
        chain: list[dict[str, Any]] = []
        domain_info: dict[str, Any] = {}
        findings: list[GuardianFinding] = []

        limit = max_redirects or self.settings.guardian_max_redirects
        to_sec = timeout or self.settings.guardian_request_timeout
        current_url = initial_url
        visited_urls: set[str] = {initial_url}

        # Safe HTTP pool with short timeouts and no automatic redirects
        pool = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=to_sec, read=to_sec),
            retries=False,
            maxsize=4,
        )

        try:
            for hop in range(1, limit + 2):
                # 1. Strictly validate every hop before opening network connection
                val_res = validate_guardian_url(current_url, resolve_dns=True)
                if not val_res.is_valid:
                    findings.append(
                        GuardianFinding(
                            name="Redirection to Prohibited or Malformed Target",
                            description=f"Hop {hop} attempted to navigate to an invalid or blocked address: {val_res.error}",
                            severity="high",
                            evidence=f"Target: {current_url}",
                            recommendation="Do not proceed. The target redirects to an unreachable or prohibited internal destination.",
                        )
                    )
                    chain.append({
                        "hop": hop,
                        "url": current_url,
                        "status": "blocked",
                        "error": val_res.error,
                    })
                    break

                if hop == 1:
                    domain_info["hostname"] = val_res.hostname
                    domain_info["resolved_ips"] = val_res.resolved_ips
                    domain_info["scheme"] = val_res.scheme

                # 2. Make lightweight HEAD request (fallback to GET with range if 405)
                resp = None
                try:
                    resp = pool.request(
                        "HEAD",
                        current_url,
                        headers={"User-Agent": "LUMO-Security-Inspector/1.0", "Accept": "*/*"},
                        redirect=False,
                    )
                    if resp.status == 405:
                        resp.release_conn()
                        resp = pool.request(
                            "GET",
                            current_url,
                            headers={
                                "User-Agent": "LUMO-Security-Inspector/1.0",
                                "Range": "bytes=0-1024",
                            },
                            redirect=False,
                            preload_content=False,
                        )
                except Exception as exc:
                    logger.debug("Network request failed for hop %d (%s): %s", hop, current_url, exc)
                    chain.append({
                        "hop": hop,
                        "url": current_url,
                        "status": "connection_failed",
                        "error": str(exc),
                    })
                    findings.append(
                        GuardianFinding(
                            name="Server Unreachable or Connection Refused",
                            description=f"Could not connect to host at hop {hop}: {exc}",
                            severity="informational",
                            evidence=f"URL: {current_url}",
                            recommendation="Verify that the server is online and port 80/443 is open.",
                        )
                    )
                    break

                status_code = resp.status
                location = resp.headers.get("Location") or resp.headers.get("location")
                content_type = resp.headers.get("Content-Type", "")

                hop_record = {
                    "hop": hop,
                    "url": current_url,
                    "status_code": status_code,
                    "content_type": content_type,
                    "ip": val_res.resolved_ips[0] if val_res.resolved_ips else None,
                }

                # Safe release
                resp.release_conn()

                # Check if this is a redirection (301, 302, 303, 307, 308)
                if status_code in {301, 302, 303, 307, 308} and location:
                    next_url = urljoin(current_url, location)
                    hop_record["redirect_to"] = next_url
                    chain.append(hop_record)

                    # Redirection loop check
                    if next_url in visited_urls:
                        findings.append(
                            GuardianFinding(
                                name="Redirection Loop Detected",
                                description="The redirect chain forms an infinite loop revisiting previously visited URLs.",
                                severity="medium",
                                evidence=f"Loop target: {next_url}",
                                recommendation="Inspect server redirect configuration to resolve routing loops.",
                            )
                        )
                        break

                    visited_urls.add(next_url)

                    # Check scheme downgrade (HTTPS -> HTTP)
                    if current_url.startswith("https://") and next_url.startswith("http://"):
                        findings.append(
                            GuardianFinding(
                                name="Insecure Protocol Downgrade During Redirection",
                                description="The redirect chain dropped encryption from HTTPS to plaintext HTTP.",
                                severity="high",
                                evidence=f"Downgrade to: {next_url}",
                                recommendation="Avoid visiting unencrypted destinations that downgrade from secure connections.",
                            )
                        )

                    current_url = next_url

                    if hop > limit:
                        findings.append(
                            GuardianFinding(
                                name="Excessive Redirects Limit Exceeded",
                                description=f"The redirect chain exceeded the maximum allowed limit of {limit} hops.",
                                severity="medium",
                                evidence=f"Exceeded at hop {hop}",
                                recommendation="Investigate the redirect chain for masking or obfuscation techniques.",
                            )
                        )
                        break
                else:
                    # Final destination reached
                    chain.append(hop_record)
                    domain_info["final_destination"] = current_url
                    domain_info["final_status_code"] = status_code
                    break

        finally:
            pool.clear()

        # 3. Safe TLS Certificate Inspection (if HTTPS)
        parsed_target = urlparse(initial_url)
        if parsed_target.scheme.lower() == "https" and domain_info.get("resolved_ips"):
            tls_meta, tls_findings = self._inspect_tls_certificate(parsed_target.hostname or "", to_sec)
            domain_info["tls_certificate"] = tls_meta
            findings.extend(tls_findings)

        return chain, domain_info, findings

    def _inspect_tls_certificate(self, hostname: str, timeout: float) -> tuple[dict[str, Any], list[GuardianFinding]]:
        """Safely fetch TLS certificate without downloading page content."""
        tls_info: dict[str, Any] = {}
        findings: list[GuardianFinding] = []

        context = ssl.create_default_context()
        try:
            with socket.create_connection((hostname, 443), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if cert:
                        subject_dict = dict(x[0] for x in cert.get("subject", ()))
                        issuer_dict = dict(x[0] for x in cert.get("issuer", ()))
                        sans = [x[1] for x in cert.get("subjectAltName", ()) if x[0] == "DNS"]

                        tls_info["subject_cn"] = subject_dict.get("commonName", "")
                        tls_info["issuer_cn"] = issuer_dict.get("commonName", "")
                        tls_info["issuer_o"] = issuer_dict.get("organizationName", "")
                        tls_info["not_after"] = cert.get("notAfter", "")
                        tls_info["not_before"] = cert.get("notBefore", "")
                        tls_info["sans"] = sans[:10]
                        tls_info["version"] = ssock.version()
                        tls_info["cipher"] = ssock.cipher()

                        # Check certificate expiration
                        try:
                            # Format: 'May 10 12:00:00 2027 GMT'
                            expiry = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                            if expiry < datetime.now(timezone.utc):
                                findings.append(
                                    GuardianFinding(
                                        name="Expired TLS Certificate",
                                        description=f"The server TLS certificate expired on {cert['notAfter']}.",
                                        severity="high",
                                        evidence=f"Expired: {cert['notAfter']}",
                                        recommendation="Do not trust this connection; expired certificates cannot guarantee transport security.",
                                    )
                                )
                        except Exception:
                            pass

        except ssl.SSLCertVerificationError as exc:
            findings.append(
                GuardianFinding(
                    name="Invalid or Untrusted TLS Certificate",
                    description=f"Certificate verification failed: {exc}",
                    severity="high",
                    evidence=str(exc),
                    recommendation="The connection is untrusted (self-signed, untrusted CA, or hostname mismatch).",
                )
            )
            tls_info["verification_error"] = str(exc)
        except Exception as exc:
            logger.debug("TLS inspection skipped/failed for %s: %s", hostname, exc)
            tls_info["inspection_error"] = str(exc)

        return tls_info, findings
