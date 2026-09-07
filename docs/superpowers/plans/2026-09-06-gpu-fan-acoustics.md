# GPU-Lüfterakustik über `gpu_od/fan_ctrl` — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die vier Akustik-Skalare einer RDNA3-Karte aus BaluHost setzen, dauerhaft halten und in der Oberfläche ehrlich darstellen — einschliesslich des Zero-RPM-Zustands, der sie im Leerlauf wirkungslos aussehen lässt.

**Architecture:** Ein zustandsloses Modul liest und schreibt die sysfs-Knoten unter `gpu_od/fan_ctrl`; eine Singleton-Zeile in der Datenbank hält die gewünschten Werte und die vor dem ersten Eingriff beobachtete Baseline; der Primary-Worker wendet sie beim Start an; zwei Endpunkte unter `/api/fans` bedienen ein Panel, das in der vorhandenen `FirmwareFanNotice` wohnt.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 + Alembic, Pydantic v2, pytest; React 18 + TypeScript, Vitest, i18next.

**Spec:** `docs/superpowers/specs/2026-09-06-gpu-fan-acoustics-design.md`

## Global Constraints

- **Keine Versionsprüfung im Code.** Gelesen wird, was vorhanden ist; fehlt das Verzeichnis, meldet die API `available: false`. Die Kernel-Matrix gehört in die Dokumentation, nicht in eine Bedingung.
- **Nur beobachtete Werte werden zurückgeschrieben.** Die Baseline wird vor dem ersten Write erfasst. Kein Rückfall auf einen geratenen Herstellerstandard, kein `r`-Kommando.
- **Nach jedem Write wird zurückgelesen.** Ein angenommener Write beweist auf dieser Karte nichts (#480).
- **Hardware-Eingriffe beim Start nur vom Primary-Worker** (`lifespan.IS_PRIMARY_WORKER`). Vier Uvicorn-Worker, siehe #555 und #559.
- **Der `sudo tee`-Fallback wird nicht nachgebaut.** `LinuxFanControlBackend._write_hwmon_file` bleibt der einzige Ort dieser Leiter (#554).
- **Alembic:** neue Migration hängt an `c9a4e77b2d10`. Vor dem Schreiben `python -m alembic heads` prüfen, nicht die Dev-DB.
- **Zeilenenden:** Das Repo läuft mit `core.autocrlf=true`. Werkzeuge, die Dateien neu schreiben, müssen CRLF erhalten.
- Backend-Tests: `cd backend ; python -m pytest <pfad> --no-cov -q`. Volle Suite gehört der CI (hängt auf Windows).
- Frontend: `cd client ; npx vitest run <pfad>`, vor dem PR zusätzlich `npx eslint .` (0 Fehler) und `npm run build`.

---

### Task 1: Die Knoten lesen

**Files:**
- Create: `backend/app/services/power/fan_gpu_acoustics.py`
- Test: `backend/tests/test_fan_gpu_acoustics_read.py`

**Interfaces:**
- Consumes: nichts
- Produces: `ParsedNode(value: int, minimum: int, maximum: int)`, `parse_node(text: str) -> ParsedNode`, `find_fan_ctrl_dir(hwmon_dir: Path) -> Optional[Path]`, `read_acoustics(fan_ctrl_dir: Path) -> Dict[str, ParsedNode]` (Schlüssel = Dateiname, z. B. `"fan_target_temperature"`)

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

```python
"""Lesen der gpu_od/fan_ctrl-Knoten (#516).

Die Formate stammen von BaluNode, RX 7900 XT, Kernel 6.12.74 — nicht aus der
Kernel-Doku. Die Schluesselnamen sind uneinheitlich (FAN_TARGET_TEMPERATURE
gegen TARGET_TEMPERATURE, OD_ACOUSTIC_LIMIT gegen ACOUSTIC_LIMIT), deshalb
liest der Parser positionell.
"""
import os
from pathlib import Path

import pytest

from app.services.power.fan_gpu_acoustics import (
    find_fan_ctrl_dir,
    parse_node,
    read_acoustics,
)

TARGET_TEMPERATURE = (
    "FAN_TARGET_TEMPERATURE:\n"
    "95\n"
    "OD_RANGE:\n"
    "TARGET_TEMPERATURE: 25 105\n"
)

ACOUSTIC_LIMIT = (
    "OD_ACOUSTIC_LIMIT:\n"
    "3000\n"
    "OD_RANGE:\n"
    "ACOUSTIC_LIMIT: 500 3000\n"
)

MINIMUM_PWM = (
    "FAN_MINIMUM_PWM:\n"
    "23\n"
    "OD_RANGE:\n"
    "MINIMUM_PWM: 23 100\n"
)


def test_parses_value_and_range():
    node = parse_node(TARGET_TEMPERATURE)
    assert (node.value, node.minimum, node.maximum) == (95, 25, 105)


def test_ignores_the_inconsistent_key_names():
    """OD_ACOUSTIC_LIMIT oben, ACOUSTIC_LIMIT unten -- der Parser liest
    positionell, sonst uebernaehme er eine Inkonsistenz des Treibers."""
    node = parse_node(ACOUSTIC_LIMIT)
    assert (node.value, node.minimum, node.maximum) == (3000, 500, 3000)


def test_parses_a_range_whose_minimum_is_not_zero():
    node = parse_node(MINIMUM_PWM)
    assert (node.value, node.minimum, node.maximum) == (23, 23, 100)


def test_unparseable_text_returns_none():
    """Ein leerer oder fremd formatierter Knoten darf nicht werfen -- er wird
    einfach nicht angeboten."""
    assert parse_node("") is None
    assert parse_node("OD_FAN_CURVE:\n0: 0C 0%\n") is None
```

- [ ] **Step 2: Lauf gegen den fehlenden Code**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_read.py --no-cov -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.services.power.fan_gpu_acoustics'`

- [ ] **Step 3: Den Parser schreiben**

```python
"""Akustik-Knoten der AMD-GPU unter gpu_od/fan_ctrl lesen und schreiben (#516).

Zustandslos: kein Datenbankzugriff, keine Konfiguration. Die aufrufende
Dienstschicht entscheidet, was gesetzt wird und was die Baseline ist.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_RANGE_LINE = re.compile(r"^\s*[A-Z_]+:\s*(-?\d+)\s+(-?\d+)\s*$")


@dataclass(frozen=True)
class ParsedNode:
    value: int
    minimum: int
    maximum: int


def parse_node(text: str) -> Optional[ParsedNode]:
    """Wert und Bereich aus dem Knoteninhalt.

    Positionell gelesen, nicht ueber Schluesselnamen: der Treiber schreibt
    sie uneinheitlich (FAN_TARGET_TEMPERATURE gegen TARGET_TEMPERATURE).
    Der Wert ist die Zeile nach der ersten Kopfzeile, der Bereich sind die
    zwei Zahlen nach OD_RANGE:.

    Returns:
        None, wenn der Inhalt nicht dieser Form folgt -- etwa fan_curve, das
        fuenf Stuetzstellen statt eines Skalars fuehrt.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return None

    try:
        value = int(lines[1])
    except ValueError:
        return None

    try:
        range_index = lines.index("OD_RANGE:")
    except ValueError:
        return None
    if range_index + 1 >= len(lines):
        return None

    match = _RANGE_LINE.match(lines[range_index + 1])
    if match is None:
        return None

    return ParsedNode(value=value, minimum=int(match.group(1)),
                      maximum=int(match.group(2)))
```

- [ ] **Step 4: Parser-Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_read.py -k parse --no-cov -q`
Expected: 4 passed

- [ ] **Step 5: Test für Verzeichnissuche und Lesen anhängen**

```python
def _card_tree(tmp_path: Path) -> Path:
    """Bildet die echte Struktur nach: hwmon traegt einen device-Symlink auf
    das PCI-Geraet, darunter liegt gpu_od/fan_ctrl. Doppelpunktfrei, damit es
    auf Windows laeuft (#532)."""
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "amdgpu-sim.1"
    fan_ctrl = device / "gpu_od" / "fan_ctrl"
    fan_ctrl.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (fan_ctrl / "fan_target_temperature").write_text(TARGET_TEMPERATURE)
    (fan_ctrl / "acoustic_limit_rpm_threshold").write_text(ACOUSTIC_LIMIT)
    (fan_ctrl / "fan_minimum_pwm").write_text(MINIMUM_PWM)
    (fan_ctrl / "fan_curve").write_text("OD_FAN_CURVE:\n0: 0C 0%\n")

    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    os.symlink(device, hwmon / "device", target_is_directory=True)
    return hwmon


def test_finds_the_fan_ctrl_directory(tmp_path):
    hwmon = _card_tree(tmp_path)
    found = find_fan_ctrl_dir(hwmon)
    assert found is not None
    assert found.name == "fan_ctrl"


def test_a_card_without_the_interface_yields_none(tmp_path):
    """Aeltere Kernel haben gpu_od/fan_ctrl nicht -- das ist kein Fehler."""
    hwmon = tmp_path / "sys" / "class" / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    assert find_fan_ctrl_dir(hwmon) is None


@pytest.mark.asyncio
async def test_fan_curve_falls_out_by_parsing_not_by_a_name_list(tmp_path):
    """fan_curve liegt im selben Verzeichnis und fuehrt fuenf Stuetzstellen.

    Es wird nicht ueber eine Namensliste ausgeschlossen, sondern faellt durch
    parse_node heraus -- deshalb kann read_acoustics aufzaehlen und nimmt
    kuenftige Skalare mit."""
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    nodes = await read_acoustics(fan_ctrl)
    assert set(nodes) == {
        "fan_target_temperature",
        "acoustic_limit_rpm_threshold",
        "fan_minimum_pwm",
    }
    assert nodes["fan_target_temperature"].value == 95


@pytest.mark.asyncio
async def test_an_unreadable_node_is_skipped_not_fatal(tmp_path):
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    (fan_ctrl / "acoustic_target_rpm_threshold").write_text("Unsinn\n")
    nodes = await read_acoustics(fan_ctrl)
    assert "acoustic_target_rpm_threshold" not in nodes
    assert "fan_target_temperature" in nodes
```

- [ ] **Step 6: Lauf gegen den fehlenden Code**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_read.py --no-cov -q`
Expected: FAIL mit `ImportError: cannot import name 'find_fan_ctrl_dir'`

- [ ] **Step 7: Suche und Lesen implementieren**

An `fan_gpu_acoustics.py` anhängen:

```python
def find_fan_ctrl_dir(hwmon_dir: Path) -> Optional[Path]:
    """Vom hwmon-Verzeichnis zum gpu_od/fan_ctrl-Verzeichnis der Karte.

    Nutzt die vorhandene Geraeteaufloesung aus fan_gpu_manual, damit die in
    #480 gelernten Fallstricke nicht ein zweites Mal geloest werden: der
    device-Symlink ist der Primaerweg, der Aufwaertslauf funktioniert nur in
    synthetischen Baeumen.
    """
    from app.services.power.fan_gpu_manual import _device_from_hwmon

    device = _device_from_hwmon(hwmon_dir)
    if device is None:
        return None
    fan_ctrl = device / "gpu_od" / "fan_ctrl"
    return fan_ctrl if fan_ctrl.is_dir() else None


async def read_acoustics(fan_ctrl_dir: Path) -> Dict[str, ParsedNode]:
    """Die angebotenen Skalare mit Wert und vom Treiber gemeldetem Bereich.

    Aufgezaehlt statt fest verdrahtet: gelesen wird, was im Verzeichnis liegt,
    und behalten wird, was sich als Skalar parsen laesst. Damit faellt
    fan_curve von selbst heraus -- es fuehrt fuenf Stuetzstellen und kein
    parse_node-Ergebnis -- und ein kuenftiger Knoten (ab Kernel 6.13
    fan_zero_rpm_enable) kommt ohne Codeaenderung mit.

    Was BaluHost davon zu SETZEN anbietet, entscheidet die Erlaubnisliste in
    Task 2. Lesen ist offen, Schreiben ist auf bekannte Namen beschraenkt.
    """
    nodes: Dict[str, ParsedNode] = {}
    for path in sorted(fan_ctrl_dir.iterdir()):
        if not path.is_file():
            continue
        try:
            parsed = parse_node(path.read_text())
        except OSError as exc:
            logger.debug("Akustik-Knoten %s nicht lesbar: %s", path.name, exc)
            continue
        if parsed is not None:
            nodes[path.name] = parsed
    return nodes
```

- [ ] **Step 8: Alle Lesetests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_read.py --no-cov -q`
Expected: 8 passed

- [ ] **Step 9: Committen**

```bash
git add backend/app/services/power/fan_gpu_acoustics.py backend/tests/test_fan_gpu_acoustics_read.py
git commit -m "feat(fans): gpu_od/fan_ctrl lesen und positionell parsen (#516)"
```

---

### Task 2: Schreiben mit Bereichsprüfung, Commit und Rücklesen

**Files:**
- Modify: `backend/app/services/power/fan_gpu_acoustics.py`
- Test: `backend/tests/test_fan_gpu_acoustics_write.py`

**Interfaces:**
- Consumes: `ParsedNode`, `read_acoustics` aus Task 1
- Produces: `ACOUSTIC_NODES` (Erlaubnisliste zum Schreiben), `async write_acoustic(fan_ctrl_dir: Path, name: str, value: int, write) -> bool` mit `write` in der Signatur `async (Path, str) -> tuple[bool, Optional[int]]` — dieselbe wie `LinuxFanControlBackend._write_hwmon_file` —, und `resolve_restores(previous_desired: dict, incoming: dict, baseline: dict) -> Dict[str, int]`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

```python
"""Schreiben der Akustik-Knoten (#516).

Der Ablauf ist Bereichspruefung, Wert, dann 'c' zum Uebernehmen, dann
Ruecklesen. Der letzte Schritt ist nicht Zierde: derselbe Treiber verschluckt
laut #480 pwm_enable-Writes wortlos, ein Rueckgabewert von True beweist hier
also nichts.
"""
import os
from pathlib import Path

import pytest

from app.services.power.fan_gpu_acoustics import find_fan_ctrl_dir, write_acoustic

TARGET_TEMPERATURE = (
    "FAN_TARGET_TEMPERATURE:\n95\nOD_RANGE:\nTARGET_TEMPERATURE: 25 105\n"
)


def _card_tree(tmp_path: Path) -> Path:
    sysfs = tmp_path / "sys"
    device = sysfs / "devices" / "platform" / "amdgpu-sim.1"
    fan_ctrl = device / "gpu_od" / "fan_ctrl"
    fan_ctrl.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (fan_ctrl / "fan_target_temperature").write_text(TARGET_TEMPERATURE)
    hwmon = device / "hwmon" / "hwmon2"
    hwmon.mkdir(parents=True)
    (hwmon / "name").write_text("amdgpu\n")
    os.symlink(device, hwmon / "device", target_is_directory=True)
    return hwmon


def _recording_write(calls, *, applied: str | None = None, fan_ctrl=None):
    """Schreibfunktion in der Form von _write_hwmon_file.

    `applied` simuliert, was der Treiber danach zurueckliest -- damit die
    Ruecklese-Kontrolle pruefbar wird.
    """
    async def write(path: Path, value: str):
        calls.append((path.name, value))
        if applied is not None and value != "c":
            (fan_ctrl / path.name).write_text(
                f"FAN_TARGET_TEMPERATURE:\n{applied}\nOD_RANGE:\n"
                f"TARGET_TEMPERATURE: 25 105\n"
            )
        return True, None
    return write


@pytest.mark.asyncio
async def test_writes_the_value_then_commits(tmp_path):
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", 75,
        _recording_write(calls, applied="75", fan_ctrl=fan_ctrl),
    )

    assert ok is True
    assert calls == [
        ("fan_target_temperature", "75"),
        ("fan_target_temperature", "c"),
    ]


@pytest.mark.asyncio
async def test_a_value_outside_the_reported_range_is_refused(tmp_path):
    """Der Kernel lehnt selbst ab (EINVAL bei 200, gemessen). Die Pruefung
    bleibt, damit die Fehlermeldung aus der UI kommt statt aus dmesg."""
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", 200, _recording_write(calls),
    )

    assert ok is False
    assert calls == [], "trotz ungueltigem Wert geschrieben"


