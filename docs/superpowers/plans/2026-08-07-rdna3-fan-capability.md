# RDNA3-Lüfter-Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BaluHost erkennt firmware-verwaltete GPU-Lüfterkurven (RDNA3+), schreibt dort kein PWM mehr ins Leere und erklärt im UI und in der Fehlermeldung wahrheitsgemäß, warum.

**Architecture:** Ein Enum-Feld `pwm_control` (`supported` / `firmware_managed` / `no_permission`) wird beim hwmon-Scan pro Lüfter bestimmt und über `_fan_cache` → `FanData` → `FanInfo` bis ins Frontend durchgereicht. Der Regel-Loop überspringt Schreibversuche bei `firmware_managed`, der Schreibpfad unterscheidet `EACCES` von `EINVAL` und stuft das Feld bei Rechteproblemen nachträglich herab.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, pytest + pytest-asyncio; React 18, TypeScript, Vitest, i18next.

**Spec:** `docs/superpowers/specs/2026-08-06-rdna3-fan-capability-design.md`
**Issue:** #480 — Folge-Issue für die eigentliche Firmware-Kurven-Steuerung: #516

## Global Constraints

- Der Erkennungsmarker ist **ausschließlich** die Existenz von `<device>/gpu_od/fan_ctrl/fan_curve`. Aus einem fehlenden `gpu_od/` darf **niemals** auf „Overdrive fehlt" geschlossen und daraus eine Handlungsempfehlung abgeleitet werden — genau dieser Fehlschluss ist der Inhalt von #480.
- Die Meldung für `firmware_managed` muss explizit erwähnen, dass `amdgpu.ppfeaturemask` daran nichts ändert.
- Backend-Meldungstexte (`last_write_error`) bleiben **englisch**, wie alle bestehenden. Nur Frontend-Strings werden übersetzt (`de` **und** `en`, Namespace `system`).
- Kein Fix der fehlenden Schreibrechte auf hwmon-/`gpu_od`-Nodes. Kein Anfassen von `deploy/`. `NO_PERMISSION` wird nur **erkannt und benannt**.
- Default für jeden Lüfter ohne Befund ist `PwmControl.SUPPORTED` — bestehendes Verhalten darf sich nirgends ändern.
- Die volle Backend-Suite läuft auf Windows nicht durch. Lokal nur die genannten Testdateien gezielt aufrufen; die Gesamtsuite übernimmt CI.

---

## File Structure

**Backend**

| Datei | Verantwortung | Änderung |
|---|---|---|
| `backend/app/schemas/fans.py` | `PwmControl`-Enum, Feld in `FanInfo` | modify |
| `backend/app/services/power/fan_gpu_manual.py` | `probe_amd_pwm_control()` — die Erkennung | modify |
| `backend/app/services/power/fan_control.py` | `FanData`-Feld, `get_status()`-Ausgabe, Loop-Skip | modify |
| `backend/app/services/power/fan_backend_linux.py` | Scan füllt das Feld, `set_pwm` bricht ab, errno-Unterscheidung | modify |
| `backend/app/services/power/fan_backend_dev.py` | Default + simulierter Firmware-GPU-Lüfter | modify |
| `backend/app/api/routes/fans.py` | Guard auf `gpu-manual-mode`, Rollback | modify |

**Frontend**

| Datei | Verantwortung | Änderung |
|---|---|---|
| `client/src/api/fan-control.ts` | `pwm_control` im `FanInfo`-Typ | modify |
| `client/src/components/fan-control/FanCard.tsx` | Badge, Bedienelemente sperren | modify |
| `client/src/components/fan-control/FanDetails.tsx` | Toggle ersetzen durch Erklärpanel | modify |
| `client/src/components/fan-control/FirmwareFanNotice.tsx` | das Erklärpanel | create |
| `client/src/i18n/locales/{de,en}/system.json` | Strings unter `fanControl.gpu.firmware.*` | modify |

**Tests**

| Datei | Deckt ab |
|---|---|
| `backend/tests/test_fan_pwm_control_probe.py` | Erkennung (create) |
| `backend/tests/test_fan_einval_diagnostic.py` | die drei Meldungsvarianten (modify) |
| `backend/tests/test_fan_firmware_managed_loop.py` | Loop schreibt nicht (create) |
| `backend/tests/test_fan_gpu_manual_mode.py` | Route-Guard + Rollback (modify) |
| `client/src/__tests__/components/fan-control/FanCard.test.tsx` | Badge + gesperrte Regler (create) |

---

## Task 1: `PwmControl`-Enum und Erkennungsfunktion

