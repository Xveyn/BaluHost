# RDNA3-Lüfter-Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BaluHost erkennt firmware-verwaltete GPU-Lüfterkurven (RDNA3+), schreibt dort kein PWM mehr ins Leere, erklärt im UI und in der Fehlermeldung wahrheitsgemäß warum — und die konfigurierte Lüfterkurve wirkt wieder (#517).

**Architecture:** Ein Enum-Feld `pwm_control` (`supported` / `firmware_managed` / `no_permission`) wird beim hwmon-Scan über den `device`-Symlink bestimmt und über `_fan_cache` → `FanData` → `FanInfo` bis ins Frontend durchgereicht. Der Regel-Loop überspringt aussichtslose Schreibversuche, der Schreibpfad unterscheidet `EACCES` von `EINVAL`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, pytest + pytest-asyncio; React 18, TypeScript, Vitest, i18next.

**Spec:** `docs/superpowers/specs/2026-08-06-rdna3-fan-capability-design.md`
**Issues:** #480 (Hauptthema), #517 (Kurven-Bug, Task 7), #516 (Folge-Feature, nur referenziert)

## Global Constraints

- **Der Erkennungspfad ist `hwmon_dir / "device" / "gpu_od" / "fan_ctrl" / "fan_curve"`.** An der Hardware verifiziert. `hwmon_dir.resolve()` mit Suche nach einer Pfadkomponente `device` funktioniert auf echter Hardware **nicht** (`readlink -f /sys/class/hwmon/hwmon2` enthält kein `/device/`) — nicht wieder einführen.
- Aus einem fehlenden `gpu_od/` darf **niemals** auf ein fehlendes Overdrive-Bit geschlossen und daraus eine Handlungsempfehlung abgeleitet werden. Genau dieser Fehlschluss ist der Inhalt von #480.
- Die Meldung für `firmware_managed` muss explizit erwähnen, dass `amdgpu.ppfeaturemask` daran nichts ändert.
- Backend-Meldungstexte (`last_write_error`) bleiben **englisch**. Frontend-Strings in `de` **und** `en`, Namespace `system`.
- **Die Modus-Buttons AUTO/SCHEDULED/MANUAL werden nie gesperrt.** Der Modus ist DB-Konfiguration, kein Hardware-Write; der AUTO-Button ist der einzige Ausweg aus einem persistierten `emergency`-Zustand.
- Kein Fix der fehlenden Schreibrechte, kein Anfassen von `deploy/`.
- Default für jeden Lüfter ohne Befund ist `PwmControl.SUPPORTED`.
- Die volle Backend-Suite läuft auf Windows nicht durch. Lokal nur die genannten Testdateien gezielt; die Gesamtsuite übernimmt CI.

---

## File Structure

**Backend**