@pytest.mark.asyncio
async def test_a_write_without_effect_is_a_failure(tmp_path):
    """Der Kern: der Treiber nimmt an und aendert nichts."""
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(
        fan_ctrl, "fan_target_temperature", 75,
        _recording_write(calls, applied="95", fan_ctrl=fan_ctrl),
    )

    assert ok is False


@pytest.mark.asyncio
async def test_an_unknown_node_is_refused(tmp_path):
    fan_ctrl = find_fan_ctrl_dir(_card_tree(tmp_path))
    calls = []

    ok = await write_acoustic(fan_ctrl, "fan_curve", 1, _recording_write(calls))

    assert ok is False
    assert calls == []


# --- Die Ruecksetz-Entscheidung, rein und ohne sysfs ---------------------
#
# Sie steckte im Entwurf als dreifach bedingte Comprehension im Route-Handler.
# Genau diese Form versteckt Fehler; #534 hat dafuer fan_restore.py gebaut.

def test_unmanaging_a_value_restores_its_baseline():
    restores = resolve_restores(
        previous_desired={"fan_target_temperature": 75},
        incoming={"fan_target_temperature": None},
        baseline={"fan_target_temperature": 95},
    )
    assert restores == {"fan_target_temperature": 95}


def test_a_value_that_was_never_managed_is_not_touched():
    """Sonst schriebe ein Speichern-Klick eine Baseline auf einen Knoten, den
    BaluHost nie angefasst hat."""
    restores = resolve_restores(
        previous_desired={"fan_minimum_pwm": None},
        incoming={"fan_minimum_pwm": None},
        baseline={"fan_minimum_pwm": 23},
    )
    assert restores == {}