**Files:**
- Modify: `backend/app/schemas/fans.py:10` (bei den übrigen Enums)
- Modify: `backend/app/services/power/fan_gpu_manual.py`
- Test: `backend/tests/test_fan_pwm_control_probe.py` (create)

**Interfaces:**
- Produces: `PwmControl` (str-Enum mit `SUPPORTED`, `FIRMWARE_MANAGED`, `NO_PERMISSION`) aus `app.schemas.fans`; `probe_amd_pwm_control(hwmon_dir: Path, drm_root: Optional[Path] = None) -> PwmControl` aus `app.services.power.fan_gpu_manual`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_pwm_control_probe.py`:

```python
"""probe_amd_pwm_control: firmware-verwaltete Luefterkurven erkennen (RDNA3+, #480)."""
from pathlib import Path

from app.schemas.fans import PwmControl
from app.services.power.fan_gpu_manual import probe_amd_pwm_control


def _amd_tree(tmp_path: Path, *, with_fan_curve: bool) -> Path:
    """Baut einen amdgpu-sysfs-Baum und gibt die hwmon-Directory zurueck."""
    device = tmp_path / "sys" / "class" / "drm" / "card0" / "device"
    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "power_dpm_force_performance_level").write_text("auto\n")
    (hwmon / "name").write_text("amdgpu\n")
    (hwmon / "pwm1_enable").write_text("2\n")
    if with_fan_curve:
        fan_ctrl = device / "gpu_od" / "fan_ctrl"
        fan_ctrl.mkdir(parents=True)
        (fan_ctrl / "fan_curve").write_text(
            "OD_FAN_CURVE:\n0: 0C 0%\nOD_RANGE:\nFAN_CURVE(fan speed): 23% 100%\n"
        )
    return hwmon