| Datei | Verantwortung | Änderung |
|---|---|---|
| `backend/app/schemas/fans.py` | `PwmControl`-Enum, Feld in `FanInfo` | modify |
| `backend/app/services/power/fan_gpu_manual.py` | `probe_amd_pwm_control()`, reparierter `_device_from_hwmon()`, Rollback | modify |
| `backend/app/services/power/fan_control.py` | `FanData`-Feld, `get_status()`, Loop-Skip, Hysterese-Fix (#517) | modify |
| `backend/app/services/power/fan_backend_linux.py` | Scan füllt das Feld, `set_pwm`, errno-Trennung | modify |
| `backend/app/services/power/fan_backend_dev.py` | Default + simulierter Firmware-GPU-Lüfter | modify |
| `backend/app/api/routes/fans.py` | Guards auf `gpu-manual-mode` und `/pwm` | modify |

**Frontend**

| Datei | Verantwortung | Änderung |
|---|---|---|
| `client/src/api/fan-control.ts` | `pwm_control` im `FanInfo`-Typ | modify |
| `client/src/components/fan-control/FanCard.tsx` | Badge, PWM-Slider sperren | modify |
| `client/src/components/fan-control/FanDetails.tsx` | Erklärpanel, per-Lüfter-Read-only | modify |
| `client/src/components/fan-control/FirmwareFanNotice.tsx` | das Erklärpanel | create |
| `client/src/components/fan-control/CurveEditorSync.tsx` | firmware-verwaltete Lüfter filtern | modify |
| `client/src/i18n/locales/{de,en}/system.json` | `fanControl.gpu.firmware.*` | modify |

---

## Task 1: Erkennung über den `device`-Symlink

**Files:**
- Modify: `backend/app/schemas/fans.py` (nach `class FanMode`, Zeile 10-15)
- Modify: `backend/app/services/power/fan_gpu_manual.py:71-82` (`_device_from_hwmon`) und neue Funktion
- Test: `backend/tests/test_fan_pwm_control_probe.py` (create)

**Interfaces:**
- Produces: `PwmControl` (str-Enum: `SUPPORTED`, `FIRMWARE_MANAGED`, `NO_PERMISSION`) aus `app.schemas.fans`; `probe_amd_pwm_control(hwmon_dir: Path) -> PwmControl` aus `app.services.power.fan_gpu_manual`.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/test_fan_pwm_control_probe.py`:

```python
"""probe_amd_pwm_control: firmware-verwaltete Luefterkurven erkennen (RDNA3+, #480)."""
from pathlib import Path

from app.schemas.fans import PwmControl
from app.services.power.fan_gpu_manual import probe_amd_pwm_control


def _hardware_shaped_tree(tmp_path: Path, *, with_fan_curve: bool) -> Path:
    """Bildet die ECHTE sysfs-Struktur nach.

    Auf der Hardware liegt hwmon unter /sys/class/hwmon/hwmonN und traegt einen
    'device'-Symlink auf das PCI-Geraet. KEIN Elternverzeichnis heisst 'device'
    — genau daran ist der erste Entwurf gescheitert.
    """
    hwmon = tmp_path / "sys" / "class" / "hwmon" / "hwmon2"
    device = hwmon / "device"
    device.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    (device / "vendor").write_text("0x1002\n")
    if with_fan_curve:
        fan_ctrl = device / "gpu_od" / "fan_ctrl"
        fan_ctrl.mkdir(parents=True)
        (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")
    return hwmon


def _drm_shaped_tree(tmp_path: Path, *, with_fan_curve: bool) -> Path:
    """Die synthetische Struktur, die bestehende Tests verwenden."""
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (hwmon / "name").write_text("amdgpu\n")
    if with_fan_curve:
        fan_ctrl = device / "gpu_od" / "fan_ctrl"
        fan_ctrl.mkdir(parents=True)
        (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")
    return hwmon


def test_hardware_layout_detects_firmware_managed(tmp_path):
    """Der Fall, der in Produktion zaehlt."""
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.FIRMWARE_MANAGED


def test_hardware_layout_without_fan_curve_is_supported(tmp_path):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=False)
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_drm_layout_still_works(tmp_path):
    """Der Aufwaertslauf bleibt als Fallback erhalten."""
    hwmon = _drm_shaped_tree(tmp_path, with_fan_curve=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.FIRMWARE_MANAGED


def test_gpu_od_without_fan_curve_is_supported(tmp_path):
    """gpu_od/ allein genuegt nicht — nur fan_curve ist der Marker."""
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=False)
    (hwmon / "device" / "gpu_od" / "fan_ctrl").mkdir(parents=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_non_amd_vendor_is_supported(tmp_path):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=True)
    (hwmon / "device" / "vendor").write_text("0x10de\n")
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_board_sensor_without_device_is_supported(tmp_path):
    hwmon = tmp_path / "sys" / "class" / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py -v`
Expected: FAIL mit `ImportError: cannot import name 'PwmControl'`

- [ ] **Step 3: Enum ergänzen**

In `backend/app/schemas/fans.py` nach `class FanMode` (Zeile 15):

```python
class PwmControl(str, Enum):
    """Ob PWM-Schreiben fuer einen Luefter moeglich ist — und wenn nicht, warum.

    SUPPORTED:        Default. Schreiben wird versucht.
    FIRMWARE_MANAGED: RDNA3+ (SMU13). Die Kurve liegt in der Firmware unter
                      gpu_od/fan_ctrl; der Treiber lehnt PWM mit EINVAL ab (#480).
    NO_PERMISSION:    EACCES beim Schreiben beobachtet. Laufzeit-Befund, kein
                      Hardware-Merkmal — wird bei erfolgreichem Write zurueckgesetzt.
    """
    SUPPORTED = "supported"
    FIRMWARE_MANAGED = "firmware_managed"
    NO_PERMISSION = "no_permission"
```

- [ ] **Step 4: `_device_from_hwmon` reparieren**

In `fan_gpu_manual.py` die Funktion (Zeilen 71-82) ersetzen:

```python
def _device_from_hwmon(hwmon_dir: Path, drm_root: Optional[Path] = None) -> Optional[Path]:
    """Finde das amdgpu-PCI-Device zu einer hwmon-Directory.

    Primaerweg: jede hwmon-Directory traegt einen 'device'-Symlink auf ihr
    PCI-Geraet. An der Hardware verifiziert:
        ls -d /sys/class/hwmon/hwmon2/device/gpu_od/fan_ctrl  -> existiert

    Fallback: Aufwaertslauf ueber den aufgeloesten Pfad. Der funktioniert NUR
    in synthetischen Baeumen — real enthaelt readlink -f keine Komponente
    namens 'device'. Bleibt erhalten, damit bestehende Tests gueltig bleiben.
    """
    direct = hwmon_dir / "device"
    try:
        if (direct / "vendor").read_text().strip() == AMD_VENDOR_ID:
            return direct
    except OSError:
        pass

    p = hwmon_dir.resolve()
    for parent in p.parents:
        if parent.name == "device" and (parent / "vendor").exists():
            try:
                if (parent / "vendor").read_text().strip() == AMD_VENDOR_ID:
                    return parent
            except OSError:
                pass
    return None
```

- [ ] **Step 5: Erkennungsfunktion ergänzen**

Import oben in `fan_gpu_manual.py`: `from app.schemas.fans import PwmControl`. Dann vor `_device_from_hwmon`:

```python
def probe_amd_pwm_control(hwmon_dir: Path) -> PwmControl:
    """Stellt fest, ob Live-PWM fuer diesen AMD-GPU-Luefter moeglich ist.

    Ab RDNA3 (SMU13) liegt die Luefterkurve in der Firmware und wird ueber
    <device>/gpu_od/fan_ctrl/ exponiert; pwm{n}-Writes lehnt der Treiber mit
    EINVAL ab. Die Existenz von fan_curve ist der Marker.

    WICHTIG: Aus einem fehlenden gpu_od/ darf NICHT auf ein fehlendes
    Overdrive-Bit geschlossen werden. Auf der Referenzkarte (RX 7900 XT) war
    amdgpu.ppfeaturemask=0xffffffff gesetzt und PWM trotzdem tot — die
    gegenteilige Annahme war der urspruengliche Fehler in #480.
    """
    device = _device_from_hwmon(hwmon_dir)
    if device is None:
        return PwmControl.SUPPORTED
    if (device / "gpu_od" / "fan_ctrl" / "fan_curve").exists():
        return PwmControl.FIRMWARE_MANAGED
    return PwmControl.SUPPORTED
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py tests/test_fan_gpu_manual_mode.py -v`
Expected: alle PASSED — die neuen sechs und die bestehenden Manual-Mode-Tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/fans.py backend/app/services/power/fan_gpu_manual.py backend/tests/test_fan_pwm_control_probe.py
git commit -m "feat(fans): RDNA3-Erkennung ueber den hwmon-device-Symlink (#480)"
```

---

## Task 2: Feld durchreichen — Cache, `FanData`, `FanInfo`

**Files:**
- Modify: `backend/app/services/power/fan_control.py:37-57`, `:707-709`, `:755-757`
- Modify: `backend/app/services/power/fan_backend_linux.py:265-358` (`_scan_pwm_fans`), `:93-110` (`get_fans`)
- Modify: `backend/app/services/power/fan_backend_dev.py:94-121` (`get_fans`)
- Modify: `backend/app/schemas/fans.py` (`FanInfo`, nach `last_write_error`)
- Test: `backend/tests/test_fan_pwm_control_probe.py` (erweitern)

**Interfaces:**
- Consumes: `PwmControl`, `probe_amd_pwm_control` (Task 1).
- Produces: `FanData.pwm_control: PwmControl`, `FanInfo.pwm_control: PwmControl`, Cache-Key `"pwm_control"`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `backend/tests/test_fan_pwm_control_probe.py` anhängen:

```python
import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


@pytest.mark.asyncio
async def test_scan_marks_rdna3_fan_firmware_managed(tmp_path, monkeypatch):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=True)
    (hwmon / "pwm1").write_text("0\n")
    (hwmon / "fan1_input").write_text("0\n")
    (hwmon / "pwm1_enable").write_text("2\n")

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", hwmon.parent)
    await backend._scan_pwm_fans()

    fan_id = next(iter(backend._fan_cache))
    assert backend._fan_cache[fan_id]["pwm_control"] is PwmControl.FIRMWARE_MANAGED

    fans = await backend.get_fans()
    assert fans[0].pwm_control is PwmControl.FIRMWARE_MANAGED


@pytest.mark.asyncio
async def test_scan_marks_normal_fan_supported(tmp_path, monkeypatch):
    hwmon = _hardware_shaped_tree(tmp_path, with_fan_curve=False)
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "fan1_input").write_text("1200\n")
    (hwmon / "pwm1_enable").write_text("2\n")

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", hwmon.parent)
    await backend._scan_pwm_fans()

    fan_id = next(iter(backend._fan_cache))
    assert backend._fan_cache[fan_id]["pwm_control"] is PwmControl.SUPPORTED
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py -v`
Expected: FAIL mit `KeyError: 'pwm_control'`

- [ ] **Step 3: `FanData` erweitern**

`fan_control.py`: im Import-Block `PwmControl` aus `app.schemas.fans` ergänzen (dort stehen bereits `FanMode`, `FanCurvePoint`), dann in der Dataclass nach `last_write_error` (Zeile 57):

```python
    pwm_control: PwmControl = PwmControl.SUPPORTED
```

- [ ] **Step 4: Linux-Backend füllen**

Imports oben in `fan_backend_linux.py`:

```python
from app.schemas.fans import FanMode, FanCurvePoint, PwmControl
from app.services.power.fan_gpu_manual import probe_amd_pwm_control
```

In `_scan_pwm_fans` vor dem `new_cache[fan_id] = {...}`-Block:

```python
                pwm_control = PwmControl.SUPPORTED
                if gpu_vendor == "amd":
                    try:
                        pwm_control = probe_amd_pwm_control(hwmon_dir)
                    except OSError as exc:
                        logger.debug(f"pwm_control probe failed for {hwmon_dir}: {exc}")
```

Im Dict-Literal nach `"device_driver": hwmon_name_value,`:

```python
                    "pwm_control": pwm_control,
```

In `get_fans()` im `FanData(...)`-Aufruf nach `last_write_error=...`:

```python
                pwm_control=fan_info.get("pwm_control", PwmControl.SUPPORTED),
```

- [ ] **Step 5: Dev-Backend gleichziehen**

`fan_backend_dev.py`: Import auf `from app.schemas.fans import FanMode, FanCurvePoint, PwmControl` erweitern, im `FanData(...)`-Aufruf nach `device_driver=...`:

```python
                pwm_control=fan_data.get("pwm_control", PwmControl.SUPPORTED),
```

- [ ] **Step 6: Bis in die API durchreichen**

`schemas/fans.py`, `FanInfo` nach `last_write_error`:

```python
    pwm_control: PwmControl = PwmControl.SUPPORTED
```

`fan_control.py` an **beiden** Stellen in `get_status()` (nach Zeile 709 und nach Zeile 757):

```python
                        "pwm_control": fan.pwm_control,
```

Beide Vorkommen sind nötig — wird nur eines geändert, verschwindet das Feld je nach Codepfad aus der API-Antwort.

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py tests/test_fan_gpu_recognition.py -v`
Expected: alle PASSED

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/fans.py backend/app/services/power/fan_control.py backend/app/services/power/fan_backend_linux.py backend/app/services/power/fan_backend_dev.py backend/tests/test_fan_pwm_control_probe.py
git commit -m "feat(fans): pwm_control von Scan bis FanInfo durchreichen (#480)"
```

---

## Task 3: Simulierter firmware-verwalteter GPU-Lüfter

**Files:**
- Modify: `backend/app/services/power/fan_backend_dev.py:25-88` (`_initialize_simulated_fans`), `:123-139` (`set_pwm`)
- Modify: `backend/tests/services/test_fan_control.py:45`, `:73`, `:372`
- Test: `backend/tests/test_fan_pwm_control_probe.py` (erweitern)

**Interfaces:**
- Produces: Lüfter-ID `dev_gpu_rdna3_pwm1` mit `pwm_control=FIRMWARE_MANAGED`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `backend/tests/test_fan_pwm_control_probe.py` anhängen:

```python
@pytest.mark.asyncio
async def test_dev_backend_exposes_a_firmware_managed_gpu_fan():
    from app.services.power.fan_backend_dev import DevFanControlBackend

    backend = DevFanControlBackend(get_settings())
    fans = {f.fan_id: f for f in await backend.get_fans()}

    assert fans["dev_gpu_pwm1"].pwm_control is PwmControl.SUPPORTED
    assert fans["dev_gpu_rdna3_pwm1"].pwm_control is PwmControl.FIRMWARE_MANAGED
    assert await backend.set_pwm("dev_gpu_rdna3_pwm1", 80) is False
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py::test_dev_backend_exposes_a_firmware_managed_gpu_fan -v`
Expected: FAIL mit `KeyError: 'dev_gpu_rdna3_pwm1'`

- [ ] **Step 3: Den simulierten Lüfter ergänzen**

In `_initialize_simulated_fans()` nach dem `dev_gpu_pwm1`-Eintrag:

```python
            "dev_gpu_rdna3_pwm1": {
                "name": "AMD RDNA3 GPU Fan (sim, firmware-managed)",
                "pwm_percent": 0,
                "target_rpm": 0,
                "current_rpm": 0,
                "min_rpm": 0,
                "max_rpm": 3000,
                "temp_sensor_id": "dev_gpu_temp",
                "last_update": time.time(),
                "is_gpu_fan": True,
                "gpu_vendor": "amd",
                "device_driver": "amdgpu",
                "pwm_control": PwmControl.FIRMWARE_MANAGED,
            },
```

Den Docstring in Zeile 26 auf `"""Initialize 5 simulated PWM fans (3 CPU + 2 GPU)."""` korrigieren.

In `set_pwm()` nach der Existenzprüfung:

```python
        if self._fans[fan_id].get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
            logger.debug(f"{fan_id}: firmware-managed, PWM write skipped")
            return False
```

- [ ] **Step 4: Bestehende Erwartungen nachziehen**

In `backend/tests/services/test_fan_control.py` die drei Stellen von `4` auf `5` ändern:
- Zeile 45: `assert len(backend._fans) == 5`
- Zeile 73: `assert len(fans) == 5`
- Zeile 372: `assert len(fans1) == len(fans2) == 5`

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py tests/services/test_fan_control.py -v`
Expected: alle PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_backend_dev.py backend/tests/test_fan_pwm_control_probe.py backend/tests/services/test_fan_control.py
git commit -m "feat(fans): simulierter firmware-verwalteter GPU-Luefter im Dev-Backend (#480)"
```

---

## Task 4: Schreibpfad — Frühabbruch, errno-Trennung, ehrliche Meldungen

**Files:**
- Modify: `backend/app/services/power/fan_backend_linux.py:114-152` (`set_pwm`), `:372-404` (`_write_hwmon_file`)
- Test: `backend/tests/test_fan_einval_diagnostic.py`

**Interfaces:**
- Produces: `_write_hwmon_file(path, value) -> Tuple[bool, Optional[int]]`; Modulkonstante `FIRMWARE_MANAGED_WRITE_ERROR: str`.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An `backend/tests/test_fan_einval_diagnostic.py` anhängen:

```python
from app.schemas.fans import PwmControl


def _amd_hwmon(tmp_path, pwm="128", rpm="1200"):
    d = tmp_path / "sys" / "class" / "hwmon" / "hwmon1"
    d.mkdir(parents=True)
    (d / "name").write_text("amdgpu\n")
    (d / "pwm1").write_text(f"{pwm}\n")
    (d / "fan1_input").write_text(f"{rpm}\n")
    (d / "pwm1_enable").write_text("2\n")
    return d


@pytest.mark.asyncio
async def test_firmware_managed_fan_is_not_written_at_all(tmp_path, monkeypatch):
    d = _amd_hwmon(tmp_path, pwm="0", rpm="0")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    fan_id = next(iter(backend._fan_cache))
    backend._fan_cache[fan_id]["pwm_control"] = PwmControl.FIRMWARE_MANAGED

    writes = []
    monkeypatch.setattr(Path, "write_text", lambda self_, v: writes.append(self_))

    ok = await backend.set_pwm(fan_id, 80)

    assert ok is False
    assert writes == []
    err = backend._fan_cache[fan_id]["last_write_error"]
    assert "ppfeaturemask" in err
    assert "enable manual mode in the UI" not in err


@pytest.mark.asyncio
async def test_eacces_reports_permission_not_kernel_rejection(tmp_path, monkeypatch):
    d = _amd_hwmon(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    fan_id = next(iter(backend._fan_cache))

    def fail_eacces(self_, value):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "write_text", fail_eacces)
    with patch("subprocess.run") as srun:
        srun.return_value.returncode = 1
        srun.return_value.stderr = b"a password is required"
        ok = await backend.set_pwm(fan_id, 80)

    assert ok is False
    err = backend._fan_cache[fan_id]["last_write_error"]
    assert "EACCES" in err
    assert "rejected by kernel" not in err
    assert backend._fan_cache[fan_id]["pwm_control"] is PwmControl.NO_PERMISSION


@pytest.mark.asyncio
async def test_successful_write_clears_no_permission(tmp_path, monkeypatch):
    """Werden Rechte zur Laufzeit korrigiert, muss der Zustand zurueckgehen."""
    d = _amd_hwmon(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", tmp_path / "sys" / "class" / "hwmon")
    await backend._scan_pwm_fans()
    fan_id = next(iter(backend._fan_cache))
    backend._fan_cache[fan_id]["pwm_control"] = PwmControl.NO_PERMISSION
    backend._fan_cache[fan_id]["last_write_error"] = "stale"

    ok = await backend.set_pwm(fan_id, 60)

    assert ok is True
    assert backend._fan_cache[fan_id]["pwm_control"] is PwmControl.SUPPORTED
    assert backend._fan_cache[fan_id]["last_write_error"] is None
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_einval_diagnostic.py -v`
Expected: die drei neuen FAIL, der bestehende `test_write_failure_captures_diagnostic` bleibt grün.

- [ ] **Step 3: `_write_hwmon_file` auf `(ok, errno)` umstellen**

Oben in `fan_backend_linux.py` `import errno` und `import getpass` ergänzen (`Tuple` ist im `typing`-Import bereits vorhanden). Dann ersetzen:

```python
    async def _write_hwmon_file(self, path: Path, value: str) -> Tuple[bool, Optional[int]]:
        """Write value to hwmon sysfs file.

        Returns (ok, errno). errno ist der Code des letzten fehlgeschlagenen
        Versuchs, damit der Aufrufer EACCES (fehlende Rechte) von EINVAL
        (Treiber lehnt ab) unterscheiden kann — beide brauchen voellig
        verschiedene Handlungsempfehlungen.
        """
        if not path or not path.exists():
            return False, None

        try:
            path.write_text(value + "\n")
            self._has_write_permission = True
            return True, None
        except OSError as exc:
            code = exc.errno
            if code not in (errno.EACCES, errno.EPERM):
                logger.debug(f"Write to {path} failed: {exc}")
                return False, code

            # Fehlende Rechte: sudo-tee-Fallback. -n, damit ein fehlender
            # sudoers-Eintrag sofort scheitert statt in den Timeout zu laufen.
            try:
                result = subprocess.run(
                    ["sudo", "-n", "tee", str(path)],
                    input=value.encode(),
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self._has_write_permission = True
                    logger.debug(f"Wrote to {path} via sudo tee")
                    return True, None
                logger.warning(f"sudo tee failed for {path}: {result.stderr.decode()}")
            except Exception as exc2:
                logger.error(f"Failed to write {path} with sudo: {exc2}")
            return False, errno.EACCES
        except Exception as exc:
            # Catch-all wie bisher: nichts Unerwartetes in den Loop propagieren.
            logger.error(f"Failed to write {path}: {exc}")
            return False, None
```

- [ ] **Step 4: `set_pwm` umbauen**

Modulkonstante nach `logger = logging.getLogger(__name__)`:

```python
FIRMWARE_MANAGED_WRITE_ERROR = (
    "This GPU manages its fan curve in firmware (RDNA3+). The amdgpu driver "
    "does not support live PWM control on this card — setting "
    "amdgpu.ppfeaturemask=0xffffffff does NOT change that. Control is only "
    "possible through the firmware curve (gpu_od/fan_ctrl), see issue #516."
)
```

`set_pwm` (Zeilen 114-152) ersetzen:

```python
    async def set_pwm(self, fan_id: str, pwm_percent: int) -> bool:
        """Set hardware PWM value."""
        if fan_id not in self._fan_cache:
            logger.warning(f"Fan {fan_id} not found in cache")
            return False

        fan_info = self._fan_cache[fan_id]

        # Firmware besitzt die Kurve: sysfs gar nicht erst anfassen.
        if fan_info.get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
            fan_info["last_write_error"] = FIRMWARE_MANAGED_WRITE_ERROR
            logger.debug(f"{fan_id}: firmware-managed fan curve, PWM write skipped")
            return False

        pwm_path = fan_info["pwm_path"]
        pwm_enable_path = fan_info.get("pwm_enable_path")

        pwm_percent = max(0, min(100, pwm_percent))
        pwm_value = self._percent_to_pwm(pwm_percent)

        if pwm_enable_path:
            ok_enable, _ = await self._write_hwmon_file(pwm_enable_path, "1")
            if not ok_enable:
                logger.warning(f"Failed to set PWM enable for {fan_id}")

        success, err_code = await self._write_hwmon_file(pwm_path, str(pwm_value))
        if success:
            fan_info["last_write_error"] = None
            if fan_info.get("pwm_control") is PwmControl.NO_PERMISSION:
                # Rechte wurden zur Laufzeit korrigiert.
                fan_info["pwm_control"] = PwmControl.SUPPORTED
            logger.debug(f"Set {fan_id} PWM to {pwm_percent}% ({pwm_value}/255)")
            return True

        if err_code in (errno.EACCES, errno.EPERM):
            fan_info["pwm_control"] = PwmControl.NO_PERMISSION
            try:
                user = getpass.getuser()
            except Exception:
                user = "the service user"
            fan_info["last_write_error"] = (
                f"No write permission for {pwm_path} (EACCES). The backend runs as "
                f"'{user}' and the udev rule does not cover hwmon PWM nodes."
            )
        else:
            driver = fan_info.get("device_driver", "unknown")
            enable_val = None
            if pwm_enable_path:
                v = await self._read_hwmon_file(pwm_enable_path)
                enable_val = v if v is not None else "?"
            fan_info["last_write_error"] = (
                f"PWM write rejected by kernel (driver={driver}, "
                f"pwm_enable={enable_val}, errno={err_code})."
            )

        logger.error(f"Failed to write PWM for {fan_id}: {fan_info['last_write_error']}")
        return False
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_einval_diagnostic.py tests/test_fan_pwm_control_probe.py -v`
Expected: alle PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_backend_linux.py backend/tests/test_fan_einval_diagnostic.py
git commit -m "fix(fans): EACCES von EINVAL trennen, firmware-verwaltete Luefter nicht schreiben (#480)"
```

---

## Task 5: Kurven-Bug #517 — Hysterese dämpft statt neu zu rechnen

**Files:**
- Modify: `backend/app/services/power/fan_control.py:533-536` (Aufrufstelle), `:557-582` (`_calculate_pwm_from_curve` entfällt), `:585-639` (`_calculate_pwm_with_hysteresis` → `_apply_hysteresis`)
- Test: `backend/tests/test_fan_curve_hysteresis.py` (create)

**Interfaces:**
- Produces: `_apply_hysteresis(fan_id: str, temperature: float, hysteresis: float, target_pwm: int) -> int`. Ersetzt `_calculate_pwm_with_hysteresis`; `_calculate_pwm_from_curve` wird gelöscht.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_curve_hysteresis.py`:

```python
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
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_curve_hysteresis.py -v`
Expected: FAIL mit `AttributeError: 'FanControlService' object has no attribute '_apply_hysteresis'`

- [ ] **Step 3: `_calculate_pwm_from_curve` löschen**

Die gesamte Methode `fan_control.py:557-582` entfernen. Sie hat nach Step 4 keinen Aufrufer mehr, und ihre Interpolation dupliziert `services/power/fan_curve_eval.py`.

- [ ] **Step 4: `_calculate_pwm_with_hysteresis` durch `_apply_hysteresis` ersetzen**

Die Methode (Zeilen 585-639) vollständig ersetzen:

```python
    def _apply_hysteresis(
        self,
        fan_id: str,
        temperature: float,
        hysteresis: float,
        target_pwm: int,
    ) -> int:
        """Daempft ein BEREITS BERECHNETES PWM-Ziel gegen Oszillation.

        Steigende Ziele greifen sofort (Sicherheit); fallende erst, wenn die
        Temperatur um `hysteresis` Grad unter den Wert gefallen ist, bei dem
        zuletzt geregelt wurde.

        #517: Der Vorgaenger rechnete das Ziel aus einer Kurve NEU — und bekam
        vom einzigen Aufrufer eine leere Liste, was den Hardcode 50 lieferte und
        das Ergebnis von evaluate_curve verwarf. Diese Funktion rechnet nichts
        mehr aus; die Kurvenauswertung gehoert allein fan_curve_eval.py.
        """
        current_time = time.time()

        if fan_id not in self._hysteresis_state:
            self._hysteresis_state[fan_id] = HysteresisState(
                last_pwm=target_pwm,
                last_pwm_temp=temperature,
                last_update=current_time,
            )
            return target_pwm

        state = self._hysteresis_state[fan_id]

        if target_pwm > state.last_pwm:
            # Temperatur steigt — sofort reagieren.
            state.last_pwm = target_pwm
            state.last_pwm_temp = temperature
            state.last_update = current_time
            return target_pwm

        if target_pwm < state.last_pwm:
            if temperature <= (state.last_pwm_temp - hysteresis):
                state.last_pwm = target_pwm
                state.last_pwm_temp = temperature
                state.last_update = current_time
                return target_pwm
            return state.last_pwm

        return state.last_pwm
```

- [ ] **Step 5: Die Aufrufstelle korrigieren**

`fan_control.py:533-536` ersetzen:

```python
                        target_pwm = self._apply_hysteresis(
                            fan.fan_id, temperature or 0.0,
                            getattr(config, "hysteresis_celsius", 3.0), target_pwm,
                        ) if eval_cfg.curve_type == "graph" else target_pwm
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_curve_hysteresis.py tests/test_fan_curve_eval.py tests/test_fan_composite_api.py tests/test_fan_sensor_label_api.py -v`
Expected: alle PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/tests/test_fan_curve_hysteresis.py
git commit -m "fix(fans): Luefterkurve wirkt wieder statt hartcodierter 50 Prozent (#517)"
```

---

## Task 6: Regel-Loop — Skip und kein Emergency-Karteileichen-Zustand

**Files:**
- Modify: `backend/app/services/power/fan_control.py:538` (nach dem Clamp), `:544-546` (Emergency-Persist)
- Test: `backend/tests/test_fan_firmware_managed_loop.py` (create)

**Interfaces:**
- Consumes: `FanData.pwm_control` (Task 2), `_apply_hysteresis` (Task 5).

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_firmware_managed_loop.py`:

```python
"""Der Regel-Loop schreibt firmware-verwaltete Luefter nicht an (#480)."""
import json
from unittest.mock import MagicMock

import pytest

from app.models.fans import FanConfig
from app.schemas.fans import FanMode, PwmControl
from app.services.power.fan_control import FanControlService, FanData


class _StubBackend:
    def __init__(self, temperature=70.0):
        self.set_pwm_calls = []
        self.temperature = temperature

    async def get_fans(self):
        return [FanData(
            fan_id="gpu_fw", name="RDNA3 GPU", rpm=0, pwm_percent=0,
            temperature_celsius=self.temperature, mode=FanMode.AUTO,
            min_pwm_percent=30, max_pwm_percent=100, emergency_temp_celsius=95.0,
            temp_sensor_id=None, curve_points=[], is_active=True,
            is_gpu_fan=True, gpu_vendor="amd",
            pwm_control=PwmControl.FIRMWARE_MANAGED,
        )]

    async def set_pwm(self, fan_id, pwm_percent):
        self.set_pwm_calls.append((fan_id, pwm_percent))
        return True


def _config_row(**overrides):
    # name ist NOT NULL ohne Default (models/fans.py:77).
    base = dict(
        fan_id="gpu_fw", name="RDNA3 GPU", mode=FanMode.AUTO.value, is_active=True,
        min_pwm_percent=30, max_pwm_percent=100, emergency_temp_celsius=95.0,
        curve_json=json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}]),
        curve_type="graph", hysteresis_celsius=3.0,
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
async def test_loop_does_not_write_firmware_managed_fan(db_session):
    db_session.add(_config_row())
    db_session.commit()

    service = _service(db_session)
    backend = _StubBackend()
    service._backend = backend
    try:
        await service._monitor_and_control_fans()

        assert backend.set_pwm_calls == []
        # Der Sample traegt den TATSAECHLICHEN Wert, nicht den Wunsch.
        assert service._sample_buffer[-1]["pwm_percent"] == 0
    finally:
        FanControlService._instance = None


@pytest.mark.asyncio
async def test_overtemp_does_not_persist_emergency_for_firmware_managed(db_session):
    """Sonst haengt der Luefter dauerhaft in EMERGENCY, ohne dass es etwas nuetzt."""
    row = _config_row()
    db_session.add(row)
    db_session.commit()

    service = _service(db_session)
    service._backend = _StubBackend(temperature=99.0)  # ueber emergency_temp
    try:
        await service._monitor_and_control_fans()
        db_session.refresh(row)
        assert row.mode == FanMode.AUTO.value
    finally:
        FanControlService._instance = None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_firmware_managed_loop.py -v`
Expected: beide FAIL — `set_pwm_calls` enthält einen Aufruf, und `row.mode` steht auf `emergency`.

- [ ] **Step 3: Den Skip einbauen**

`fan_control.py` direkt nach dem Clamp (Zeile 538):

```python
                target_pwm = max(config.min_pwm_percent, min(config.max_pwm_percent, target_pwm))

                if fan.pwm_control is PwmControl.FIRMWARE_MANAGED:
                    # Die Firmware besitzt die Kurve (RDNA3+). Kein Write-Versuch,
                    # und der Sample protokolliert den tatsaechlichen Wert.
                    target_pwm = fan.pwm_percent
```

- [ ] **Step 4: Emergency-Persistierung überspringen**

Den Block bei Zeile 544-546 ersetzen:

```python
                if (
                    mode == FanMode.EMERGENCY
                    and config.mode != FanMode.EMERGENCY.value
                    and fan.pwm_control is not PwmControl.FIRMWARE_MANAGED
                ):
                    # Bei firmware-verwalteten Lueftern brachte EMERGENCY nichts
                    # ausser einem Zustand, aus dem nur der AUTO-Button wieder
                    # herausfuehrt. Die Benachrichtigung oben bleibt erhalten.
                    config.mode = FanMode.EMERGENCY.value
                    db.commit()
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_firmware_managed_loop.py tests/test_fan_schedule.py tests/test_fan_curve_hysteresis.py -v`
Expected: alle PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/tests/test_fan_firmware_managed_loop.py
git commit -m "fix(fans): Loop ueberspringt firmware-verwaltete Luefter ohne Emergency-Karteileiche (#480)"
```

---

## Task 7: Route-Guards und Rollback

**Files:**
- Modify: `backend/app/api/routes/fans.py:142-170` (`set_fan_pwm`), `:979-1018` (`set_gpu_manual_mode`)
- Modify: `backend/app/services/power/fan_gpu_manual.py:30-52` (`enable_amd_manual`)
- Test: `backend/tests/test_fan_gpu_manual_mode.py`

**Interfaces:**
- Consumes: `PwmControl`, Cache-Feld `pwm_control`.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An `backend/tests/test_fan_gpu_manual_mode.py` anhängen:

```python
from app.services.power.fan_gpu_manual import enable_amd_manual


@pytest.mark.asyncio
async def test_enable_rolls_back_performance_level_when_pwm_enable_fails(tmp_path, monkeypatch):
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "power_dpm_force_performance_level").write_text("auto\n")
    (hwmon / "name").write_text("amdgpu\n")
    (hwmon / "pwm1_enable").write_text("2\n")

    real_write = Path.write_text

    def fail_on_pwm_enable(self_, value, *a, **kw):
        if self_.name == "pwm1_enable":
            raise PermissionError(13, "Permission denied")
        return real_write(self_, value, *a, **kw)

    monkeypatch.setattr(Path, "write_text", fail_on_pwm_enable)

    with pytest.raises(PermissionError):
        await enable_amd_manual(hwmon_dir=hwmon, drm_root=None)

    monkeypatch.undo()
    assert (device / "power_dpm_force_performance_level").read_text().strip() == "auto"
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_manual_mode.py -v`
Expected: der neue Test FAIL — `performance_level` steht auf `manual`.

- [ ] **Step 3: Rollback implementieren**

In `fan_gpu_manual.py`, `enable_amd_manual`, die Zeilen 47-49 ersetzen:

```python
    await asyncio.to_thread(level_path.write_text, "manual")
    if pwm_enable_path is not None:
        try:
            await asyncio.to_thread(pwm_enable_path.write_text, "1")
        except OSError:
            # Nichts halb angewendet zuruecklassen.
            try:
                await asyncio.to_thread(level_path.write_text, prev_level or "auto")
            except OSError:
                logger.error("Rollback of performance_level failed for %s", device)
            raise
```

- [ ] **Step 4: Guard auf `gpu-manual-mode` — nur beim Einschalten**

In `set_gpu_manual_mode` den `if body.enable:`-Zweig um den Guard ergänzen; die Route sieht danach so aus:

```python
    from app.schemas.fans import PwmControl

    if body.enable:
        if info.get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This GPU manages its fan curve in firmware (RDNA3+); manual "
                    "PWM mode has no effect. See issue #516."
                ),
            )
        state = await enable_amd_manual(hwmon_dir=hwmon_dir, drm_root=None)
        _gpu_manual_state[fan_id] = state
    else:
        state = _gpu_manual_state.pop(fan_id, None)
        if state is None:
            state = AmdManualState(previous_level="auto", previous_pwm_enable=2)
        await disable_amd_manual(hwmon_dir=hwmon_dir, drm_root=None, state=state)
