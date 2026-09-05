# Rückgabe an die Board-Automatik beim Dienst-Ende — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Beim Beenden des Dienstes `pwm_enable` auf den Automatikmodus zurückschreiben, den BaluHost am selben Chip zuvor selbst beobachtet hat — damit nach einem Deploy nicht niemand regelt.

**Architecture:** Ein kleines reines Modul entscheidet, *ob* und *worauf* zurückgegeben wird. Der Scan liest `pwm_enable` einmal pro Start (vor dem ersten Write) in den Cache; der Primary-Worker persistiert daraus eine Beobachtung. Eine neue Backend-Methode schreibt den Wert zurück und liest ihn zur Kontrolle wieder. Kein Besitz-Modell, kein geratener Treiber-Fallback.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, pytest. Keine neuen Abhängigkeiten.

**Spec:** `docs/superpowers/specs/2026-09-05-fan-ownership-handback-design.md`

## Global Constraints

- **Nur beobachtete Werte.** Zurückgeschrieben wird ausschliesslich ein `pwm_enable`-Wert **≥ 2**, den BaluHost am selben Chip gelesen hat. Kein Treiber-Fallback, kein geratener Modus.
- **`0` und `1` sind keine Automatik.** `1` ist Handsteuerung; `0` heisst laut hwmon-Konvention „no fan speed control (i.e. fan at full speed)".
- **Keine GPU-Lüfter.** Ausschluss über `gpu_vendor is not None` (nicht über `FIRMWARE_MANAGED` — das deckt Pre-RDNA3 nicht).
- **Nur der Primary-Worker gibt zurück.** Gelesen als `getattr(lifespan, "IS_PRIMARY_WORKER", False)` — `lifespan` als **Modul** importiert, nie `from ... import` (das Flag wird erst zur Laufzeit gesetzt).
- **`updated_at` darf nicht wandern.** Die Spalte trägt `onupdate=func.now()` (`models/fans.py:107-112`) und ist das Rangkriterium des Identitäts-Abgleichs (`fan_reconcile.py:151`).
- Keine neuen Abhängigkeiten. Python-Kommentare und Log-Meldungen auf Deutsch, **ohne Umlaute**; in `.md`-Dateien sind Umlaute erwünscht.
- Die volle Backend-Suite läuft in der CI, nicht lokal (hängt auf Windows). Lokal: `cd backend ; python -m pytest -k "fan or power" -q`.
- **Die Messlatte ist vor Task 1 einmal zu messen** und mit Datum zu notieren — eine Zahl aus einem früheren Lauf ist keine Messlatte.
- Testbäume platform-förmig und **doppelpunktfrei** (NTFS verbietet Doppelpunkte in Verzeichnisnamen). Muster: `test_fan_pwm_backoff.py:28-51`, `test_fan_scan_stable_ids.py`.

---

### Task 1: `fan_restore.py` — die Entscheidungsregel

Drei reine Funktionen. Sie fassen weder sysfs noch Datenbank an und tragen die gesamte Politik des Vorhabens.

**Files:**
- Create: `backend/app/services/power/fan_restore.py`
- Test: `backend/tests/test_fan_restore_rule.py`

**Interfaces:**
- Produces: `is_observation(value: Optional[int]) -> bool`, `resolve_restore_value(scanned: Optional[int], stored: Optional[int]) -> Optional[int]`, `needs_release(current: Optional[int], target: Optional[int]) -> bool`

- [ ] **Step 1: Messlatte festhalten**

Run: `cd backend ; python -m pytest -k "fan or power" -q`
Notiere die Zahl und das Datum im Task-Report. Sie ist der Vergleichswert für alle folgenden Tasks.

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_restore_rule.py`:

```python
"""Regel fuer die Rueckgabe an die Board-Automatik (#534).

Zurueckgeschrieben wird ausschliesslich ein Wert, den BaluHost am selben Chip
selbst gelesen hat. 0 und 1 sind keine Automatik: 1 ist Handsteuerung, 0 heisst
laut hwmon-Konvention "no fan speed control (i.e. fan at full speed)".
"""
import pytest

from app.services.power.fan_restore import (
    is_observation,
    needs_release,
    resolve_restore_value,
)


@pytest.mark.parametrize("value,expected", [
    (5, True),      # Smart Fan IV
    (2, True),      # Thermal Cruise
    (1, False),     # Handsteuerung -- jemand hat uebernommen
    (0, False),     # Vollgas, keine Chip-Regelung
    (None, False),  # nicht lesbar
])
def test_is_observation(value, expected):
    assert is_observation(value) is expected


def test_observation_is_stored():
    assert resolve_restore_value(scanned=5, stored=None) == 5


def test_newer_observation_wins():
    """Der Chip meldet jetzt Thermal Cruise -- das ist die aktuellere Wahrheit."""
    assert resolve_restore_value(scanned=2, stored=5) == 2


def test_non_observation_keeps_stored_value():
    """Nach einem Deploy-Neustart steht dort 1; der gespeicherte Wert bleibt."""
    assert resolve_restore_value(scanned=1, stored=5) == 5
    assert resolve_restore_value(scanned=0, stored=5) == 5
    assert resolve_restore_value(scanned=None, stored=5) == 5


