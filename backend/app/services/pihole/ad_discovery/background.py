"""Background task for periodic ad discovery analysis.

Follows the same async pattern as DnsQueryCollector:
singleton instance, start/stop lifecycle, asyncio.create_task loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AdDiscoveryBackgroundTask:
    """Periodically runs ad discovery analysis."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._db_factory: Callable[[], Session] | None = None

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self, db_session_factory: Callable[[], Session]) -> None:
        """Start the background analysis task."""
        if self._task and not self._task.done():
            logger.warning("Ad Discovery background task already running")
            return
        self._db_factory = db_session_factory
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Ad Discovery background task started")

    async def stop(self) -> None:
        """Stop the background task gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Ad Discovery background task stopped")

    async def _poll_loop(self) -> None:
        """Main analysis loop."""
        # Warmup — let services initialise before first run
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._run_analysis()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Ad Discovery background analysis failed")

            # Read interval from config
            interval_hours = self._get_interval_hours()
            await asyncio.sleep(interval_hours * 3600)

    async def _run_analysis(self) -> None:
        """Run a single analysis cycle."""
        if not self._db_factory:
            return

        db = self._db_factory()
        try:
            from app.models.ad_discovery import AdDiscoveryConfig
            config = db.query(AdDiscoveryConfig).filter(AdDiscoveryConfig.id == 1).first()
            if config and not config.background_enabled:
                logger.debug("Ad Discovery background task disabled in config")
                return

            from app.services.pihole.ad_discovery.scorer import Scorer
            from app.services.pihole.ad_discovery.community_matcher import get_community_matcher
            from app.services.pihole.ad_discovery.analyzer import Analyzer

            scorer = Scorer()
            scorer.load_patterns_from_db(db)

            matcher = get_community_matcher()
            await matcher.refresh_all(db)

            analyzer = Analyzer(db, scorer, matcher)
            result = analyzer.analyze_queries(period="24h")

            logger.info(
                "Ad Discovery analysis complete: %d new, %d updated, %d analyzed",
                result["new_suspects"],
                result["updated_suspects"],
                result["total_domains_analyzed"],
            )
        finally:
            db.close()

    def _get_interval_hours(self) -> int:
        """Read background interval from config."""
        if not self._db_factory:
            return 6
        db = self._db_factory()
        try:
            from app.models.ad_discovery import AdDiscoveryConfig
            config = db.query(AdDiscoveryConfig).filter(AdDiscoveryConfig.id == 1).first()
            return config.background_interval_hours if config else 6
        except Exception:
            return 6
        finally:
            db.close()


# Module-level singleton
_background_task = AdDiscoveryBackgroundTask()


def get_ad_discovery_task() -> AdDiscoveryBackgroundTask:
    """Get the module-level Ad Discovery background task singleton."""
    return _background_task
