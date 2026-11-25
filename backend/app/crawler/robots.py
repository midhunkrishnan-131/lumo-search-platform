"""Robots.txt parser and caching system.

Handles retrieval, parsing, caching, and compliance checks according to the
Robots Exclusion Standard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from urllib.parse import urlparse
import urllib.robotparser

from app.core.logging import get_logger

logger = get_logger("crawler.robots")

DEFAULT_CACHE_TTL = 3600  # 1 hour cache for robots.txt


@dataclass
class RobotsPolicy:
    parser: urllib.robotparser.RobotFileParser | None
    fetched_at: float
    crawl_delay: float | None = None
    is_allowed_all: bool = False
    is_blocked_all: bool = False

    def can_fetch(self, user_agent: str, url: str) -> bool:
        if self.is_blocked_all:
            return False
        if self.is_allowed_all or self.parser is None:
            return True
        return self.parser.can_fetch(user_agent, url)


class RobotsManager:
    """Maintains domain-level robots.txt cache and authorization logic."""

    def __init__(self, cache_ttl: float = DEFAULT_CACHE_TTL) -> None:
        self.cache_ttl = cache_ttl
        self._cache: dict[str, RobotsPolicy] = {}
        self._lock = asyncio.Lock()

    def get_origin(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}".lower()

    async def can_fetch(
        self,
        url: str,
        user_agent: str,
        fetcher: Any,  # SafeFetcher instance
    ) -> tuple[bool, float | None]:
        """Check whether the user agent is permitted to crawl the given URL.

        Returns (is_permitted, crawl_delay).
        """
        origin = self.get_origin(url)

        async with self._lock:
            cached = self._cache.get(origin)
            now = time.monotonic()
            if cached and (now - cached.fetched_at) < self.cache_ttl:
                allowed = cached.can_fetch(user_agent, url)
                return allowed, cached.crawl_delay

        # Fetch and parse robots.txt for origin
        policy = await self._fetch_robots(origin, user_agent, fetcher)

        async with self._lock:
            self._cache[origin] = policy

        allowed = policy.can_fetch(user_agent, url)
        return allowed, policy.crawl_delay

    async def _fetch_robots(self, origin: str, user_agent: str, fetcher: Any) -> RobotsPolicy:
        robots_url = f"{origin}/robots.txt"
        now = time.monotonic()

        try:
            result = await fetcher.fetch(robots_url, is_robots_request=True)
            if result.status_code == 200 and result.text:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(result.text.splitlines())
                delay = parser.crawl_delay(user_agent)
                logger.info("Parsed robots.txt for %s (crawl-delay: %s)", origin, delay)
                return RobotsPolicy(
                    parser=parser,
                    fetched_at=now,
                    crawl_delay=delay,
                )
            elif result.status_code == 404:
                # Missing robots.txt means no restrictions
                logger.info("No robots.txt found for %s (404); allowing all.", origin)
                return RobotsPolicy(parser=None, fetched_at=now, is_allowed_all=True)
            elif result.status_code in {401, 403}:
                # Explicit access denied to robots.txt: fail conservatively
                logger.warning("Access denied to robots.txt for %s (%s); disallowing all.", origin, result.status_code)
                return RobotsPolicy(parser=None, fetched_at=now, is_blocked_all=True)
            else:
                # Any other error/timeout: allow conservatively with None parser
                logger.warning("Unsuccessful robots.txt fetch for %s (status: %s)", origin, result.status_code)
                return RobotsPolicy(parser=None, fetched_at=now, is_allowed_all=True)
        except Exception as exc:
            logger.warning("Error fetching robots.txt for %s (%s); allowing by default.", origin, type(exc).__name__)
            return RobotsPolicy(parser=None, fetched_at=now, is_allowed_all=True)

    def clear(self) -> None:
        self._cache.clear()