def test_without_observation_there_is_no_target():
    """Der Kern des Entwurfs: ohne Beobachtung passiert nichts."""
    assert resolve_restore_value(scanned=1, stored=None) is None
    assert resolve_restore_value(scanned=0, stored=None) is None
    assert resolve_restore_value(scanned=None, stored=None) is None


def test_needs_release_only_with_a_target():
    assert needs_release(current=1, target=5) is True
    assert needs_release(current=5, target=5) is False
    assert needs_release(current=1, target=None) is False


def test_manual_at_full_speed_reads_as_zero_and_still_needs_release():
    """reg_to_pwm_enable() meldet Manual mit Duty 255 als 0, nicht als 1."""
    assert needs_release(current=0, target=5) is True


def test_unreadable_current_value_is_treated_as_deviation():
    """Lieber einmal zu viel schreiben als die Automatik ausgeschaltet lassen."""
    assert needs_release(current=None, target=5) is True
```

- [ ] **Step 3: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_restore_rule.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.services.power.fan_restore'`

- [ ] **Step 4: Modul anlegen**

`backend/app/services/power/fan_restore.py`:

```python
"""Entscheidet, ob und worauf ein Luefter an die Board-Automatik zurueckgeht (#534).

Reine Regel ohne sysfs- und ohne DB-Zugriff. Der Entwurf steht und faellt mit
einem Grundsatz: zurueckgeschrieben wird ausschliesslich ein Wert, den BaluHost
am selben Chip selbst gelesen hat. Ein geratener Treibermodus waere eine
Annahme ueber fremde Hardware, die niemand ueberpruefen kann.
"""
from __future__ import annotations

from typing import Optional

# Ab hier regelt der Chip selbst. Darunter liegen die beiden Zustaende, in
# denen er es NICHT tut:
#   1 = Handsteuerung (jemand hat uebernommen -- in aller Regel wir)
#   0 = "no fan speed control (i.e. fan at full speed)" laut hwmon-Konvention;
#       der nct6775-Treiber setzt dabei zusaetzlich Duty 255
_LOWEST_AUTOMATIC_MODE = 2


def is_observation(value: Optional[int]) -> bool:
    """Taugt der gelesene pwm_enable-Wert als Rueckgabeziel?"""
    return value is not None and value >= _LOWEST_AUTOMATIC_MODE


def resolve_restore_value(scanned: Optional[int],
                          stored: Optional[int]) -> Optional[int]:
    """Der Rueckgabewert: juengere Beobachtung schlaegt gespeicherten Wert.

    Ist der gescannte Wert keine Beobachtung, bleibt der gespeicherte
    unveraendert -- er stammt dann aus einem frueheren Kaltstart und ist das
    Beste, was wir haben. Gibt es auch den nicht, gibt es keine Rueckgabe.
    """
    if is_observation(scanned):
        return scanned
    return stored


def needs_release(current: Optional[int], target: Optional[int]) -> bool:
    """Muss geschrieben werden?

    Ein nicht lesbarer Ist-Wert gilt als Abweichung: lieber einmal zu viel
    schreiben, als die Board-Automatik ausgeschaltet zu lassen.
    """
    if target is None:
        return False
    return current != target
```

- [ ] **Step 5: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_restore_rule.py -v`
Expected: PASS (13 Fälle)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/fan_restore.py backend/tests/test_fan_restore_rule.py
git commit -m "feat(fans): Regel fuer die Rueckgabe an die Board-Automatik (#534)"
```

---

### Task 2: Spalte und Migration

**Files:**
- Modify: `backend/app/models/fans.py` (`FanConfig`)
- Create: `backend/alembic/versions/<rev>_fan_pwm_enable_restore.py`

**Interfaces:**
- Produces: `FanConfig.pwm_enable_restore: Optional[int]`

- [ ] **Step 1: Head prüfen**

Run: `cd backend ; python -m alembic heads`
Expected: genau eine Zeile. Zum Zeitpunkt der Planung war das `193f03f94b4e` — **verlasse dich nicht darauf**, sondern nimm die Ausgabe von jetzt. Zeigt der Befehl mehr als eine Zeile, **stoppe** und melde BLOCKED: das Projekt hatte bereits einen Deploy-Fehler durch mehrere Heads.

- [ ] **Step 2: Modell erweitern**

`backend/app/models/fans.py`, in `FanConfig` direkt nach `legacy_fan_id`:

```python
    # Der pwm_enable-Wert, auf den beim Dienst-Ende zurueckgeschaltet wird
    # (#534). Wird ausschliesslich aus einer eigenen Beobachtung gefuellt --
    # ein Wert >= 2, den der Scan vor dem ersten Write gelesen hat. NULL heisst:
    # noch nie eine Automatik gesehen, also keine Rueckgabe.
    pwm_enable_restore: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 3: Migration erzeugen**

Run: `cd backend ; python -m alembic revision --autogenerate -m "fan pwm_enable restore"`

**Autogenerate ist hier eine Falle.** Es vergleicht die Modelle mit deiner lokalen Dev-Datenbank und liefert Operationen mit, die niemand bestellt hat — bekannt ist mindestens ein `alter_column` auf `status_bar_pill_config.pill_id` (siehe #549, dort erklärt). Prüfe die erzeugte Datei Zeile für Zeile und entferne **alles** ausser dem einen `add_column` und seinem `drop_column` im `downgrade()`. Findest du weitere Operationen, nenne sie im Report.

Prüfe ausserdem, dass `down_revision` auf den in Step 1 gelesenen Head zeigt.

- [ ] **Step 4: Migration anwenden und zurückrollen**

```bash
cd backend
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
python -m alembic heads
```
Expected: alle Läufe fehlerfrei, danach genau ein Head.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/fans.py backend/alembic/versions/
git commit -m "feat(fans): Spalte fuer den beobachteten Rueckgabewert (#534)"
```