```

Der Guard steht **im** `if body.enable:`-Zweig. Vor der Fallunterscheidung würde er auch das Abschalten blockieren — wer den Toggle je benutzt hat, käme dann nie wieder aus `performance_level=manual` heraus.

- [ ] **Step 5: Guard auf `POST /api/fans/pwm`**

In `set_fan_pwm` vor dem `service.set_fan_pwm`-Aufruf:

```python
    backend = service._backend
    cache = getattr(backend, "_fan_cache", None)
    if cache and body.fan_id in cache:
        from app.schemas.fans import PwmControl
        if cache[body.fan_id].get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
            raise HTTPException(
                status_code=400,
                detail=cache[body.fan_id].get("last_write_error")
                or "This GPU manages its fan curve in firmware; PWM has no effect.",
            )
```

Ohne diesen Guard bliebe die generische Antwort „Failed to set PWM (fan not in manual mode or not found)" stehen — genau die Sorte irreführender Auskunft, die dieser PR abschafft.

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_manual_mode.py -v`
Expected: alle PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/fans.py backend/app/services/power/fan_gpu_manual.py backend/tests/test_fan_gpu_manual_mode.py
git commit -m "fix(fans): Route-Guards fuer firmware-verwaltete GPUs, Rollback bei Teilfehler (#480)"
```

---

## Task 8: Frontend — Badge, gesperrter Slider, Erklärpanel

**Files:**
- Modify: `client/src/api/fan-control.ts` (`FanInfo`, nach `last_write_error`)
- Modify: `client/src/components/fan-control/FanCard.tsx`
- Modify: `client/src/components/fan-control/FanDetails.tsx:148-157`
- Modify: `client/src/components/fan-control/CurveEditorSync.tsx:24`
- Create: `client/src/components/fan-control/FirmwareFanNotice.tsx`
- Modify: `client/src/components/fan-control/index.ts`
- Modify: `client/src/i18n/locales/de/system.json:1014-1023`, `en/system.json:1019-1028`
- Test: `client/src/__tests__/components/fan-control/FanCard.test.tsx` (create)

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`client/src/__tests__/components/fan-control/FanCard.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanCard from '../../../components/fan-control/FanCard';
import { FanMode } from '../../../api/fan-control';
import type { FanInfo } from '../../../api/fan-control';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