def test_rdna3_tree_reports_firmware_managed(tmp_path):
    hwmon = _amd_tree(tmp_path, with_fan_curve=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.FIRMWARE_MANAGED


def test_pre_rdna3_tree_reports_supported(tmp_path):
    hwmon = _amd_tree(tmp_path, with_fan_curve=False)
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_gpu_od_without_fan_curve_reports_supported(tmp_path):
    """gpu_od/ allein genuegt nicht — nur fan_curve ist der Marker."""
    hwmon = _amd_tree(tmp_path, with_fan_curve=False)
    (hwmon.parent.parent / "gpu_od" / "fan_ctrl").mkdir(parents=True)
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED


def test_hwmon_without_device_parent_reports_supported(tmp_path):
    """Board-Sensor ohne PCI-Device darueber: keine Aussage moeglich, Default."""
    hwmon = tmp_path / "sys" / "class" / "hwmon" / "hwmon0"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    assert probe_amd_pwm_control(hwmon) is PwmControl.SUPPORTED
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py -v`
Expected: FAIL mit `ImportError: cannot import name 'PwmControl'`

- [ ] **Step 3: Enum ergänzen**

In `backend/app/schemas/fans.py`, direkt nach `class FanMode` (Zeile 10-15):

```python
class PwmControl(str, Enum):
    """Ob PWM-Schreiben fuer einen Luefter moeglich ist — und wenn nicht, warum.

    SUPPORTED:        Default. Schreiben wird versucht.
    FIRMWARE_MANAGED: RDNA3+ (SMU13). Die Luefterkurve liegt in der Firmware
                      unter gpu_od/fan_ctrl; der amdgpu-Treiber lehnt PWM-Writes
                      mit EINVAL ab. Siehe Issue #480.
    NO_PERMISSION:    Beim Schreiben wurde EACCES beobachtet. Anders als die
                      beiden anderen Werte ist das ein Laufzeit-Befund, kein
                      Hardware-Merkmal.
    """
    SUPPORTED = "supported"
    FIRMWARE_MANAGED = "firmware_managed"
    NO_PERMISSION = "no_permission"
```

- [ ] **Step 4: Erkennungsfunktion implementieren**

In `backend/app/services/power/fan_gpu_manual.py` — Import oben ergänzen (`from app.schemas.fans import PwmControl`), dann ans Ende der öffentlichen Funktionen, vor `_device_from_hwmon`:

```python
def probe_amd_pwm_control(hwmon_dir: Path, drm_root: Optional[Path] = None) -> PwmControl:
    """Stellt fest, ob Live-PWM fuer diesen AMD-GPU-Luefter moeglich ist.

    Ab RDNA3 (SMU13) liegt die Luefterkurve in der Firmware und wird ueber
    <device>/gpu_od/fan_ctrl/ exponiert; pwm{n}-Writes lehnt der Treiber mit
    EINVAL ab. Die Existenz von fan_curve ist der Marker.

    WICHTIG: Aus einem fehlenden gpu_od/ darf NICHT auf ein fehlendes
    Overdrive-Bit geschlossen werden. Auf der vermessenen Referenzkarte
    (RX 7900 XT) war amdgpu.ppfeaturemask=0xffffffff gesetzt und PWM trotzdem
    tot — die gegenteilige Annahme war der urspruengliche Fehler in #480.
    """
    device = _device_from_hwmon(hwmon_dir, drm_root)
    if device is None:
        return PwmControl.SUPPORTED
    if (device / "gpu_od" / "fan_ctrl" / "fan_curve").exists():
        return PwmControl.FIRMWARE_MANAGED
    return PwmControl.SUPPORTED
```

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py -v`
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/fans.py backend/app/services/power/fan_gpu_manual.py backend/tests/test_fan_pwm_control_probe.py
git commit -m "feat(fans): PwmControl-Enum und RDNA3-Erkennung ueber gpu_od/fan_ctrl (#480)"
```

---

## Task 2: Feld durchreichen — Cache, `FanData`, `FanInfo`

**Files:**
- Modify: `backend/app/services/power/fan_control.py:37-57` (`FanData`), `:707-709` und `:755-757` (`get_status`)
- Modify: `backend/app/services/power/fan_backend_linux.py:301-348` (`_scan_pwm_fans`), `:93-110` (`get_fans`)
- Modify: `backend/app/services/power/fan_backend_dev.py:103-119` (`get_fans`)
- Modify: `backend/app/schemas/fans.py:88-90` (`FanInfo`)
- Test: `backend/tests/test_fan_pwm_control_probe.py` (erweitern)

**Interfaces:**
- Consumes: `PwmControl`, `probe_amd_pwm_control` aus Task 1.
- Produces: `FanData.pwm_control: PwmControl`, `FanInfo.pwm_control: PwmControl`, Cache-Key `"pwm_control"`. Ab hier lesen Loop (Task 5), Schreibpfad (Task 4), Route (Task 6) und Frontend (Task 7) dieses Feld.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `backend/tests/test_fan_pwm_control_probe.py` anhängen:

```python
import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


@pytest.mark.asyncio
async def test_scan_marks_rdna3_fan_firmware_managed(tmp_path, monkeypatch):
    hwmon = _amd_tree(tmp_path, with_fan_curve=True)
    (hwmon / "pwm1").write_text("0\n")
    (hwmon / "fan1_input").write_text("0\n")

    backend = LinuxFanControlBackend(get_settings())
    # hwmon_base zeigt auf das hwmon-Verzeichnis IM Device-Baum, damit der
    # Probe von dort zum PCI-Device hochlaufen kann.
    monkeypatch.setattr(backend, "_hwmon_base", hwmon.parent)
    await backend._scan_pwm_fans()

    fan_id = next(iter(backend._fan_cache))
    assert backend._fan_cache[fan_id]["pwm_control"] is PwmControl.FIRMWARE_MANAGED

    fans = await backend.get_fans()
    assert fans[0].pwm_control is PwmControl.FIRMWARE_MANAGED


@pytest.mark.asyncio
async def test_scan_marks_pre_rdna3_fan_supported(tmp_path, monkeypatch):
    hwmon = _amd_tree(tmp_path, with_fan_curve=False)
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "fan1_input").write_text("1200\n")

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

`backend/app/services/power/fan_control.py`, im Import-Block oben `PwmControl` aus `app.schemas.fans` ergänzen (dort werden bereits `FanMode` und `FanCurvePoint` importiert), dann in der Dataclass nach Zeile 57:

```python
    last_write_error: Optional[str] = None
    pwm_control: PwmControl = PwmControl.SUPPORTED
```

- [ ] **Step 4: Scan und `get_fans` im Linux-Backend füllen**

In `fan_backend_linux.py` oben ergänzen:

```python
from app.schemas.fans import FanMode, FanCurvePoint, PwmControl
from app.services.power.fan_gpu_manual import probe_amd_pwm_control
```

In `_scan_pwm_fans`, direkt vor dem `new_cache[fan_id] = {...}`-Block (nach Zeile 336):

```python
                pwm_control = PwmControl.SUPPORTED
                if gpu_vendor == "amd":
                    try:
                        pwm_control = probe_amd_pwm_control(hwmon_dir)
                    except OSError as exc:
                        logger.debug(f"pwm_control probe failed for {hwmon_dir}: {exc}")
```

