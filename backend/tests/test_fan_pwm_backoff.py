"""Backoff gegen dauerhaft fehlschlagende PWM-Writes (#533).

Der Regelkreis schreibt alle 5 s. Gegen einen Knoten, den der Treiber nie
annimmt, ergab das 17k Logzeilen und 34k sudo-Aufrufe pro Tag. Die Tests hier
messen, dass nach einem Fehlschlag *nicht mehr geschrieben* wird, bis das
Backoff-Fenster abgelaufen ist.

Muster wie in test_fan_einval_diagnostic.py: echter tmp-sysfs-Baum, und
Path.write_text wird als I/O-Grenze ersetzt, damit die Fehlschlaege
reproduzierbar sind und die tatsaechlichen Schreibversuche zaehlbar bleiben.
"""
import json
import logging
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import get_settings
from app.models.fans import FanConfig
from app.schemas.fans import FanMode, PwmControl
from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.services.power.fan_control import FanControlService, FanData


def _hwmon(tmp_path: Path) -> Path:
    d = tmp_path / "sys" / "class" / "hwmon" / "hwmon1"
    d.mkdir(parents=True)
    (d / "name").write_text("nct6798\n")
    (d / "pwm1").write_text("128\n")
    (d / "fan1_input").write_text("1200\n")
    (d / "pwm1_enable").write_text("1\n")
    return d