function fan(overrides: Partial<FanInfo> = {}): FanInfo {
  return {
    fan_id: 'hwmon2_pwm1',
    name: 'RDNA3 GPU',
    rpm: 0,
    pwm_percent: 0,
    temperature_celsius: 55,
    mode: FanMode.MANUAL,
    is_active: true,
    min_pwm_percent: 30,
    max_pwm_percent: 100,
    emergency_temp_celsius: 95,
    temp_sensor_id: null,
    curve_points: [],
    hysteresis_celsius: 3,
    is_gpu_fan: true,
    gpu_vendor: 'amd',
    pwm_control: 'supported',
    ...overrides,
  };
}

const noop = vi.fn();

function renderCard(f: FanInfo) {
  return render(
    <FanCard
      fan={f}
      isSelected={false}
      onSelect={noop}
      onModeChange={noop}
      onPWMChange={noop}
      isReadOnly={false}
      isLoading={false}
      sensors={[]}
    />
  );
}

describe('FanCard bei firmware-verwalteter GPU', () => {
  it('zeigt kein Firmware-Badge bei normalem Luefter', () => {
    renderCard(fan());
    expect(screen.queryByTestId('fan-firmware-badge')).toBeNull();
  });

  it('zeigt das Firmware-Badge', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    expect(screen.getByTestId('fan-firmware-badge')).toBeTruthy();
  });

  it('sperrt den PWM-Slider', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.disabled).toBe(true);
  });

  it('laesst die Modus-Buttons bedienbar — sonst sperrt sich der Nutzer aus', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    const enabled = screen
      .getAllByRole('button')
      .filter((b) => !(b as HTMLButtonElement).disabled);
    // AUTO und SCHEDULED sind klickbar (MANUAL ist der aktive Modus)
    expect(enabled.length).toBeGreaterThanOrEqual(2);
  });
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FanCard.test.tsx`
Expected: FAIL — `pwm_control` existiert im Typ nicht, Badge fehlt.

- [ ] **Step 3: Typ ergänzen**

`client/src/api/fan-control.ts`, im `FanInfo`-Interface nach `last_write_error`:

```ts
  pwm_control?: 'supported' | 'firmware_managed' | 'no_permission';
