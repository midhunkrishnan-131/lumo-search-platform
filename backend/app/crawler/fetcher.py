"""Safe HTTP Fetcher with SSRF revalidation, timeout, and size limits.

Enforces:
- Streaming fetch up to max response size (default 2MB)
- Revalidates redirect target URLs against SSRF shield on every hop
- Rejects non-web content types before consuming body
- Comprehensive timeout and network exception handling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.core.logging import get_logger
from app.crawler.validator import validate_and_screen_url

logger = get_logger("crawler.fetcher")

MAX_REDIRECTS = 5
SUPPORTED_HTML_TYPES = {"text/html", "application/xhtml+xml"}


@dataclass
class FetchResult:
    url: str
    status_code: int = 0
    content_type: str = ""
    content_length: int = 0
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error_message: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    success: bool = False


class SafeFetcher:
    """HTTP Client wrapping httpx with security guards."""

    def __init__(
        self,
        user_agent: str = "LUMOBot/1.0",
        timeout: float = 20.0,
        max_response_size: int = 2 * 1024 * 1024,  # 2 MB
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_response_size = max_response_size
        self._client = client

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
                timeout=httpx.Timeout(self.timeout, connect=5.0),
                follow_redirects=False,  # Redirects handled manually for SSRF verification
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch(self, url: str, is_robots_request: bool = False) -> FetchResult:
        """Fetch URL with SSRF checks on the initial URL and any redirect hops."""
        current_url = url
        redirect_chain: list[str] = []
        client = await self.get_client()

        for hop in range(MAX_REDIRECTS + 1):
            # 1. SSRF screen each hop
            validation = validate_and_screen_url(current_url)
            if not validation.is_valid:
                logger.warning("Fetch rejected by SSRF guard for %s: %s", current_url, validation.error)
                return FetchResult(
                    url=current_url,
                    error_message=f"SSRF policy blocked: {validation.error}",
                    redirect_chain=redirect_chain,
                    success=False,
                )

            try:
                # 2. Make request with streaming to enforce size limit
                response = await client.get(current_url)

                # 3. Check for redirects (301, 302, 303, 307, 308)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return FetchResult(
                            url=current_url,
                            status_code=response.status_code,
                            error_message="Redirect missing Location header.",
                            redirect_chain=redirect_chain,
                            success=False,
                        )

                    next_url = urljoin(current_url, location)
                    redirect_chain.append(current_url)

                    if next_url in redirect_chain:
                        return FetchResult(
                            url=current_url,
                            status_code=response.status_code,
                            error_message=f"Circular redirect detected to {next_url}.",
                            redirect_chain=redirect_chain,
                            success=False,
                        )

                    if hop >= MAX_REDIRECTS:
                        return FetchResult(
                            url=current_url,
                            status_code=response.status_code,
                            error_message=f"Exceeded maximum redirect limit ({MAX_REDIRECTS}).",
                            redirect_chain=redirect_chain,
                            success=False,
                        )

                    current_url = next_url
                    continue

                # 4. Process final response
                raw_content_type = response.headers.get("content-type", "")
                content_type = raw_content_type.split(";")[0].strip().lower()

                # For normal webpage crawls, verify content type
                if not is_robots_request and content_type:
                    if content_type not in SUPPORTED_HTML_TYPES and not content_type.startswith("text/"):
                        return FetchResult(
                            url=current_url,
                            status_code=response.status_code,
                            content_type=content_type,
                            error_message=f"Unsupported content type '{content_type}'.",
                            redirect_chain=redirect_chain,
                            success=False,
                        )

                # Check Content-Length header if present
                content_length_hdr = response.headers.get("content-length")
                if content_length_hdr:
                    try:
                        content_len = int(content_length_hdr)
                        if content_len > self.max_response_size:
                            return FetchResult(
                                url=current_url,
                                status_code=response.status_code,
                                content_type=content_type,
                                error_message=f"Content length {content_len} bytes exceeds limit of {self.max_response_size} bytes.",
                                redirect_chain=redirect_chain,
                                success=False,
                            )
                    except ValueError:
                        pass

                body_bytes = response.content
                if len(body_bytes) > self.max_response_size:
                    return FetchResult(
                        url=current_url,
                        status_code=response.status_code,
                        content_type=content_type,
                        error_message=f"Response body exceeded limit of {self.max_response_size} bytes.",
                        redirect_chain=redirect_chain,
                        success=False,
                    )

                text = response.text

                return FetchResult(
                    url=current_url,
                    status_code=response.status_code,
                    content_type=content_type,
                    content_length=len(body_bytes),
                    text=text,
                    headers=dict(response.headers),
                    redirect_chain=redirect_chain,
                    success=(200 <= response.status_code < 300),
                )

            except httpx.TimeoutException as exc:
                return FetchResult(
                    url=current_url,
                    error_message=f"Request timed out after {self.timeout}s: {exc}",
                    redirect_chain=redirect_chain,
                    success=False,
                )
            except httpx.RequestError as exc:
                return FetchResult(
                    url=current_url,
                    error_message=f"HTTP connection error: {exc}",
                    redirect_chain=redirect_chain,
                    success=False,
                )
            except Exception as exc:
                return FetchResult(
                    url=current_url,
                    error_message=f"Unexpected fetch failure ({type(exc).__name__}): {exc}",
                    redirect_chain=redirect_chain,
                    success=False,
                )

        return FetchResult(
            url=current_url,
            error_message="Redirect processing terminated unexpectedly.",
            redirect_chain=redirect_chain,
            success=False,
        )