def test_without_a_baseline_nothing_is_restored():
    """Kein Rueckfall auf einen geratenen Herstellerstandard (#534)."""
    restores = resolve_restores(
        previous_desired={"fan_target_temperature": 75},
        incoming={"fan_target_temperature": None},
        baseline={"fan_target_temperature": None},
    )
    assert restores == {}


def test_a_changed_value_is_not_a_restore():
    restores = resolve_restores(
        previous_desired={"fan_target_temperature": 75},
        incoming={"fan_target_temperature": 80},
        baseline={"fan_target_temperature": 95},
    )
    assert restores == {}
```

Den Import am Dateikopf ergänzen: `from app.services.power.fan_gpu_acoustics import find_fan_ctrl_dir, resolve_restores, write_acoustic`

- [ ] **Step 2: Lauf gegen den fehlenden Code**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_write.py --no-cov -q`
Expected: FAIL mit `ImportError: cannot import name 'write_acoustic'`

- [ ] **Step 3: Implementieren**

An `fan_gpu_acoustics.py` anhängen:

```python
# Die vier Skalare, die BaluHost zu SETZEN anbietet. Gelesen wird mehr --
# read_acoustics zaehlt auf. fan_curve gehoert bewusst nicht dazu: es schaltet
# die Karte in den Manual-Modus, in dem diese vier nicht mehr wirken
# (Kernel-Doku: "works under auto fan control mode only").
ACOUSTIC_NODES = (
    "fan_target_temperature",
    "acoustic_limit_rpm_threshold",
    "acoustic_target_rpm_threshold",
    "fan_minimum_pwm",
)


def resolve_restores(previous_desired: dict, incoming: dict,
                     baseline: dict) -> Dict[str, int]:
    """Welche Knoten auf ihre Baseline zurueckgeschrieben werden muessen.

    Rein: kein sysfs, keine Datenbank. Ein Knoten wird zurueckgesetzt, wenn
    BaluHost ihn bisher verwaltet hat, der neue Wunsch None ist -- also 'nicht
    mehr verwalten' -- und eine beobachtete Baseline vorliegt.

    Fehlt die Baseline, passiert nichts. Kein Rueckfall auf einen geratenen
    Herstellerstandard; zurueckgeschrieben wird nur, was BaluHost selbst
    gelesen hat (#534).
    """
    return {
        name: baseline[name]
        for name, value in incoming.items()
        if value is None
        and previous_desired.get(name) is not None
        and baseline.get(name) is not None
    }


async def write_acoustic(fan_ctrl_dir: Path, name: str, value: int, write) -> bool:
    """Einen Akustikwert setzen und uebernehmen.

    Args:
        write: Schreibfunktion in der Form von
            LinuxFanControlBackend._write_hwmon_file -- async (Path, str)
            nach (ok, errno). Sie wird hereingereicht, statt die Leiter aus
            direktem Write und sudo-tee-Fallback nachzubauen; sie soll genau
            einen Ort haben (#554).

    Returns:
        True nur, wenn der Wert danach tatsaechlich anliegt.
    """
    if name not in ACOUSTIC_NODES:
        logger.warning("Unbekannter Akustik-Knoten: %s", name)
        return False

    nodes = await read_acoustics(fan_ctrl_dir)
    node = nodes.get(name)
    if node is None:
        logger.warning("Akustik-Knoten %s nicht lesbar, kein Write", name)
        return False

    if not node.minimum <= value <= node.maximum:
        logger.warning(
            "%s=%s liegt ausserhalb des gemeldeten Bereichs %s..%s",
            name, value, node.minimum, node.maximum,
        )
        return False

    path = fan_ctrl_dir / name
    ok, err = await write(path, str(value))
    if not ok:
        logger.warning("%s nicht schreibbar (errno=%s)", name, err)
        return False

    ok, err = await write(path, "c")
    if not ok:
        logger.warning("%s: Commit fehlgeschlagen (errno=%s)", name, err)
        return False

    applied = (await read_acoustics(fan_ctrl_dir)).get(name)
    if applied is None or applied.value != value:
        logger.warning(
            "%s ohne Wirkung: geschrieben=%s, gelesen=%s",
            name, value, None if applied is None else applied.value,
        )
        return False

    logger.info("%s auf %s gesetzt", name, value)
    return True
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_write.py --no-cov -q`
Expected: 8 passed

- [ ] **Step 5: Committen**

```bash
git add backend/app/services/power/fan_gpu_acoustics.py backend/tests/test_fan_gpu_acoustics_write.py
git commit -m "feat(fans): Akustikwerte schreiben, committen und zurueckpruefen (#516)"
```

---

### Task 3: Datenmodell, Migration, Persistenz

**Files:**
- Modify: `backend/app/models/fans.py` (am Dateiende anhängen)
- Create: `backend/app/schemas/gpu_fan_acoustics.py`
- Create: `backend/alembic/versions/d1e5a83f47c2_gpu_fan_acoustics_config.py`
- Create: `backend/app/services/power/fan_gpu_acoustics_store.py`
- Test: `backend/tests/test_fan_gpu_acoustics_store.py`

**Interfaces:**
- Consumes: nichts aus Task 1/2
- Produces: `GpuFanAcousticsValues` (Pydantic, vier `Optional[int]`), `GpuFanAcousticsConfig` (`desired`, `baseline`), `load_acoustics_config(db) -> GpuFanAcousticsConfig`, `save_acoustics_config(db, config) -> bool`

- [ ] **Step 1: Schema schreiben**

`backend/app/schemas/gpu_fan_acoustics.py`:

```python
"""Pydantic-Schemas fuer die GPU-Luefterakustik (#516)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class GpuFanAcousticsValues(BaseModel):
    """Die vier Skalare. None heisst 'BaluHost verwaltet diesen Wert nicht'."""

    fan_target_temperature: Optional[int] = None
    acoustic_limit_rpm_threshold: Optional[int] = None
    acoustic_target_rpm_threshold: Optional[int] = None
    fan_minimum_pwm: Optional[int] = None


class GpuFanAcousticsConfig(BaseModel):
    """desired: was angewendet werden soll.

    baseline: was auf der Karte stand, bevor BaluHost sie erstmals angefasst
    hat. Zurueckgesetzt wird auf die Baseline, nicht auf den Treiber-Standard
    -- 'wie du es hattest' statt 'wie der Hersteller es vorsah' (#534).
    """

    desired: GpuFanAcousticsValues = GpuFanAcousticsValues()
    baseline: GpuFanAcousticsValues = GpuFanAcousticsValues()
```

- [ ] **Step 2: Modell anhängen**

Am Ende von `backend/app/models/fans.py`:

```python
class GpuFanAcousticsConfigDb(Base):
    """Singleton-Zeile (id=1) mit der GPU-Akustik-Konfiguration als JSON.

    Gleiches Muster wie GpuPowerConfigDb. Eigene Tabelle statt einer
    Erweiterung jener: die Akustikwerte gehoeren nicht in die
    Power-Konfiguration (#516).

    JSON statt vier Spalten, damit ein fuenfter Regler -- etwa
    fan_zero_rpm_enable ab Kernel 6.13 -- eine Schema-Aenderung ohne
    Migration bleibt.
    """

    __tablename__ = "gpu_fan_acoustics_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<GpuFanAcousticsConfigDb(id={self.id})>"
```

- [ ] **Step 3: Migration erzeugen**

Erst den echten Head prüfen — **nicht** den der Dev-DB:

```bash
cd backend ; python -m alembic heads
```