```

- [ ] **Step 4: `FanCard` anpassen**

Nach der `getModeColor`-Definition:

```tsx
  const isFirmwareManaged = fan.pwm_control === 'firmware_managed';
```

Badge im Kopfbereich nach dem GPU-Badge:

```tsx
            {isFirmwareManaged && (
              <span
                data-testid="fan-firmware-badge"
                className="inline-flex items-center px-1.5 py-0.5 text-xs bg-sky-500/20 text-sky-300 rounded"
                title={t('system:fanControl.gpu.firmware.badgeHint')}
              >
                {t('system:fanControl.gpu.firmware.badge')}
              </span>
            )}
```

Im PWM-Slider `disabled={isReadOnly}` ersetzen durch:

```tsx
            disabled={isReadOnly || isFirmwareManaged}
```

**Die drei Modus-Buttons bleiben unverändert.** Ihr `disabled` darf `isFirmwareManaged` nicht enthalten — der AUTO-Button ist der einzige Ausweg aus einem persistierten `emergency`- oder `manual`-Zustand.

- [ ] **Step 5: Erklärpanel anlegen**

`client/src/components/fan-control/FirmwareFanNotice.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
import { Cpu } from 'lucide-react';

export default function FirmwareFanNotice() {
  const { t } = useTranslation(['system']);

  return (
    <div className="border border-sky-500/30 bg-sky-500/5 rounded p-3">
      <div className="flex items-start gap-2">
        <Cpu size={16} className="text-sky-400 mt-0.5" />
        <div className="flex-1">
          <div className="text-sm font-medium text-white">
            {t('system:fanControl.gpu.firmware.title')}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {t('system:fanControl.gpu.firmware.explanation')}
          </div>
        </div>
      </div>
    </div>
  );
}
```

In `client/src/components/fan-control/index.ts` ans Ende anhängen:

```ts
export { default as FirmwareFanNotice } from './FirmwareFanNotice';
```

- [ ] **Step 6: `FanDetails` umstellen**

Import ergänzen: `import FirmwareFanNotice from './FirmwareFanNotice';`

Ganz oben in der Komponente, nach der Props-Destrukturierung:

```tsx
  const isFirmwareManaged = fan.pwm_control === 'firmware_managed';
  const editingLocked = isReadOnly || isFirmwareManaged;
