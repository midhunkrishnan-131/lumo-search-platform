"""Guardian Reputation Intelligence: Provider abstraction and optional VirusTotal integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
import base64
import json
from typing import Any
import urllib.request
import urllib.error

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("guardian.reputation")


class BaseReputationProvider(ABC):
    """Abstract interface for external threat intelligence reputation providers."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required API credentials and connectivity are configured."""
        ...

    @abstractmethod
    def lookup_url(self, url: str) -> dict[str, Any]:
        """Query reputation for a target URL."""
        ...

    @abstractmethod
    def lookup_file_hash(self, sha256_hash: str) -> dict[str, Any]:
        """Query reputation for a file SHA-256 hash."""
        ...


class VirusTotalProvider(BaseReputationProvider):
    """Optional VirusTotal v3 API integration. Works strictly without exposing credentials or auto-uploading files."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.guardian_virustotal_api_key.strip())

    def lookup_url(self, url: str) -> dict[str, Any]:
        """Look up URL analysis report via VirusTotal v3 API using base64 identifier."""
        if not self.is_configured():
            return {
                "provider": "virustotal",
                "configured": False,
                "status": "unconfigured",
                "note": "VirusTotal API key is not configured in backend settings.",
            }

        # VirusTotal v3 URL ID is base64-encoded URL string without trailing '=' padding
        url_id = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
        endpoint = f"{self.settings.guardian_virustotal_base_url.rstrip('/')}/urls/{url_id}"
        return self._make_request(endpoint)

    def lookup_file_hash(self, sha256_hash: str) -> dict[str, Any]:
        """Look up file reputation report via VirusTotal v3 API using SHA-256 hash."""
        if not self.is_configured():
            return {
                "provider": "virustotal",
                "configured": False,
                "status": "unconfigured",
                "note": "VirusTotal API key is not configured in backend settings.",
            }

        clean_hash = sha256_hash.strip().lower()
        endpoint = f"{self.settings.guardian_virustotal_base_url.rstrip('/')}/files/{clean_hash}"
        return self._make_request(endpoint)

    def _make_request(self, endpoint: str) -> dict[str, Any]:
        req = urllib.request.Request(
            endpoint,
            headers={
                "x-apikey": self.settings.guardian_virustotal_api_key,
                "Accept": "application/json",
                "User-Agent": "LUMO-Security-Guardian/1.0",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.settings.guardian_virustotal_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                attributes = data.get("data", {}).get("attributes", {})
                stats = attributes.get("last_analysis_stats", {})

                return {
                    "provider": "virustotal",
                    "configured": True,
                    "status": "completed",
                    "malicious_count": stats.get("malicious", 0),
                    "suspicious_count": stats.get("suspicious", 0),
                    "harmless_count": stats.get("harmless", 0),
                    "undetected_count": stats.get("undetected", 0),
                    "total_engines": sum(stats.values()) if stats else 0,
                    "reputation_score": attributes.get("reputation", 0),
                    "tags": attributes.get("tags", []),
                }
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {
                    "provider": "virustotal",
                    "configured": True,
                    "status": "not_found",
                    "note": "Item not found in VirusTotal database (not previously submitted or analyzed).",
                    "malicious_count": 0,
                    "suspicious_count": 0,
                }
            elif exc.code == 429:
                logger.warning("VirusTotal API rate limit encountered (HTTP 429)")
                return {
                    "provider": "virustotal",
                    "configured": True,
                    "status": "rate_limited",
                    "note": "External threat intelligence rate limit reached. Analysis completed using static checks only.",
                }
            else:
                logger.error("VirusTotal API returned error HTTP %d", exc.code)
                return {
                    "provider": "virustotal",
                    "configured": True,
                    "status": "error",
                    "note": f"Reputation API returned HTTP {exc.code}.",
                }
        except Exception as exc:
            logger.warning("VirusTotal request failed: %s", exc)
            return {
                "provider": "virustotal",
                "configured": True,
                "status": "error",
                "note": f"Failed to connect to external reputation provider: {exc}",
            }


# Global reputation provider instance
reputation_provider = VirusTotalProvider()
