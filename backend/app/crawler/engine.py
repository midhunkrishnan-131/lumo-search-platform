"""Controlled web crawl execution engine.

Coordinates URL queues, robots.txt compliance, fetching, link extraction,
and database persistence. Runs locally in the FastAPI background.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.crawler.extractor import extract_links_from_html
from app.crawler.fetcher import SafeFetcher
from app.crawler.robots import RobotsManager
from app.crawler.validator import validate_and_screen_url
from app.models.crawler import CrawlSession, CrawlUrl
from app.processor.pipeline import process_document

logger = get_logger("crawler.engine")


class CrawlerEngine:
    """Manages active crawl sessions and task lifecycles."""

    def __init__(
        self,
        robots_manager: RobotsManager | None = None,
        fetcher_factory: Callable[..., SafeFetcher] | None = None,
    ) -> None:
        self.robots_manager = robots_manager or RobotsManager()
        self.fetcher_factory = fetcher_factory or (lambda **kwargs: SafeFetcher(**kwargs))
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._stop_signals: dict[str, asyncio.Event] = {}
        self._domain_last_crawl: dict[str, float] = {}

    def is_running(self, session_id: str) -> bool:
        task = self._active_tasks.get(session_id)
        return task is not None and not task.done()

    def stop_session(self, session_id: str) -> bool:
        """Signal an active crawl session to halt gracefully."""
        event = self._stop_signals.get(session_id)
        if event:
            event.set()
            logger.info("Crawl session stop requested: %s", session_id)
            return True
        return False

    async def start_session(
        self,
        session_id: str,
        session_factory: Callable[[], Session],
        user_agent: str = "LUMOBot/1.0",
        request_timeout: float = 20.0,
        max_response_size: int = 2 * 1024 * 1024,
    ) -> None:
        """Launch background crawling task for the session."""
        if self.is_running(session_id):
            logger.warning("Session %s is already running.", session_id)
            return

        stop_event = asyncio.Event()
        self._stop_signals[session_id] = stop_event

        task = asyncio.create_task(
            self._crawl_loop(
                session_id=session_id,
                session_factory=session_factory,
                stop_event=stop_event,
                user_agent=user_agent,
                request_timeout=request_timeout,
                max_response_size=max_response_size,
            )
        )
        self._active_tasks[session_id] = task

        def _cleanup(fut: asyncio.Future[None]) -> None:
            self._active_tasks.pop(session_id, None)
            self._stop_signals.pop(session_id, None)

        task.add_done_callback(_cleanup)

    async def _crawl_loop(
        self,
        session_id: str,
        session_factory: Callable[[], Session],
        stop_event: asyncio.Event,
        user_agent: str,
        request_timeout: float,
        max_response_size: int,
    ) -> None:
        logger.info("Starting crawl loop for session: %s", session_id)
        fetcher = self.fetcher_factory(
            user_agent=user_agent,
            timeout=request_timeout,
            max_response_size=max_response_size,
        )

        try:
            # 1. Update session status to running
            with session_factory() as db:
                session_rec = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
                if not session_rec:
                    logger.error("Session %s not found in database.", session_id)
                    return
                session_rec.status = "running"
                session_rec.started_at = datetime.now(timezone.utc)
                max_depth = session_rec.max_depth
                max_pages = session_rec.max_pages
                configured_delay = session_rec.crawl_delay
                db.commit()

            # 2. Main crawling loop
            while not stop_event.is_set():
                # Check limits and get next queued URL
                with session_factory() as db:
                    session_rec = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
                    if not session_rec:
                        break

                    if session_rec.pages_crawled >= max_pages:
                        logger.info("Reached maximum pages (%s) for session %s", max_pages, session_id)
                        session_rec.status = "completed"
                        session_rec.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        break

                    next_url_rec = (
                        db.query(CrawlUrl)
                        .filter(CrawlUrl.session_id == session_id, CrawlUrl.status == "queued")
                        .order_by(CrawlUrl.depth.asc(), CrawlUrl.id.asc())
                        .first()
                    )

                    if not next_url_rec:
                        logger.info("Crawl queue exhausted for session %s", session_id)
                        session_rec.status = "completed"
                        session_rec.completed_at = datetime.now(timezone.utc)
                        db.commit()
                        break

                    url_id = next_url_rec.id
                    target_url = next_url_rec.url
                    current_depth = next_url_rec.depth

                    # Mark URL in progress
                    next_url_rec.status = "in_progress"
                    db.commit()

                # Check robots.txt compliance
                domain = urlparse(target_url).netloc.lower()
                can_crawl, robot_delay = await self.robots_manager.can_fetch(target_url, user_agent, fetcher)

                if not can_crawl:
                    logger.info("URL blocked by robots.txt: %s", target_url)
                    with session_factory() as db:
                        rec = db.query(CrawlUrl).filter(CrawlUrl.id == url_id).first()
                        if rec:
                            rec.status = "skipped"
                            rec.error_message = "Disallowed by robots.txt"
                            rec.fetched_at = datetime.now(timezone.utc)
                            db.commit()
                    continue

                # Rate limiting / Crawl delay
                delay = robot_delay if (robot_delay is not None and robot_delay > 0) else configured_delay
                if delay > 0:
                    await asyncio.sleep(min(delay, 5.0))  # Cap delay at 5s locally to prevent indefinite stalls

                if stop_event.is_set():
                    break

                # 3. Fetch URL
                fetch_res = await fetcher.fetch(target_url)

                # 4. Process result and extract links
                with session_factory() as db:
                    url_record = db.query(CrawlUrl).filter(CrawlUrl.id == url_id).first()
                    sess_record = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()

                    if url_record and sess_record:
                        url_record.fetched_at = datetime.now(timezone.utc)
                        url_record.http_status = fetch_res.status_code
                        url_record.content_type = fetch_res.content_type
                        url_record.content_length = fetch_res.content_length

                        if fetch_res.success:
                            url_record.status = "fetched"
                            sess_record.pages_crawled += 1

                            # Link extraction if depth limit permits
                            extracted = extract_links_from_html(fetch_res.text, target_url)
                            url_record.title = extracted.title

                            # Phase 4: Document content extraction and deduplication
                            is_html = any(t in (fetch_res.content_type or "") for t in ("text/html", "application/xhtml+xml"))
                            if is_html and fetch_res.text:
                                try:
                                    process_document(
                                        html=fetch_res.text,
                                        url=target_url,
                                        session_id=session_id,
                                        url_id=url_record.id,
                                        db=db,
                                    )
                                except Exception as exc:
                                    logger.error("Document extraction failed for %s: %s", target_url, exc)

                            if current_depth < max_depth:
                                for discovered in extracted.links:
                                    screen = validate_and_screen_url(discovered)
                                    if not screen.is_valid:
                                        continue

                                    # Check deduplication within session
                                    exists = (
                                        db.query(CrawlUrl.id)
                                        .filter(
                                            CrawlUrl.session_id == session_id,
                                            CrawlUrl.normalized_url == screen.normalized_url,
                                        )
                                        .first()
                                    )

                                    if not exists:
                                        new_rec = CrawlUrl(
                                            session_id=session_id,
                                            url=discovered,
                                            normalized_url=screen.normalized_url,
                                            depth=current_depth + 1,
                                            is_seed=False,
                                            status="queued",
                                            parent_url=target_url,
                                        )
                                        db.add(new_rec)
                        else:
                            url_record.status = "failed"
                            url_record.error_message = fetch_res.error_message or f"HTTP {fetch_res.status_code}"

                        db.commit()

            # Handle user stop
            if stop_event.is_set():
                with session_factory() as db:
                    session_rec = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
                    if session_rec and session_rec.status == "running":
                        session_rec.status = "stopped"
                        session_rec.completed_at = datetime.now(timezone.utc)
                        db.commit()
                logger.info("Crawl session %s was stopped by user.", session_id)

        except Exception as exc:
            logger.error("Unhandled error in crawl loop for session %s: %s", session_id, exc, exc_info=True)
            with session_factory() as db:
                session_rec = db.query(CrawlSession).filter(CrawlSession.id == session_id).first()
                if session_rec:
                    session_rec.status = "failed"
                    session_rec.error_message = str(exc)
                    session_rec.completed_at = datetime.now(timezone.utc)
                    db.commit()
        finally:
            await fetcher.close()
            logger.info("Crawl session loop ended: %s", session_id)


# Global crawler engine instance
crawler_engine = CrawlerEngine()
