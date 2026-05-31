"""Desktop (display-manager) control service."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from app.core.config import settings
from app.schemas.desktop import DesktopStatus
from app.services.power.desktop_backend import (
    DesktopBackend,
    DevDesktopBackend,
    LinuxDesktopBackend,
)

logger = logging.getLogger(__name__)

_service: Optional["DesktopService"] = None


class DesktopService:
    def __init__(self, backend: Optional[DesktopBackend] = None) -> None:
        if backend is not None:
            self._backend = backend
        elif getattr(settings, "is_dev_mode", False):
            self._backend = DevDesktopBackend()
        else:
            self._backend = LinuxDesktopBackend()

    async def get_status(self) -> DesktopStatus:
        return await self._backend.get_status()

    async def enable(self) -> Tuple[bool, str]:
        logger.info("Desktop enable requested")
        return await self._backend.enable()

    async def disable(self) -> Tuple[bool, str]:
        logger.info("Desktop disable requested")
        return await self._backend.disable()


def get_desktop_service() -> DesktopService:
    global _service
    if _service is None:
        _service = DesktopService()
    return _service
