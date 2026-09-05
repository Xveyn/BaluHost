"""Beim Beenden geht die Regelung an die Board-Automatik zurueck (#534).

Entschieden wird am Ist-Wert in sysfs, nicht an einer Besitz-Buchfuehrung: ein
Luefter im MANUAL-Modus wird vom Regelkreis nie geschrieben, ein Besitz-Modell
haette ihn deshalb nie erfasst -- und genau er stuende am Ende ungeregelt da.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService


def _service(monkeypatch, *, primary=True):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, MagicMock())
    service._use_linux_backend = True
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def _backend(current_enable):
    backend = MagicMock()
    backend._fan_cache = {
        "nct6798-isa-0290:pwm1": {
            "pwm_enable_path": MagicMock(),
            "gpu_vendor": None,
        }
    }
    backend._read_hwmon_file = AsyncMock(return_value=current_enable)
    backend.release_to_board = AsyncMock(return_value=True)
    return backend


@pytest.mark.asyncio
async def test_releases_when_value_deviates(monkeypatch):
    service = _service(monkeypatch)
    service._backend = _backend(current_enable=1)
    service._restore_values = {"nct6798-isa-0290:pwm1": 5}

    await service._release_all_to_board()

    service._backend.release_to_board.assert_awaited_once_with(
        "nct6798-isa-0290:pwm1", 5
    )


@pytest.mark.asyncio
async def test_no_write_when_already_on_target(monkeypatch):
    service = _service(monkeypatch)
    service._backend = _backend(current_enable=5)
    service._restore_values = {"nct6798-isa-0290:pwm1": 5}

    await service._release_all_to_board()

    service._backend.release_to_board.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_restore_value_means_no_write(monkeypatch):
    """Ohne Beobachtung passiert nichts -- der Kern des Entwurfs."""
    service = _service(monkeypatch)
    service._backend = _backend(current_enable=1)
    service._restore_values = {}

    await service._release_all_to_board()

    service._backend.release_to_board.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_at_full_speed_reads_zero_and_is_released(monkeypatch):
    """reg_to_pwm_enable() meldet Manual mit Duty 255 als 0."""
    service = _service(monkeypatch)
    service._backend = _backend(current_enable=0)
    service._restore_values = {"nct6798-isa-0290:pwm1": 5}

    await service._release_all_to_board()

    service._backend.release_to_board.assert_awaited_once()


@pytest.mark.asyncio
async def test_secondary_worker_releases_nothing(monkeypatch):
    service = _service(monkeypatch, primary=False)
    service._backend = _backend(current_enable=1)
    service._restore_values = {"nct6798-isa-0290:pwm1": 5}

    await service._release_all_to_board()

    service._backend.release_to_board.assert_not_awaited()


@pytest.mark.asyncio
async def test_gpu_fan_is_never_released(monkeypatch):
    service = _service(monkeypatch)
    backend = _backend(current_enable=1)
    backend._fan_cache["nct6798-isa-0290:pwm1"]["gpu_vendor"] = "amd"
    service._backend = backend
    service._restore_values = {"nct6798-isa-0290:pwm1": 5}

    await service._release_all_to_board()

    backend.release_to_board.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_cancels_the_loop_before_releasing(monkeypatch):
    """Umgekehrte Reihenfolge liesse die Schleife gegen die Rueckgabe schreiben."""
    service = _service(monkeypatch)
    service._backend = _backend(current_enable=1)
    service._restore_values = {"nct6798-isa-0290:pwm1": 5}
    order = []

    async def note_release():
        order.append("release")

    monkeypatch.setattr(service, "_release_all_to_board", note_release)
    service._is_running = True

    async def loop():
        try:
            await asyncio.sleep(3600)
        except BaseException:
            order.append("cancel")
            raise

    service._monitoring_task = asyncio.create_task(loop())
    await asyncio.sleep(0)

    await service.stop()

    assert order == ["cancel", "release"]


@pytest.mark.asyncio
async def test_release_is_idempotent(monkeypatch):
    """Zweiter Lauf: der Ist-Wert stimmt bereits, es wird nichts geschrieben."""
    service = _service(monkeypatch)
    backend = _backend(current_enable=1)
    service._backend = backend
    service._restore_values = {"nct6798-isa-0290:pwm1": 5}

    await service._release_all_to_board()
    backend._read_hwmon_file = AsyncMock(return_value=5)
    await service._release_all_to_board()

    assert backend.release_to_board.await_count == 1
