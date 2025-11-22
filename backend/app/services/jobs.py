from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core.config import settings
from app.services import smart as smart_service
from app.services import system as system_service

logger = logging.getLogger(__name__)

_health_task: Optional[asyncio.Task] = None


async def _health_check_loop(interval_seconds: int) -> None:
    while True:
        try:
            system_service.get_system_info()
            smart_service.get_smart_status()
        except Exception as exc:  # pragma: no cover - diagnostics logging only
            logger.debug("Health check iteration failed: %s", exc)
        await asyncio.sleep(interval_seconds)


async def start_health_monitor(interval_seconds: int = 300) -> None:
    global _health_task

    if settings.is_dev_mode:
        logger.info("Dev mode active – background health monitor not scheduled")
        return

    if _health_task is not None and not _health_task.done():
        logger.info("Health monitor already running")
        return

    loop = asyncio.get_running_loop()
    _health_task = loop.create_task(_health_check_loop(interval_seconds))
    logger.info("Background health monitor started (interval=%ss)", interval_seconds)


async def stop_health_monitor() -> None:
    global _health_task

    if _health_task is None:
        return

    _health_task.cancel()
    try:
        await _health_task
    except asyncio.CancelledError:  # pragma: no cover - expected on shutdown
        pass
    finally:
        _health_task = None
        logger.info("Background health monitor stopped")
