"""Minimal official Python SDK client for the LUMO Intelligence API (v1)."""

from __future__ import annotations

from typing import Any
import httpx


class LumoApiError(RuntimeError):
    """Structured error raised by LumoClient on non-2xx API responses."""

    def __init__(self, status_code: int, detail: str, request_id: str | None = None) -> None:
        super().__init__(f"LUMO API {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail
        self.request_id = request_id


class LumoClient:
    """Lightweight Python client for LUMO Search, AI, Research, Documents, Graph, Guardian, and Workspace."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", api_key: str = "", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        hdrs = {"Accept": "application/json"}
        if self.api_key:
            hdrs["X-API-Key"] = self.api_key
        return hdrs

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(method, url, headers=self._headers(), **kwargs)
        if resp.status_code >= 400:
            data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
            raise LumoApiError(resp.status_code, str(data.get("detail") or resp.text), data.get("request_id"))
        return resp.json()

    def platform_info(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/developer/info")

    def search(self, query: str, mode: str = "hybrid", page: int = 1, per_page: int = 10) -> dict[str, Any]:
        return self._request("GET", "/api/v1/search", params={"q": query, "mode": mode, "page": page, "per_page": per_page})

    def ai_search(self, query: str, provider: str = "auto") -> dict[str, Any]:
        return self._request("GET", "/api/v1/ai/search", params={"q": query, "provider": provider})

    def create_research(self, topic: str, max_iterations: int = 2, provider: str = "auto") -> dict[str, Any]:
        return self._request("POST", "/api/v1/research", json={"topic": topic, "max_iterations": max_iterations, "provider": provider})

    def get_research(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/research/{session_id}")

    def analyze_document(self, document_id: str, mode: str = "summarize", question: str | None = None) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/intelligence/documents/{document_id}/analyze", json={"mode": mode, "question": question})

    def query_graph(self, query: str, limit: int = 15) -> dict[str, Any]:
        return self._request("GET", "/api/v1/graph/entities", params={"q": query, "limit": limit})

    def guardian_analyze_url(self, url: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/guardian/analyze-url", json={"url": url})

    def workspace_search(self, query: str, mode: str = "hybrid", limit: int = 15) -> dict[str, Any]:
        return self._request("POST", "/api/v1/workspace/search", json={"query": query, "mode": mode, "limit": limit})
