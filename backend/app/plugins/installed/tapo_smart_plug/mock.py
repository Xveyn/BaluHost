"""TapoMockService — mock Tapo communication for dev mode.

Provides realistic simulated data for Tapo P110/P115 smart plugs when
running on Windows or without real hardware.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict

from app.plugins.smart_device.capabilities import PowerReading, SwitchState


class TapoMockService:
    """Mock Tapo service for dev mode (no real hardware).

    Simulates:
    - NAS-typical power consumption: 60-180 W
    - EU voltage: 230 V +/- 5 V
    - Daily energy accumulation: 1.5-3.5 kWh
    - Switch state (defaults to ON, toggleable)
    """

    def __init__(self) -> None:
        # Track mock switch state per device
        self._switch_states: Dict[str, bool] = {}

    def _generate_power(self) -> PowerReading:
        """Generate a realistic mock power reading.

        Simulates NAS power consumption with:
        - Base load: ~120 W with +-30/+60 W variation
        - EU standard 230 V with +/- 5 V fluctuation
        - Current calculated from P = V * I
        - Daily energy: 1.5-3.5 kWh
        """
        base_watts = 120.0
        variation = random.uniform(-30, 60)  # Disk spin-up, network activity
        watts = max(60.0, min(180.0, base_watts + variation))

        voltage = 230.0 + random.uniform(-5, 5)
        current = watts / voltage
        energy_today = random.uniform(1.5, 3.5)

        return PowerReading(
            watts=round(watts, 1),
            voltage=round(voltage, 1),
            current=round(current, 3),
            energy_today_kwh=round(energy_today, 2),
            timestamp=datetime.now(timezone.utc),
        )

    async def connect(self, device_id: str) -> bool:
        """Simulate connecting to a device (always succeeds).

        Args:
            device_id: Logical device identifier.

        Returns:
            Always True in mock mode.
        """
        # Default to ON
        if device_id not in self._switch_states:
            self._switch_states[device_id] = True
        return True

    async def poll(self, device_id: str) -> Dict[str, Any]:
        """Return realistic mock data for a device.

        Args:
            device_id: Logical device identifier.

        Returns:
            Dict mapping capability name to state model.
        """
        is_on = self._switch_states.get(device_id, True)

        if is_on:
            power = self._generate_power()
        else:
            # Device off: 0 W standby (plug still reports voltage)
            power = PowerReading(
                watts=0.0,
                voltage=round(230.0 + random.uniform(-5, 5), 1),
                current=0.0,
                energy_today_kwh=round(random.uniform(0.5, 1.5), 2),
                timestamp=datetime.now(timezone.utc),
            )

        return {
            "switch": SwitchState(
                is_on=is_on,
                changed_at=datetime.now(timezone.utc),
            ),
            "power_monitor": power,
        }

    async def turn_on(self, device_id: str) -> SwitchState:
        """Simulate turning the plug ON.

        Args:
            device_id: Logical device identifier.

        Returns:
            Updated SwitchState.
        """
        self._switch_states[device_id] = True
        return SwitchState(is_on=True, changed_at=datetime.now(timezone.utc))

    async def turn_off(self, device_id: str) -> SwitchState:
        """Simulate turning the plug OFF.

        Args:
            device_id: Logical device identifier.

        Returns:
            Updated SwitchState.
        """
        self._switch_states[device_id] = False
        return SwitchState(is_on=False, changed_at=datetime.now(timezone.utc))

    async def get_power(self, device_id: str) -> PowerReading:
        """Get a mock power reading.

        Args:
            device_id: Logical device identifier.

        Returns:
            Mock PowerReading.
        """
        is_on = self._switch_states.get(device_id, True)
        if is_on:
            return self._generate_power()
        return PowerReading(
            watts=0.0,
            voltage=round(230.0 + random.uniform(-5, 5), 1),
            current=0.0,
            energy_today_kwh=round(random.uniform(0.5, 1.5), 2),
            timestamp=datetime.now(timezone.utc),
        )

    def disconnect(self, device_id: str) -> None:
        """Remove mock state for a device.

        Args:
            device_id: Logical device identifier.
        """
        self._switch_states.pop(device_id, None)

    def clear(self) -> None:
        """Clear all mock state."""
        self._switch_states.clear()