Erwartet: `c9a4e77b2d10 (head)`. Dann von Hand anlegen (kein Autogenerate — es erzeugt auf SQLite ein Phantom auf `status_bar_pill_config.pill_id`, siehe #549):

```python
"""gpu fan acoustics config

Revision ID: d1e5a83f47c2
Revises: c9a4e77b2d10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1e5a83f47c2"
down_revision: Union[str, Sequence[str], None] = "c9a4e77b2d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gpu_fan_acoustics_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by_pid", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("gpu_fan_acoustics_config")
```

- [ ] **Step 4: Migration im Rundlauf prüfen**

Run: `cd backend ; python -m alembic upgrade head ; python -m alembic downgrade -1 ; python -m alembic upgrade head ; python -m alembic heads`
Expected: dreimal ohne Fehler, danach genau ein Head — der neue.

- [ ] **Step 5: Den fehlschlagenden Test schreiben**

```python
"""Persistenz der GPU-Akustik-Konfiguration (#516)."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.fans import GpuFanAcousticsConfigDb
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig, GpuFanAcousticsValues
from app.services.power.fan_gpu_acoustics_store import (
    load_acoustics_config,
    save_acoustics_config,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_loading_without_a_row_gives_empty_defaults(session_factory):
    """Frisch migriert heisst: BaluHost verwaltet nichts."""
    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.desired.fan_target_temperature is None
    assert config.baseline.fan_target_temperature is None


def test_round_trip(session_factory):
    config = GpuFanAcousticsConfig(
        desired=GpuFanAcousticsValues(fan_target_temperature=75),
        baseline=GpuFanAcousticsValues(fan_target_temperature=95),
    )
    with session_factory() as db:
        assert save_acoustics_config(db, config) is True
    with session_factory() as db:
        loaded = load_acoustics_config(db)
    assert loaded.desired.fan_target_temperature == 75
    assert loaded.baseline.fan_target_temperature == 95


def test_saving_twice_keeps_a_single_row(session_factory):
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig())
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_minimum_pwm=40)))
    with session_factory() as db:
        rows = list(db.execute(select(GpuFanAcousticsConfigDb)).scalars())
    assert len(rows) == 1
    stored = GpuFanAcousticsConfig.model_validate_json(rows[0].config_json)
    assert stored.desired.fan_minimum_pwm == 40


def test_corrupt_json_falls_back_to_defaults(session_factory):
    """Eine von Hand verunstaltete Zeile darf den Start nicht verhindern."""
    with session_factory() as db:
        db.add(GpuFanAcousticsConfigDb(id=1, config_json="{kaputt"))
        db.commit()
    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.desired.fan_target_temperature is None
```

- [ ] **Step 6: Lauf gegen den fehlenden Code**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_store.py --no-cov -q`
Expected: FAIL mit `ModuleNotFoundError: ... fan_gpu_acoustics_store`

- [ ] **Step 7: Den Store implementieren**

`backend/app/services/power/fan_gpu_acoustics_store.py`:

```python
"""Persistenz der GPU-Akustik-Konfiguration (#516).

Singleton-Zeile, JSON-Feld -- gleiches Muster wie config_store.py fuer die
GPU-Power-Konfiguration.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import select

from app.models.fans import GpuFanAcousticsConfigDb
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


def load_acoustics_config(db) -> GpuFanAcousticsConfig:
    """Die gespeicherte Konfiguration, sonst leere Vorgaben.

    Ein Fehler beim Lesen darf den Start nicht verhindern: ohne Konfiguration
    verwaltet BaluHost eben nichts, und das ist ein gueltiger Zustand.
    """
    try:
        row = db.execute(
            select(GpuFanAcousticsConfigDb)
            .where(GpuFanAcousticsConfigDb.id == _SINGLETON_ID)
        ).scalar_one_or_none()
        if row is None or not row.config_json:
            return GpuFanAcousticsConfig()
        return GpuFanAcousticsConfig.model_validate_json(row.config_json)
    except Exception as exc:
        logger.warning("GPU-Akustik-Konfiguration nicht lesbar: %s", exc)
        return GpuFanAcousticsConfig()


def save_acoustics_config(db, config: GpuFanAcousticsConfig) -> bool:
    """Konfiguration ablegen. False bei einem Datenbankfehler."""
    try:
        row = db.execute(
            select(GpuFanAcousticsConfigDb)
            .where(GpuFanAcousticsConfigDb.id == _SINGLETON_ID)
        ).scalar_one_or_none()
        if row is None:
            row = GpuFanAcousticsConfigDb(id=_SINGLETON_ID)
            db.add(row)
        row.config_json = config.model_dump_json()
        row.updated_by_pid = os.getpid()
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("GPU-Akustik-Konfiguration nicht schreibbar: %s", exc)
        return False
```

- [ ] **Step 8: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_store.py --no-cov -q`
Expected: 4 passed

- [ ] **Step 9: Committen**

```bash
git add backend/app/models/fans.py backend/app/schemas/gpu_fan_acoustics.py backend/app/services/power/fan_gpu_acoustics_store.py backend/alembic/versions/ backend/tests/test_fan_gpu_acoustics_store.py
git commit -m "feat(fans): Datenmodell und Persistenz der GPU-Akustik (#516)"
```

---

### Task 4: Dienstschicht — Baseline erfassen, `desired` beim Start anwenden

**Files:**
- Modify: `backend/app/services/power/fan_control.py`
- Test: `backend/tests/test_fan_gpu_acoustics_apply.py`

**Interfaces:**
- Consumes: `read_acoustics`, `write_acoustic` (Task 1/2), `load_acoustics_config`, `save_acoustics_config` (Task 3)
- Produces: `FanControlService.apply_acoustics()` — async, **ohne** Primary-Gate, für den `PUT`-Pfad; `FanControlService.apply_gpu_acoustics()` — async, **mit** Primary-Gate, für den Startpfad

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

```python
"""Die Dienstschicht erfasst die Baseline und wendet desired an (#516).

Zwei Zusagen: nur der Primary schreibt Hardware (#555, #559), und die
Baseline wird VOR dem ersten Write erfasst -- danach nicht mehr, sonst
zeichnete sie den eigenen Eingriff auf.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig, GpuFanAcousticsValues
from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService
from app.services.power.fan_gpu_acoustics import ParsedNode
from app.services.power.fan_gpu_acoustics_store import (
    load_acoustics_config,
    save_acoustics_config,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _service(session_factory, monkeypatch, *, primary: bool = True):
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    service = FanControlService(config, session_factory)
    service._use_linux_backend = True
    service._backend = MagicMock()
    service._backend._fan_cache = {
        "amdgpu-pci-0300:pwm1": {
            "gpu_vendor": "amd",
            "pwm_path": Path("/sys/class/hwmon/hwmon2/pwm1"),
        }
    }
    service._backend._write_hwmon_file = AsyncMock(return_value=(True, None))
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def _patch_module(monkeypatch, *, current: dict, written: list):
    monkeypatch.setattr(fan_control_module, "find_fan_ctrl_dir",
                        lambda hwmon: Path("/fake/fan_ctrl"))
    monkeypatch.setattr(fan_control_module, "read_acoustics",
                        AsyncMock(return_value=current))

    async def write(fan_ctrl, name, value, writer):
        written.append((name, value))
        return True

    monkeypatch.setattr(fan_control_module, "write_acoustic", write)


CURRENT = {
    "fan_target_temperature": ParsedNode(value=95, minimum=25, maximum=105),
    "fan_minimum_pwm": ParsedNode(value=23, minimum=23, maximum=100),
}


@pytest.mark.asyncio
async def test_captures_the_baseline_before_the_first_write(
        session_factory, monkeypatch):
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))

    await service.apply_gpu_acoustics()

    with session_factory() as db:
        config = load_acoustics_config(db)
    assert config.baseline.fan_target_temperature == 95, "Baseline nicht erfasst"
    assert written == [("fan_target_temperature", 75)]


@pytest.mark.asyncio
async def test_an_existing_baseline_is_not_overwritten(
        session_factory, monkeypatch):
    """Sonst zeichnete der zweite Start den eigenen Eingriff als Baseline auf."""
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75),
            baseline=GpuFanAcousticsValues(fan_target_temperature=88)))

    await service.apply_gpu_acoustics()

    with session_factory() as db:
        assert load_acoustics_config(db).baseline.fan_target_temperature == 88


@pytest.mark.asyncio
async def test_nothing_desired_writes_nothing(session_factory, monkeypatch):
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)

    await service.apply_gpu_acoustics()

    assert written == []


@pytest.mark.asyncio
async def test_a_follower_writes_no_hardware(session_factory, monkeypatch):
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch, primary=False)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))

    await service.apply_gpu_acoustics()

    assert written == []


@pytest.mark.asyncio
async def test_the_put_path_writes_even_on_a_follower(session_factory, monkeypatch):
    """Der Blocker: eine ausdrueckliche Nutzeraktion landet bei vier Workern
    in drei von vier Faellen auf einem Follower. Ohne diesen Test quittierte
    der Endpunkt mit 200 und aenderte an der Karte nichts."""
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch, primary=False)
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75)))

    await service.apply_acoustics()

    assert written == [("fan_target_temperature", 75)]


@pytest.mark.asyncio
async def test_start_applies_the_configuration(session_factory, monkeypatch):
    """Verdrahtung: ohne diesen Test koennte man den Aufruf in start()
    entfernen und die Suite bliebe gruen."""
    written = []
    _patch_module(monkeypatch, current=CURRENT, written=written)
    service = _service(session_factory, monkeypatch)
    service.config.fan_control_enabled = True
    monkeypatch.setattr(service, "_initialize_backend", AsyncMock())
    monkeypatch.setattr(service, "_rebuild_registry", AsyncMock())
    monkeypatch.setattr(service, "_load_fan_configs", AsyncMock())
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_minimum_pwm=40)))

    await service.start(monitoring=False)

    assert written == [("fan_minimum_pwm", 40)]
```

- [ ] **Step 2: Lauf gegen den fehlenden Code**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_apply.py --no-cov -q`
Expected: FAIL mit `AttributeError: 'FanControlService' object has no attribute 'apply_gpu_acoustics'`

- [ ] **Step 3: Importe in `fan_control.py` ergänzen**

Neben die vorhandenen `fan_*`-Importe:

```python
from app.services.power.fan_gpu_acoustics import (
    find_fan_ctrl_dir,
    read_acoustics,
    write_acoustic,
)
from app.services.power.fan_gpu_acoustics_store import (
    load_acoustics_config,
    save_acoustics_config,
)
```

- [ ] **Step 4: Die Methode implementieren**

In `FanControlService`, neben `_release_all_to_board`:

```python
    async def apply_gpu_acoustics(self) -> None:
        """Startpfad: nur der Primary wendet an.

        Beim Start wuerden sonst vier Uvicorn-Worker dieselben vier Werte
        gegeneinander setzen (#555, #559).

        Das Gate sitzt bewusst NUR hier und nicht in apply_acoustics: eine
        ausdrueckliche Nutzeraktion ueber den PUT-Endpunkt landet auf dem
        Worker, der die Anfrage bedient -- bei vier Workern in drei von vier
        Faellen auf einem Follower. Steckte das Gate weiter innen, quittierte
        der Endpunkt mit 200 und aenderte an der Karte nichts.
        """
        if not getattr(lifespan, "IS_PRIMARY_WORKER", False):
            return
        await self.apply_acoustics()

    async def apply_acoustics(self) -> None:
        """Beobachtet die Baseline und wendet die gewuenschten Werte an (#516).

        Ohne Primary-Gate -- siehe apply_gpu_acoustics. Die Baseline wird nur
        erfasst, wo sie noch fehlt: sonst zeichnete der zweite Aufruf den
        eigenen Eingriff als 'wie es vorher war' auf.
        """
        fan_ctrl = self._gpu_fan_ctrl_dir()
        if fan_ctrl is None:
            return

        with self.db_session_factory() as db:
            config = load_acoustics_config(db)

        desired = config.desired.model_dump()
        if not any(value is not None for value in desired.values()):
            return

        current = await read_acoustics(fan_ctrl)

        baseline = config.baseline.model_dump()
        changed_baseline = False
        for name, value in desired.items():
            if value is None or baseline.get(name) is not None:
                continue
            node = current.get(name)
            if node is not None:
                baseline[name] = node.value
                changed_baseline = True

        if changed_baseline:
            config.baseline = type(config.baseline)(**baseline)
            with self.db_session_factory() as db:
                save_acoustics_config(db, config)

        for name, value in desired.items():
            if value is None:
                continue
            await write_acoustic(
                fan_ctrl, name, value, self._backend._write_hwmon_file
            )

    def _gpu_fan_ctrl_dir(self):
        """Das fan_ctrl-Verzeichnis der AMD-GPU, falls die Karte es anbietet.

        Gefunden wird es ueber einen gescannten GPU-Luefter, obwohl die
        Akustikwerte der KARTE gehoeren. Hat die Karte keinen gescannten
        Luefter -- etwa weil fan1_input fehlt --, bleibt das Panel aus,
        obwohl die Schnittstelle vorhanden waere. Auf der Referenzhardware
        tritt das nicht auf; eine zweite Geraeteaufloesung dafuer zu bauen
        waere Aufwand ohne belegten Anlass (#516).
        """
        cache = getattr(self._backend, "_fan_cache", None)
        if not isinstance(cache, dict):
            return None
        for info in cache.values():
            if not isinstance(info, dict) or info.get("gpu_vendor") != "amd":
                continue
            pwm_path = info.get("pwm_path")
            if pwm_path is None:
                continue
            found = find_fan_ctrl_dir(pwm_path.parent)
            if found is not None:
                return found
        return None
```

- [ ] **Step 5: In `start()` verdrahten**

In `FanControlService.start()`, innerhalb des `async with self._lifecycle_lock:`, direkt nach `await self._load_fan_configs()`:

```python
            # Die GPU-Akustik gehoert zum Start, nicht in den Regelzyklus:
            # sie ist Konfiguration, kein Regelkreis (#516).
            try:
                await self.apply_gpu_acoustics()
            except Exception:
                logger.exception("GPU-Akustik konnte nicht angewendet werden")
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_apply.py --no-cov -q`
Expected: 6 passed

- [ ] **Step 7: Gegenprobe der Verdrahtung**

Den `await self.apply_gpu_acoustics()`-Aufruf aus `start()` vorübergehend durch `pass` ersetzen.

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_apply.py --no-cov -q`
Expected: FAIL bei `test_start_applies_the_configuration`. Danach den Aufruf wiederherstellen und erneut laufen lassen: 6 passed.

Zweite Gegenprobe für den Blocker: das Primary-Gate versuchsweise von `apply_gpu_acoustics` nach `apply_acoustics` verschieben. Erwartet: FAIL bei `test_the_put_path_writes_even_on_a_follower`. Danach zurückbauen.

- [ ] **Step 8: Fan- und Power-Suite laufen lassen**

Run: `cd backend ; python -m pytest -k "fan or power" --no-cov -q`
Expected: alle bestanden, keine neuen Fehlschläge.

- [ ] **Step 9: Committen**

```bash
git add backend/app/services/power/fan_control.py backend/tests/test_fan_gpu_acoustics_apply.py
git commit -m "feat(fans): GPU-Akustik beim Start anwenden, Baseline beobachten (#516)"
```

---

### Task 5: API — lesen, setzen, zurücksetzen

**Files:**
- Modify: `backend/app/api/routes/fans.py`
- Modify: `backend/app/schemas/gpu_fan_acoustics.py`
- Test: `backend/tests/test_fan_gpu_acoustics_api.py`

**Interfaces:**
- Consumes: alles aus Task 1–4
- Produces: `GET /api/fans/gpu-acoustics`, `PUT /api/fans/gpu-acoustics`; Antwortschema `GpuFanAcousticsStatus`

- [ ] **Step 1: Antwortschema ergänzen**

An `backend/app/schemas/gpu_fan_acoustics.py` anhängen:

```python
class GpuFanAcousticsNode(BaseModel):
    """Ein Regler: aktueller Stand, Bereich vom Treiber, verwalteter Wert."""

    current: int
    minimum: int
    maximum: int
    desired: Optional[int] = None


class GpuFanAcousticsStatus(BaseModel):
    """Kein zero_rpm-Feld: das Frontend hat die Luefterliste ohnehin und
    leitet es aus pwm_control und rpm ab. Serverseitig zu bestimmen hiesse,
    get_status() pro Poll ein zweites Mal zu durchlaufen -- und die beiden
    Anzeigen koennten auseinanderlaufen (#516)."""

    available: bool
    competing_manager: Optional[str] = None
    nodes: dict[str, GpuFanAcousticsNode] = {}