und im Dict-Literal nach `"device_driver": hwmon_name_value,`:

```python
                    "pwm_control": pwm_control,
```

In `get_fans()` im `FanData(...)`-Aufruf nach `last_write_error=...`:

```python
                pwm_control=fan_info.get("pwm_control", PwmControl.SUPPORTED),
```

- [ ] **Step 5: Dev-Backend gleichziehen**

In `fan_backend_dev.py` den Import auf `from app.schemas.fans import FanMode, FanCurvePoint, PwmControl` erweitern und im `FanData(...)`-Aufruf in `get_fans()` nach `device_driver=...`:

```python
                pwm_control=fan_data.get("pwm_control", PwmControl.SUPPORTED),
```

- [ ] **Step 6: Bis in die API durchreichen**

In `backend/app/schemas/fans.py`, `FanInfo` nach Zeile 90 (`last_write_error`):

```python
    pwm_control: PwmControl = PwmControl.SUPPORTED
```

In `fan_control.py` an **beiden** Stellen in `get_status()` (nach Zeile 709 und nach Zeile 757) jeweils ergänzen:

```python
                        "pwm_control": fan.pwm_control,
```

Beide Vorkommen sind nötig — `get_status()` baut die Lüfterliste an zwei Stellen auf. Wird nur eine geändert, verschwindet das Feld je nach Codepfad aus der API-Antwort.

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py tests/test_fan_gpu_recognition.py -v`
Expected: alle PASSED

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/fans.py backend/app/services/power/fan_control.py backend/app/services/power/fan_backend_linux.py backend/app/services/power/fan_backend_dev.py backend/tests/test_fan_pwm_control_probe.py
git commit -m "feat(fans): pwm_control von Scan bis FanInfo durchreichen (#480)"
```

---

## Task 3: Simulierter firmware-verwalteter GPU-Lüfter im Dev-Backend

**Files:**
- Modify: `backend/app/services/power/fan_backend_dev.py:27-88`

**Interfaces:**
- Consumes: `PwmControl` (Task 1), das `pwm_control`-Cache-Feld (Task 2).
- Produces: Lüfter-ID `dev_gpu_rdna3_pwm1` mit `pwm_control=FIRMWARE_MANAGED`, an der der UI-Pfad aus Task 7 lokal sichtbar wird.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_pwm_control_probe.py` anhängen:

```python
@pytest.mark.asyncio
async def test_dev_backend_exposes_a_firmware_managed_gpu_fan():
    from app.services.power.fan_backend_dev import DevFanControlBackend

    backend = DevFanControlBackend(get_settings())
    fans = {f.fan_id: f for f in await backend.get_fans()}

    assert fans["dev_gpu_pwm1"].pwm_control is PwmControl.SUPPORTED
    assert fans["dev_gpu_rdna3_pwm1"].pwm_control is PwmControl.FIRMWARE_MANAGED
    assert fans["dev_gpu_rdna3_pwm1"].is_gpu_fan is True
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py::test_dev_backend_exposes_a_firmware_managed_gpu_fan -v`
Expected: FAIL mit `KeyError: 'dev_gpu_rdna3_pwm1'`

- [ ] **Step 3: Den simulierten Lüfter ergänzen**

In `_initialize_simulated_fans()` nach dem `dev_gpu_pwm1`-Eintrag (Zeile 79) einfügen:

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

Und in `set_pwm()` direkt nach der Existenzprüfung (nach Zeile 127), damit die Simulation dieselbe Wand hat wie die Hardware:

```python
        if self._fans[fan_id].get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
            logger.debug(f"{fan_id}: firmware-managed, PWM write skipped")
            return False
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_pwm_control_probe.py -v`
Expected: alle PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_backend_dev.py backend/tests/test_fan_pwm_control_probe.py
git commit -m "feat(fans): simulierter firmware-verwalteter GPU-Luefter im Dev-Backend (#480)"
```

---

## Task 4: Schreibpfad — Frühabbruch, errno-Unterscheidung, ehrliche Meldungen

**Files:**
- Modify: `backend/app/services/power/fan_backend_linux.py:114-152` (`set_pwm`), `:372-404` (`_write_hwmon_file`)
- Test: `backend/tests/test_fan_einval_diagnostic.py`

**Interfaces:**
- Consumes: `PwmControl`, Cache-Feld `pwm_control` (Tasks 1-2).
- Produces: `_write_hwmon_file(path, value) -> Tuple[bool, Optional[int]]` (vorher `bool`); Modulkonstante `FIRMWARE_MANAGED_WRITE_ERROR: str`. Der Cache-Eintrag kann nach EACCES auf `PwmControl.NO_PERMISSION` stehen.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An `backend/tests/test_fan_einval_diagnostic.py` anhängen:

```python
from app.schemas.fans import PwmControl


@pytest.mark.asyncio
async def test_firmware_managed_fan_is_not_written_at_all(tmp_path, monkeypatch):
    """Bei firmware-verwalteter Kurve wird sysfs gar nicht erst angefasst."""
    d = tmp_path / "sys" / "class" / "hwmon" / "hwmon1"
    d.mkdir(parents=True)
    (d / "name").write_text("amdgpu\n")
    (d / "pwm1").write_text("0\n")
    (d / "fan1_input").write_text("0\n")
    (d / "pwm1_enable").write_text("2\n")

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
    """EACCES darf nicht als 'rejected by kernel' verkauft werden."""
    d = tmp_path / "sys" / "class" / "hwmon" / "hwmon1"
    d.mkdir(parents=True)
    (d / "name").write_text("amdgpu\n")
    (d / "pwm1").write_text("128\n")
    (d / "fan1_input").write_text("1200\n")
    (d / "pwm1_enable").write_text("2\n")

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
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_einval_diagnostic.py -v`
Expected: die zwei neuen Tests FAIL (der bestehende bleibt grün)

- [ ] **Step 3: `_write_hwmon_file` auf `(ok, errno)` umstellen**

In `fan_backend_linux.py` oben `import errno` und `import getpass` ergänzen sowie `Tuple` im `typing`-Import (bereits vorhanden). Dann `_write_hwmon_file` ersetzen:

```python
    async def _write_hwmon_file(self, path: Path, value: str) -> Tuple[bool, Optional[int]]:
        """Write value to hwmon sysfs file.

        Returns (ok, errno). errno ist der Fehlercode des letzten
        fehlgeschlagenen Versuchs, damit der Aufrufer EACCES (fehlende Rechte)
        von EINVAL (Treiber lehnt ab) unterscheiden kann — die beiden brauchen
        voellig verschiedene Handlungsempfehlungen.
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
```

- [ ] **Step 4: `set_pwm` umbauen**

Modulkonstante oben in `fan_backend_linux.py`, nach `logger = logging.getLogger(__name__)`:

```python
FIRMWARE_MANAGED_WRITE_ERROR = (
    "This GPU manages its fan curve in firmware (RDNA3+). The amdgpu driver "
    "does not support live PWM control on this card — setting "
    "amdgpu.ppfeaturemask=0xffffffff does NOT change that. Control is only "
    "possible through the firmware curve (gpu_od/fan_ctrl), see issue #516."
)
```

Dann `set_pwm` (Zeilen 114-152) ersetzen:

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
Expected: alle PASSED. Der bestehende `test_write_failure_captures_diagnostic` prüft `"amdgpu" in err` und `"pwm_enable=2" in err` — beides bleibt im EINVAL-Zweig erhalten.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_backend_linux.py backend/tests/test_fan_einval_diagnostic.py
git commit -m "fix(fans): EACCES von EINVAL trennen, firmware-verwaltete Luefter nicht schreiben (#480)"
```

---

## Task 5: Regel-Loop überspringt firmware-verwaltete Lüfter

**Files:**
- Modify: `backend/app/services/power/fan_control.py:538-542`
- Test: `backend/tests/test_fan_firmware_managed_loop.py` (create)

**Interfaces:**
- Consumes: `FanData.pwm_control` (Task 2).
- Produces: keine neuen Symbole; Verhaltensänderung im Loop.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_firmware_managed_loop.py`:

```python
"""Der Regel-Loop schreibt firmware-verwaltete Luefter nicht an (#480)."""
import json
from unittest.mock import MagicMock

import pytest

from app.models.fans import FanConfig
from app.schemas.fans import FanMode, FanCurvePoint, PwmControl
from app.services.power.fan_control import FanControlService, FanData


class _StubBackend:
    """Backend mit genau einem firmware-verwalteten GPU-Luefter."""

    def __init__(self):
        self.set_pwm_calls = []

    async def get_fans(self):
        return [FanData(
            fan_id="gpu_fw", name="RDNA3 GPU", rpm=0, pwm_percent=0,
            temperature_celsius=70.0, mode=FanMode.AUTO,
            min_pwm_percent=30, max_pwm_percent=100, emergency_temp_celsius=95.0,
            temp_sensor_id=None, curve_points=[], is_active=True,
            is_gpu_fan=True, gpu_vendor="amd",
            pwm_control=PwmControl.FIRMWARE_MANAGED,
        )]

    async def set_pwm(self, fan_id, pwm_percent):
        self.set_pwm_calls.append((fan_id, pwm_percent))
        return True


@pytest.mark.asyncio
async def test_loop_does_not_write_firmware_managed_fan(db_session):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = False
    config.is_dev_mode = True
    config.fan_sample_interval_seconds = 2

    # name ist NOT NULL ohne Default (models/fans.py:77) — weglassen bricht mit
    # IntegrityError ab, bevor der Test ueberhaupt etwas prueft.
    db_session.add(FanConfig(
        fan_id="gpu_fw", name="RDNA3 GPU", mode=FanMode.AUTO.value, is_active=True,
        min_pwm_percent=30, max_pwm_percent=100, emergency_temp_celsius=95.0,
        curve_json=json.dumps([{"temp": 35, "pwm": 30}, {"temp": 85, "pwm": 100}]),
        curve_type="graph", hysteresis_celsius=3.0,
    ))
    db_session.commit()

    service = FanControlService(config, lambda: db_session)
    backend = _StubBackend()
    service._backend = backend
    try:
        await service._monitor_and_control_fans()

        assert backend.set_pwm_calls == []
        # Der gepufferte Sample traegt den TATSAECHLICHEN Wert, nicht den Wunsch.
        assert service._sample_buffer[-1]["pwm_percent"] == 0
    finally:
        FanControlService._instance = None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_firmware_managed_loop.py -v`
Expected: FAIL — `set_pwm_calls` enthält einen Aufruf und der Sample trägt 30 statt 0.

- [ ] **Step 3: Den Skip einbauen**

In `fan_control.py` direkt nach dem Clamp (Zeile 538):

```python
                target_pwm = max(config.min_pwm_percent, min(config.max_pwm_percent, target_pwm))

                if fan.pwm_control is PwmControl.FIRMWARE_MANAGED:
                    # Die Firmware besitzt die Kurve (RDNA3+). Kein Write-Versuch,
                    # und der Sample protokolliert den tatsaechlichen Wert statt
                    # eines Wunschwerts, der die Hardware nie erreicht.
                    target_pwm = fan.pwm_percent
```

Die bestehende Zeile `if target_pwm != fan.pwm_percent:` bleibt unverändert und greift dadurch nicht mehr.

- [ ] **Step 4: Test laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_firmware_managed_loop.py tests/test_fan_schedule.py -v`
Expected: alle PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/tests/test_fan_firmware_managed_loop.py
git commit -m "fix(fans): Regel-Loop schreibt firmware-verwaltete Luefter nicht mehr an (#480)"
```

---

## Task 6: Route-Guard und Rollback in `enable_amd_manual`

**Files:**
- Modify: `backend/app/api/routes/fans.py:979-1018` (`set_gpu_manual_mode`)
- Modify: `backend/app/services/power/fan_gpu_manual.py:30-52` (`enable_amd_manual`)
- Test: `backend/tests/test_fan_gpu_manual_mode.py`

**Interfaces:**
- Consumes: `PwmControl` (Task 1), Cache-Feld `pwm_control` (Task 2).
- Produces: `enable_amd_manual` lässt bei Fehlschlag des `pwm_enable`-Writes keinen halb angewendeten Zustand zurück.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An `backend/tests/test_fan_gpu_manual_mode.py` anhängen:

```python
from app.services.power.fan_gpu_manual import enable_amd_manual


@pytest.mark.asyncio
async def test_enable_rolls_back_performance_level_when_pwm_enable_fails(tmp_path, monkeypatch):
    drm = tmp_path / "sys" / "class" / "drm" / "card0"
    device = drm / "device"
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
        await enable_amd_manual(hwmon_dir=hwmon, drm_root=tmp_path / "sys" / "class" / "drm")

    monkeypatch.undo()
    # performance_level darf NICHT auf 'manual' stehengeblieben sein
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
            # Nichts halb angewendet zuruecklassen: performance_level zurueckdrehen.
            try:
                await asyncio.to_thread(level_path.write_text, prev_level or "auto")
            except OSError:
                logger.error("Rollback of performance_level failed for %s", device)
            raise
```

- [ ] **Step 4: Den Route-Guard einbauen**

In `backend/app/api/routes/fans.py`, in `set_gpu_manual_mode` nach der bestehenden AMD-Prüfung (nach Zeile 1005):