```

Danach in den Kurven- und Einstellungs-Komponenten `isReadOnly` durch `editingLocked` ersetzen — betroffen sind `CurveTypeSelector`, die Kurveneditoren, die vier `disabled={isReadOnly}`-Felder und `AdvancedFanSettings`. Der `FanCurveChart`-Block (`isReadOnly`-Prop) zieht mit.

Den GPU-Block (Zeilen 148-157) ersetzen — beachte, dass der bestehende Block eine äußere Bedingung, einen `<div className="mt-4">`-Wrapper und das schließende `)}` umfasst:

```tsx
      {/* GPU Manual Mode Toggle (AMD GPU fans only) */}
      {fan.is_gpu_fan && fan.gpu_vendor === 'amd' && (
        <div className="mt-4">
          {isFirmwareManaged ? (
            <FirmwareFanNotice />
          ) : (
            <GpuManualModeToggle
              fanId={fan.fan_id}
              enabled={editor.localGpuManualEnabled}
              onChange={editor.setLocalGpuManualEnabled}
            />
          )}
        </div>
      )}
```

- [ ] **Step 7: `CurveEditorSync` filtern**

In `CurveEditorSync.tsx:24` die Lüfterliste um firmware-verwaltete Einträge bereinigen. Ein Lüfter, der sich per `sync` an die GPU koppelt, würde sonst dauerhaft auf `min_pwm_percent` festgenagelt, weil `pwm1` auf RDNA3 konstant `0` liest:

```tsx
    .filter((f) => f.pwm_control !== 'firmware_managed')
