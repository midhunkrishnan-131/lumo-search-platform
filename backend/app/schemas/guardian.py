"""Pydantic schemas for Download Guardian URL and File security analyses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GuardianFinding(BaseModel):
    """An individual security finding produced by deterministic static or network analysis."""

    name: str = Field(description="Finding identifier / title")
    description: str = Field(description="Explanation of why this pattern is notable")
    severity: str = Field(description="informational, low, medium, high, or critical")
    evidence: str = Field(description="Specific token, header, byte pattern, or value triggering this finding")
    recommendation: str = Field(description="Defensive guidance for the user")


class UrlAnalysisRequest(BaseModel):
    """Request payload to analyze a suspicious URL."""

    url: str = Field(min_length=1, max_length=2048, description="URL to be defensively inspected")
    check_network: bool = Field(default=True, description="Whether to safely probe redirects and TLS without downloading payloads")
    check_reputation: bool = Field(default=False, description="User consent to query external threat intelligence using the domain/URL")
    explain_ai: bool = Field(default=False, description="Whether to generate a plain-English explanation of findings using LUMO AI")


class FileHashLookupRequest(BaseModel):
    """Request payload to inspect a client-computed file hash without transmitting file contents."""

    filename: str = Field(default="", max_length=255)
    size_bytes: int = Field(default=0, ge=0)
    mime_type: str = Field(default="application/octet-stream", max_length=128)
    sha256: str = Field(default="", min_length=64, max_length=64, description="Hexadecimal SHA-256 digest")
    check_reputation: bool = Field(default=False, description="User consent to query external threat intelligence using SHA-256")
    explain_ai: bool = Field(default=False, description="Whether to generate a plain-English explanation of findings using LUMO AI")


class UrlAnalysisResponse(BaseModel):
    """Full security inspection report for an analyzed URL."""

    id: str
    analysis_type: str = "url"
    input_url: str
    normalized_url: str
    hostname: str
    created_at: datetime
    risk_level: str
    risk_score: int
    findings: list[GuardianFinding] = Field(default_factory=list)
    redirect_chain: list[dict[str, Any]] = Field(default_factory=list)
    domain_info: dict[str, Any] = Field(default_factory=dict)
    reputation: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ai_explanation: str | None = None
    status: str = "completed"
    error_message: str | None = None

    @property
    def risk_classification(self) -> str:
        return f"{self.risk_level} Risk" if not self.risk_level.endswith("Risk") else self.risk_level

    @property
    def redirects(self) -> list[dict[str, Any]]:
        return self.redirect_chain

    @property
    def domain_reputation(self) -> str:
        if not self.reputation:
            return "Unknown"
        status = self.reputation.get("status", "unknown")
        if status == "completed":
            return f"{self.reputation.get('malicious_count', 0)} malicious / {self.reputation.get('total_engines', 0)} vendors"
        return self.reputation.get("note", status)

    @property
    def classification(self) -> str:
        return self.risk_level

    @property
    def summary(self) -> str:
        rec = self.recommendations[0] if self.recommendations else "Analysis completed."
        return f"Risk Level: {self.risk_level} (Score {self.risk_score}/100). Findings: {len(self.findings)}. {rec}"

    model_config = ConfigDict(from_attributes=True)


class FileAnalysisResponse(BaseModel):
    """Full security inspection report for an analyzed file."""

    id: str
    analysis_type: str = "file"
    original_filename: str
    file_size_bytes: int
    detected_mime: str
    magic_signature: str
    sha256: str
    sha1: str = ""
    md5: str = ""
    created_at: datetime
    risk_level: str
    risk_score: int
    findings: list[GuardianFinding] = Field(default_factory=list)
    static_features: dict[str, Any] = Field(default_factory=dict)
    reputation: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ai_explanation: str | None = None
    status: str = "completed"
    error_message: str | None = None

    @property
    def risk_classification(self) -> str:
        return f"{self.risk_level} Risk" if not self.risk_level.endswith("Risk") else self.risk_level

    @property
    def redirects(self) -> list[dict[str, Any]]:
        return self.redirect_chain

    @property
    def domain_reputation(self) -> str:
        if not self.reputation:
            return "Unknown"
        status = self.reputation.get("status", "unknown")
        if status == "completed":
            return f"{self.reputation.get('malicious_count', 0)} malicious / {self.reputation.get('total_engines', 0)} vendors"
        return self.reputation.get("note", status)

    @property
    def classification(self) -> str:
        return self.risk_level

    @property
    def summary(self) -> str:
        rec = self.recommendations[0] if self.recommendations else "Analysis completed."
        return f"Risk Level: {self.risk_level} (Score {self.risk_score}/100). Findings: {len(self.findings)}. {rec}"

    model_config = ConfigDict(from_attributes=True)


class GuardianHistoryItemResponse(BaseModel):
    """Summary record of a previous security analysis."""

    id: str
    analysis_type: str
    target: str
    target_identifier: str | None = None
    risk_level: str
    risk_score: int
    findings_count: int = 0
    created_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


class GuardianHistoryListResponse(BaseModel):
    """Paginated list of historical security analyses."""

    items: list[GuardianHistoryItemResponse]
    total: int
    limit: int
    offset: int