```python
    from app.schemas.fans import PwmControl

    if info.get("pwm_control") is PwmControl.FIRMWARE_MANAGED:
        raise HTTPException(
            status_code=400,
            detail=(
                "This GPU manages its fan curve in firmware (RDNA3+); manual PWM "
                "mode has no effect. See issue #516."
            ),
        )
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_manual_mode.py -v`
Expected: alle PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/fans.py backend/app/services/power/fan_gpu_manual.py backend/tests/test_fan_gpu_manual_mode.py
git commit -m "fix(fans): gpu-manual-mode blockt firmware-verwaltete GPUs, Rollback bei Teilfehler (#480)"
```

---

## Task 7: Frontend — Badge, gesperrte Regler, Erklärpanel

**Files:**
- Modify: `client/src/api/fan-control.ts:58-76` (`FanInfo`)
- Modify: `client/src/components/fan-control/FanCard.tsx:83-232`
- Modify: `client/src/components/fan-control/FanDetails.tsx:145-156`
- Create: `client/src/components/fan-control/FirmwareFanNotice.tsx`
- Modify: `client/src/i18n/locales/de/system.json:1014-1023`, `client/src/i18n/locales/en/system.json:1019-1028`
- Test: `client/src/__tests__/components/fan-control/FanCard.test.tsx` (create)

**Interfaces:**
- Consumes: `FanInfo.pwm_control` aus der API (Task 2).
- Produces: `FirmwareFanNotice` (default export, keine Props).

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`client/src/__tests__/components/fan-control/FanCard.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanCard from '../../../components/fan-control/FanCard';
import { FanMode } from '../../../api/fan-control';
import type { FanInfo } from '../../../api/fan-control';