```

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

```python
"""Die Akustik-Endpunkte (#516).

Aufgerufen wird __wrapped__, also der Handler ohne slowapi-Dekorator:
geprueft wird die Verdrahtung, nicht das Rate-Limit.
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import fans as fans_routes
from app.models.base import Base
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig, GpuFanAcousticsValues
from app.services.power.fan_gpu_acoustics import ParsedNode
from app.services.power.fan_gpu_acoustics_store import (
    load_acoustics_config,
    save_acoustics_config,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def service(session_factory):
    @contextmanager
    def factory():
        with session_factory() as db:
            yield db

    svc = SimpleNamespace(db_session_factory=factory)
    svc._backend = MagicMock()
    svc._backend._write_hwmon_file = AsyncMock(return_value=(True, None))
    # apply_acoustics, nicht apply_gpu_acoustics: der PUT-Pfad darf nicht am
    # Primary-Gate haengen (#516).
    svc.apply_acoustics = AsyncMock()
    svc._gpu_fan_ctrl_dir = lambda: Path("/fake/fan_ctrl")
    return svc


CURRENT = {
    "fan_target_temperature": ParsedNode(value=95, minimum=25, maximum=105),
}


@pytest.fixture(autouse=True)
def patched_module(monkeypatch, tmp_path):
    monkeypatch.setattr(fans_routes, "read_acoustics",
                        AsyncMock(return_value=CURRENT))
    monkeypatch.setattr(fans_routes, "LACT_CONFIG_PATH", tmp_path / "lact.yaml")


async def _get(service):
    handler = fans_routes.get_gpu_acoustics.__wrapped__
    return await handler(request=SimpleNamespace(), response=SimpleNamespace(),
                         current_user=MagicMock(), service=service)


async def _put(service, values):
    handler = fans_routes.set_gpu_acoustics.__wrapped__
    return await handler(request=SimpleNamespace(), response=SimpleNamespace(),
                         body=values, current_user=MagicMock(), service=service)


@pytest.mark.asyncio
async def test_get_reports_values_and_ranges(service):
    body = await _get(service)
    assert body.available is True
    node = body.nodes["fan_target_temperature"]
    assert (node.current, node.minimum, node.maximum) == (95, 25, 105)
    assert node.desired is None


@pytest.mark.asyncio
async def test_a_card_without_the_interface_reports_unavailable(service):
    service._gpu_fan_ctrl_dir = lambda: None
    body = await _get(service)
    assert body.available is False
    assert body.nodes == {}


@pytest.mark.asyncio
async def test_a_competing_manager_is_named(service, monkeypatch, tmp_path):
    config = tmp_path / "lact.yaml"
    config.write_text("daemon:\n  pmfw_options:\n    acoustic_limit: 3000\n")
    monkeypatch.setattr(fans_routes, "LACT_CONFIG_PATH", config)

    body = await _get(service)

    assert body.competing_manager == "lact"


@pytest.mark.asyncio
async def test_put_stores_and_applies(service, session_factory):
    await _put(service, GpuFanAcousticsValues(fan_target_temperature=75))

    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature == 75
    service.apply_acoustics.assert_awaited()


@pytest.mark.asyncio
async def test_put_with_null_restores_the_baseline(
        service, session_factory, monkeypatch):
    """Der Zuruecksetzen-Knopf: alle Felder null.

    Gepatcht wird ueber monkeypatch, nicht per Zuweisung an das Modul -- eine
    Zuweisung ueberlebt den Test und leckt in die naechsten.
    """
    with session_factory() as db:
        save_acoustics_config(db, GpuFanAcousticsConfig(
            desired=GpuFanAcousticsValues(fan_target_temperature=75),
            baseline=GpuFanAcousticsValues(fan_target_temperature=95)))

    written = []

    async def recording(fan_ctrl, name, value, writer):
        written.append((name, value))
        return True

    monkeypatch.setattr(fans_routes, "write_acoustic", recording)

    await _put(service, GpuFanAcousticsValues())

    assert written == [("fan_target_temperature", 95)], "Baseline nicht zurueckgeschrieben"
    with session_factory() as db:
        assert load_acoustics_config(db).desired.fan_target_temperature is None
```

- [ ] **Step 3: Lauf gegen den fehlenden Code**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_api.py --no-cov -q`
Expected: FAIL mit `AttributeError: module ... has no attribute 'get_gpu_acoustics'`

- [ ] **Step 4: Die Endpunkte implementieren**

In `backend/app/api/routes/fans.py`, am Ende des GPU-Abschnitts:

```python
from pathlib import Path as _Path

from app.schemas.gpu_fan_acoustics import (
    GpuFanAcousticsNode,
    GpuFanAcousticsStatus,
    GpuFanAcousticsValues,
)
from app.services.power.fan_gpu_acoustics import (
    read_acoustics,
    resolve_restores,
    write_acoustic,
)
from app.services.power.fan_gpu_acoustics_store import (
    load_acoustics_config,
    save_acoustics_config,
)

# Erkennung eines zweiten Verwalters ueber die Konfigurationsdatei statt ueber
# pgrep: kein Subprozess, keine Testflakiness, und die Warnung verschwindet von
# selbst, sobald der Block entfernt wird (#516).
LACT_CONFIG_PATH = _Path("/etc/lact/config.yaml")


def _competing_manager() -> Optional[str]:
    try:
        if LACT_CONFIG_PATH.exists() and "pmfw_options" in LACT_CONFIG_PATH.read_text():
            return "lact"
    except OSError:
        pass
    return None


async def _acoustics_status(service) -> GpuFanAcousticsStatus:
    """Der Zustand, den beide Endpunkte zurueckgeben.

    Eigene Funktion statt eines Aufrufs von get_gpu_acoustics.__wrapped__ aus
    dem PUT: einen Handler aus einem Handler zu rufen umgeht die
    Abhaengigkeiten und bricht, sobald jemand einen Dekorator ergaenzt.
    """
    fan_ctrl = service._gpu_fan_ctrl_dir()
    if fan_ctrl is None:
        return GpuFanAcousticsStatus(available=False)

    current = await read_acoustics(fan_ctrl)
    with service.db_session_factory() as db:
        desired = load_acoustics_config(db).desired.model_dump()

    return GpuFanAcousticsStatus(
        available=True,
        competing_manager=_competing_manager(),
        nodes={
            name: GpuFanAcousticsNode(
                current=node.value,
                minimum=node.minimum,
                maximum=node.maximum,
                desired=desired.get(name),
            )
            for name, node in current.items()
        },
    )


@router.get("/gpu-acoustics", response_model=GpuFanAcousticsStatus)
@user_limiter.limit(get_limit("admin_operations"))
async def get_gpu_acoustics(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
    service: FanControlService = Depends(get_fan_service),
):
    """Akustikwerte der GPU samt der vom Treiber gemeldeten Bereiche.

    Fehlt die Schnittstelle -- aeltere Kernel haben gpu_od/fan_ctrl nicht --,
    kommt available=false statt eines Fehlers, damit die Oberflaeche das Panel
    ausblenden kann.
    """
    return await _acoustics_status(service)


@router.put("/gpu-acoustics", response_model=GpuFanAcousticsStatus)
@user_limiter.limit(get_limit("admin_operations"))
async def set_gpu_acoustics(
    request: Request, response: Response,
    body: GpuFanAcousticsValues,
    current_user: User = Depends(get_current_admin),
    service: FanControlService = Depends(get_fan_service),
):
    """Akustikwerte setzen.

    null fuer ein Feld heisst 'nicht mehr verwalten' und schreibt die
    beobachtete Baseline zurueck. Der Zuruecksetzen-Knopf ist damit ein PUT
    mit lauter null. Gibt es keine Baseline, passiert nichts -- es wird kein
    Herstellerstandard geraten (#534).
    """
    fan_ctrl = service._gpu_fan_ctrl_dir()
    if fan_ctrl is None:
        return GpuFanAcousticsStatus(available=False)

    with service.db_session_factory() as db:
        config = load_acoustics_config(db)

    to_restore = resolve_restores(
        previous_desired=config.desired.model_dump(),
        incoming=body.model_dump(),
        baseline=config.baseline.model_dump(),
    )

    config.desired = body
    with service.db_session_factory() as db:
        save_acoustics_config(db, config)

    for name, value in to_restore.items():
        await write_acoustic(
            fan_ctrl, name, value, service._backend._write_hwmon_file
        )

    # apply_acoustics, NICHT apply_gpu_acoustics: der Aufruf landet bei vier
    # Workern meist auf einem Follower, und das Primary-Gate gehoert nur an
    # den Startpfad (#516).
    await service.apply_acoustics()
    return await _acoustics_status(service)
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_fan_gpu_acoustics_api.py --no-cov -q`
Expected: 5 passed

- [ ] **Step 6: Ruff und die Fan-Suite**

Run: `cd backend ; python -m ruff check app/ tests/ ; python -m pytest -k "fan or power" --no-cov -q`
Expected: `All checks passed!`, alle Tests bestanden

- [ ] **Step 7: Committen**

```bash
git add backend/app/api/routes/fans.py backend/app/schemas/gpu_fan_acoustics.py backend/tests/test_fan_gpu_acoustics_api.py
git commit -m "feat(fans): Endpunkte fuer die GPU-Akustik (#516)"
```

---

### Task 6: Schreibrechte über die udev-Regel

**Files:**
- Modify: `deploy/install/templates/70-baluhost-amd-gpu.rules`
- Modify: `deploy/scripts/install-amd-gpu-permissions.sh`
- Modify: `docs/deployment/AMD_GPU_PERMISSIONS.de.md`

**Interfaces:** keine Code-Schnittstelle; liefert die Voraussetzung, dass Task 4 und 5 auf echter Hardware schreiben können.

Die Regel selbst wirkt nur auf echter Hardware. **Testbar ist aber die Doppelung:** die Dateiliste steht zweimal im Repo — in der Vorlage und im Installationsskript, das die Regel per Here-Doc erzeugt. Genau dieses Auseinanderlaufen hat auf dieser Box schon einmal zu einer Fehldiagnose geführt. Der Test dagegen ist billig.

Ergänze `Test: backend/tests/test_amd_gpu_udev_rule.py` in der Dateiliste oben.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

```python
"""Vorlage und Installationsskript fuehren dieselbe Dateiliste (#516).

Die udev-Regel existiert zweimal: als Vorlage unter deploy/install/templates
und als Here-Doc im Installationsskript. Laufen sie auseinander, traegt die
installierte Regel andere Pfade als die im Repo -- und die Diagnose beginnt
an der falschen Datei.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "deploy" / "install" / "templates" / "70-baluhost-amd-gpu.rules"
SCRIPT = REPO / "deploy" / "scripts" / "install-amd-gpu-permissions.sh"

ACOUSTIC_NODES = (
    "fan_target_temperature",
    "acoustic_limit_rpm_threshold",
    "acoustic_target_rpm_threshold",
    "fan_minimum_pwm",
)

_SYSFS = re.compile(r"/sys/class/drm/%k/device/[A-Za-z0-9_/]+")


def _sysfs_paths(text: str) -> set:
    return set(_SYSFS.findall(text))


def test_template_and_script_carry_the_same_paths():
    assert _sysfs_paths(TEMPLATE.read_text()) == _sysfs_paths(SCRIPT.read_text())


def test_the_acoustic_nodes_are_covered():
    paths = _sysfs_paths(TEMPLATE.read_text())
    for node in ACOUSTIC_NODES:
        assert any(p.endswith("gpu_od/fan_ctrl/" + node) for p in paths), node
```

- [ ] **Step 2: Lauf gegen die unveränderte Regel**

Run: `cd backend ; python -m pytest tests/test_amd_gpu_udev_rule.py --no-cov -q`
Expected: `test_the_acoustic_nodes_are_covered` schlägt fehl — die vier Knoten fehlen noch.

- [ ] **Step 3: Die udev-Regel erweitern**

In `70-baluhost-amd-gpu.rules` die Dateiliste im `RUN+=`-Ausdruck um die vier Akustik-Knoten ergänzen. Der Aufbau bleibt: `for f in <liste>; do [ -e "$f" ] && chgrp video "$f" && chmod g+w "$f"; done`.

Ergänzte Pfade:

```
/sys/class/drm/%k/device/gpu_od/fan_ctrl/fan_target_temperature
/sys/class/drm/%k/device/gpu_od/fan_ctrl/acoustic_limit_rpm_threshold
/sys/class/drm/%k/device/gpu_od/fan_ctrl/acoustic_target_rpm_threshold
/sys/class/drm/%k/device/gpu_od/fan_ctrl/fan_minimum_pwm
```

Im Kopfkommentar der Datei festhalten, warum diese Knoten dazukommen und dass `gpu_od/` erst mit der Overdrive-Initialisierung entsteht — der `[ -e ]`-Schutz fängt das ab, aber es ist der Grund für den Reboot-Test in Task 9.

- [ ] **Step 4: Dieselbe Liste im Installationsskript nachziehen**

`install-amd-gpu-permissions.sh` schreibt die Regel per Here-Doc. Die Dateiliste dort muss identisch sein — sonst weichen installierte und im Repo liegende Regel voneinander ab, was auf dieser Box schon einmal zu einer Fehldiagnose geführt hat (siehe `project_deploy_sudoers_provisioning`).

- [ ] **Step 5: Die Betriebsdokumentation ergänzen**

In `docs/deployment/AMD_GPU_PERMISSIONS.de.md` die vier neuen Knoten aufführen, mit dem Hinweis, dass die Regel erst greift, wenn `gpu_od/` existiert, und dass der Deploy dafür einmal mit `SYNC_PERMISSIONS=1` laufen muss.

- [ ] **Step 6: Test laufen lassen und committen**

Run: `cd backend ; python -m pytest tests/test_amd_gpu_udev_rule.py --no-cov -q` — Expected: 2 passed

```bash
git add backend/tests/test_amd_gpu_udev_rule.py deploy/install/templates/70-baluhost-amd-gpu.rules deploy/scripts/install-amd-gpu-permissions.sh docs/deployment/AMD_GPU_PERMISSIONS.de.md
git commit -m "chore(deploy): Schreibrechte fuer gpu_od/fan_ctrl ueber die udev-Regel (#516)"
```

---

### Task 7: Frontend — das Akustik-Panel

**Files:**
- Modify: `client/src/api/fan-control.ts`
- Modify: `client/src/components/fan-control/FirmwareFanNotice.tsx`
- Modify: `client/src/i18n/locales/de/system.json`, `client/src/i18n/locales/en/system.json`
- Test: `client/src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx`

**Interfaces:**
- Consumes: `GET`/`PUT /api/fans/gpu-acoustics` aus Task 5
- Produces: `getGpuAcoustics()`, `setGpuAcoustics(values)` im API-Client

- [ ] **Step 1: API-Client erweitern**

In `client/src/api/fan-control.ts`:

```ts
export interface GpuAcousticsNode {
  current: number;
  minimum: number;
  maximum: number;
  desired: number | null;
}

export interface GpuAcousticsStatus {
  available: boolean;
  competing_manager: string | null;
  nodes: Record<string, GpuAcousticsNode>;
}

export async function getGpuAcoustics(): Promise<GpuAcousticsStatus> {
  const { data } = await api.get<GpuAcousticsStatus>('/fans/gpu-acoustics');
  return data;
}

export async function setGpuAcoustics(
  values: Record<string, number | null>,
): Promise<GpuAcousticsStatus> {
  const { data } = await api.put<GpuAcousticsStatus>('/fans/gpu-acoustics', values);
  return data;
}
```

- [ ] **Step 2: i18n-Schlüssel ergänzen**

Unter `fanControl.gpu.acoustics` in beiden Sprachdateien, einsortiert nach `firmware`:

| Schlüssel | de | en |
|---|---|---|
| `title` | Akustik der Grafikkarte | Graphics card acoustics |
| `hint` | Diese Werte greifen erst, wenn der Lüfter läuft. Im Leerlauf hält die Karte ihn an (Zero-RPM). | These values only take effect once the fan is running. At idle the card stops it (zero RPM). |
| `competing` | LACT verwaltet dieselben Werte. Entferne den Block `pmfw_options` aus `/etc/lact/config.yaml`, sonst überschreibt es deine Einstellung. | LACT manages the same values. Remove the `pmfw_options` block from `/etc/lact/config.yaml`, otherwise it will overwrite your setting. |
| `curveWarning` | Diese Regler schalten die Karte in den Auto-Modus. Eine anderswo gesetzte Firmware-Kurve wird dabei inaktiv. | These controls switch the card to auto mode. A firmware curve set elsewhere becomes inactive. |
| `reset` | Auf den Ausgangszustand zurücksetzen | Restore the original state |
| `save` | Übernehmen | Apply |
| `fan_target_temperature` | Zieltemperatur | Target temperature |
| `acoustic_limit_rpm_threshold` | Maximale Drehzahl | Maximum fan speed |
| `acoustic_target_rpm_threshold` | Angestrebte Drehzahl | Target fan speed |
| `fan_minimum_pwm` | Minimale Leistung | Minimum duty |

- [ ] **Step 3: Den fehlschlagenden Test schreiben**

An `FirmwareFanNotice.test.tsx` anhängen:

```tsx
const STATUS = {
  available: true,
  competing_manager: null as string | null,
  nodes: {
    fan_target_temperature: { current: 95, minimum: 25, maximum: 105, desired: null },
  },
};

it('zeigt einen Regler je gemeldetem Knoten, mit den Grenzen des Treibers', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(STATUS);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);

  const slider = await screen.findByRole('slider', { name: /fan_target_temperature/ });
  expect((slider as HTMLInputElement).min).toBe('25');
  expect((slider as HTMLInputElement).max).toBe('105');
});

