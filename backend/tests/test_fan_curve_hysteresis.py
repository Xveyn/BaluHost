"""Die konfigurierte Kurve muss wirken, statt vom Hardcode 50 ersetzt zu werden (#517)."""
from unittest.mock import MagicMock

import pytest

from app.services.power.fan_control import FanControlService


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
        assert not hasattr(service, "_calculate_pwm_from_curve")
        assert service._apply_hysteresis("f1", 20.0, 3.0, 30) == 30
    finally:
        FanControlService._instance = None