function fan(overrides: Partial<FanInfo> = {}): FanInfo {
  return {
    fan_id: 'hwmon2_pwm1',
    name: 'RDNA3 GPU',
    rpm: 0,
    pwm_percent: 0,
    temperature_celsius: 55,
    mode: FanMode.AUTO,
    is_active: true,
    min_pwm_percent: 30,
    max_pwm_percent: 100,
    emergency_temp_celsius: 95,
    temp_sensor_id: null,
    curve_points: [],
    is_gpu_fan: true,
    gpu_vendor: 'amd',
    pwm_control: 'supported',
    ...overrides,
  } as FanInfo;
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

  it('sperrt die Modus-Buttons', () => {
    renderCard(fan({ pwm_control: 'firmware_managed' }));
    for (const btn of screen.getAllByRole('button')) {
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it('laesst die Modus-Buttons bei supported bedienbar', () => {
    renderCard(fan());
    const enabled = screen.getAllByRole('button').filter((b) => !(b as HTMLButtonElement).disabled);
    expect(enabled.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FanCard.test.tsx`
Expected: FAIL — `pwm_control` existiert im Typ nicht, Badge fehlt.

- [ ] **Step 3: Typ ergänzen**

In `client/src/api/fan-control.ts`, im `FanInfo`-Interface nach `last_write_error` (Zeile 75):

```ts
  pwm_control?: 'supported' | 'firmware_managed' | 'no_permission';
```

- [ ] **Step 4: `FanCard` anpassen**

In `FanCard.tsx` nach der `getModeColor`-Definition (Zeile 81):

```tsx
  const isFirmwareManaged = fan.pwm_control === 'firmware_managed';
  const controlsDisabled = isReadOnly || isFirmwareManaged;
```

Badge im Kopfbereich nach dem GPU-Badge (nach Zeile 101):

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

Danach in **allen drei** Modus-Buttons (Zeilen 164, 182, 200) und im PWM-Slider (Zeile 227) `isReadOnly` durch `controlsDisabled` ersetzen. Der `disabled`-Ausdruck der Buttons lautet danach z. B. `disabled={fan.mode === FanMode.AUTO || controlsDisabled || isLoading}`.

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

- [ ] **Step 6: `FanDetails` umstellen**

In `FanDetails.tsx` den Import ergänzen (`import FirmwareFanNotice from './FirmwareFanNotice';`) und den `GpuManualModeToggle`-Block (Zeilen 150-156) ersetzen:

```tsx
        {fan.is_gpu_fan && fan.gpu_vendor === 'amd' && (
          fan.pwm_control === 'firmware_managed' ? (
            <FirmwareFanNotice />
          ) : (
            <GpuManualModeToggle
              fanId={fan.fan_id}
              enabled={editor.localGpuManualEnabled}
              onChange={editor.setLocalGpuManualEnabled}
            />
          )
        )}
```

In `client/src/components/fan-control/index.ts` ans Ende anhängen:

```ts
export { default as FirmwareFanNotice } from './FirmwareFanNotice';
```

- [ ] **Step 7: Übersetzungen ergänzen**

In `client/src/i18n/locales/de/system.json`, im Block `fanControl.gpu` (Zeile 1014) nach dem `manualMode`-Objekt:

```json
      "firmware": {
        "badge": "Firmware",
        "badgeHint": "Die Lüfterkurve dieser GPU wird von der Firmware verwaltet und kann von BaluHost nicht gesetzt werden.",
        "title": "Firmware-verwaltete Lüfterkurve",
        "explanation": "Ab RDNA3 liegt die Lüfterkurve in der GPU-Firmware. Der amdgpu-Treiber lehnt direkte PWM-Steuerung ab — auch mit gesetztem Kernel-Parameter amdgpu.ppfeaturemask. Drehzahl und Temperatur werden weiter angezeigt."
      }
```

In `client/src/i18n/locales/en/system.json` an derselben Stelle:

```json
      "firmware": {
        "badge": "Firmware",
        "badgeHint": "This GPU's fan curve is managed by firmware and cannot be set by BaluHost.",
        "title": "Firmware-managed fan curve",
        "explanation": "From RDNA3 onward the fan curve lives in the GPU firmware. The amdgpu driver rejects direct PWM control — even with the amdgpu.ppfeaturemask kernel parameter set. Speed and temperature are still shown."
      }
```

Auf das Komma nach dem vorangehenden `manualMode`-Objekt achten; beide Dateien müssen gültiges JSON bleiben.

- [ ] **Step 8: Tests und Gates laufen lassen**

```bash
cd client
npx vitest run src/__tests__/components/fan-control/FanCard.test.tsx
npx eslint .
npm run build
```

Expected: Vitest PASSED, eslint 0 Fehler, Build erfolgreich.

- [ ] **Step 9: Commit**

```bash
git add client/src/api/fan-control.ts client/src/components/fan-control/FanCard.tsx client/src/components/fan-control/FanDetails.tsx client/src/components/fan-control/FirmwareFanNotice.tsx client/src/components/fan-control/index.ts client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json client/src/__tests__/components/fan-control/FanCard.test.tsx
git commit -m "feat(client): firmware-verwaltete GPU-Luefter als read-only ausweisen (#480)"
```

---

## Task 8: Abschluss-Verifikation

**Files:** keine Änderungen — reiner Prüfschritt.

- [ ] **Step 1: Betroffene Backend-Tests gebündelt**

```bash
cd backend
python -m pytest tests/test_fan_pwm_control_probe.py tests/test_fan_einval_diagnostic.py tests/test_fan_firmware_managed_loop.py tests/test_fan_gpu_manual_mode.py tests/test_fan_gpu_recognition.py tests/test_fan_schedule.py -v
```

Expected: alle PASSED. Die vollstaendige Suite nicht lokal starten — sie haengt auf Windows; das übernimmt CI.

- [ ] **Step 2: Frontend-Gates**

```bash
cd client
npx vitest run
npx eslint .
npm run build
```

Expected: alle PASSED, 0 eslint-Fehler, Build erfolgreich.

- [ ] **Step 3: Dev-Mode-Sichtprüfung**

`python start_dev.py` starten, Fan Control öffnen. Erwartet: der Lüfter „AMD RDNA3 GPU Fan (sim, firmware-managed)" trägt das Firmware-Badge, seine Modus-Buttons sind ausgegraut, und in den Details erscheint das Erklärpanel statt des Manual-Mode-Toggles. Der bestehende „AMD GPU Fan (sim)" verhält sich unverändert.

- [ ] **Step 4: Abschluss-Commit falls nötig**

Nur wenn die Verifikation Korrekturen erzwungen hat:

```bash
git add -A
git commit -m "fix(fans): Nacharbeiten aus der Abschluss-Verifikation (#480)"
```

---

## Verifikation auf BaluNode (nach dem Deploy)

Kein Plan-Schritt, sondern die Bestätigung am echten Gerät. Nach dem Merge auf `main` und dem Prod-Deploy:

```bash
# 1. Log-Rauschen muss verschwunden sein
sudo journalctl -u baluhost-backend --since "10 min ago" | grep -c "Failed to write PWM"
# Erwartet: 0 (vorher: ein Eintrag pro Monitoring-Tick)

# 2. Das Feld muss in der API stehen
curl -s -H "Authorization: Bearer <admin-jwt>" http://localhost:8000/api/fans/status \
  | jq '.fans[] | select(.is_gpu_fan) | {fan_id, pwm_control, last_write_error}'
# Erwartet: pwm_control == "firmware_managed"
```