async def _backend(tmp_path, monkeypatch) -> tuple[LinuxFanControlBackend, str]:
    _hwmon(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    return backend, next(iter(backend._fan_cache))


class _Clock:
    """Steuerbare monotone Uhr."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _fail_writes(monkeypatch) -> list[Path]:
    """Laesst jeden sysfs-Write mit EINVAL scheitern und zaehlt die Versuche."""
    attempts: list[Path] = []

    def failing_write(self_, _value, *_a, **_kw):
        attempts.append(self_)
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr(Path, "write_text", failing_write)
    return attempts


@pytest.mark.asyncio
async def test_second_write_within_backoff_window_is_suppressed(tmp_path, monkeypatch):
    """Nach einem Fehlschlag darf der naechste Zyklus die Hardware nicht anfassen."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)

    attempts = _fail_writes(monkeypatch)

    assert await backend.set_pwm(fan_id, 80) is False
    attempts_after_first = len(attempts)
    assert attempts_after_first > 0, "der erste Versuch muss die Hardware anfassen"

    clock.advance(5.0)  # ein Regelzyklus
    assert await backend.set_pwm(fan_id, 81) is False

    assert len(attempts) == attempts_after_first, (
        "innerhalb des Backoff-Fensters darf kein weiterer Write erfolgen"
    )


@pytest.mark.asyncio
async def test_backoff_window_doubles_with_each_failure(tmp_path, monkeypatch):
    """Zweiter Fehlschlag sperrt doppelt so lange wie der erste."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    attempts = _fail_writes(monkeypatch)

    await backend.set_pwm(fan_id, 80)  # Fehlschlag 1 -> 10 s Sperre

    clock.advance(10.0)
    await backend.set_pwm(fan_id, 81)  # Fehlschlag 2 -> 20 s Sperre
    attempts_after_second = len(attempts)

    clock.advance(10.0)  # erst die Haelfte des neuen Fensters
    await backend.set_pwm(fan_id, 82)
    assert len(attempts) == attempts_after_second, (
        "nach dem zweiten Fehlschlag muss das Fenster 20 s betragen, nicht wieder 10 s"
    )

    clock.advance(10.0)  # jetzt sind die 20 s um
    await backend.set_pwm(fan_id, 83)
    assert len(attempts) > attempts_after_second, "nach Fensterablauf muss neu versucht werden"


@pytest.mark.asyncio
async def test_backoff_window_is_capped_at_fifteen_minutes(tmp_path, monkeypatch):
    """Ohne Deckel waere das Fenster nach 10 Fehlschlaegen bei ueber 85 Minuten."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    attempts = _fail_writes(monkeypatch)

    for _ in range(10):
        await backend.set_pwm(fan_id, 80)
        clock.advance(100_000.0)  # jedes Fenster sicher ueberspringen

    await backend.set_pwm(fan_id, 80)  # Fehlschlag 11 setzt das Fenster neu
    attempts_before = len(attempts)

    clock.advance(900.0)  # exakt der Deckel
    await backend.set_pwm(fan_id, 81)

    assert len(attempts) > attempts_before, (
        "nach 15 Minuten muss wieder versucht werden, egal wie viele Fehlschlaege vorlagen"
    )


class _Writer:
    """sysfs-Write, der zwischen Erfolg und EINVAL umgeschaltet werden kann."""

    def __init__(self, monkeypatch) -> None:
        self.attempts: list[Path] = []
        self.fail = True
        real_write = Path.write_text

        def write(self_, value, *a, **kw):
            self.attempts.append(self_)
            if self.fail:
                raise OSError(22, "Invalid argument")
            return real_write(self_, value, *a, **kw)

        monkeypatch.setattr(Path, "write_text", write)


@pytest.mark.asyncio
async def test_successful_write_clears_the_backoff(tmp_path, monkeypatch):
    """Nach einem erfolgreichen Write faengt die Zaehlung wieder bei null an."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    writer = _Writer(monkeypatch)

    await backend.set_pwm(fan_id, 80)  # Fehlschlag 1
    clock.advance(10.0)
    await backend.set_pwm(fan_id, 81)  # Fehlschlag 2 -> 20 s

    clock.advance(20.0)
    writer.fail = False
    assert await backend.set_pwm(fan_id, 82) is True
    assert fan_id not in backend._write_backoff

    # Ein neuer Fehlschlag beginnt wieder mit dem Basisfenster (10 s), nicht 40 s.
    writer.fail = True
    await backend.set_pwm(fan_id, 83)
    before = len(writer.attempts)
    clock.advance(10.0)
    await backend.set_pwm(fan_id, 84)
    assert len(writer.attempts) > before, (
        "nach dem Erfolg muss die Eskalation zurueckgesetzt sein"
    )


@pytest.mark.asyncio
async def test_force_bypasses_the_backoff_window(tmp_path, monkeypatch):
    """Ein Nutzer-Klick bekommt einen echten Versuch, kein stilles False."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    attempts = _fail_writes(monkeypatch)

    await backend.set_pwm(fan_id, 80)  # Fehlschlag -> Fenster steht
    before = len(attempts)

    await backend.set_pwm(fan_id, 90, force=True)

    assert len(attempts) > before, "force muss die Hardware trotz Fenster anfassen"


@pytest.mark.asyncio
async def test_forced_success_clears_the_backoff(tmp_path, monkeypatch):
    """Wenn der erzwungene Versuch klappt, ist die Episode vorbei."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    writer = _Writer(monkeypatch)

    await backend.set_pwm(fan_id, 80)
    assert fan_id in backend._write_backoff

    writer.fail = False
    assert await backend.set_pwm(fan_id, 90, force=True) is True
    assert fan_id not in backend._write_backoff


# --- Aufrufer-Verdrahtung: wer darf das Fenster umgehen? ---------------------


class _RecordingBackend:
    """Merkt sich, ob der Aufrufer force gesetzt hat."""

    def __init__(self, temperature=70.0, pwm_percent=40):
        self.calls: list[tuple[str, int, bool]] = []
        self.temperature = temperature
        self.pwm_percent = pwm_percent

    async def get_fans(self):
        return [FanData(
            fan_id="case1", name="Gehaeuse", rpm=800, pwm_percent=self.pwm_percent,
            temperature_celsius=self.temperature, mode=FanMode.AUTO,
            min_pwm_percent=20, max_pwm_percent=100, emergency_temp_celsius=85.0,
            temp_sensor_id="hwmon:case1", curve_points=[], is_active=True,
            pwm_control=PwmControl.SUPPORTED,
        )]

    async def set_pwm(self, fan_id, pwm_percent, force=False):
        self.calls.append((fan_id, pwm_percent, force))
        return True


def _row(**overrides):
    base = dict(
        fan_id="case1", name="Gehaeuse", mode=FanMode.AUTO.value, is_active=True,
        min_pwm_percent=20, max_pwm_percent=100, emergency_temp_celsius=85.0,
        curve_json=json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}]),
        curve_type="graph", hysteresis_celsius=3.0, temp_sensor_id="hwmon:case1",
    )
    base.update(overrides)
    return FanConfig(**base)


def _service(db_session):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = False
    config.is_dev_mode = True
    config.fan_sample_interval_seconds = 2
    return FanControlService(config, lambda: db_session)


@pytest.mark.asyncio
async def test_regular_loop_respects_the_backoff(db_session):
    """Der 5-s-Takt ist genau der Aufrufer, der gedaempft werden soll."""
    db_session.add(_row())
    db_session.commit()
    service = _service(db_session)
    service._registry.get_temp = AsyncMock(return_value=60.0)
    service._backend = _RecordingBackend(temperature=60.0)
    try:
        await service._monitor_and_control_fans()
        assert service._backend.calls, "der Loop sollte in diesem Aufbau schreiben"
        assert all(force is False for _, _, force in service._backend.calls)
    finally:
        FanControlService._instance = None


@pytest.mark.asyncio
async def test_emergency_bypasses_the_backoff(db_session):
    """Thermische Sicherheit schlaegt Log-Hygiene."""
    db_session.add(_row())
    db_session.commit()
    service = _service(db_session)
    service._registry.get_temp = AsyncMock(return_value=99.0)  # ueber emergency_temp
    service._backend = _RecordingBackend(temperature=99.0)
    try:
        await service._monitor_and_control_fans()
        assert service._backend.calls, "im Notfall muss geschrieben werden"
        assert all(force is True for _, _, force in service._backend.calls)
    finally:
        FanControlService._instance = None


@pytest.mark.asyncio
async def test_manual_set_bypasses_the_backoff(db_session):
    """Der Nutzer hat geklickt: echter Versuch, echte Fehlermeldung."""
    db_session.add(_row(mode=FanMode.MANUAL.value))
    db_session.commit()
    service = _service(db_session)
    service._backend = _RecordingBackend()
    try:
        ok, _ = await service.set_fan_pwm("case1", 70)
        assert ok is True
        assert service._backend.calls == [("case1", 70, True)]
    finally:
        FanControlService._instance = None


# --- Log-Hygiene: der eigentliche Zweck von #533 -----------------------------


@pytest.mark.asyncio
async def test_repeated_failures_produce_exactly_one_error_line(tmp_path, monkeypatch, caplog):
    """17k identische ERROR-Zeilen machten jedes Alerting unbrauchbar."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    _fail_writes(monkeypatch)

    with caplog.at_level(logging.DEBUG, logger="app.services.power.fan_backend_linux"):
        for _ in range(20):
            await backend.set_pwm(fan_id, 80)
            clock.advance(100_000.0)  # jedes Fenster ueberspringen -> 20 Fehlschlaege

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, (
        f"eine Fehler-Episode darf genau eine ERROR-Zeile erzeugen, waren {len(errors)}"
    )
    assert "next retry in" in errors[0].getMessage()


@pytest.mark.asyncio
async def test_recovery_is_logged_once_at_info(tmp_path, monkeypatch, caplog):
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    writer = _Writer(monkeypatch)

    await backend.set_pwm(fan_id, 80)
    clock.advance(100_000.0)

    with caplog.at_level(logging.INFO, logger="app.services.power.fan_backend_linux"):
        writer.fail = False
        await backend.set_pwm(fan_id, 81)

    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("succeeded again" in m for m in infos), infos


@pytest.mark.asyncio
async def test_failure_episode_emits_no_warning_lines(tmp_path, monkeypatch, caplog):
    """Die WARNING-Zeilen verdoppelten die Diagnose, die die ERROR-Zeile schon traegt."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)

    # EACCES: hier greift zusaetzlich der sudo-tee-Fallback.
    def eacces_write(self_, value, *a, **kw):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(Path, "write_text", eacces_write)

    class _Result:
        returncode = 1
        stderr = b"tee: Permission denied"

    monkeypatch.setattr(
        "app.services.power.fan_backend_linux.subprocess.run",
        lambda *a, **kw: _Result(),
    )

    with caplog.at_level(logging.DEBUG, logger="app.services.power.fan_backend_linux"):
        await backend.set_pwm(fan_id, 80)

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [], f"unerwartete WARNING-Zeilen: {warnings}"


# --- Rescan: der Backoff darf nicht mit dem Cache verschwinden ---------------


@pytest.mark.asyncio
async def test_backoff_survives_a_rescan(tmp_path, monkeypatch):
    """_fan_cache wird beim Rescan neu gebaut — der Backoff-Zustand nicht."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(backend, "_monotonic", clock, raising=False)
    writer = _Writer(monkeypatch)

    await backend.set_pwm(fan_id, 80)
    assert fan_id in backend._write_backoff

    await backend._scan_pwm_fans()

    assert fan_id in backend._write_backoff, "der Rescan darf den Backoff nicht loeschen"
    before = len(writer.attempts)
    clock.advance(5.0)
    await backend.set_pwm(fan_id, 81)
    assert len(writer.attempts) == before, "das Fenster muss den Rescan ueberdauern"


@pytest.mark.asyncio
async def test_rescan_prunes_backoff_of_vanished_fans(tmp_path, monkeypatch):
    """Sonst waechst das Dict ueber Treiber-Reloads und Renumbering hinweg (#532).

    Bewusst mit ZWEI Lueftern: verschwindet der einzige, behaelt _scan_pwm_fans()
    absichtlich den alten Cache ("found 0 fans, keeping cached"). Der Fall, der
    hier zaehlt, ist der Teilverlust.
    """
    d = _hwmon(tmp_path)
    (d / "pwm2").write_text("140\n")
    (d / "fan2_input").write_text("900\n")
    (d / "pwm2_enable").write_text("1\n")

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    assert len(backend._fan_cache) == 2, sorted(backend._fan_cache)

    monkeypatch.setattr(backend, "_monotonic", _Clock(), raising=False)
    _Writer(monkeypatch)

    for fan_id in list(backend._fan_cache):
        await backend.set_pwm(fan_id, 80)
    assert len(backend._write_backoff) == 2

    # Ein Kanal verschwindet (Treiber-Reload, Geraet weg)
    gone = "hwmon1_pwm2"
    (d / "pwm2").unlink()
    await backend._scan_pwm_fans()

    assert gone not in backend._write_backoff, "verwaister Backoff-Eintrag"
    assert "hwmon1_pwm1" in backend._write_backoff, "der verbliebene Luefter behaelt sein Fenster"