```

Der Filter gehört in die Kette, die die Auswahloptionen erzeugt, nach dem bestehenden Ausschluss des eigenen Lüfters.

- [ ] **Step 8: Übersetzungen ergänzen**

`client/src/i18n/locales/de/system.json`, im Block `fanControl.gpu` nach dem `manualMode`-Objekt (Komma nicht vergessen):

```json
      "firmware": {
        "badge": "Firmware",
        "badgeHint": "Die Lüfterkurve dieser GPU wird von der Firmware verwaltet und kann von BaluHost nicht gesetzt werden.",
        "title": "Firmware-verwaltete Lüfterkurve",
        "explanation": "Ab RDNA3 liegt die Lüfterkurve in der GPU-Firmware. Der amdgpu-Treiber lehnt direkte PWM-Steuerung ab — auch mit gesetztem Kernel-Parameter amdgpu.ppfeaturemask. Drehzahl und Temperatur werden weiter angezeigt."
      }
```

`client/src/i18n/locales/en/system.json` an derselben Stelle:

```json
      "firmware": {
        "badge": "Firmware",
        "badgeHint": "This GPU's fan curve is managed by firmware and cannot be set by BaluHost.",
        "title": "Firmware-managed fan curve",
        "explanation": "From RDNA3 onward the fan curve lives in the GPU firmware. The amdgpu driver rejects direct PWM control — even with the amdgpu.ppfeaturemask kernel parameter set. Speed and temperature are still shown."
      }
