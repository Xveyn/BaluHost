"""Public SMART API functions.

Depends on: cache, collector, mock_data.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.schemas.system import SmartStatusResponse

from app.services.hardware.smart import cache as _cache
from app.services.hardware.smart.collector import _read_real_smart_data
from app.services.hardware.smart.mock_data import _mock_status

logger = logging.getLogger(__name__)


def _check_smart_for_notifications(status: SmartStatusResponse) -> None:
    """Check SMART status for issues and emit notifications."""
    try:
        from app.services.notifications.events import (
            emit_smart_failure_sync,
            emit_smart_warning_sync,
        )

        for device in status.devices:
            if device.status == "FAILED":
                emit_smart_failure_sync(device.name, details=f"Status: FAILED, Modell: {device.model}")
                continue

            # Check for failing attributes
            for attr in device.attributes:
                if getattr(attr, "when_failed", None) == "FAILING_NOW":
                    emit_smart_warning_sync(
                        device.name,
                        details=f"Attribut '{attr.name}' ist im FAILING-Zustand",
                    )
                    break  # One warning per device is enough

            # Check for reallocated sectors
            for attr in device.attributes:
                if attr.name and "reallocated" in attr.name.lower() and attr.raw_value:
                    try:
                        count = int(str(attr.raw_value).split()[0])
                        if count > 0:
                            emit_smart_warning_sync(
                                device.name,
                                details=f"{count} reallocated Sektoren erkannt",
                            )
                    except (ValueError, IndexError):
                        pass
                    break

    except Exception as exc:
        logger.debug("Failed to check SMART notifications: %s", exc)


def get_smart_status() -> SmartStatusResponse:
    """Return SMART diagnostics information.

    In Dev-Mode: Respektiert _DEV_USE_MOCK_DATA Toggle.
    In Production: Versucht immer echte SMART-Daten zu lesen, Fallback zu Mock bei Fehlern.
    """
    cached = _cache.get_cached_smart_status()
    if cached:
        return cached

    # Dev-Mode: Respektiere Toggle
    if settings.is_dev_mode:
        if _cache._DEV_USE_MOCK_DATA:
            logger.debug("Dev-Mode: Using mock SMART data (toggled)")
            mock = _mock_status()
            _cache._set_smart_cache(mock)
            return mock
        else:
            logger.debug("Dev-Mode: Using real SMART data (toggled)")
            try:
                data = _read_real_smart_data()
                if not data.devices:
                    logger.warning("No real SMART devices found, using mock as fallback")
                    mock = _mock_status()
                    _cache._set_smart_cache(mock)
                    return mock
                _cache._set_smart_cache(data)
                _check_smart_for_notifications(data)
                return data
            except Exception as e:
                logger.warning("Failed to read real SMART data in dev-mode: %s", e)
                mock = _mock_status()
                _cache._set_smart_cache(mock)
                return mock

    # Production: Versuche echte Daten, Fallback zu Mock
    try:
        data = _read_real_smart_data()
        if not data.devices:
            raise _cache.SmartUnavailableError("No devices")
        _cache._set_smart_cache(data)
        _check_smart_for_notifications(data)
        return data
    except _cache.SmartUnavailableError as e:
        logger.warning("SMART fallback to mock: %s", e)
        mock = _mock_status()
        _cache._set_smart_cache(mock)
        return mock
    except Exception as e:
        logger.error("SMART unexpected error fallback: %s", e)
        mock = _mock_status()
        _cache._set_smart_cache(mock)
        return mock


def get_smart_device_models() -> dict[str, str]:
    """Lightweight mapping disk name -> model (cached)."""
    status = get_smart_status()
    mapping: dict[str, str] = {}
    for dev in status.devices:
        mapping[dev.name.lower()] = dev.model
    return mapping


def get_smart_device_order() -> list[str]:
    """Get ordered list of device names as returned by smartctl --scan.

    This is useful for mapping psutil disk indices to SMART device names.
    On Windows, the order corresponds to PhysicalDrive0, PhysicalDrive1, etc.

    Returns:
        list[str]: Ordered list of device names (e.g., ['/dev/sda', '/dev/sdb', ...])
    """
    status = get_smart_status()
    # Die Reihenfolge der Devices im SmartStatusResponse entspricht der Scan-Reihenfolge
    return [dev.name for dev in status.devices]
