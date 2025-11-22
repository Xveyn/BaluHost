from __future__ import annotations

import logging
import platform
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.system import SmartAttribute, SmartDevice, SmartStatusResponse

logger = logging.getLogger(__name__)


class SmartUnavailableError(RuntimeError):
    """Raised when SMART diagnostics cannot be accessed."""


def _mock_status() -> SmartStatusResponse:
    now = datetime.now(tz=timezone.utc)
    devices = [
        SmartDevice(
            name="/dev/sda",
            model="Baluhost Virtual Drive",
            serial="BH-DEV-0001",
            temperature=34,
            status="PASSED",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=66,
                    worst=43,
                    threshold=0,
                    raw="34",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
    ]
    return SmartStatusResponse(checked_at=now, devices=devices)


def get_smart_status() -> SmartStatusResponse:
    """Return SMART diagnostics information.

    In development mode (or on non-Linux platforms) a deterministic mock payload is
    returned so the frontend can be exercised on Windows. The production branch will
    be wired to smartctl or vendor-specific tooling on a Linux NAS host.
    """

    if settings.is_dev_mode or platform.system().lower() != "linux":
        return _mock_status()

    logger.warning("SMART integration not yet implemented for platform '%s'", platform.system())
    raise SmartUnavailableError("SMART diagnostics are not available on this platform yet")