```

- [ ] **Step 9: Tests und Gates**

```bash
cd client
npx vitest run src/__tests__/components/fan-control/FanCard.test.tsx
npx eslint .
npm run build
```

Expected: Vitest PASSED, eslint 0 Fehler, Build erfolgreich.

- [ ] **Step 10: Commit**

```bash
git add client/src/api/fan-control.ts client/src/components/fan-control/ client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json client/src/__tests__/components/fan-control/FanCard.test.tsx
git commit -m "feat(client): firmware-verwaltete GPU-Luefter als read-only ausweisen (#480)"
```

---

## Task 9: Abschluss-Verifikation

**Files:** keine Änderungen — reiner Prüfschritt.

- [ ] **Step 1: Betroffene Backend-Tests gebündelt**

```bash
cd backend
python -m pytest tests/test_fan_pwm_control_probe.py tests/test_fan_einval_diagnostic.py tests/test_fan_firmware_managed_loop.py tests/test_fan_curve_hysteresis.py tests/test_fan_gpu_manual_mode.py tests/test_fan_gpu_recognition.py tests/test_fan_schedule.py tests/test_fan_curve_eval.py tests/test_fan_composite_api.py tests/test_fan_sensor_label_api.py tests/services/test_fan_control.py -v
```

Expected: alle PASSED. Die vollständige Suite nicht lokal starten — sie hängt auf Windows; das übernimmt CI.

- [ ] **Step 2: Frontend-Gates**

```bash
cd client
npx vitest run
npx eslint .
npm run build
```

Expected: alle PASSED, 0 eslint-Fehler, Build erfolgreich.

- [ ] **Step 3: Dev-Mode-Sichtprüfung**

`python start_dev.py`, dann Fan Control öffnen. Erwartet:
- „AMD RDNA3 GPU Fan (sim, firmware-managed)" trägt das Firmware-Badge
- seine Modus-Buttons sind **bedienbar**, der PWM-Slider im MANUAL-Modus ist gesperrt
- in den Details erscheint das Erklärpanel statt des Manual-Mode-Toggles
- „AMD GPU Fan (sim)" verhält sich unverändert
- ein Lüfter mit `sync`-Kurve bietet den RDNA3-Lüfter nicht mehr als Quelle an

---

## Verifikation auf BaluNode (nach dem Deploy)

```bash
# 1. Log-Rauschen muss verschwunden sein
sudo journalctl -u baluhost-backend --since "10 min ago" | grep -c "Failed to write PWM"
# Erwartet: 0 (vorher: ein Eintrag pro Monitoring-Tick)

# 2. Das Feld muss in der API stehen
curl -s -H "Authorization: Bearer <admin-jwt>" http://localhost:8000/api/fans/status \
  | jq '.fans[] | select(.is_gpu_fan) | {fan_id, pwm_control, last_write_error}'
# Erwartet: pwm_control == "firmware_managed"

# 3. #517: die Kurve muss wirken
# Gehaeuseluefter-PWM ueber die Zeit beobachten — vorher konstant ~50%,
# jetzt der konfigurierten Kurve folgend.
curl -s -H "Authorization: Bearer <admin-jwt>" http://localhost:8000/api/fans/status \
  | jq '.fans[] | {fan_id, pwm_percent, temperature_celsius}'
```
