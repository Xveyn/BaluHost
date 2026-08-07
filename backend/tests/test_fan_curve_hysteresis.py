"""Die konfigurierte Kurve muss wirken, statt vom Hardcode 50 ersetzt zu werden (#517)."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.fans import FanConfig
from app.schemas.fans import FanMode, PwmControl
from app.services.power.fan_control import FanControlService, FanData


def _service():
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = False
    config.is_dev_mode = True
    return FanControlService(config, MagicMock())


def test_hysteresis_returns_the_given_target_on_first_call():
    service = _service()
    try:
        assert service._apply_hysteresis("f1", 50.0, 3.0, 42) == 42
    finally:
        FanControlService._instance = None


def test_rising_target_takes_effect_immediately():
    service = _service()
    try:
        service._apply_hysteresis("f1", 50.0, 3.0, 40)
        assert service._apply_hysteresis("f1", 60.0, 3.0, 70) == 70
    finally:
        FanControlService._instance = None


def test_falling_target_is_held_inside_the_deadband():
    service = _service()
    try:
        service._apply_hysteresis("f1", 60.0, 3.0, 70)
        # Nur 1 Grad gefallen, Hysterese ist 3 -> alter Wert wird gehalten
        assert service._apply_hysteresis("f1", 59.0, 3.0, 40) == 70
    finally:
        FanControlService._instance = None


def test_falling_target_applies_beyond_the_deadband():
    service = _service()
    try:
        service._apply_hysteresis("f1", 60.0, 3.0, 70)
        assert service._apply_hysteresis("f1", 55.0, 3.0, 40) == 40
    finally:
        FanControlService._instance = None


def test_hardcoded_fifty_is_gone():
    """Regression #517: kein Pfad darf mehr 50 aus dem Nichts liefern."""
    service = _service()
    try:
        assert service._apply_hysteresis("f1", 20.0, 3.0, 30) == 30
    finally:
        FanControlService._instance = None


# ---------------------------------------------------------------------------
# Integrationstest: deckt die eigentliche #517-Bruchstelle ab, die Aufrufstelle
# in _monitor_and_control_fans. Ein reiner Unit-Test von _apply_hysteresis
# haette den urspruenglichen Fehler (Ziel landete im falschen Parameter-Slot,
# plus eine leere Kurvenliste) nie gefangen, weil er die Verdrahtung zwischen
# evaluate_curve() und der Haemmpfung gar nicht ausuebt.
# ---------------------------------------------------------------------------

class _StubBackend:
    """Minimaler FanControlBackend-Stub: eine Karte, PWM-Schreiben moeglich."""

    def __init__(self, temperature: float, pwm_percent: int):
        self.temperature = temperature
        self.pwm_percent = pwm_percent
        self.set_pwm_calls = []

    async def get_fans(self):
        return [FanData(
            fan_id="f1", name="Test Fan", rpm=1000, pwm_percent=self.pwm_percent,
            temperature_celsius=self.temperature, mode=FanMode.AUTO,
            min_pwm_percent=10, max_pwm_percent=100, emergency_temp_celsius=95.0,
            temp_sensor_id="hwmon:test", curve_points=[], is_active=True,
            pwm_control=PwmControl.SUPPORTED,
        )]

    async def set_pwm(self, fan_id, pwm_percent):
        self.set_pwm_calls.append((fan_id, pwm_percent))
        return True


def _config_row(**overrides):
    # name ist NOT NULL ohne Default (models/fans.py).
    base = dict(
        fan_id="f1", name="Test Fan", mode=FanMode.AUTO.value, is_active=True,
        min_pwm_percent=10, max_pwm_percent=100, emergency_temp_celsius=95.0,
        curve_json=json.dumps([{"temp": 40, "pwm": 30}, {"temp": 80, "pwm": 100}]),
        curve_type="graph", hysteresis_celsius=3.0, temp_sensor_id="hwmon:test",
    )
    base.update(overrides)
    return FanConfig(**base)


def _monitor_service(db_session):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = False
    config.is_dev_mode = True
    config.fan_sample_interval_seconds = 2
    return FanControlService(config, lambda: db_session)


@pytest.mark.asyncio
async def test_monitor_loop_applies_the_curve_target_not_fifty(db_session):
    """#517: _monitor_and_control_fans muss das Kurvenziel an set_pwm reichen.

    Kurve: (40°C, 30%) -> (80°C, 100%). Bei 60°C interpoliert auf 65% — ein
    Wert, der weder der Hardcode 50 noch min_pwm_percent (10) ist, damit der
    Test die Verdrahtung tatsaechlich beweist.
    """
    db_session.add(_config_row())
    db_session.commit()

    service = _monitor_service(db_session)
    service._registry.get_temp = AsyncMock(return_value=60.0)
    backend = _StubBackend(temperature=60.0, pwm_percent=0)
    service._backend = backend
    try:
        await service._monitor_and_control_fans()

        assert backend.set_pwm_calls == [("f1", 65)]
        assert backend.set_pwm_calls[0][1] != 50
        assert backend.set_pwm_calls[0][1] != 10  # min_pwm_percent
    finally:
        FanControlService._instance = None
