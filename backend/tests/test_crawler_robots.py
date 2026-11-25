"""Unit tests for robots.txt parsing and permission caching."""

import pytest

from app.crawler.fetcher import FetchResult
from app.crawler.robots import RobotsManager


class FakeFetcher:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.fetch_count = 0

    async def fetch(self, url: str, is_robots_request: bool = False) -> FetchResult:
        self.fetch_count += 1
        return FetchResult(
            url=url,
            status_code=self.status_code,
            text=self.text,
            success=(self.status_code == 200),
        )


@pytest.mark.anyio
async def test_robots_respects_disallow_rules():
    robots_text = """
    User-agent: *
    Disallow: /secret
    Disallow: /admin/
    Crawl-delay: 3
    """
    fetcher = FakeFetcher(status_code=200, text=robots_text)
    mgr = RobotsManager()

    allowed_public, delay = await mgr.can_fetch("https://example.com/public", "LUMOBot/1.0", fetcher)
    assert allowed_public is True
    assert delay == 3.0

    allowed_secret, _ = await mgr.can_fetch("https://example.com/secret", "LUMOBot/1.0", fetcher)
    assert allowed_secret is False

    allowed_admin, _ = await mgr.can_fetch("https://example.com/admin/page", "LUMOBot/1.0", fetcher)
    assert allowed_admin is False


@pytest.mark.anyio
async def test_robots_404_allows_all():
    fetcher = FakeFetcher(status_code=404, text="")
    mgr = RobotsManager()

    allowed, delay = await mgr.can_fetch("https://example.com/anything", "LUMOBot/1.0", fetcher)
    assert allowed is True
    assert delay is None


@pytest.mark.anyio
async def test_robots_403_blocks_all_conservatively():
    fetcher = FakeFetcher(status_code=403, text="")
    mgr = RobotsManager()

    allowed, _ = await mgr.can_fetch("https://example.com/page", "LUMOBot/1.0", fetcher)
    assert allowed is False


@pytest.mark.anyio
async def test_robots_cache_avoids_repeated_fetches():
    fetcher = FakeFetcher(status_code=200, text="User-agent: *\nDisallow: /hidden")
    mgr = RobotsManager()

    await mgr.can_fetch("https://example.com/one", "LUMOBot/1.0", fetcher)
    await mgr.can_fetch("https://example.com/two", "LUMOBot/1.0", fetcher)

    assert fetcher.fetch_count == 1
