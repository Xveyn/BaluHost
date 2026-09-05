"""Vorbedingungen und Gate des Identitaets-Abgleichs (#532)."""
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.fans import FanCurvePoint, FanMode
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService, FanData


def _service(monkeypatch, *, primary: bool, linux: bool):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, MagicMock())
    service._use_linux_backend = linux
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def test_skips_when_not_primary_worker(monkeypatch):
    service = _service(monkeypatch, primary=False, linux=True)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_on_dev_backend(monkeypatch):
    # is_available() faellt bei 0 gefundenen Lueftern auch in Produktion auf
    # das Dev-Backend zurueck. Liefe der Abgleich dann, deaktivierte er in
    # einem Rutsch alle hwmon-Zeilen.
    service = _service(monkeypatch, primary=True, linux=False)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_when_scan_found_no_chip(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=0) is False


def test_runs_when_all_preconditions_hold(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=3) is True


@pytest.mark.asyncio
async def test_reconcile_failure_does_not_create_configs(monkeypatch, caplog):
    """Wirft reconcile_fan_identities, darf die Anlage-Schleife NICHT laufen.

    Sonst legte sie eine frische Default-Config unter der bereits neuen
    Scan-ID an, deren updated_at "jetzt" ist -- die schluege beim naechsten
    Abgleich jede echte Nutzerkurve. Genau das soll dieser Abgleich
    verhindern; ihn bei einem eigenen Fehler trotzdem durchlaufen zu lassen,
    waere derselbe Datenverlust auf einem Umweg.
    """
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False

    service = FanControlService(config, MagicMock())
    service._use_linux_backend = True
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)

    fan = FanData(
        fan_id="nct6798-isa-0290:pwm1",
        name="nct6798 PWM1",
        rpm=900,
        pwm_percent=40,
        temperature_celsius=None,
        mode=FanMode.AUTO,
        min_pwm_percent=0,
        max_pwm_percent=100,
        emergency_temp_celsius=85.0,
        temp_sensor_id=None,
        curve_points=[FanCurvePoint(temp=35, pwm=30)],
        is_active=True,
    )

    backend = AsyncMock()
    backend.get_fans.return_value = [fan]
    backend.get_available_temp_sensors.return_value = []
    backend._fan_cache = {
        "nct6798-isa-0290:pwm1": {
            "identity_stable": True,
            "device_driver": "nct6798",
        },
    }
    backend._temp_paths = {}
    service._backend = backend

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # keine Altzeile vorhanden
    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__enter__ = MagicMock(return_value=mock_db)
    mock_session_factory.return_value.__exit__ = MagicMock(return_value=False)
    service.db_session_factory = mock_session_factory

    def _boom(*args, **kwargs):
        raise RuntimeError("Abgleich kaputt")

    monkeypatch.setattr(fan_control_module, "reconcile_fan_identities", _boom)

    with caplog.at_level(logging.ERROR, logger="app.services.power.fan_control"):
        await service._load_fan_configs()  # darf NICHT werfen

    assert mock_db.add.call_count == 0, "Anlage-Schleife durfte nicht laufen"
    assert mock_db.commit.call_count == 0, "kein Commit nach fehlgeschlagenem Abgleich"
    assert any(r.levelno == logging.ERROR for r in caplog.records), (
        "Fehlschlag muss als ERROR mit Traceback geloggt werden"
    )