---

### Task 3: Der Scan liest `pwm_enable`

**Files:**
- Modify: `backend/app/services/power/fan_backend_linux.py` (`_scan_pwm_fans`, um Zeile 484-516)
- Test: `backend/tests/test_fan_scan_pwm_enable.py`

**Interfaces:**
- Produces: `_fan_cache[fan_id]["pwm_enable_at_scan"]: Optional[int]`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_scan_pwm_enable.py`:

```python
"""Der Scan liest pwm_enable, bevor der erste Write ihn ueberschreibt (#534).

_scan_pwm_fans laeuft aus is_available() beim Backend-Init -- einmal pro Start
und vor dem ersten set_pwm. Das ist der einzige Moment, in dem der Board-Wert
ueberhaupt sichtbar sein kann.
"""
import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _tree(tmp_path: Path, enable_value: str | None) -> Path:
    """nct6798 an platform/nct6775.656, doppelpunktfrei (Windows)."""
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "fan1_input").write_text("900\n")
    (hwmon / "temp1_input").write_text("42000\n")
    if enable_value is not None:
        (hwmon / "pwm1_enable").write_text(enable_value + "\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_scan_captures_automatic_mode(tmp_path, monkeypatch):
    klass = _tree(tmp_path, "5")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    fan_id = next(iter(cache))
    assert cache[fan_id]["pwm_enable_at_scan"] == 5


@pytest.mark.asyncio
async def test_scan_captures_manual_mode_as_is(tmp_path, monkeypatch):
    """Der Scan bewertet nicht -- er liest. Die Regel entscheidet spaeter."""
    klass = _tree(tmp_path, "1")
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    fan_id = next(iter(cache))
    assert cache[fan_id]["pwm_enable_at_scan"] == 1


@pytest.mark.asyncio
async def test_missing_enable_file_yields_none(tmp_path, monkeypatch):
    klass = _tree(tmp_path, None)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)

    cache = await backend._scan_pwm_fans()

    fan_id = next(iter(cache))
    assert cache[fan_id]["pwm_enable_at_scan"] is None
    assert cache[fan_id]["pwm_enable_path"] is None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_scan_pwm_enable.py -v`
Expected: FAIL mit `KeyError: 'pwm_enable_at_scan'`

- [ ] **Step 3: Den Wert im Scan lesen**

In `_scan_pwm_fans`, direkt **nach** der Zeile, die `pwm_enable_path` bestimmt (`pwm_enable_path = hwmon_dir / f"pwm{pwm_num}_enable"`), einfügen:

```python
                # pwm_enable EINMAL pro Start lesen, bevor set_pwm es auf 1
                # setzt. Nach dem ersten Regelzyklus steht dort unser eigener
                # Wert -- dies ist der einzige Moment, in dem der Board-Wert
                # sichtbar sein kann (#534).
                pwm_enable_at_scan = None
                if pwm_enable_path.exists():
                    pwm_enable_at_scan = await self._read_hwmon_file(pwm_enable_path)
```

Im Dict-Literal `new_cache[fan_id] = {...}` nach `"pwm_enable_path": ...` ergänzen:

```python
                    "pwm_enable_at_scan": pwm_enable_at_scan,
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_scan_pwm_enable.py tests/test_fan_scan_stable_ids.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/fan_backend_linux.py backend/tests/test_fan_scan_pwm_enable.py
git commit -m "feat(fans): Scan liest pwm_enable vor dem ersten Write (#534)"
```

---

### Task 4: `release_to_board` auf dem Backend

**Files:**
- Modify: `backend/app/services/power/fan_control.py:86-124` (ABC `FanControlBackend`)
- Modify: `backend/app/services/power/fan_backend_linux.py`
- Modify: `backend/app/services/power/fan_backend_dev.py`
- Test: `backend/tests/test_fan_release_to_board.py`

**Interfaces:**
- Produces: `FanControlBackend.release_to_board(fan_id: str, enable_value: int) -> bool`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_release_to_board.py`:

```python
"""Rueckgabe von pwm_enable an die Board-Automatik (#534).

Der Rueckgabe-Write umgeht das Backoff aus #533 von selbst: dessen Sperre sitzt
in set_pwm (fan_backend_linux.py:168-174), nicht in _write_hwmon_file. Laege sie
davor, unterbliebe die Rueckgabe ausgerechnet bei den Kanaelen, die zuvor
Schreibfehler hatten -- den kritischsten.
"""
import errno
import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services.power.fan_backend_dev import DevFanControlBackend
from app.services.power.fan_backend_linux import LinuxFanControlBackend


def _tree(tmp_path: Path) -> Path:
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "pwm1_enable").write_text("1\n")
    (hwmon / "fan1_input").write_text("900\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)
    return klass


async def _backend(tmp_path, monkeypatch):
    klass = _tree(tmp_path)
    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()
    return backend, next(iter(backend._fan_cache))


@pytest.mark.asyncio
async def test_release_writes_the_value(tmp_path, monkeypatch):
    backend, fan_id = await _backend(tmp_path, monkeypatch)

    ok = await backend.release_to_board(fan_id, 5)

    assert ok is True
    path = backend._fan_cache[fan_id]["pwm_enable_path"]
    assert path.read_text().strip() == "5"


@pytest.mark.asyncio
async def test_release_verifies_by_reading_back(tmp_path, monkeypatch):
    """Ein still ignorierter Write darf nicht als Erfolg durchgehen."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)

    async def swallow(path, value):
        return True, None   # tut so, als haette es geschrieben

    monkeypatch.setattr(backend, "_write_hwmon_file", swallow)

    ok = await backend.release_to_board(fan_id, 5)

    assert ok is False


@pytest.mark.asyncio
async def test_release_reports_write_failure(tmp_path, monkeypatch):
    backend, fan_id = await _backend(tmp_path, monkeypatch)

    async def refuse(path, value):
        return False, errno.EINVAL

    monkeypatch.setattr(backend, "_write_hwmon_file", refuse)

    assert await backend.release_to_board(fan_id, 5) is False


@pytest.mark.asyncio
async def test_release_ignores_the_write_backoff(tmp_path, monkeypatch):
    """Genau die Kanaele mit Schreibfehlern brauchen die Rueckgabe."""
    backend, fan_id = await _backend(tmp_path, monkeypatch)
    backend._write_backoff[fan_id] = (8, backend._monotonic() + 900)

    assert await backend.release_to_board(fan_id, 5) is True


@pytest.mark.asyncio
async def test_release_on_unknown_fan_is_false(tmp_path, monkeypatch):
    backend, _ = await _backend(tmp_path, monkeypatch)
    assert await backend.release_to_board("gibt-es-nicht:pwm9", 5) is False


@pytest.mark.asyncio
async def test_dev_backend_release_is_a_noop():
    backend = DevFanControlBackend(get_settings())
    fans = await backend.get_fans()
    assert await backend.release_to_board(fans[0].fan_id, 5) is True
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_release_to_board.py -v`
Expected: FAIL mit `AttributeError: 'LinuxFanControlBackend' object has no attribute 'release_to_board'`

- [ ] **Step 3: Die ABC erweitern**

`fan_control.py`, in `FanControlBackend` nach `set_pwm`:

```python
    @abstractmethod
    async def release_to_board(self, fan_id: str, enable_value: int) -> bool:
        """pwm_enable auf einen Automatikmodus zurueckschreiben (#534).

        Args:
            fan_id: Luefter-Kennung
            enable_value: der beobachtete Automatikmodus (>= 2)

        Returns:
            True nur, wenn der Wert danach tatsaechlich anliegt.
        """
        pass
```

- [ ] **Step 4: Linux-Implementierung**

`fan_backend_linux.py`, nach `set_pwm`:

```python
    async def release_to_board(self, fan_id: str, enable_value: int) -> bool:
        """Gibt die Regelung dieses Kanals an die Chip-Automatik zurueck.

        Umgeht das Write-Backoff aus #533 bewusst: dessen Sperre sitzt in
        set_pwm, nicht hier. Ein Kanal mit Schreibfehlern ist genau der, bei dem
        eine abgeschaltete Board-Automatik am meisten weh tut.
        """
        fan_info = self._fan_cache.get(fan_id)
        if fan_info is None:
            logger.warning(f"Rueckgabe fuer unbekannten Luefter {fan_id}")
            return False

        pwm_enable_path = fan_info.get("pwm_enable_path")
        if pwm_enable_path is None:
            return False

        driver = fan_info.get("device_driver", "unknown")
        ok, err_code = await self._write_hwmon_file(pwm_enable_path, str(enable_value))
        if not ok:
            # Achtung bei der Formulierung: _write_hwmon_file meldet nach einem
            # gescheiterten sudo-tee-Fallback EACCES, auch wenn der Kernel
            # eigentlich EINVAL geliefert hat (etwa weil check_trip_points()
            # nicht-monotone BIOS-Stuetzstellen gefunden hat). Der errno wird
            # deshalb genannt, aber nicht gedeutet.
            logger.warning(
                f"Rueckgabe an die Board-Automatik fehlgeschlagen: {fan_id} "
                f"(driver={driver}, Ziel={enable_value}, errno={err_code}). "
                f"Der Luefter bleibt in Handsteuerung -- es regelt niemand."
            )
            return False

        readback = await self._read_hwmon_file(pwm_enable_path)
        if readback != enable_value:
            logger.warning(
                f"Rueckgabe an die Board-Automatik ohne Wirkung: {fan_id} "
                f"(driver={driver}, geschrieben={enable_value}, "
                f"gelesen={readback}). Der Write wurde stillschweigend "
                f"verworfen."
            )
            return False

        logger.info(f"{fan_id}: an die Board-Automatik zurueckgegeben (pwm_enable={enable_value})")
        return True
```

- [ ] **Step 5: Dev-Implementierung**

`fan_backend_dev.py`, nach `set_pwm`:

```python
    async def release_to_board(self, fan_id: str, enable_value: int) -> bool:
        """Kein hwmon im Dev-Modus -- es gibt nichts zurueckzugeben."""
        return True
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_release_to_board.py -v`
Expected: PASS (6 Tests)

Danach zur Absicherung, dass die neue abstrakte Methode keine bestehende Test-Doubles bricht:

