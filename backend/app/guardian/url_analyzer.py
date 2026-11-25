"""Guardian URL Analyzer: Pure static structural analysis, pattern inspection, and risk indicators."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse

from app.schemas.guardian import GuardianFinding

KNOWN_SHORTENERS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "is.gd",
    "ow.ly",
    "buff.ly",
    "cutt.ly",
    "goo.gl",
    "rebrand.ly",
    "shorte.st",
    "v.gd",
    "bl.ink",
}

SUSPICIOUS_REDIRECT_PARAMS = {
    "url",
    "redirect",
    "redirect_url",
    "redirect_uri",
    "dest",
    "destination",
    "target",
    "next",
    "goto",
    "link",
    "r",
    "return",
    "return_url",
    "out",
    "view",
}

SUSPICIOUS_EXTENSIONS = {
    ".exe": "Windows Executable binary",
    ".scr": "Screensaver executable",
    ".bat": "Windows Batch command script",
    ".cmd": "Windows Command script",
    ".vbs": "VBScript executable script",
    ".ps1": "PowerShell command script",
    ".apk": "Android application package",
    ".dmg": "macOS disk image installer",
    ".iso": "Raw disk image / container",
    ".jar": "Java archive executable",
    ".msi": "Windows installer package",
    ".pif": "Program information file",
    ".hta": "HTML Application executable",
}

DECEPTIVE_BRAND_KEYWORDS = {
    "paypal",
    "apple",
    "microsoft",
    "google",
    "netflix",
    "amazon",
    "bank",
    "chase",
    "wellsfargo",
    "login",
    "secure",
    "account-verify",
    "signin",
}


class UrlStructureAnalyzer:
    """Analyzes URL syntax, hostname, path, query parameters, and encoding for defensive indicators."""

    def analyze(self, raw_url: str, normalized_url: str) -> tuple[list[GuardianFinding], dict[str, Any]]:
        findings: list[GuardianFinding] = []
        metadata: dict[str, Any] = {}

        parsed = urlparse(normalized_url)
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        path = parsed.path
        query = parsed.query

        metadata["scheme"] = scheme
        metadata["hostname"] = hostname
        metadata["path"] = path
        metadata["query"] = query
        metadata["url_length"] = len(raw_url)

        # 1. Scheme Check
        if scheme == "http":
            findings.append(
                GuardianFinding(
                    name="Insecure HTTP Scheme",
                    description="The URL uses plaintext unencrypted HTTP rather than HTTPS.",
                    severity="medium",
                    evidence=f"Scheme: {scheme}://",
                    recommendation="Avoid transmitting credentials, sensitive data, or downloading executables over unencrypted HTTP.",
                )
            )

        # 2. IP Literal as Hostname
        is_ip_host = False
        try:
            ipaddress.ip_address(hostname)
            is_ip_host = True
            findings.append(
                GuardianFinding(
                    name="IP Address Literal in Hostname",
                    description="The URL accesses a server directly by numeric IP address rather than a registered domain name.",
                    severity="medium",
                    evidence=f"Hostname is raw IP: {hostname}",
                    recommendation="Verify the intended service. Legitimate services typically use established domain names with certificates.",
                )
            )
        except ValueError:
            is_ip_host = False

        # 3. Unicode / Punycode / Homograph Checks
        if "xn--" in hostname:
            findings.append(
                GuardianFinding(
                    name="Punycode / Internationalized Domain (IDN)",
                    description="The hostname uses Punycode encoding (xn-- prefix), which can be used in homograph attacks to impersonate familiar characters.",
                    severity="medium",
                    evidence=f"Punycode hostname: {hostname}",
                    recommendation="Inspect the decoded unicode hostname carefully for lookalike or spoofed characters.",
                )
            )
        elif any(ord(char) > 127 for char in hostname):
            findings.append(
                GuardianFinding(
                    name="Non-ASCII Characters in Hostname",
                    description="The hostname contains non-ASCII characters that may represent internationalized or spoofed symbols.",
                    severity="medium",
                    evidence=f"Hostname contains non-ASCII: {hostname}",
                    recommendation="Examine the domain character-by-character to verify genuine ownership.",
                )
            )

        # 4. Excessive Subdomains
        domain_parts = [p for p in hostname.split(".") if p]
        metadata["subdomain_count"] = max(0, len(domain_parts) - 2)
        if len(domain_parts) > 4 and not is_ip_host:
            findings.append(
                GuardianFinding(
                    name="Excessive Subdomain Depth",
                    description=f"The domain contains {len(domain_parts)} segments, which can be used to obfuscate the root domain.",
                    severity="low",
                    evidence=f"Host structure: {hostname}",
                    recommendation="Check the rightmost domain name and public suffix to ensure you are visiting the intended organization.",
                )
            )

        # 5. Known URL Shortener
        if hostname in KNOWN_SHORTENERS:
            findings.append(
                GuardianFinding(
                    name="URL Shortening Service",
                    description=f"The domain '{hostname}' is a known public URL shortening service that masks destination endpoints.",
                    severity="low",
                    evidence=f"Shortener domain: {hostname}",
                    recommendation="Inspect the redirect chain to evaluate the final destination before browsing or downloading.",
                )
            )

        # 6. Deceptive Brand Keywords in Subdomains or Path
        if len(domain_parts) >= 2 and not is_ip_host:
            # Check if brand keyword appears in subdomain but is not the base domain
            base_domain = ".".join(domain_parts[-2:])
            subdomains_text = ".".join(domain_parts[:-2])
            for brand in DECEPTIVE_BRAND_KEYWORDS:
                if brand in subdomains_text and brand not in base_domain:
                    findings.append(
                        GuardianFinding(
                            name="Brand Keyword in Subdomain",
                            description=f"The well-known keyword '{brand}' appears in the subdomain prefix of unrelated domain '{base_domain}'.",
                            severity="high",
                            evidence=f"Keyword '{brand}' in host '{hostname}'",
                            recommendation="This pattern is frequently used in phishing. Verify the true apex domain operator.",
                        )
                    )
                    break

        # 7. Suspicious File Extension in URL Path
        lower_path = path.lower()
        for ext, desc in SUSPICIOUS_EXTENSIONS.items():
            if lower_path.endswith(ext) or f"{ext}?" in lower_path or f"{ext}&" in lower_path:
                findings.append(
                    GuardianFinding(
                        name="Potentially Dangerous File Download",
                        description=f"The URL points to a {desc} ({ext}) that could execute code upon download.",
                        severity="high",
                        evidence=f"File extension {ext} detected in path: {path}",
                        recommendation="Do not open or execute unexpected downloads. Verify file signatures and SHA-256 hashes.",
                    )
                )
                metadata["download_extension"] = ext
                break

        # 8. Suspicious Redirect Query Parameters
        query_params = parse_qsl(query, keep_blank_values=True)
        redirect_targets: list[str] = []
        for key, val in query_params:
            if key.lower() in SUSPICIOUS_REDIRECT_PARAMS and val:
                redirect_targets.append(f"{key}={val}")
                if val.startswith("http://") or val.startswith("https://") or val.startswith("//"):
                    findings.append(
                        GuardianFinding(
                            name="Open Redirect Query Parameter",
                            description=f"Parameter '{key}' contains an embedded target URL, which can be exploited for deceptive redirection.",
                            severity="medium",
                            evidence=f"Param: {key}={val[:60]}",
                            recommendation="Ensure the server strictly validates redirection destinations against an allowlist.",
                        )
                    )
        metadata["redirect_params"] = redirect_targets

        # 9. Encoding Anomalies
        if "%25" in raw_url:
            findings.append(
                GuardianFinding(
                    name="Double Percent-Encoding Detected",
                    description="The URL contains '%25', which indicates double URL encoding. This is often used to bypass basic keyword filters.",
                    severity="medium",
                    evidence="Token '%25' present in raw URL",
                    recommendation="Inspect the decoded URL value to ensure parameters are properly sanitized.",
                )
            )
        if "%00" in raw_url.lower():
            findings.append(
                GuardianFinding(
                    name="Null Byte Injection Token Detected",
                    description="The URL contains '%00' (null byte), a legacy path-truncation and bypass technique.",
                    severity="high",
                    evidence="Null byte '%00' found in URL",
                    recommendation="Reject requests containing null byte characters immediately.",
                )
            )

        # 10. URL Length Checks
        if len(raw_url) > 250:
            findings.append(
                GuardianFinding(
                    name="Unusually Long URL",
                    description=f"The URL is {len(raw_url)} characters long. Excessive lengths are often used to hide malicious payload parameters.",
                    severity="low",
                    evidence=f"Length: {len(raw_url)} chars",
                    recommendation="Review all query parameters and payload components for hidden tokens.",
                )
            )
        elif len(raw_url) < 100:
            metadata["length_status"] = "normal"

        return findings, metadata
