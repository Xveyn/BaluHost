"""TapoService — real plugp100 communication for Tapo P110/P115 smart plugs.

Migrated from ``app.services.power.monitor._sample_device()`` into the
smart-device plugin framework.  Uses plugp100 v5.x API for device
communication, with client caching to avoid repeated authentication.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from app.plugins.smart_device.capabilities import PowerReading, SwitchState

if TYPE_CHECKING:
    from plugp100.new.tapodevice import TapoDevice

logger = logging.getLogger(__name__)

# Timeout for individual device operations (connect, update, on/off)
_DEVICE_TIMEOUT = 10.0


class TapoService:
    """Handles real plugp100 communication for Tapo smart plugs.

    Maintains a per-device client cache to avoid repeated authentication.
    On timeout or error, the cached client is evicted so the next call
    reconnects from scratch.
    """

    def __init__(self) -> None:
        # cache_key (device_id:ip) -> connected plugp100 device object
        self._client_cache: Dict[str, TapoDevice] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_device(
        self, device_id: str, ip: str, email: str, password: str
    ) -> TapoDevice:
        """Return a connected plugp100 device, using the cache if available.

        Args:
            device_id: Logical device identifier.
            ip: Device IP address.
            email: Tapo account email (plaintext).
            password: Tapo account password (plaintext).

        Returns:
            A connected plugp100 device object with up-to-date state.

        Raises:
            ImportError: If plugp100 is not installed.
            asyncio.TimeoutError: If device does not respond in time.
            Exception: Any other plugp100 / network error.
        """
        from plugp100.new import device_factory

        cache_key = f"{device_id}:{ip}"

        if cache_key not in self._client_cache:
            credentials = device_factory.AuthCredential(email, password)
            config = device_factory.DeviceConnectConfiguration(
                host=ip, credentials=credentials
            )
            device = await asyncio.wait_for(
                device_factory.connect(config), timeout=_DEVICE_TIMEOUT
            )
            await device.update()
            self._client_cache[cache_key] = device
        else:
            device = self._client_cache[cache_key]
            await asyncio.wait_for(device.update(), timeout=_DEVICE_TIMEOUT)

        return device

    def _evict(self, device_id: str, ip: str) -> None:
        """Remove a cached client so the next call reconnects."""
        cache_key = f"{device_id}:{ip}"
        self._client_cache.pop(cache_key, None)

    def _extract_power(self, device: TapoDevice) -> PowerReading:
        """Extract power reading from a connected plugp100 device.

        Uses the EnergyComponent to read power_info and energy_info,
        matching the extraction logic from the legacy power/monitor.py.

        Args:
            device: Connected plugp100 device object (post-update).

        Returns:
            PowerReading with watts, voltage, current, and energy data.
        """
        from plugp100.new.components.energy_component import EnergyComponent

        if not device.has_component(EnergyComponent):
            # Device doesn't support energy monitoring
            return PowerReading(
                watts=0.0, voltage=230.0, current=0.0,
                energy_today_kwh=0.0,
                timestamp=datetime.now(timezone.utc),
            )

        energy = device.get_component(EnergyComponent)
        power_info = energy.power_info
        energy_info = energy.energy_info

        # Extract values safely (matching legacy code)
        current_power = 0
        current_power_mw = 0
        today_energy_wh = 0

        if power_info is not None and hasattr(power_info, "info") and power_info.info:
            current_power = power_info.info.get("current_power", 0)

        if energy_info is not None and hasattr(energy_info, "info") and energy_info.info:
            current_power_mw = energy_info.info.get("current_power", 0)
            today_energy_wh = energy_info.info.get("today_energy", 0)

        # Use the more precise mW value from energy_info (convert mW -> W)
        watts = current_power_mw / 1000.0 if current_power_mw > 0 else float(current_power)

        # Convert Wh -> kWh
        energy_kwh = today_energy_wh / 1000.0

        # EU standard 230V, calculate current from P = V * I
        voltage = 230.0
        current_amps = watts / voltage if watts > 0 else 0.0

        return PowerReading(
            watts=round(watts, 1),
            voltage=round(voltage, 1),
            current=round(current_amps, 3),
            energy_today_kwh=round(energy_kwh, 2),
            timestamp=datetime.now(timezone.utc),
        )

    def _extract_switch_state(self, device: TapoDevice) -> SwitchState:
        """Extract switch state from a connected plugp100 device.

        Args:
            device: Connected plugp100 device object (post-update).

        Returns:
            SwitchState indicating whether the plug is on or off.
        """
        is_on = False
        try:
            is_on = bool(device.device_info.device_on)
        except (AttributeError, TypeError):
            logger.debug("Could not read device_on from device_info")

        return SwitchState(is_on=is_on, changed_at=datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(
        self, device_id: str, ip: str, email: str, password: str
    ) -> bool:
        """Establish connection to a Tapo device.

        Args:
            device_id: Logical device identifier.
            ip: Device IP address.
            email: Tapo account email (plaintext).
            password: Tapo account password (plaintext).

        Returns:
            True if the connection succeeded.
        """
        try:
            await self._get_device(device_id, ip, email, password)
            logger.info("Connected to Tapo device %s at %s", device_id, ip)
            return True

        except ImportError:
            logger.error(
                "plugp100 library not installed. "
                "Install with: pip install plugp100"
            )
            return False

        except asyncio.TimeoutError:
            logger.warning(
                "Timeout connecting to Tapo device %s at %s", device_id, ip
            )
            self._evict(device_id, ip)
            return False

        except Exception as exc:
            logger.warning(
                "Failed to connect to Tapo device %s at %s: %s",
                device_id, ip, str(exc)[:200],
            )
            self._evict(device_id, ip)
            return False

    async def poll(
        self, device_id: str, ip: str, email: str, password: str
    ) -> Dict[str, Any]:
        """Poll device for current switch state and power reading.

        Args:
            device_id: Logical device identifier.
            ip: Device IP address.
            email: Tapo account email (plaintext).
            password: Tapo account password (plaintext).

        Returns:
            Dict mapping capability name to state model::

                {"switch": SwitchState(...), "power_monitor": PowerReading(...)}

        Raises:
            RuntimeError: If device communication fails.
        """
        try:
            device = await self._get_device(device_id, ip, email, password)
            switch_state = self._extract_switch_state(device)
            power_reading = self._extract_power(device)

            logger.debug(
                "Tapo %s: on=%s, %.1fW, %.2f kWh today",
                device_id, switch_state.is_on,
                power_reading.watts, power_reading.energy_today_kwh or 0.0,
            )

            return {
                "switch": switch_state,
                "power_monitor": power_reading,
            }

        except ImportError:
            logger.error("plugp100 library not installed")
            raise RuntimeError("plugp100 library not installed")

        except asyncio.TimeoutError:
            logger.warning("Timeout polling Tapo device %s at %s", device_id, ip)
            self._evict(device_id, ip)
            raise RuntimeError(f"Timeout polling device {device_id}")

        except TypeError as exc:
            # Handle plugp100 library bugs (e.g., super() argument error)
            logger.warning("Tapo library error for device %s (%s): %s", device_id, ip, exc)
            self._evict(device_id, ip)
            raise RuntimeError(f"Library error: {exc}")

        except AttributeError as exc:
            # Handle NoneType errors when device doesn't respond properly
            logger.warning("Incomplete data from Tapo device %s (%s): %s", device_id, ip, exc)
            self._evict(device_id, ip)
            raise RuntimeError(f"Incomplete data: {exc}")

        except RuntimeError:
            raise

        except Exception as exc:
            error_str = str(exc)
            known_errors = [
                "Cannot write", "Connection", "Errno", "Forbidden",
                "handshake", "authentication", "400", "reset by peer",
            ]
            if any(err in error_str for err in known_errors):
                logger.warning("Tapo device %s (%s) unavailable: %s", device_id, ip, error_str[:100])
            else:
                logger.error("Error polling Tapo device %s (%s): %s", device_id, ip, exc, exc_info=True)
            self._evict(device_id, ip)
            raise RuntimeError(f"Device unavailable: {error_str[:200]}")

    async def turn_on(
        self, device_id: str, ip: str, email: str, password: str
    ) -> SwitchState:
        """Turn the Tapo smart plug ON.

        Args:
            device_id: Logical device identifier.
            ip: Device IP address.
            email: Tapo account email (plaintext).
            password: Tapo account password (plaintext).

        Returns:
            Updated SwitchState after the command.
        """
        try:
            device = await self._get_device(device_id, ip, email, password)
            await asyncio.wait_for(device.turn_on(), timeout=_DEVICE_TIMEOUT)
            await asyncio.wait_for(device.update(), timeout=_DEVICE_TIMEOUT)
            logger.info("Tapo device %s turned ON", device_id)
            return self._extract_switch_state(device)

        except Exception as exc:
            logger.warning("Failed to turn on Tapo device %s: %s", device_id, exc)
            self._evict(device_id, ip)
            raise RuntimeError(f"Turn on failed: {exc}")

    async def turn_off(
        self, device_id: str, ip: str, email: str, password: str
    ) -> SwitchState:
        """Turn the Tapo smart plug OFF.

        Args:
            device_id: Logical device identifier.
            ip: Device IP address.
            email: Tapo account email (plaintext).
            password: Tapo account password (plaintext).

        Returns:
            Updated SwitchState after the command.
        """
        try:
            device = await self._get_device(device_id, ip, email, password)
            await asyncio.wait_for(device.turn_off(), timeout=_DEVICE_TIMEOUT)
            await asyncio.wait_for(device.update(), timeout=_DEVICE_TIMEOUT)
            logger.info("Tapo device %s turned OFF", device_id)
            return self._extract_switch_state(device)

        except Exception as exc:
            logger.warning("Failed to turn off Tapo device %s: %s", device_id, exc)
            self._evict(device_id, ip)
            raise RuntimeError(f"Turn off failed: {exc}")

    async def get_power(
        self, device_id: str, ip: str, email: str, password: str
    ) -> PowerReading:
        """Get current power reading from the device.

        Args:
            device_id: Logical device identifier.
            ip: Device IP address.
            email: Tapo account email (plaintext).
            password: Tapo account password (plaintext).

        Returns:
            Current PowerReading.
        """
        try:
            device = await self._get_device(device_id, ip, email, password)
            return self._extract_power(device)

        except Exception as exc:
            logger.warning("Failed to read power from Tapo device %s: %s", device_id, exc)
            self._evict(device_id, ip)
            raise RuntimeError(f"Power read failed: {exc}")

    def disconnect(self, device_id: str) -> None:
        """Remove cached client for a device.

        Args:
            device_id: Logical device identifier.
        """
        keys_to_remove = [k for k in self._client_cache if k.startswith(f"{device_id}:")]
        for key in keys_to_remove:
            del self._client_cache[key]
        if keys_to_remove:
            logger.debug("Disconnected Tapo device %s (cleared %d cached clients)", device_id, len(keys_to_remove))

    def clear_cache(self) -> None:
        """Clear all cached clients (used during shutdown)."""
        count = len(self._client_cache)
        self._client_cache.clear()
        if count:
            logger.debug("Cleared %d cached Tapo clients", count)