Run: `cd backend ; python -m pytest -k "fan or power" -q`

Schlagen Tests mit `TypeError: Can't instantiate abstract class` fehl, fehlt die Methode in einem Test-Double — ergänze sie dort (Kandidaten: `test_fan_pwm_backoff.py:253`, `test_fan_firmware_managed_loop.py:28`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/app/services/power/fan_backend_linux.py backend/app/services/power/fan_backend_dev.py backend/tests/
git commit -m "feat(fans): release_to_board mit Ruecklese-Kontrolle (#534)"
```

---

### Task 5: Persistenz der Beobachtung

**Files:**
- Modify: `backend/app/services/power/fan_control.py` (`_load_fan_configs`, Anlage-Schleife ab Zeile 428; Konstruktor)
- Test: `backend/tests/test_fan_restore_persistence.py`

**Interfaces:**
- Consumes: `is_observation`, `resolve_restore_value` (Task 1); `_fan_cache[...]["pwm_enable_at_scan"]` (Task 3); `FanConfig.pwm_enable_restore` (Task 2)
- Produces: `FanControlService._restore_values: Dict[str, int]`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_restore_persistence.py`:

```python
"""Die Beobachtung wird persistiert -- und updated_at bleibt unangetastet (#534).

updated_at traegt onupdate=func.now() (models/fans.py:107-112) und ist das
Rangkriterium des Identitaets-Abgleichs (fan_reconcile.py:151). Ein Schreiben
bei jedem Start setzte jede Zeile auf "gerade angefasst" und entwertete es.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import FanConfig
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _service(session_factory, monkeypatch, *, primary=True):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def test_persist_does_not_create_rows(session_factory, monkeypatch):
    """_persist_restore_values fasst nur bestehende Zeilen an.

    Die Erstbeobachtung eines NEUEN Luefters kommt nicht von hier, sondern
    direkt am FanConfig(...)-Objekt der Anlage-Schleife (Step 5) -- sonst
    entstuende unmittelbar nach dem INSERT ein zweiter Schreibvorgang.
    """
    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one_or_none()
    assert row is None


def test_existing_row_is_updated(session_factory, monkeypatch):
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True))
        db.commit()

    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.pwm_enable_restore == 5


def test_updated_at_does_not_move(session_factory, monkeypatch):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True, updated_at=stamp))
        db.commit()

    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.updated_at.replace(tzinfo=timezone.utc) == stamp


def test_unchanged_value_writes_nothing(session_factory, monkeypatch):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True, updated_at=stamp,
                         pwm_enable_restore=5))
        db.commit()

    service = _service(session_factory, monkeypatch)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.updated_at.replace(tzinfo=timezone.utc) == stamp
    assert row.pwm_enable_restore == 5


def test_secondary_worker_persists_nothing(session_factory, monkeypatch):
    with session_factory() as db:
        db.add(FanConfig(fan_id="nct6798-isa-0290:pwm1", name="nct6798 PWM1",
                         mode="auto", is_active=True))
        db.commit()

    service = _service(session_factory, monkeypatch, primary=False)
    service._persist_restore_values({"nct6798-isa-0290:pwm1": 5})

    with session_factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.pwm_enable_restore is None
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_restore_persistence.py -v`
Expected: FAIL mit `AttributeError: 'FanControlService' object has no attribute '_persist_restore_values'`

- [ ] **Step 3: Speicher und Persistenz implementieren**

Importe in `fan_control.py` ergänzen:

```python
from sqlalchemy import update
from app.services.power.fan_restore import is_observation, resolve_restore_value
```

Im Konstruktor, neben den übrigen Zustandsfeldern:

```python
        # Rueckgabewerte pro Luefter, beim Start aus der DB geladen. stop()
        # braucht sie ohne Datenbankzugriff (#534).
        self._restore_values: Dict[str, int] = {}
```

Neue Methode auf `FanControlService`:

```python
    def _persist_restore_values(self, observations: Dict[str, int]) -> None:
        """Beobachtete pwm_enable-Werte speichern und in den Speicher laden.

        Nur der Primary schreibt. Geschrieben wird ausschliesslich bei echter
        Aenderung, und updated_at wird dabei ausdruecklich mitgefuehrt: die
        Spalte traegt onupdate=func.now() und ist das Rangkriterium des
        Identitaets-Abgleichs (fan_reconcile.py). Ein Schreibvorgang bei jedem
        Start setzte jede Zeile auf "gerade angefasst".
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return

        with self.db_session_factory() as db:
            rows = list(db.execute(select(FanConfig)).scalars())
            by_id = {row.fan_id: row for row in rows}

            changed = 0
            for fan_id, row in by_id.items():
                target = resolve_restore_value(observations.get(fan_id),
                                               row.pwm_enable_restore)
                if target is not None:
                    self._restore_values[fan_id] = target
                if target == row.pwm_enable_restore or target is None:
                    continue
                db.execute(
                    update(FanConfig)
                    .where(FanConfig.id == row.id)
                    .values(pwm_enable_restore=target,
                            updated_at=row.updated_at)
                )
                changed += 1
                logger.info(
                    "Rueckgabewert fuer %s beobachtet: pwm_enable=%s",
                    fan_id, target,
                )
            if changed:
                db.commit()
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_restore_persistence.py -v`
Expected: PASS (5 Tests)

- [ ] **Step 5: Beobachtungen sammeln und in `_load_fan_configs` einhängen**

Zuerst ein Helfer, der die Beobachtungen aus dem Cache zieht — er wird an **zwei** Stellen gebraucht:

```python
    def _collect_pwm_enable_observations(self) -> Dict[str, int]:
        """Beobachtete Automatikmodi aus dem Scan-Cache.

        GPU-Luefter bleiben draussen: fuer AMD-Karten existiert mit
        AmdManualState / disable_amd_manual bereits ein eigener Rueckgabeweg,
        der zusaetzlich das Performance-Level zuruecksetzt, und nouveau hat
        gar keinen. Der isinstance-Schutz folgt dem Muster, das fuer dieselben
        Cache-Zugriffe in #532 eingefuehrt wurde.
        """
        cache = getattr(self._backend, "_fan_cache", None) or {}
        return {
            fan_id: info["pwm_enable_at_scan"]
            for fan_id, info in cache.items()
            if isinstance(info, dict)
            and info.get("gpu_vendor") is None
            and is_observation(info.get("pwm_enable_at_scan"))
        }
```

In `_load_fan_configs`, **vor** der Anlage-Schleife (also vor `for fan in fans:` bei Zeile 428):

```python
            observations = self._collect_pwm_enable_observations()
```

Im `FanConfig(...)`-Aufruf der Anlage-Schleife, nach `is_active=True`:

```python
                        pwm_enable_restore=observations.get(fan.fan_id),
```

Das ist die Stelle, die die Spec meint: der erste Scan eines Lüfters ist die einzige Gelegenheit, seinen Board-Wert zu sehen, und die Zeile entsteht hier ohnehin. Ihn stattdessen per UPDATE nachzureichen erzeugte einen zweiten Schreibvorgang unmittelbar nach dem INSERT.

Am Ende der Methode, **nach** dem `db.commit()` der Anlage-Schleife:

```python
        self._persist_restore_values(observations)
```

- [ ] **Step 6: Test für die Anlage-Schleife ergänzen**

An `backend/tests/test_fan_restore_persistence.py` anhängen:

```python
def test_new_row_carries_the_observation():
    """Die Erstbeobachtung landet am neu angelegten FanConfig-Objekt.

    Geprueft wird der Konstruktoraufruf, nicht der UPDATE-Pfad -- fuer einen
    neuen Luefter gibt es zum Zeitpunkt der Anlage noch keine Zeile, die man
    aktualisieren koennte.
    """
    from app.models.fans import FanConfig

    observations = {"nct6798-isa-0290:pwm1": 5}
    config = FanConfig(
        fan_id="nct6798-isa-0290:pwm1",
        name="nct6798 PWM1",
        mode="auto",
        is_active=True,
        pwm_enable_restore=observations.get("nct6798-isa-0290:pwm1"),
    )
    assert config.pwm_enable_restore == 5

    unknown = FanConfig(
        fan_id="nct6798-isa-0290:pwm2",
        name="nct6798 PWM2",
        mode="auto",
        is_active=True,
        pwm_enable_restore=observations.get("nct6798-isa-0290:pwm2"),
    )
    assert unknown.pwm_enable_restore is None
```

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_restore_persistence.py tests/test_fan_reconcile_wiring.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/tests/test_fan_restore_persistence.py
git commit -m "feat(fans): beobachtete Rueckgabewerte persistieren, ohne updated_at zu bewegen (#534)"
```

---

### Task 6: Die Rückgabe beim Beenden und beim Backend-Wechsel

**Files:**
- Modify: `backend/app/services/power/fan_control.py:210-221` (`stop`), `:1065-1090` (`switch_backend`)
- Test: `backend/tests/test_fan_handback_on_stop.py`

**Interfaces:**
- Consumes: `needs_release` (Task 1), `release_to_board` (Task 4), `_restore_values` (Task 5)
- Produces: `FanControlService._release_all_to_board() -> None`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_fan_handback_on_stop.py`:

```python
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
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_fan_handback_on_stop.py -v`
Expected: FAIL mit `AttributeError: ... has no attribute '_release_all_to_board'`

- [ ] **Step 3: Die Rückgabe implementieren**

Import in `fan_control.py` ergänzen:

```python
from app.services.power.fan_restore import needs_release
```

Neue Methode auf `FanControlService`:

```python
    async def _release_all_to_board(self) -> None:
        """Gibt alle Luefter mit bekanntem Rueckgabewert an die Automatik zurueck.

        Entschieden wird am Ist-Wert in sysfs statt an einer Besitz-Buchfuehrung.
        Ein Luefter im MANUAL-Modus wird vom Regelkreis nie geschrieben (Ziel ==
        Ist), sein einziger Schreibweg ist die HTTP-Route -- und die landet bei
        vier Workern meist auf einem Sekundaer. Eine primary-gebundene
        Besitzverfolgung haette ihn nie erfasst, und genau er stuende am Ende
        ungeregelt da.
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return
        if not self._restore_values:
            return

        cache = getattr(self._backend, "_fan_cache", None) or {}
        released = 0
        failed = 0

        for fan_id, target in self._restore_values.items():
            info = cache.get(fan_id)
            if not isinstance(info, dict):
                continue
            if info.get("gpu_vendor") is not None:
                continue
            pwm_enable_path = info.get("pwm_enable_path")
            if pwm_enable_path is None:
                continue

            current = await self._backend._read_hwmon_file(pwm_enable_path)
            if not needs_release(current, target):
                continue

            if await self._backend.release_to_board(fan_id, target):
                released += 1
            else:
                failed += 1

        if released or failed:
            logger.info(
                "Rueckgabe an die Board-Automatik: %d erfolgreich, %d fehlgeschlagen",
                released, failed,
            )
```

- [ ] **Step 4: In `stop()` einhängen**

`fan_control.py:210-221`, die Methode `stop()` erweitern — die Rückgabe **nach** dem Abbruch der Monitoring-Task:

```python
    async def stop(self):
        """Stop fan control service."""
        self._is_running = False

        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        # Erst die Schleife stilllegen, dann zurueckgeben -- umgekehrt schriebe
        # sie im naechsten Zyklus pwm_enable=1 gegen die Rueckgabe (#534).
        try:
            await self._release_all_to_board()
        except Exception:
            logger.exception("Rueckgabe an die Board-Automatik fehlgeschlagen")

        logger.info("Fan control service stopped")
```

Der `try` ist nötig, weil `stop()` im Shutdown-Pfad läuft: eine Ausnahme dort dürfte den restlichen Shutdown nicht abbrechen.

- [ ] **Step 5: In `switch_backend` einhängen**

`fan_control.py:1065-1090`. Diese Methode bricht die Monitoring-Task heute **nicht** ab. Ergänze am Anfang der Methode, vor jedem Backend-Tausch:

```python
        # Gleiche Reihenfolge wie in stop(): erst die Schleife stilllegen, dann
        # zurueckgeben, dann tauschen. Ohne das schriebe die weiterlaufende
        # Schleife pwm_enable=1 gegen die Rueckgabe, und ein Wechsel auf das
        # Dev-Backend liesse jeden Kanal in Handsteuerung zurueck -- niemand
        # regelt, ueber einen Admin-Endpunkt (#534).
        was_running = self._is_running
        self._is_running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        try:
            await self._release_all_to_board()
        except Exception:
            logger.exception("Rueckgabe beim Backend-Wechsel fehlgeschlagen")
```

Am Ende der Methode, nach dem Tausch, die Schleife wieder starten, falls sie lief:

```python
        if was_running:
            self._is_running = True
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_handback_on_stop.py -v`
Expected: PASS (8 Tests)

Run: `cd backend ; python -m pytest -k "fan or power" -q`
Expected: mindestens die in Task 1 notierte Messlatte plus die neuen Tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/tests/test_fan_handback_on_stop.py
git commit -m "feat(fans): Rueckgabe an die Board-Automatik beim Beenden und beim Backend-Wechsel (#534)"
```

---

### Task 7: Der Round-Trip, Dokumentation und Abschluss-Gates

**Files:**
- Test: `backend/tests/test_fan_handback_roundtrip.py`
- Modify: `docs/TECHNICAL_DOCUMENTATION.md` (Abschnitt Lüftersteuerung)
- Modify: `backend/app/services/CLAUDE.md` (`power/`-Block)

- [ ] **Step 1: Den Round-Trip-Test schreiben**

Er prüft die Naht, die keine Einzeltabelle abdeckt: Beobachtung → Persistenz → Rückgabe → erneuter Scan.

`backend/tests/test_fan_handback_roundtrip.py`:

```python
"""Beobachtung -> Persistenz -> Rueckgabe -> erneuter Scan (#534).

Der Test bildet zwei Startzyklen auf demselben sysfs-Baum ab und belegt, dass
der zurueckgegebene Wert beim naechsten Start wieder als Beobachtung ankommt --
ohne dass sich etwas verschiebt.
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from app.core.config import get_settings
from app.models.base import Base
from app.models.fans import FanConfig
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.services.power.fan_control import FanControlService


def _tree(tmp_path: Path, enable_value: str) -> Path:
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "nct6775.656"
    hwmon = device / "hwmon" / "hwmon3"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("nct6798\n")
    (hwmon / "pwm1").write_text("128\n")
    (hwmon / "pwm1_enable").write_text(enable_value + "\n")
    (hwmon / "fan1_input").write_text("900\n")
    bus = sysfs / "bus" / "platform"
    bus.mkdir(parents=True, exist_ok=True)
    os.symlink(bus, device / "subsystem", target_is_directory=True)
    os.symlink(device, hwmon / "device", target_is_directory=True)
    klass = sysfs / "class" / "hwmon"
    klass.mkdir(parents=True, exist_ok=True)
    os.symlink(hwmon, klass / "hwmon3", target_is_directory=True)
    return klass


@pytest.mark.asyncio
async def test_observation_survives_a_full_cycle(tmp_path, monkeypatch):
    klass = _tree(tmp_path, "5")   # Kaltstart: BIOS hat Smart Fan IV gesetzt
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        True, raising=False)

    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, factory)
    service._use_linux_backend = True

    backend = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend, "_hwmon_base", klass)
    await backend._scan_pwm_fans()
    service._backend = backend
    fan_id = next(iter(backend._fan_cache))

    with factory() as db:
        db.add(FanConfig(fan_id=fan_id, name="nct6798 PWM1", mode="auto",
                         is_active=True))
        db.commit()

    # Erster Zyklus: Beobachtung persistieren
    service._persist_restore_values({fan_id: 5})
    with factory() as db:
        assert db.execute(select(FanConfig)).scalar_one().pwm_enable_restore == 5

    # BaluHost regelt: pwm_enable steht auf 1
    backend._fan_cache[fan_id]["pwm_enable_path"].write_text("1\n")

    # Beenden: Rueckgabe
    await service._release_all_to_board()
    assert backend._fan_cache[fan_id]["pwm_enable_path"].read_text().strip() == "5"

    # Zweiter Zyklus: neuer Scan liest den zurueckgegebenen Wert
    backend2 = LinuxFanControlBackend(get_settings())
    monkeypatch.setattr(backend2, "_hwmon_base", klass)
    await backend2._scan_pwm_fans()
    assert backend2._fan_cache[fan_id]["pwm_enable_at_scan"] == 5

    # ... und die Persistenz aendert nichts mehr
    service._backend = backend2
    with factory() as db:
        before = db.execute(select(FanConfig)).scalar_one().updated_at
    service._persist_restore_values({fan_id: 5})
    with factory() as db:
        row = db.execute(select(FanConfig)).scalar_one()
    assert row.pwm_enable_restore == 5
    assert row.updated_at == before
```

- [ ] **Step 2: Test laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_handback_roundtrip.py -v`
Expected: PASS

- [ ] **Step 3: Dokumentation**

In `docs/TECHNICAL_DOCUMENTATION.md`, im Lüfter-Abschnitt, ergänzen — und dabei die Grenzen so deutlich benennen wie die Funktion:

- Beim Beenden des Dienstes wird `pwm_enable` auf den Automatikmodus zurückgeschrieben, den BaluHost am selben Chip zuvor gelesen hat. Damit regelt nach einem Deploy-Neustart das Board, statt dass die Lüfter auf dem letzten Wert einfrieren.
- **Nur beobachtete Werte.** Es wird nichts geraten. Ein Wert wird nur übernommen, wenn der Scan beim Start einen Automatikmodus (`pwm_enable >= 2`) vorfindet — das ist nach einem Kaltstart der Fall, nicht nach einem Dienst-Neustart.
- **Auf einer laufenden Installation greift die Funktion daher erst nach dem nächsten Kaltstart.** Wer nicht warten will, setzt den Wert einmal bei gestopptem Dienst von Hand (`echo 5 > /sys/class/hwmon/hwmonN/pwmM_enable`); der nächste Start übernimmt ihn.
- **GPU-Lüfter sind ausgenommen.** Für AMD-Karten existiert ein eigener Rückgabeweg, der zusätzlich das Performance-Level zurücksetzt.
- **Bei `SIGKILL` oder Stromausfall gibt es keine Rückgabe.** `systemctl stop` und der Deploy-Neustart senden `SIGTERM` und sind abgedeckt.
- Ein Hinweis zum Ablesen: ein Lüfter, der bei 100 % läuft, meldet `pwm_enable` als `0`, nicht als `1`.

In `backend/app/services/CLAUDE.md` im `power/`-Block ergänzen:

```
- `fan_restore.py` — Regel fuer die Rueckgabe an die Board-Automatik (#534):
  `is_observation()`, `resolve_restore_value()`, `needs_release()`. Rein, ohne
  sysfs- und DB-Zugriff. Zurueckgeschrieben wird ausschliesslich ein selbst
  beobachteter Wert; es gibt bewusst keinen Treiber-Fallback.
```

- [ ] **Step 4: Alle Gates**

```bash
cd backend
python -m pytest -k "fan or power" -q
python -m ruff check app/services/power/ tests/
cd ../client
npx eslint .
npm run build
```
Expected: alles grün; die Testzahl mindestens die in Task 1 notierte Messlatte plus die neuen Tests. Das Frontend wird von dieser Arbeit nicht angefasst, die Gates laufen zur Absicherung mit.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_fan_handback_roundtrip.py docs/TECHNICAL_DOCUMENTATION.md backend/app/services/CLAUDE.md
git commit -m "docs(fans): Rueckgabe an die Board-Automatik dokumentieren, Round-Trip-Test (#534)"
```

---

## Feldverifikation nach dem Deploy

Kein Task — der Nachweis am lebenden Objekt, in dieser Reihenfolge.

1. **Direkt nach dem Deploy:**
   `SELECT fan_id, pwm_enable_restore FROM fan_configs WHERE is_active`
   Erwartung: **`NULL`** für alle. Es gab keinen Kaltstart, also keine Beobachtung. Steht dort ein Wert, ist die Regel verletzt.
2. **Nach einem Reboot:** dieselbe Abfrage. Erwartung: der BIOS-Wert, für die vier nct6798-Kanäle vermutlich `5`. **Das ist die erste Messung des tatsächlichen Board-Defaults dieser Maschine** — bisher wurde er nie beobachtet, jede frühere Messung lief nach BaluHost-Betrieb.
3. **Der Kern:** `systemctl stop baluhost-backend`, dann `cat /sys/class/hwmon/hwmon3/pwm{1,2,3,7}_enable`. Erwartung: der in Schritt 2 gelesene Wert. Heute steht dort `1` — das ist die Lücke. Ein Lüfter, der bei 100 % lief, zeigt vorher `0`.
4. **Gegenprobe:** Dienst starten, eine Minute warten, erneut lesen. Erwartung `1` — BaluHost hat die Kontrolle zurückgenommen.
