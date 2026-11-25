"""Unit tests for SafeFetcher (SSRF guard on redirects, size limits, content-type checks)."""

import pytest

from app.crawler.fetcher import SafeFetcher


@pytest.mark.anyio
async def test_safe_fetcher_blocks_direct_private_ip():
    fetcher = SafeFetcher()
    result = await fetcher.fetch("http://127.0.0.1:8000/api/v1/health")
    assert result.success is False
    assert "SSRF policy blocked" in (result.error_message or "")


@pytest.mark.anyio
async def test_safe_fetcher_blocks_unsupported_scheme():
    fetcher = SafeFetcher()
    result = await fetcher.fetch("ftp://example.com/file.txt")
    assert result.success is False
    assert "SSRF policy blocked" in (result.error_message or "")


@pytest.mark.anyio
async def test_safe_fetcher_handles_timeouts():
    import httpx

    # Create a transport that raises timeout
    class TimeoutTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ReadTimeout("Connection timed out", request=request)

    client = httpx.AsyncClient(transport=TimeoutTransport())
    fetcher = SafeFetcher(client=client, timeout=0.1)

    # Use resolve_dns=False to test fetcher error path
    result = await fetcher.fetch("https://8.8.8.8/test")
    assert result.success is False
    assert "timed out" in (result.error_message or "").lower()