it('nennt Zero-RPM, damit ein wirkungsloser Regler nicht wie ein Defekt aussieht', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue(STATUS);
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);
  expect(await screen.findByTestId('gpu-acoustics-zero-rpm-hint')).toBeTruthy();
});

it('warnt vor einem zweiten Verwalter', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue({ ...STATUS, competing_manager: 'lact' });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);
  expect(await screen.findByTestId('gpu-acoustics-competing')).toBeTruthy();
});

it('blendet sich aus, wenn die Karte die Schnittstelle nicht hat', async () => {
  vi.mocked(getGpuAcoustics).mockResolvedValue({ ...STATUS, available: false, nodes: {} });
  render(<FirmwareFanNotice fanId="amdgpu-pci-0300:pwm1" />);
  await waitFor(() =>
    expect(screen.queryByRole('slider')).toBeNull());
});
```

Den Mock am Dateikopf ergänzen:

```tsx
vi.mock('../../../api/fan-control', async (importActual) => {
  const actual = await importActual<typeof import('../../../api/fan-control')>();
  return { ...actual, getGpuAcoustics: vi.fn(), setGpuAcoustics: vi.fn() };
});
```

- [ ] **Step 4: Lauf gegen den fehlenden Code**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx`
Expected: FAIL — kein Slider gefunden

- [ ] **Step 5: Das Panel implementieren**

In `FirmwareFanNotice.tsx` unterhalb des vorhandenen Erklärtexts einfügen:

```tsx
const [status, setStatus] = useState<GpuAcousticsStatus | null>(null);
const [draft, setDraft] = useState<Record<string, number>>({});

useEffect(() => {
  getGpuAcoustics()
    .then((s) => {
      setStatus(s);
      setDraft(Object.fromEntries(
        Object.entries(s.nodes).map(([k, n]) => [k, n.desired ?? n.current]),
      ));
    })
    .catch((err) => handleApiError(err, t('system:fanControl.gpu.acoustics.title')));
}, [t]);

const apply = async (values: Record<string, number | null>) => {
  try {
    const next = await setGpuAcoustics(values);
    setStatus(next);
  } catch (err) {
    handleApiError(err, t('system:fanControl.gpu.acoustics.title'));
  }
};
```

Und im JSX, nur wenn `status?.available`:

```tsx
{status?.available && (
  <div className="mt-3 space-y-3">
    <div className="text-sm font-medium text-white">
      {t('system:fanControl.gpu.acoustics.title')}
    </div>

    {Object.entries(status.nodes).map(([name, node]) => (
      <label key={name} className="block">
        <span className="text-xs text-slate-400">
          {t(`system:fanControl.gpu.acoustics.${name}`)}: {draft[name]}
        </span>
        <input
          type="range"
          aria-label={name}
          min={node.minimum}
          max={node.maximum}
          value={draft[name]}
          onChange={(e) =>
            setDraft({ ...draft, [name]: parseInt(e.target.value, 10) })}
          className="w-full"
        />
      </label>
    ))}

    <p data-testid="gpu-acoustics-zero-rpm-hint" className="text-xs text-slate-400">
      {t('system:fanControl.gpu.acoustics.hint')}
    </p>
    <p className="text-xs text-slate-400">
      {t('system:fanControl.gpu.acoustics.curveWarning')}
    </p>
    {status.competing_manager && (
      <p data-testid="gpu-acoustics-competing" className="text-xs text-amber-400">
        {t('system:fanControl.gpu.acoustics.competing')}
      </p>
    )}

    <div className="flex gap-2">
      <button
        onClick={() => apply(draft)}
        className="px-3 py-1 text-sm rounded bg-sky-500 text-white"
      >
        {t('system:fanControl.gpu.acoustics.save')}
      </button>
      <button
        onClick={() => apply(Object.fromEntries(
          Object.keys(status.nodes).map((k) => [k, null])))}
        className="px-3 py-1 text-sm rounded bg-slate-700 text-slate-200"
      >
        {t('system:fanControl.gpu.acoustics.reset')}
      </button>
    </div>
  </div>
)}
```

Bei `available: false` bleibt es beim bisherigen Erklärtext ohne Regler — die Bedingung oben erledigt das.

- [ ] **Step 6: Tests laufen lassen**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx`
Expected: alle bestanden

- [ ] **Step 7: Committen**

```bash
git add client/src/api/fan-control.ts client/src/components/fan-control/FirmwareFanNotice.tsx client/src/i18n/locales client/src/__tests__/components/fan-control/FirmwareFanNotice.test.tsx
git commit -m "feat(fans): Akustik-Panel fuer die GPU im Firmware-Hinweis (#516)"
```

---

### Task 8: Frontend — Zero-RPM als benannter Zustand auf der Lüfterkarte

**Files:**
- Modify: `client/src/components/fan-control/FanCard.tsx`
- Modify: `client/src/i18n/locales/de/system.json`, `client/src/i18n/locales/en/system.json`
- Test: `client/src/__tests__/components/fan-control/FanCard.test.tsx`

**Interfaces:**
- Consumes: `fan.pwm_control`, `fan.rpm` (vorhanden)
- Produces: nichts für spätere Tasks

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An `FanCard.test.tsx` anhängen:

```tsx
it('benennt Zero-RPM, statt eine nackte Null zu zeigen', () => {
  renderCard(fan({ pwm_control: 'firmware_managed', rpm: 0 }));
  expect(screen.getByTestId('fan-zero-rpm')).toBeTruthy();
});

it('zeigt den Hinweis nicht, wenn der Luefter laeuft', () => {
  renderCard(fan({ pwm_control: 'firmware_managed', rpm: 900 }));
  expect(screen.queryByTestId('fan-zero-rpm')).toBeNull();
});

it('zeigt ihn nicht bei einem gewoehnlichen Luefter mit 0 RPM', () => {
  // Ein stehender Gehaeuseluefter ist ein Befund, kein Zero-RPM-Modus.
  renderCard(fan({ pwm_control: 'supported', rpm: 0 }));
  expect(screen.queryByTestId('fan-zero-rpm')).toBeNull();
});
```

- [ ] **Step 2: Lauf gegen den fehlenden Code**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FanCard.test.tsx`
Expected: FAIL — `fan-zero-rpm` nicht gefunden

- [ ] **Step 3: i18n-Schlüssel ergänzen**

`fanControl.card.zeroRpm` — de: „Zero-RPM — die Karte hat den Lüfter angehalten", en: „Zero RPM — the card has stopped the fan".

- [ ] **Step 4: In `FanCard.tsx` implementieren**

Neben `isFirmwareManaged`:

```tsx
  // Abgeleitet, nicht gelesen: einen fan_zero_rpm_enable-Knoten gibt es erst
  // ab Kernel 6.13. Geschlossen wird aus "firmware-verwaltet und 0 RPM" (#516).
  const isZeroRpm = isFirmwareManaged && (fan.rpm ?? 0) === 0;
```

Im RPM-Block bei `isZeroRpm` statt der Zahl den Text mit `data-testid="fan-zero-rpm"` ausgeben.

- [ ] **Step 5: Tests laufen lassen**

Run: `cd client ; npx vitest run src/__tests__/components/fan-control/FanCard.test.tsx`
Expected: alle bestanden

- [ ] **Step 6: Volle Frontend-Prüfung**

Run: `cd client ; npx vitest run ; npx eslint . ; npm run build`
Expected: alle Tests grün, eslint 0 Fehler, Build erfolgreich

- [ ] **Step 7: Committen**

```bash
git add client/src/components/fan-control/FanCard.tsx client/src/i18n/locales client/src/__tests__/components/fan-control/FanCard.test.tsx
git commit -m "feat(fans): Zero-RPM als benannten Zustand auf der Luefterkarte zeigen (#516)"
```

---

### Task 9: Dokumentation und Abnahme auf der Hardware

**Files:**
- Modify: `docs/TECHNICAL_DOCUMENTATION.md`
- Modify: `backend/app/services/CLAUDE.md`

**Interfaces:** keine

- [ ] **Step 1: Nutzerdokumentation schreiben**

In `docs/TECHNICAL_DOCUMENTATION.md`, im Lüfter-Abschnitt nach „Handback to Board Automation on Shutdown (#534)", einen Abschnitt „GPU Fan Acoustics (#516)" mit:

- Welche vier Werte es gibt und was sie bewirken.
- **Die Kernel-Matrix**, wörtlich aus der Spec: unter 6.7 gibt es die Schnittstelle auf RDNA3 nicht; 6.7–6.12 die fünf Knoten; ab 6.13 zusätzlich die Zero-RPM-Steuerung. Das ist der Grund, warum das Panel auf manchen Installationen leer bleibt — es gehört an die Stelle, an der jemand danach sucht.
- Zero-RPM: die Werte greifen erst, wenn der Lüfter läuft.
- Dass die Regler die Karte in den Auto-Modus schalten und eine Firmware-Kurve dabei inaktiv wird.
- Dass LACT dieselben Werte verwaltet und wie man es abgibt.
- Dass die Schreibrechte über die udev-Regel kommen und der Deploy dafür einmal mit `SYNC_PERMISSIONS=1` laufen muss.

- [ ] **Step 2: `services/CLAUDE.md` nachziehen**

Unter `power/` zwei Zeilen für `fan_gpu_acoustics.py` und `fan_gpu_acoustics_store.py`, im Stil der vorhandenen Einträge.

- [ ] **Step 3: Committen**

```bash
git add docs/TECHNICAL_DOCUMENTATION.md backend/app/services/CLAUDE.md
git commit -m "docs(fans): GPU-Akustik dokumentieren, inklusive Kernel-Matrix (#516)"
```

- [ ] **Step 4: Nach dem Deploy — Rechte prüfen**

Auf der Maschine, **nach einem Reboot** (die Regel muss beim Booten greifen, nicht nur beim Ausrollen):

```
ls -l /sys/class/drm/card0/device/gpu_od/fan_ctrl/
```

Erwartet: `root video` mit `-rw-rw-r--` auf den vier Akustik-Knoten.

Steht dort weiter `root root`, ist das der in der Spec benannte Fall: udev feuert, bevor `gpu_od/` existiert. Dann **keine** Ausweitung der sudoers-Regel, sondern ein systemd-Oneshot nach `multi-user.target` — als eigene Aufgabe, nicht in diesem Plan.

- [ ] **Step 5: Abnahme unter Last**

Zero-RPM macht den Leerlauf aussagelos. Ein Spiel starten, bis der Lüfter dreht — Display an und Steam-Client offen reichen nicht, das bringt die Karte nur auf 52 °C Junction bei stehendem Lüfter.

Messreihe, jeweils Junction (`hwmon2/temp2_input`), Drehzahl (`fan1_input`) und Duty (`pwm1`):

| | junction | fan1_input | pwm1 |
|---|---|---|---|
| Last, unverwaltet | | | |
| Last, Zieltemperatur 75 | | | |
| nach „Zurücksetzen" | | | |

Erwartet zwischen der ersten und zweiten Zeile: **Drehzahl steigt, Junction sinkt.**

Bleibt beides gleich, ist der Regler auch unter Last wirkungslos. Das ist dann das Ergebnis und gehört so gemeldet — nicht als Feature ausgeliefert.

- [ ] **Step 6: Persistenz prüfen**

- Backend neu starten → die gesetzten Werte stehen wieder auf der Karte.
- Reboot → dasselbe.
- „Zurücksetzen" → die Baseline steht wieder da, `desired` ist leer.
