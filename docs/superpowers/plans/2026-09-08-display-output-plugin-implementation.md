# Display-Output-Plugin — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein bundled Plugin `display_output`, das die KWin-Ausgänge von BaluNode
enumeriert und Auswahl plus Video-Modus über einen einzigen `kscreen-doctor`-Aufruf
setzt, bedient über ein Popover in der Topbar.

**Architecture:** Layout und Schichtung spiegeln `audio_control` Datei für Datei —
ein Modul kapselt das externe Werkzeug (`kscreen.py`), ein Protocol trennt Dev- von
Linux-Backend, ein Service-Singleton hält die Auswahl, der Router hängt im Plugin.
Modi werden über die **lebende** Mode-ID aus derselben Enumeration adressiert und
beim Anwenden gegen den mitgeschickten Namen gegengeprüft; die UI ist eine
Core-Komponente, die nur prüft, ob das Plugin aktiv ist.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 + Alembic,
pytest; React 18 + TypeScript, Tailwind, i18next, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-08-display-output-plugin-design.md`
**Vorgänger-Diagnose:** `docs/superpowers/plans/2026-09-08-display-output-control.md`
**Issue:** #590

## Global Constraints

- **Kein `from __future__ import annotations` in `backend/app/plugins/installed/display_output/__init__.py`.** In allen anderen Modulen des Plugins gehört es an den Anfang. Grund: zusammen mit Pydantic v2 und FastAPIs Body-Erkennung durch den `@user_limiter.limit`-Wrapper werden aufgeschobene Annotationen zu ForwardRefs, die FastAPI nicht mehr auflöst — der Request-Body würde als Query-Parameter gelesen und jedes `POST` antwortete 422.
- **`get_ui_manifest()` muss überschrieben werden** und `PluginUIManifest(enabled=True)` liefern. Ohne Override ist das Plugin im Frontend dauerhaft „aus", ohne Fehler und ohne Logzeile.
- **Kein `shell=True`, ausschließlich Listen-Argumente, immer mit Timeout.** `KSCREEN_TIMEOUT_SECONDS = 10`.
- **`subprocess.run` immer in `asyncio.to_thread`.** Ein blockierender Aufruf auf dem Event-Loop legt den ganzen Worker lahm.
- **stdout/stderr von `kscreen-doctor` erreichen nie eine Client-Antwort.** Sie tragen EDID-Namen und Pfade; sie werden geloggt, die Antwort trägt eine kuratierte Meldung.
- **Kein Wert aus dem Request wird zu einem argv-Element, ohne vorher in der Live-Enumeration gestanden zu haben.**
- **Modi werden über `id` adressiert, niemals über `name`.** `libkscreen`'s `findMode()` bildet den Namen mit `qRound(refreshRate)`; 119,88 und 120,000 heißen beide `3840x2160@120`, und der erste Treffer gewinnt.
- **Die neue Alembic-Migration setzt auf `down_revision = "e2f81c4a7b93"`** — das ist der einzige echte Head (Stand 2026-09-08, aus den Dateien berechnet). **Nicht** den Head der lokalen Dev-DB verwenden.
- **Neue Rate-Limit-Kategorie:** `"display_output": "60/minute"`.
- **Alle Routen** tragen `Depends(require_power_manage_displays)` **und** `@user_limiter.limit(get_limit("display_output"))` — die lesende eingeschlossen.
- Backend-Docstrings auf Deutsch ohne Umlaute (`ue`, `ae`, `oe`, `ss`), wie in `audio_control`. Kommentare im Frontend dürfen Umlaute tragen.
- **Die volle Backend-Suite läuft auf Windows nicht durch** (bekannter Hänger). Führe nur die in den Schritten genannten Testdateien aus; die volle Suite ist Sache der CI.

---

## Dateistruktur

| Pfad | Verantwortung |
|---|---|
| `backend/app/plugins/installed/display_output/__init__.py` | Plugin-Klasse, Router, Audit, Fehlerabbildung |
| `backend/app/plugins/installed/display_output/models.py` | Pydantic-Modelle = API-Vertrag |
| `backend/app/plugins/installed/display_output/kscreen.py` | Einziger Ort, der `kscreen-doctor` kennt: Parser, Runner, argv-Bau |
| `backend/app/plugins/installed/display_output/backend.py` | Protocol, `DevDisplayBackend`, `KWinDisplayBackend` |
| `backend/app/plugins/installed/display_output/service.py` | `DisplayService`, Validierung, Singleton |
| `backend/app/plugins/installed/display_output/CLAUDE.md` | Invarianten und Fallen dieses Plugins |
| `backend/app/services/power/gpu/display_detector.py` | **Änderung:** `get_connector_states()` ergänzen |
| `backend/alembic/versions/<neu>_add_can_manage_displays_permission.py` | Migration |
| `client/src/api/displayOutput.ts` | Typisierter API-Client |
| `client/src/components/topbar/DisplayMenu.tsx` | Popover |
| `client/src/i18n/locales/{de,en}/display.json` | Eigener Namensraum |

---

## Task 1: Fixture, Modelle und der Mode-Parser

**Files:**
- Create: `backend/tests/plugins/fixtures/kscreen_balunode.json`
- Create: `backend/app/plugins/installed/display_output/__init__.py` (vorerst leer)
- Create: `backend/app/plugins/installed/display_output/models.py`
- Create: `backend/app/plugins/installed/display_output/kscreen.py`
- Test: `backend/tests/plugins/test_display_output_parser.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
```python
# models.py
class DisplayMode(BaseModel):
    id: str
    name: str
    width: int
    height: int
    refresh_rate: float

class DisplayOutput(BaseModel):
    name: str
    connected: bool
    selected: bool
    lit: Optional[bool] = None
    current_mode_id: Optional[str] = None
    preferred_mode_id: Optional[str] = None
    scale: float = 1.0
    priority: int = 0
    modes: List[DisplayMode] = Field(default_factory=list)

class DisplayLayout(BaseModel):
    outputs: List[DisplayOutput] = Field(default_factory=list)
    displays_powered: bool = False
    available: bool = True
    detail: Optional[str] = None

class DisplayOutputRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    selected: bool
    mode_id: Optional[str] = Field(default=None, max_length=32)
    mode_name: Optional[str] = Field(default=None, max_length=64)

class DisplayApplyRequest(BaseModel):
    outputs: List[DisplayOutputRequest] = Field(..., min_length=1)

# kscreen.py
def parse_modes(raw_modes: list) -> list[DisplayMode]
def parse_outputs(payload: object) -> list[DisplayOutput]
```

- [ ] **Step 1: Fixture bereitstellen**

Die Fixture ist ein **gemessener** Mitschnitt von BaluNode, kein erfundener
Payload. Sie wird dort erzeugt mit:

```
XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 kscreen-doctor -j
```

Die Ausgabe **unverändert** (alle Felder, alle Modi) nach
`backend/tests/plugins/fixtures/kscreen_balunode.json` speichern. Der Mitschnitt
vom 2026-09-08 liegt im Gesprächsverlauf dieser Sitzung; ist er dort nicht mehr
greifbar, den Befehl erneut ausführen lassen.

Die Fixture muss diese Eigenschaften erfüllen — sie sind die Grundlage aller
folgenden Zusicherungen:

| Eigenschaft | Wert |
|---|---|
| Ausgänge | genau 2: `HDMI-A-1`, `DP-3` |
| `HDMI-A-1` | `enabled: false`, `currentModeId: "1"`, 55 Modi, 45 verschiedene Namen |
| `DP-3` | `enabled: true`, `currentModeId: "57"`, `scale: 2.5`, 58 Modi |
| Namenskollision | `DP-3` id 57 (`refreshRate` 120) und id 58 (119.87999725341797), beide `"3840x2160@120"` |
| Exakte Dublette | `HDMI-A-1` id 9 und id 10, beide `1920x1080`, `refreshRate` 60 |
| Feldlücke | `DP-3` hat **kein** `vrrPolicy`, `HDMI-A-1` hat es |
| Nicht enthalten | `DP-1`, `DP-2` — `kscreen-doctor` listet unverbundene Ausgänge nicht |

Zusätzlich anlegen: `backend/tests/plugins/fixtures/__init__.py` ist **nicht**
nötig (reines Datenverzeichnis).

- [ ] **Step 2: Write the failing test**

Create `backend/tests/plugins/test_display_output_parser.py`:

```python
"""Parser-Tests gegen den gemessenen kscreen-doctor-Mitschnitt von BaluNode."""
import json
from pathlib import Path

import pytest

from app.plugins.installed.display_output.kscreen import parse_modes, parse_outputs

FIXTURE = Path(__file__).parent / "fixtures" / "kscreen_balunode.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def outputs(payload):
    return parse_outputs(payload)


class TestOutputs:
    def test_lists_both_connected_outputs(self, outputs):
        assert [o.name for o in outputs] == ["HDMI-A-1", "DP-3"]

    def test_selected_mirrors_kwin_enabled(self, outputs):
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-3"].selected is True
        assert by_name["HDMI-A-1"].selected is False

    def test_lit_is_unknown_until_the_drm_layer_is_merged(self, outputs):
        # Der Parser kennt sysfs nicht. None heisst "nicht beantwortet",
        # nicht "aus" - siehe Spec 5.
        assert all(o.lit is None for o in outputs)

    def test_current_and_preferred_are_mode_ids(self, outputs):
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-3"].current_mode_id == "57"
        assert by_name["DP-3"].preferred_mode_id == "56"
        assert by_name["HDMI-A-1"].current_mode_id == "1"

    def test_scale_is_read(self, outputs):
        by_name = {o.name: o for o in outputs}
        assert by_name["DP-3"].scale == 2.5

    def test_a_missing_optional_field_does_not_break_the_parser(self, outputs):
        # DP-3 traegt kein vrrPolicy. Ein direkter Indexzugriff kippte hier.
        assert len(outputs) == 2


class TestModes:
    def test_exact_duplicates_collapse_and_distinct_rates_survive(self, outputs):
        hdmi = next(o for o in outputs if o.name == "HDMI-A-1")
        # 55 Roheintraege, fuenf exakte Dubletten fallen weg.
        assert len(hdmi.modes) == 50

    def test_the_collapsed_duplicate_keeps_the_lower_id(self, outputs):
        hdmi = next(o for o in outputs if o.name == "HDMI-A-1")
        fullhd_60 = [
            m for m in hdmi.modes
            if m.width == 1920 and m.height == 1080 and round(m.refresh_rate, 2) == 60.0
        ]
        assert len(fullhd_60) == 1
        assert fullhd_60[0].id == "9"

    def test_the_120hz_pair_is_kept_apart(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        uhd = [m for m in dp3.modes if m.width == 3840 and m.height == 2160]
        rates = sorted(round(m.refresh_rate, 2) for m in uhd if round(m.refresh_rate, 2) >= 119)
        assert rates == [119.88, 120.0]

    def test_both_of_the_pair_carry_the_same_ambiguous_name(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        pair = {m.id: m.name for m in dp3.modes if m.id in ("57", "58")}
        assert pair == {"57": "3840x2160@120", "58": "3840x2160@120"}

    def test_modes_are_sorted_by_area_then_refresh_descending(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        keys = [(-(m.width * m.height), -m.refresh_rate) for m in dp3.modes]
        assert keys == sorted(keys)

    def test_the_refresh_rate_is_not_rounded(self, outputs):
        dp3 = next(o for o in outputs if o.name == "DP-3")
        mode58 = next(m for m in dp3.modes if m.id == "58")
        assert mode58.refresh_rate == pytest.approx(119.87999725, rel=1e-9)


class TestParseModesInIsolation:
    def test_a_mode_without_size_is_skipped(self):
        modes = parse_modes([
            {"id": "1", "name": "1920x1080@60", "refreshRate": 60,
             "size": {"width": 1920, "height": 1080}},
            {"id": "2", "name": "broken"},
        ])
        assert [m.id for m in modes] == ["1"]

    def test_an_empty_list_yields_no_modes(self):
        assert parse_modes([]) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_parser.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.installed.display_output'`

- [ ] **Step 4: Paketdatei und Modelle anlegen**

Create `backend/app/plugins/installed/display_output/__init__.py` mit vorerst nur
einem Docstring (der Router folgt in Task 7):

```python
"""Displaysteuerung — bundled Plugin.

Enumeriert die KWin-Ausgaenge und setzt Auswahl und Video-Modus ueber
kscreen-doctor. Laeuft als bundled Plugin im Host-Prozess und damit unter
derselben UID wie die Desktop-Session; ein Sandbox-Plugin kaeme nicht an den
Wayland-Socket.
"""
```

Create `backend/app/plugins/installed/display_output/models.py`:

```python
"""Pydantic-Modelle der Displaysteuerung.

Die Feldnamen sind zugleich der API-Vertrag zum Frontend.

``selected`` und ``lit`` heissen absichtlich nicht beide ``enabled``: KWin und
DRM meinen mit diesem Wort verschiedene Dinge (die Ausgangswahl gegen "es
werden wirklich Pixel getrieben"), und die Namensgleichheit ist die Ursache
der Verwirrung, die dieses Feature aufloesen soll.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class DisplayMode(BaseModel):
    """Ein waehlbarer Video-Modus eines Ausgangs."""

    id: str = Field(..., description="Lebende KWin-Mode-ID; nur innerhalb dieses Vorgangs gueltig")
    name: str = Field(..., description="'3840x2160@120' — NICHT eindeutig, dient nur der Gegenpruefung")
    width: int
    height: int
    refresh_rate: float = Field(..., description="Ungerundet, z. B. 119.87999725341797")


class DisplayOutput(BaseModel):
    """Ein von KWin gemeldeter Ausgang."""

    name: str = Field(..., description="Connector-Name, z. B. 'DP-3'")
    connected: bool
    selected: bool = Field(..., description="KWin-Ebene: ist dieser Ausgang gewaehlt?")
    lit: Optional[bool] = Field(
        default=None,
        description="DRM-Ebene: werden Pixel getrieben? None = nicht zuordenbar",
    )
    current_mode_id: Optional[str] = None
    preferred_mode_id: Optional[str] = None
    scale: float = Field(default=1.0, description="Nur Anzeige; in v1 nicht setzbar")
    priority: int = 0
    modes: List[DisplayMode] = Field(default_factory=list)


class DisplayLayout(BaseModel):
    """Gesamtzustand, wie ihn GET /state liefert."""

    outputs: List[DisplayOutput] = Field(default_factory=list)
    displays_powered: bool = Field(
        default=False, description="Globaler DPMS-Zustand: leuchtet mindestens ein Ausgang?"
    )
    available: bool = Field(default=True, description="False, wenn KWin nicht erreichbar ist")
    detail: Optional[str] = Field(default=None, description="Kurzer Hinweis fuer die UI")


class DisplayOutputRequest(BaseModel):
    """Gewuenschter Zustand eines Ausgangs."""

    name: str = Field(..., min_length=1, max_length=64)
    selected: bool
    mode_id: Optional[str] = Field(default=None, max_length=32)
    mode_name: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Pflicht, sobald mode_id gesetzt ist — die Gegenprobe zur ID",
    )


class DisplayApplyRequest(BaseModel):
    """Rumpf von POST /apply."""

    outputs: List[DisplayOutputRequest] = Field(..., min_length=1)
```

- [ ] **Step 5: Parser schreiben**

Create `backend/app/plugins/installed/display_output/kscreen.py`:

```python
"""Der einzige Ort, der weiss, dass es kscreen-doctor gibt.

Kapselt Aufruf, Auswertung und Argumentbau. Ein spaeterer Wechsel auf die
KScreen-D-Bus-Schnittstelle beruehrt nur diese Datei.

**Modi werden ueber ihre ID adressiert, niemals ueber den Namen.** libkscreen
bildet den Namen in ``findMode()`` mit ``qRound(refreshRate)``, weshalb 119,88
und 120,000 beide ``3840x2160@120`` heissen; die Funktion nimmt den ersten
Treffer und bricht ab. Eine Adressierung ueber den Namen setzt also je nach
Listenreihenfolge einen anderen Modus — ohne Fehlermeldung.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.plugins.installed.display_output.models import DisplayMode, DisplayOutput

logger = logging.getLogger(__name__)

# Auf wie viele Nachkommastellen zwei Bildwiederholraten als gleich gelten.
# Feiner zu unterscheiden hiesse, Gleitkomma-Rauschen zu Modi zu erklaeren.
_RATE_PRECISION = 3


def parse_modes(raw_modes: object) -> List[DisplayMode]:
    """Wandelt die Modenliste eines Ausgangs in eine anzeigbare Liste.

    Drei Schritte, alle drei aus gemessenen Daten begruendet:

    1. **Exakte Dubletten zusammenfassen** (gleiche Breite, Hoehe und
       Bildwiederholrate). Auf BaluNode traegt HDMI-A-1 fuenf solcher Paare;
       sie unterscheiden sich nur in DRM-Timing-Flags (CEA gegen DMT), was
       sich einem Menschen nicht sinnvoll anzeigen laesst. Die kleinere ID
       gewinnt.
    2. **Absteigend nach Flaeche, dann nach Rate sortieren.** kscreen-doctor
       liefert lexikografisch nach ID-String ("1", "10", "11", ..., "2", "20").
    3. Die Rate bleibt **ungerundet** — ``119.88`` und ``120.00`` sind der
       einzige Unterschied, an dem ein Mensch die beiden 4K-Modi von DP-3
       auseinanderhaelt.

    Args:
        raw_modes: Die ``modes``-Liste eines Ausgangs aus ``kscreen-doctor -j``.

    Returns:
        Sortierte, entdoppelte Modi. Unbrauchbare Eintraege werden
        uebersprungen, nicht als Fehler gemeldet — ein defekter Modus darf
        die Enumeration nicht scheitern lassen.
    """
    if not isinstance(raw_modes, list):
        return []

    seen: dict[tuple, DisplayMode] = {}
    for raw in raw_modes:
        if not isinstance(raw, dict):
            continue
        size = raw.get("size")
        mode_id = raw.get("id")
        if not isinstance(size, dict) or mode_id is None:
            logger.debug("Modus ohne Groesse oder ID uebersprungen: %r", raw)
            continue
        width = size.get("width")
        height = size.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            continue
        try:
            rate = float(raw.get("refreshRate", 0.0))
        except (TypeError, ValueError):
            continue

        mode = DisplayMode(
            id=str(mode_id),
            name=str(raw.get("name", "")),
            width=width,
            height=height,
            refresh_rate=rate,
        )
        key = (width, height, round(rate, _RATE_PRECISION))
        existing = seen.get(key)
        # Kleinere ID gewinnt. IDs sind Zeichenketten, deshalb numerisch
        # vergleichen, wo moeglich - sonst waere "10" kleiner als "9".
        if existing is None or _id_sort_key(mode.id) < _id_sort_key(existing.id):
            seen[key] = mode

    return sorted(seen.values(), key=lambda m: (-(m.width * m.height), -m.refresh_rate, m.id))


def _id_sort_key(mode_id: str) -> tuple:
    """Sortierschluessel, der numerische IDs numerisch ordnet."""
    return (0, int(mode_id)) if mode_id.isdigit() else (1, mode_id)


def parse_outputs(payload: object) -> List[DisplayOutput]:
    """Liest die Ausgangsliste aus der JSON-Struktur von ``kscreen-doctor -j``.

    ``lit`` bleibt hier ``None``: dieses Modul kennt sysfs nicht. Die
    DRM-Ebene ergaenzt das Backend (Task 4).

    Jeder Feldzugriff laeuft ueber ``.get()``. Die Felder sind nicht bei jedem
    Ausgang vorhanden — auf BaluNode traegt HDMI-A-1 ein ``vrrPolicy``, DP-3
    nicht.
    """
    if not isinstance(payload, dict):
        return []
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list):
        return []

    outputs: List[DisplayOutput] = []
    for raw in raw_outputs:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            continue
        preferred = raw.get("preferredModes")
        preferred_id: Optional[str] = None
        if isinstance(preferred, list) and preferred:
            preferred_id = str(preferred[0])
        current = raw.get("currentModeId")

        outputs.append(
            DisplayOutput(
                name=name,
                connected=bool(raw.get("connected", False)),
                selected=bool(raw.get("enabled", False)),
                lit=None,
                current_mode_id=str(current) if current is not None else None,
                preferred_mode_id=preferred_id,
                scale=float(raw.get("scale", 1.0) or 1.0),
                priority=int(raw.get("priority", 0) or 0),
                modes=parse_modes(raw.get("modes")),
            )
        )
    return outputs
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_parser.py -q --no-cov`
Expected: PASS (alle Tests)

Schlägt `test_exact_duplicates_collapse_and_distinct_rates_survive` mit einer
anderen Zahl als 50 fehl, **zuerst die Fixture prüfen** — die Zahl stammt aus
der Messung, nicht aus einer Schätzung. Weicht die Fixture ab, ist sie die
Wahrheit und die Zahl im Test wird korrigiert; das ist dann eine bewusste
Änderung, kein Anpassen bis grün.

- [ ] **Step 7: Lint und Commit**

```bash
cd backend && python -m ruff check app/plugins/installed/display_output tests/plugins/test_display_output_parser.py
git add backend/app/plugins/installed/display_output backend/tests/plugins/test_display_output_parser.py backend/tests/plugins/fixtures/kscreen_balunode.json
git commit -m "feat(display-output): Modelle und kscreen-doctor-Parser mit Modus-Entdopplung"
```

---

## Task 2: Runner und Argumentbau

**Files:**
- Modify: `backend/app/plugins/installed/display_output/kscreen.py` (anfügen)
- Test: `backend/tests/plugins/test_display_output_kscreen.py`

**Interfaces:**
- Consumes: `DisplayOutput` aus Task 1.
- Produces:
```python
KSCREEN_TIMEOUT_SECONDS: int = 10
KSCREEN_BINARY: str = "kscreen-doctor"
def run_kscreen(args: list[str]) -> tuple[bool, str]
def run_kscreen_json() -> Optional[object]
def build_apply_args(
    wanted: dict[str, tuple[bool, Optional[str]]],
    live_outputs: list[DisplayOutput],
) -> list[str]
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_display_output_kscreen.py`:

```python
"""Runner und Argumentbau: kein Wert ohne Enumeration, ein Aufruf, kein Hang."""
import subprocess
from unittest.mock import patch

from app.plugins.installed.display_output import kscreen
from app.plugins.installed.display_output.models import DisplayMode, DisplayOutput


def _output(name: str, selected: bool, mode_ids: list[str]) -> DisplayOutput:
    return DisplayOutput(
        name=name,
        connected=True,
        selected=selected,
        modes=[
            DisplayMode(id=i, name=f"m{i}", width=1920, height=1080, refresh_rate=60.0)
            for i in mode_ids
        ],
    )


LIVE = [_output("HDMI-A-1", False, ["1", "9"]), _output("DP-3", True, ["57", "58"])]


class TestBuildApplyArgs:
    def test_one_call_carries_every_change(self):
        args = kscreen.build_apply_args(
            {"DP-3": (True, "57"), "HDMI-A-1": (False, None)}, LIVE
        )
        assert args == [
            "kscreen-doctor",
            "output.HDMI-A-1.disable",
            "output.DP-3.enable",
            "output.DP-3.mode.57",
        ]

    def test_order_follows_the_enumeration_not_the_request(self):
        # Deterministisch, damit der Vektor pruefbar ist - und unabhaengig
        # davon, in welcher Reihenfolge der Client seine Ausgaenge schickt.
        a = kscreen.build_apply_args({"DP-3": (True, None), "HDMI-A-1": (True, None)}, LIVE)
        b = kscreen.build_apply_args({"HDMI-A-1": (True, None), "DP-3": (True, None)}, LIVE)
        assert a == b
        assert a.index("output.HDMI-A-1.enable") < a.index("output.DP-3.enable")

    def test_an_output_the_request_omits_is_left_alone(self):
        args = kscreen.build_apply_args({"DP-3": (True, "58")}, LIVE)
        assert not any("HDMI-A-1" in a for a in args)

    def test_a_mode_on_a_deselected_output_is_ignored(self):
        # Siehe Spec 7: KWin behaelt die Modus-Wahl eines abgewaehlten
        # Ausgangs ohnehin; ein Fehler waere Schikane gegen eine UI, die
        # schlicht den angezeigten Zustand zurueckschickt.
        args = kscreen.build_apply_args({"HDMI-A-1": (False, "9")}, LIVE)
        assert args == ["kscreen-doctor", "output.HDMI-A-1.disable"]

    def test_mode_is_addressed_by_id_never_by_name(self):
        args = kscreen.build_apply_args({"DP-3": (True, "58")}, LIVE)
        assert "output.DP-3.mode.58" in args
        assert not any("@" in a for a in args)


class TestRunKscreen:
    def test_a_missing_binary_is_reported_not_raised(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, message = kscreen.run_kscreen(["--dpms", "on"])
        assert ok is False
        assert "kscreen-doctor" in message

    def test_a_timeout_is_reported_not_raised(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 10)):
            ok, message = kscreen.run_kscreen(["-j"])
        assert ok is False

    def test_a_nonzero_exit_is_a_failure(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with patch("subprocess.run", return_value=completed):
            ok, message = kscreen.run_kscreen(["-j"])
        assert ok is False
        assert message == "boom"

    def test_the_call_always_carries_a_timeout(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=completed) as run:
            kscreen.run_kscreen(["-j"])
        assert run.call_args.kwargs["timeout"] == kscreen.KSCREEN_TIMEOUT_SECONDS
        assert run.call_args.kwargs.get("shell") in (None, False)


class TestRunKscreenJson:
    def test_invalid_json_yields_none_instead_of_raising(self):
        with patch.object(kscreen, "run_kscreen", return_value=(True, "not json")):
            assert kscreen.run_kscreen_json() is None

    def test_a_failed_call_yields_none(self):
        with patch.object(kscreen, "run_kscreen", return_value=(False, "boom")):
            assert kscreen.run_kscreen_json() is None

    def test_valid_json_is_parsed(self):
        with patch.object(kscreen, "run_kscreen", return_value=(True, '{"outputs": []}')):
            assert kscreen.run_kscreen_json() == {"outputs": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_kscreen.py -q --no-cov`
Expected: FAIL — `AttributeError: module 'app.plugins.installed.display_output.kscreen' has no attribute 'build_apply_args'`

- [ ] **Step 3: Runner und Argumentbau anfügen**

An `backend/app/plugins/installed/display_output/kscreen.py` anhängen (die
Importe oben um `import json` und `import subprocess` sowie
`from app.services.power.session_env import wayland_session_env` ergänzen):

```python
# kscreen-doctor darf niemals haengen bleiben und dabei einen Worker blockieren.
KSCREEN_TIMEOUT_SECONDS = 10
KSCREEN_BINARY = "kscreen-doctor"


def run_kscreen(args: List[str]) -> tuple[bool, str]:
    """Fuehrt kscreen-doctor mit Listen-Argumenten aus.

    Args:
        args: Argumente ohne den Programmnamen, etwa ``["-j"]``.

    Returns:
        (Erfolg, Ausgabe bzw. Fehlertext). Die Ausgabe ist roh und enthaelt
        EDID-Namen und Pfade. Sie ist fuer Log und Weiterverarbeitung gedacht —
        Aufrufer duerfen sie **nicht** in eine Client-Antwort uebernehmen.
    """
    try:
        completed = subprocess.run(
            [KSCREEN_BINARY, *args],
            capture_output=True,
            text=True,
            timeout=KSCREEN_TIMEOUT_SECONDS,
            env=wayland_session_env(),
        )
    except FileNotFoundError:
        logger.warning("kscreen-doctor ist nicht installiert")
        return False, "kscreen-doctor nicht gefunden"
    except subprocess.TimeoutExpired:
        logger.warning("kscreen-doctor-Zeitueberschreitung: %s", args)
        return False, "Zeitueberschreitung"
    except OSError as exc:
        logger.warning("kscreen-doctor-Aufruf fehlgeschlagen: %s", exc)
        return False, "Aufruf fehlgeschlagen"

    if completed.returncode != 0:
        logger.warning(
            "kscreen-doctor %s endete mit %s: %s",
            args, completed.returncode, completed.stderr.strip(),
        )
        return False, completed.stderr.strip() or "kscreen-doctor-Fehler"
    return True, completed.stdout.strip()


def run_kscreen_json() -> Optional[object]:
    """Liest ``kscreen-doctor -j`` und gibt die geparste Struktur zurueck.

    Returns:
        Die geparste JSON-Struktur, oder None bei Fehler oder ungueltigem JSON.
    """
    ok, output = run_kscreen(["-j"])
    if not ok:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        logger.warning("kscreen-doctor lieferte ungueltiges JSON")
        return None


def build_apply_args(
    wanted: dict,
    live_outputs: List[DisplayOutput],
) -> List[str]:
    """Baut den vollstaendigen Argumentvektor fuer **einen** Aufruf.

    kscreen-doctor wendet alle Argumente eines Aufrufs gemeinsam an. Genau ein
    Unterprozess heisst deshalb: kein Teilzustand, wenn etwas schiefgeht.

    Die Reihenfolge folgt der **Enumeration**, nicht dem Request. Das macht den
    Vektor deterministisch und damit pruefbar, und es nimmt dem Client jeden
    Einfluss auf die Abarbeitungsreihenfolge.

    Args:
        wanted: Abbildung Ausgangsname -> (selected, mode_id oder None). Nur
            Ausgaenge, die der Aufrufer bereits validiert hat.
        live_outputs: Die aktuelle Enumeration; bestimmt Reihenfolge und
            Zugehoerigkeit.

    Returns:
        Der vollstaendige argv inklusive Programmname.
    """
    args: List[str] = [KSCREEN_BINARY]
    for output in live_outputs:
        if output.name not in wanted:
            continue
        selected, mode_id = wanted[output.name]
        if not selected:
            args.append(f"output.{output.name}.disable")
            continue
        args.append(f"output.{output.name}.enable")
        if mode_id:
            args.append(f"output.{output.name}.mode.{mode_id}")
    return args
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_kscreen.py -q --no-cov`
Expected: PASS

- [ ] **Step 5: Lint und Commit**

```bash
cd backend && python -m ruff check app/plugins/installed/display_output tests/plugins/test_display_output_kscreen.py
git add backend/app/plugins/installed/display_output/kscreen.py backend/tests/plugins/test_display_output_kscreen.py
git commit -m "feat(display-output): kscreen-doctor-Runner und atomarer Argumentbau"
```

---

## Task 3: DRM-Connector-Zustände im Core

**Files:**
- Modify: `backend/app/services/power/gpu/display_detector.py`
- Test: `backend/tests/test_display_detector_connector_states.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
```python
def get_connector_states_sync(sysfs_root: Path = Path("/")) -> dict[str, bool]
async def get_connector_states(sysfs_root: Path = Path("/")) -> dict[str, bool]
```
Schlüssel ist der KWin-Name (`DP-3`), nicht der sysfs-Name (`card0-DP-3`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_display_detector_connector_states.py`:

```python
"""Pro-Connector-Zustaende aus sysfs, mit KWin-kompatiblen Namen."""
import pytest

from app.services.power.gpu.display_detector import (
    get_connector_states,
    get_connector_states_sync,
)


def _connector(root, name: str, status: str, enabled: str) -> None:
    d = root / "sys" / "class" / "drm" / name
    d.mkdir(parents=True)
    (d / "status").write_text(status)
    (d / "enabled").write_text(enabled)


class TestConnectorStates:
    def test_strips_the_card_prefix_to_match_kwin_names(self, tmp_path):
        _connector(tmp_path, "card0-DP-3", "connected", "enabled")
        assert get_connector_states_sync(tmp_path) == {"DP-3": True}

    def test_a_dark_connector_is_false_not_absent(self, tmp_path):
        # DPMS-off: verbunden, aber es werden keine Pixel getrieben.
        _connector(tmp_path, "card0-DP-3", "connected", "disabled")
        assert get_connector_states_sync(tmp_path) == {"DP-3": False}

    def test_a_disconnected_connector_is_reported_as_dark(self, tmp_path):
        _connector(tmp_path, "card0-DP-1", "disconnected", "disabled")
        assert get_connector_states_sync(tmp_path) == {"DP-1": False}

    def test_a_writeback_connector_is_never_lit(self, tmp_path):
        # Gemessen auf BaluNode: status=unknown, enabled=disabled. Ein
        # Writeback-Connector ist kein Bildschirm.
        _connector(tmp_path, "card0-Writeback-1", "unknown", "disabled")
        assert get_connector_states_sync(tmp_path) == {"Writeback-1": False}

    def test_entries_that_are_not_connectors_are_skipped(self, tmp_path):
        drm = tmp_path / "sys" / "class" / "drm" / "renderD128"
        drm.mkdir(parents=True)
        _connector(tmp_path, "card0-DP-3", "connected", "enabled")
        assert list(get_connector_states_sync(tmp_path)) == ["DP-3"]

    def test_a_missing_drm_directory_yields_an_empty_map(self, tmp_path):
        assert get_connector_states_sync(tmp_path) == {}

    @pytest.mark.asyncio
    async def test_the_async_variant_agrees_with_the_sync_one(self, tmp_path):
        _connector(tmp_path, "card0-HDMI-A-1", "connected", "enabled")
        assert await get_connector_states(tmp_path) == get_connector_states_sync(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/test_display_detector_connector_states.py -q --no-cov`
Expected: FAIL — `ImportError: cannot import name 'get_connector_states'`

- [ ] **Step 3: Die beiden Funktionen ergänzen**

An `backend/app/services/power/gpu/display_detector.py` anhängen:

```python
def _states_sync(sysfs_root: Path) -> dict:
    """Liest je Connector, ob er tatsaechlich Pixel treibt."""
    drm = sysfs_root / "sys" / "class" / "drm"
    if not drm.exists():
        return {}
    states: dict = {}
    for entry in sorted(drm.iterdir()):
        if not _CONNECTOR_RE.match(entry.name):
            continue
        status_file = entry / "status"
        enabled_file = entry / "enabled"
        if not status_file.exists() or not enabled_file.exists():
            continue
        try:
            status = status_file.read_text().strip()
            enabled = enabled_file.read_text().strip()
        except OSError as exc:
            logger.debug("Cannot read %s: %s", entry.name, exc)
            continue
        # KWin kennt den Connector ohne das "card<N>-" davor.
        states[_CONNECTOR_RE.sub("", entry.name)] = (
            status == "connected" and enabled == "enabled"
        )
    return states


def get_connector_states_sync(sysfs_root: Path = Path("/")) -> dict:
    """Per-connector 'is this driving pixels?', keyed by the KWin name.

    Same sysfs pass as get_active_display_count(), but keeps the names. The
    display_output plugin needs to say WHICH output is lit, not how many are -
    and a second sysfs reader for the same question would be the worse answer.
    """
    return _states_sync(sysfs_root)


async def get_connector_states(sysfs_root: Path = Path("/")) -> dict:
    """Async variant, for callers already on an event loop."""
    return await asyncio.to_thread(_states_sync, sysfs_root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend ; python -m pytest tests/test_display_detector_connector_states.py -q --no-cov`
Expected: PASS

- [ ] **Step 5: Regression der bestehenden Zähler-Tests**

Run: `cd backend ; python -m pytest tests/ -q --no-cov -k display_detector`
Expected: PASS, keine neuen Fehler.

- [ ] **Step 6: Lint und Commit**

```bash
cd backend && python -m ruff check app/services/power/gpu/display_detector.py tests/test_display_detector_connector_states.py
git add backend/app/services/power/gpu/display_detector.py backend/tests/test_display_detector_connector_states.py
git commit -m "feat(power): DRM-Connector-Zustaende mit Namen, nicht nur als Anzahl"
```

---

## Task 4: Backends

**Files:**
- Create: `backend/app/plugins/installed/display_output/backend.py`
- Test: `backend/tests/plugins/test_display_output_backend.py`

**Interfaces:**
- Consumes: `parse_outputs`, `run_kscreen`, `run_kscreen_json`, `build_apply_args` (Tasks 1–2); `get_connector_states` (Task 3).
- Produces:
```python
class DisplayBackend(Protocol):
    async def get_layout(self) -> DisplayLayout: ...
    async def apply(self, wanted: dict, live_outputs: list) -> tuple[bool, str]: ...

class DevDisplayBackend: ...
class KWinDisplayBackend: ...
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_display_output_backend.py`:

```python
"""Dev-Backend und die DRM-Verschmelzung des KWin-Backends."""
import pytest

from app.plugins.installed.display_output.backend import DevDisplayBackend, KWinDisplayBackend


class TestDevBackend:
    @pytest.mark.asyncio
    async def test_mirrors_balunode_with_two_connected_outputs(self):
        layout = await DevDisplayBackend().get_layout()
        assert [o.name for o in layout.outputs] == ["HDMI-A-1", "DP-3"]
        assert all(o.connected for o in layout.outputs)

    @pytest.mark.asyncio
    async def test_carries_the_ambiguous_120hz_pair(self):
        # Ohne diese Dublette laesst sich die Beschriftungslogik unter Windows
        # nicht bedienen - und genau sie ist der Grund fuer die ID-Adressierung.
        layout = await DevDisplayBackend().get_layout()
        dp3 = next(o for o in layout.outputs if o.name == "DP-3")
        names = [m.name for m in dp3.modes if m.name == "3840x2160@120"]
        assert len(names) == 2

    @pytest.mark.asyncio
    async def test_apply_changes_what_the_next_read_returns(self):
        backend = DevDisplayBackend()
        live = (await backend.get_layout()).outputs
        ok, _ = await backend.apply({"HDMI-A-1": (True, "1"), "DP-3": (False, None)}, live)
        assert ok is True
        after = {o.name: o for o in (await backend.get_layout()).outputs}
        assert after["HDMI-A-1"].selected is True
        assert after["DP-3"].selected is False
        assert after["HDMI-A-1"].current_mode_id == "1"

    @pytest.mark.asyncio
    async def test_lit_follows_selected_in_dev_mode(self):
        backend = DevDisplayBackend()
        layout = await backend.get_layout()
        for output in layout.outputs:
            assert output.lit == output.selected
        assert layout.displays_powered is True


class TestKWinBackend:
    @pytest.mark.asyncio
    async def test_an_unreachable_session_is_reported_not_raised(self):
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=None
        ):
            layout = await KWinDisplayBackend().get_layout()
        assert layout.available is False
        assert layout.outputs == []

    @pytest.mark.asyncio
    async def test_merges_the_drm_layer_into_lit(self):
        payload = {"outputs": [{
            "name": "DP-3", "connected": True, "enabled": True, "currentModeId": "57",
            "modes": [{"id": "57", "name": "3840x2160@120", "refreshRate": 120,
                       "size": {"width": 3840, "height": 2160}}],
        }]}
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=payload
        ), patch(
            "app.plugins.installed.display_output.backend.get_connector_states",
            return_value={"DP-3": True},
        ):
            layout = await KWinDisplayBackend().get_layout()
        assert layout.outputs[0].lit is True
        assert layout.displays_powered is True

    @pytest.mark.asyncio
    async def test_an_unmappable_output_stays_unknown_not_dark(self):
        payload = {"outputs": [{
            "name": "DP-9", "connected": True, "enabled": True,
            "modes": [{"id": "1", "name": "1920x1080@60", "refreshRate": 60,
                       "size": {"width": 1920, "height": 1080}}],
        }]}
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=payload
        ), patch(
            "app.plugins.installed.display_output.backend.get_connector_states",
            return_value={"DP-3": True},
        ):
            layout = await KWinDisplayBackend().get_layout()
        assert layout.outputs[0].lit is None

    @pytest.mark.asyncio
    async def test_the_selection_is_dark_when_no_connector_is_lit(self):
        payload = {"outputs": [{
            "name": "DP-3", "connected": True, "enabled": True,
            "modes": [{"id": "1", "name": "1920x1080@60", "refreshRate": 60,
                       "size": {"width": 1920, "height": 1080}}],
        }]}
        with patch(
            "app.plugins.installed.display_output.backend.run_kscreen_json", return_value=payload
        ), patch(
            "app.plugins.installed.display_output.backend.get_connector_states",
            return_value={"DP-3": False},
        ):
            layout = await KWinDisplayBackend().get_layout()
        # Genau der Zustand, der DesktopTogglePanel "Gestoppt" melden laesst,
        # waehrend KWin DP-3 fuer gewaehlt haelt. Kein Widerspruch, zwei Ebenen.
        assert layout.outputs[0].selected is True
        assert layout.outputs[0].lit is False
        assert layout.displays_powered is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_backend.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: ... display_output.backend`

- [ ] **Step 3: Backends schreiben**

Create `backend/app/plugins/installed/display_output/backend.py`:

```python
"""Display-Backends: ein Protokoll, eine Attrappe, eine echte Umsetzung.

Der Aufbau spiegelt ``services/power/desktop_backend.py`` und
``audio_control/backend.py``: ein Protocol, ein Dev-Backend fuer Windows und
Entwicklungsbetrieb, ein Linux-Backend, das mit der realen Session spricht.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Protocol, Tuple

from app.plugins.installed.display_output.kscreen import (
    build_apply_args,
    parse_outputs,
    run_kscreen,
    run_kscreen_json,
)
from app.plugins.installed.display_output.models import (
    DisplayLayout,
    DisplayMode,
    DisplayOutput,
)
from app.services.power.gpu.display_detector import get_connector_states


class DisplayBackend(Protocol):
    async def get_layout(self) -> DisplayLayout: ...
    async def apply(
        self, wanted: Dict[str, Tuple[bool, Optional[str]]], live_outputs: List[DisplayOutput]
    ) -> Tuple[bool, str]: ...


def _dev_modes(entries: List[tuple]) -> List[DisplayMode]:
    return [
        DisplayMode(id=i, name=n, width=w, height=h, refresh_rate=r)
        for i, n, w, h, r in entries
    ]


class DevDisplayBackend:
    """Zustand im Speicher, damit das Feature auf Windows entwickelbar ist.

    Bildet BaluNode nach: **zwei** verbundene Ausgaenge. Ein
    ``disconnected``-Ausgang gehoert bewusst nicht dazu — kscreen-doctor listet
    unverbundene Connectoren gar nicht erst, ein solcher Eintrag waere also ein
    Zustand, den das echte Backend nie liefert.

    Die namensgleichen Modus-Paare sind Absicht: an ihnen haengt die gesamte
    Begruendung fuer die ID-Adressierung, und ohne sie liesse sich die
    Beschriftung unter Windows nicht pruefen.
    """

    def __init__(self) -> None:
        self._outputs: List[DisplayOutput] = [
            DisplayOutput(
                name="HDMI-A-1", connected=True, selected=False,
                current_mode_id="1", preferred_mode_id="1", scale=1.0, priority=0,
                modes=_dev_modes([
                    ("1", "2560x1440@144", 2560, 1440, 143.99899291992188),
                    ("8", "1920x1200@144", 1920, 1200, 143.99899291992188),
                    ("9", "1920x1080@60", 1920, 1080, 60.0),
                    ("11", "1920x1080@60", 1920, 1080, 59.939998626708984),
                    ("50", "1920x1080@144", 1920, 1080, 143.8820037841797),
                ]),
            ),
            DisplayOutput(
                name="DP-3", connected=True, selected=True,
                current_mode_id="57", preferred_mode_id="56", scale=2.5, priority=1,
                modes=_dev_modes([
                    ("57", "3840x2160@120", 3840, 2160, 120.0),
                    ("58", "3840x2160@120", 3840, 2160, 119.87999725341797),
                    ("56", "3840x2160@60", 3840, 2160, 60.0),
                    ("67", "2560x1440@120", 2560, 1440, 119.99800109863281),
                    ("69", "1920x1080@120", 1920, 1080, 120.0),
                ]),
            ),
        ]

    async def get_layout(self) -> DisplayLayout:
        outputs = [o.model_copy(update={"lit": o.selected}) for o in self._outputs]
        return DisplayLayout(
            outputs=outputs,
            displays_powered=any(o.lit for o in outputs),
            available=True,
            detail="Dev-Backend (im Speicher)",
        )

    async def apply(
        self, wanted: Dict[str, Tuple[bool, Optional[str]]], live_outputs: List[DisplayOutput]
    ) -> Tuple[bool, str]:
        for output in self._outputs:
            if output.name not in wanted:
                continue
            selected, mode_id = wanted[output.name]
            output.selected = selected
            if selected and mode_id:
                output.current_mode_id = mode_id
        return True, "Angewendet (Dev)"


class KWinDisplayBackend:
    """Spricht ueber kscreen-doctor mit der KWin-Instanz der Desktop-Session.

    Das Backend laeuft unter derselben UID wie die Session, deshalb genuegt die
    Umgebung aus ``wayland_session_env()``; es wird kein Sudo benoetigt.
    """

    async def get_layout(self) -> DisplayLayout:
        payload = await asyncio.to_thread(run_kscreen_json)
        if payload is None:
            return DisplayLayout(available=False, detail="KWin nicht erreichbar")

        outputs = parse_outputs(payload)
        states = await get_connector_states()
        merged = [
            # .get() statt [] : ein Name ohne Connector ist "unbekannt",
            # nicht "aus". Eine unbekannte Antwort als aus auszugeben waere
            # eine Falschaussage.
            o.model_copy(update={"lit": states.get(o.name)})
            for o in outputs
        ]
        return DisplayLayout(
            outputs=merged,
            displays_powered=any(o.lit is True for o in merged),
            available=True,
        )

    async def apply(
        self, wanted: Dict[str, Tuple[bool, Optional[str]]], live_outputs: List[DisplayOutput]
    ) -> Tuple[bool, str]:
        args = build_apply_args(wanted, live_outputs)
        # Genau ein Aufruf: kscreen-doctor wendet alle Argumente gemeinsam an.
        return await asyncio.to_thread(run_kscreen, args[1:])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_backend.py -q --no-cov`
Expected: PASS

- [ ] **Step 5: Lint und Commit**

```bash
cd backend && python -m ruff check app/plugins/installed/display_output tests/plugins/test_display_output_backend.py
git add backend/app/plugins/installed/display_output/backend.py backend/tests/plugins/test_display_output_backend.py
git commit -m "feat(display-output): Dev- und KWin-Backend mit getrennter KWin-/DRM-Ebene"
```

---

## Task 5: Service mit Whitelist-Validierung

**Files:**
- Create: `backend/app/plugins/installed/display_output/service.py`
- Test: `backend/tests/plugins/test_display_output_service.py`

**Interfaces:**
- Consumes: Backends aus Task 4, Modelle aus Task 1.
- Produces:
```python
class DisplayError(Exception): ...
class DisplayUnavailable(DisplayError): ...
class InvalidRequest(DisplayError): ...        # -> 400
class ModeMismatch(DisplayError): ...          # -> 409

class DisplayService:
    def __init__(self, backend: Optional[DisplayBackend] = None) -> None
    async def get_layout(self) -> DisplayLayout
    async def apply(self, request: DisplayApplyRequest) -> tuple[bool, str]

def get_display_service() -> DisplayService
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_display_output_service.py`:

```python
"""Validierung: kein Wert wird zum Argument, der nicht enumeriert wurde."""
import pytest

from app.plugins.installed.display_output.backend import DevDisplayBackend
from app.plugins.installed.display_output.models import DisplayApplyRequest
from app.plugins.installed.display_output.service import (
    DisplayService,
    DisplayUnavailable,
    InvalidRequest,
    ModeMismatch,
)


def _req(outputs: list) -> DisplayApplyRequest:
    return DisplayApplyRequest(outputs=outputs)


@pytest.fixture
def service() -> DisplayService:
    return DisplayService(backend=DevDisplayBackend())


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_a_valid_change_is_applied(self, service):
        ok, _ = await service.apply(_req([
            {"name": "HDMI-A-1", "selected": True, "mode_id": "1", "mode_name": "2560x1440@144"},
            {"name": "DP-3", "selected": False},
        ]))
        assert ok is True
        layout = await service.get_layout()
        assert {o.name: o.selected for o in layout.outputs} == {"HDMI-A-1": True, "DP-3": False}

    @pytest.mark.asyncio
    async def test_selecting_without_a_mode_keeps_the_current_one(self, service):
        ok, _ = await service.apply(_req([{"name": "DP-3", "selected": True}]))
        assert ok is True
        dp3 = next(o for o in (await service.get_layout()).outputs if o.name == "DP-3")
        assert dp3.current_mode_id == "57"


class TestWhitelist:
    @pytest.mark.asyncio
    async def test_an_unknown_output_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{"name": "DP-99", "selected": True}]))

    @pytest.mark.asyncio
    async def test_a_mode_belonging_to_another_output_is_rejected(self, service):
        # Das ist #589 als Testfall: Mode-IDs sind global vergeben, also
        # existiert "57" - aber nicht an HDMI-A-1.
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{
                "name": "HDMI-A-1", "selected": True,
                "mode_id": "57", "mode_name": "3840x2160@120",
            }]))

    @pytest.mark.asyncio
    async def test_an_unknown_mode_id_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{
                "name": "DP-3", "selected": True, "mode_id": "9999", "mode_name": "x",
            }]))

    @pytest.mark.asyncio
    async def test_a_duplicate_output_in_one_request_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([
                {"name": "DP-3", "selected": True},
                {"name": "DP-3", "selected": False},
            ]))


class TestModeCrossCheck:
    @pytest.mark.asyncio
    async def test_a_mode_id_without_a_name_is_rejected(self, service):
        # Sonst waere die Gegenprobe vom Client abschaltbar.
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{"name": "DP-3", "selected": True, "mode_id": "58"}]))

    @pytest.mark.asyncio
    async def test_a_name_without_an_id_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([{
                "name": "DP-3", "selected": True, "mode_name": "3840x2160@120",
            }]))

    @pytest.mark.asyncio
    async def test_a_stale_name_for_a_live_id_is_a_conflict(self, service):
        with pytest.raises(ModeMismatch):
            await service.apply(_req([{
                "name": "DP-3", "selected": True,
                "mode_id": "58", "mode_name": "1920x1080@60",
            }]))

    @pytest.mark.asyncio
    async def test_the_ambiguous_pair_is_addressable_member_by_member(self, service):
        # Beide heissen "3840x2160@120". Ueber die ID sind sie trotzdem
        # unterscheidbar - der ganze Punkt des Entwurfs.
        for mode_id in ("57", "58"):
            ok, _ = await service.apply(_req([{
                "name": "DP-3", "selected": True,
                "mode_id": mode_id, "mode_name": "3840x2160@120",
            }]))
            assert ok is True
            dp3 = next(o for o in (await service.get_layout()).outputs if o.name == "DP-3")
            assert dp3.current_mode_id == mode_id


class TestInvariant:
    @pytest.mark.asyncio
    async def test_deselecting_every_connected_output_is_rejected(self, service):
        with pytest.raises(InvalidRequest):
            await service.apply(_req([
                {"name": "HDMI-A-1", "selected": False},
                {"name": "DP-3", "selected": False},
            ]))

    @pytest.mark.asyncio
    async def test_an_omitted_output_still_counts_as_selected(self, service):
        # DP-3 steht nicht im Request und bleibt gewaehlt - also ist das
        # Abwaehlen von HDMI-A-1 erlaubt.
        ok, _ = await service.apply(_req([{"name": "HDMI-A-1", "selected": False}]))
        assert ok is True

    @pytest.mark.asyncio
    async def test_a_mode_on_a_deselected_output_is_ignored_not_rejected(self, service):
        ok, _ = await service.apply(_req([{
            "name": "HDMI-A-1", "selected": False,
            "mode_id": "1", "mode_name": "2560x1440@144",
        }]))
        assert ok is True


class TestUnavailable:
    @pytest.mark.asyncio
    async def test_an_unreachable_session_raises_before_anything_is_applied(self):
        from app.plugins.installed.display_output.models import DisplayLayout

        class _Dead:
            async def get_layout(self):
                return DisplayLayout(available=False, detail="KWin nicht erreichbar")

            async def apply(self, wanted, live_outputs):
                raise AssertionError("apply darf bei toter Session nicht laufen")

        dead = DisplayService(backend=_Dead())
        with pytest.raises(DisplayUnavailable):
            await dead.apply(_req([{"name": "DP-3", "selected": True}]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_service.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: ... display_output.service`

- [ ] **Step 3: Service schreiben**

Create `backend/app/plugins/installed/display_output/service.py`:

```python
"""Service-Schicht der Displaysteuerung.

Waehlt das Backend, haelt die Auswahl als Singleton und traegt die gesamte
Validierung. Der Aufbau spiegelt ``audio_control/service.py``.

**Die Validierung ist die eigentliche Schutzmassnahme.** Listen-Argumente
schliessen eine Shell-Injektion ohnehin aus; hier wird sichergestellt, dass
ueberhaupt nur Werte in den Argumentvektor gelangen, die zuvor in der
Live-Enumeration standen.
"""
from __future__ import annotations

import logging
import platform
from typing import Dict, Optional, Tuple

from app.core.config import settings
from app.plugins.installed.display_output.backend import (
    DevDisplayBackend,
    DisplayBackend,
    KWinDisplayBackend,
)
from app.plugins.installed.display_output.models import DisplayApplyRequest, DisplayLayout

logger = logging.getLogger(__name__)

_service: Optional["DisplayService"] = None


class DisplayError(Exception):
    """Basis der Fehler, die die Route in Statuscodes uebersetzt."""


class DisplayUnavailable(DisplayError):
    """KWin ist nicht erreichbar — wird zu 502."""


class InvalidRequest(DisplayError):
    """Der Wunsch ist nicht erfuellbar — wird zu 400."""


class ModeMismatch(DisplayError):
    """Die ID meint inzwischen einen anderen Modus — wird zu 409."""


class DisplayService:
    """Duenne Huelle um das gewaehlte Backend, plus Validierung."""

    def __init__(self, backend: Optional[DisplayBackend] = None) -> None:
        if backend is not None:
            self._backend: DisplayBackend = backend
        elif getattr(settings, "is_dev_mode", False) or platform.system() != "Linux":
            # kscreen-doctor gibt es auf Windows nicht, und im Dev-Modus soll
            # nichts an einer echten Session herumstellen.
            self._backend = DevDisplayBackend()
        else:
            self._backend = KWinDisplayBackend()

    async def get_layout(self) -> DisplayLayout:
        """Liest Ausgaenge, Modi und den globalen DPMS-Zustand."""
        return await self._backend.get_layout()

    async def apply(self, request: DisplayApplyRequest) -> Tuple[bool, str]:
        """Prueft den Wunsch gegen die Live-Enumeration und wendet ihn an.

        Raises:
            DisplayUnavailable: KWin antwortet nicht.
            InvalidRequest: unbekannter Ausgang, unbekannte oder fremde
                Mode-ID, doppelter Ausgang, unvollstaendige Modusangabe, oder
                ein Ergebnis ohne einen einzigen gewaehlten Ausgang.
            ModeMismatch: die ID existiert, meint aber einen anderen Modus als
                der mitgeschickte Name.
        """
        layout = await self._backend.get_layout()
        if not layout.available:
            raise DisplayUnavailable(layout.detail or "KWin nicht erreichbar")

        by_name = {o.name: o for o in layout.outputs}
        wanted: Dict[str, Tuple[bool, Optional[str]]] = {}

        for item in request.outputs:
            if item.name in wanted:
                raise InvalidRequest(f"Ausgang doppelt im Wunsch: {item.name}")
            output = by_name.get(item.name)
            if output is None:
                raise InvalidRequest(f"Unbekannter Ausgang: {item.name}")

            mode_id: Optional[str] = None
            if item.mode_id is not None or item.mode_name is not None:
                if item.mode_id is None or item.mode_name is None:
                    # Ohne beide Haelften waere die Gegenprobe abschaltbar.
                    raise InvalidRequest("mode_id und mode_name gehoeren zusammen")
                if item.selected:
                    mode = next((m for m in output.modes if m.id == item.mode_id), None)
                    if mode is None:
                        raise InvalidRequest(
                            f"Modus {item.mode_id} gehoert nicht zu {item.name}"
                        )
                    if mode.name != item.mode_name:
                        raise ModeMismatch(
                            f"Modus {item.mode_id} heisst inzwischen {mode.name}"
                        )
                    mode_id = mode.id
                # Bei selected=False bleibt mode_id None: KWin behaelt die
                # Modus-Wahl eines abgewaehlten Ausgangs ohnehin.

            wanted[item.name] = (item.selected, mode_id)

        self._assert_something_stays_selected(by_name, wanted)

        logger.info("Display-Wunsch: %s", wanted)
        return await self._backend.apply(wanted, layout.outputs)

    @staticmethod
    def _assert_something_stays_selected(by_name: dict, wanted: dict) -> None:
        """Verbietet ein apply, nach dem kein Ausgang mehr gewaehlt waere.

        "Nichts soll leuchten" ist ein legitimer Wunsch, aber der Weg dafuer
        ist der DPMS-Schalter: der ist reversibel und wirft die
        KWin-Konfiguration nicht weg. Alle Ausgaenge abzuwaehlen wuerde sie
        wegwerfen.

        Ausgaenge, die der Wunsch nicht nennt, behalten ihren Zustand und
        zaehlen deshalb mit.
        """
        for name, output in by_name.items():
            if not output.connected:
                continue
            selected = wanted[name][0] if name in wanted else output.selected
            if selected:
                return
        raise InvalidRequest("Mindestens ein verbundener Ausgang muss gewaehlt bleiben")


def get_display_service() -> DisplayService:
    """Liefert die Service-Instanz und legt sie beim ersten Aufruf an."""
    global _service
    if _service is None:
        _service = DisplayService()
    return _service
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_service.py -q --no-cov`
Expected: PASS

- [ ] **Step 5: Lint und Commit**

```bash
cd backend && python -m ruff check app/plugins/installed/display_output tests/plugins/test_display_output_service.py
git add backend/app/plugins/installed/display_output/service.py backend/tests/plugins/test_display_output_service.py
git commit -m "feat(display-output): Service mit Whitelist, Modus-Gegenprobe und Auswahl-Invariante"
```

---

## Task 6: Recht `can_manage_displays`

**Files:**
- Create: `backend/alembic/versions/b8c41d92e7f5_add_can_manage_displays_permission.py`
- Modify: `backend/app/models/power_permissions.py` (nach `can_control_audio`)
- Modify: `backend/app/schemas/power_permissions.py` (3 Klassen)
- Modify: `backend/app/services/power_permissions.py` (`_ACTION_FIELD_MAP` und 4 Wertelisten)
- Modify: `backend/app/api/deps.py:404` (eine Zeile anfügen)
- Modify: `backend/app/api/routes/sleep.py:360-376`
- Test: `backend/tests/test_power_permissions_manage_displays.py`

**Interfaces:**
- Consumes: nichts.
- Produces: `app.api.deps.require_power_manage_displays`, Spalte `user_power_permissions.can_manage_displays`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_power_permissions_manage_displays.py`:

```python
"""Das neue Power-Recht: Standard aus, Admin implizit, sauber verdrahtet."""
import pytest

from app.schemas.power_permissions import (
    MyPowerPermissionsResponse,
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.power_permissions import _ACTION_FIELD_MAP


class TestWiring:
    def test_the_action_maps_to_the_column(self):
        assert _ACTION_FIELD_MAP["manage_displays"] == "can_manage_displays"

    def test_the_dependency_exists(self):
        from app.api import deps
        assert hasattr(deps, "require_power_manage_displays")

    def test_the_model_has_the_column(self):
        from app.models.power_permissions import UserPowerPermission
        assert hasattr(UserPowerPermission, "can_manage_displays")


class TestSchemas:
    def test_it_defaults_to_denied(self):
        assert UserPowerPermissionsResponse(user_id=1).can_manage_displays is False
        assert MyPowerPermissionsResponse().can_manage_displays is False

    def test_the_update_schema_leaves_it_untouched_by_default(self):
        # None heisst "nicht angefasst" - nicht "entziehen".
        assert UserPowerPermissionsUpdate().can_manage_displays is None

    def test_the_update_schema_accepts_it(self):
        assert UserPowerPermissionsUpdate(can_manage_displays=True).can_manage_displays is True


class TestGrantAndRevoke:
    def test_granting_and_revoking_round_trip(self, db_session, test_user, admin_user):
        from app.services.power_permissions import check_permission, update_permissions

        assert check_permission(db_session, test_user.id, "manage_displays") is False

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_displays=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_displays") is True

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_displays=False),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_displays") is False

    def test_it_does_not_drag_other_permissions_along(self, db_session, test_user, admin_user):
        # Es steht neben den Sleep-Ketten und ist bewusst nicht in
        # _apply_implications - wie can_control_audio.
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_displays=True),
            granted_by=admin_user.id,
        )
        perms = get_permissions(db_session, test_user.id)
        assert perms.can_manage_displays is True
        assert perms.can_suspend is False
        assert perms.can_toggle_desktop is False
```

Die Fixtures `db_session`, `test_user` und `admin_user` stehen bereits in
`backend/tests/conftest.py` (nachgeprüft am 2026-09-08) — keine neuen anlegen.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend ; python -m pytest tests/test_power_permissions_manage_displays.py -q --no-cov`
Expected: FAIL — `KeyError: 'manage_displays'`

- [ ] **Step 3: Migration anlegen**

Create `backend/alembic/versions/b8c41d92e7f5_add_can_manage_displays_permission.py`:

```python
"""add can_manage_displays permission

Revision ID: b8c41d92e7f5
Revises: e2f81c4a7b93
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c41d92e7f5'
down_revision: Union[str, Sequence[str], None] = 'e2f81c4a7b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt can_manage_displays zu user_power_permissions hinzu (standardmaessig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_manage_displays', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_manage_displays."""
    op.drop_column('user_power_permissions', 'can_manage_displays')
```

**Vor dem Weitermachen prüfen**, dass `e2f81c4a7b93` immer noch der einzige Head
ist (sonst entsteht ein Multi-Head, der den Prod-Deploy zerlegt):

Run: `cd backend ; python -m alembic heads`
Expected: genau eine Zeile, und sie nennt `b8c41d92e7f5` nach dem Anlegen.

- [ ] **Step 4: Modell und Schemas ergänzen**

In `backend/app/models/power_permissions.py` **direkt nach** der Zeile
`can_control_audio: Mapped[bool] = ...` einfügen:

```python
    can_manage_displays: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
```

In `backend/app/schemas/power_permissions.py` an drei Stellen ergänzen —
in `UserPowerPermissionsResponse` und `MyPowerPermissionsResponse` jeweils nach
`can_control_audio: bool = False`:

```python
    can_manage_displays: bool = False
```

und in `UserPowerPermissionsUpdate` nach der `can_control_audio`-Zeile:

```python
    can_manage_displays: Optional[bool] = Field(default=None, description="Allow choosing display outputs and video modes")
```

- [ ] **Step 5: Service verdrahten**

In `backend/app/services/power_permissions.py` vier Stellen ergänzen.

`_ACTION_FIELD_MAP` um einen Eintrag:

```python
    "manage_displays": "can_manage_displays",
```

In `get_permissions()` im `UserPowerPermissionsResponse(...)`-Aufruf nach
`can_control_audio=perm.can_control_audio,`:

```python
        can_manage_displays=perm.can_manage_displays,
```

In `update_permissions()` in **beiden** Wörterbüchern (`old_values` und
`new_values`) nach der `can_control_audio`-Zeile:

```python
        "can_manage_displays": perm.can_manage_displays,
```

Und im Block der expliziten Aktualisierungen nach
`if update.can_control_audio is not None:`-Block:

```python
    if update.can_manage_displays is not None:
        perm.can_manage_displays = update.can_manage_displays
```

**Nicht** in `_apply_implications` aufnehmen — das Recht steht neben den
Sleep-Ketten, genau wie `can_control_audio`.

- [ ] **Step 6: Dependency und Admin-Implikation**

In `backend/app/api/deps.py` nach Zeile 404 anfügen:

```python
require_power_manage_displays = _make_power_dependency("manage_displays")
```

In `backend/app/api/routes/sleep.py` in `get_my_power_permissions()` beide
Rückgaben ergänzen — im Admin-Zweig nach `can_control_audio=True,`:

```python
            can_manage_displays=True,
```

und im Nutzer-Zweig nach `can_control_audio=perms.can_control_audio,`:

```python
        can_manage_displays=perms.can_manage_displays,
```

- [ ] **Step 7: Run tests to verify they pass**

```
cd backend ; python -m pytest tests/test_power_permissions_manage_displays.py -q --no-cov
```
Expected: PASS

Dann die bestehenden Berechtigungs-Tests auf Regressionen:

```
cd backend ; python -m pytest tests/ -q --no-cov -k power_permission
```
Expected: PASS, keine neuen Fehler.

- [ ] **Step 8: Lint und Commit**

```bash
cd backend && python -m ruff check app/models/power_permissions.py app/schemas/power_permissions.py app/services/power_permissions.py app/api/deps.py app/api/routes/sleep.py alembic/versions/b8c41d92e7f5_add_can_manage_displays_permission.py tests/test_power_permissions_manage_displays.py
git add backend/alembic/versions/b8c41d92e7f5_add_can_manage_displays_permission.py backend/app/models/power_permissions.py backend/app/schemas/power_permissions.py backend/app/services/power_permissions.py backend/app/api/deps.py backend/app/api/routes/sleep.py backend/tests/test_power_permissions_manage_displays.py
git commit -m "feat(power): Recht can_manage_displays, standardmaessig verweigert"
```

---

## Task 7: Router, Plugin-Klasse und Fehlerabbildung

**Files:**
- Modify: `backend/app/plugins/installed/display_output/__init__.py` (vollständig ersetzen)
- Modify: `backend/app/core/rate_limiter.py` (Kategorie ergänzen)
- Test: `backend/tests/plugins/test_display_output_routes.py`
- Test: `backend/tests/plugins/test_display_output_ui_manifest.py`

**Interfaces:**
- Consumes: `DisplayService` und die Fehlerklassen (Task 5), `require_power_manage_displays` (Task 6).
- Produces: `DisplayOutputPlugin`, Routen `GET /state` und `POST /apply` unter `/api/plugins/display_output`.

- [ ] **Step 1: Rate-Limit-Kategorie ergänzen**

In `backend/app/core/rate_limiter.py` unmittelbar **vor** der schließenden
Klammer des Limit-Wörterbuchs (nach der `"audio_control"`-Zeile) einfügen:

```python

    # Displaysteuerung — das Popover fragt nur im geoeffneten Zustand alle 5 s
    # ab (~12/Minute). admin_operations (30/Minute) waere bei zwei offenen
    # Tabs bereits knapp.
    "display_output": "60/minute",
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/plugins/test_display_output_routes.py`:

```python
"""Routen-Tests: Berechtigung, Statuscodes, keine Interna in der Antwort."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_power_manage_displays
from app.plugins.installed.display_output import DisplayOutputPlugin
from app.plugins.installed.display_output import service as service_module
from app.plugins.installed.display_output.backend import DevDisplayBackend
from app.plugins.installed.display_output.models import DisplayLayout
from app.plugins.installed.display_output.service import DisplayService

BASE = "/api/plugins/display_output"


class _User:
    username = "admin"
    role = "admin"
    id = 1


def _app(service: DisplayService) -> TestClient:
    app = FastAPI()
    app.include_router(DisplayOutputPlugin().get_router(), prefix=BASE)
    app.dependency_overrides[require_power_manage_displays] = lambda: _User()
    return TestClient(app)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    service = DisplayService(backend=DevDisplayBackend())
    monkeypatch.setattr(service_module, "get_display_service", lambda: service)
    return _app(service)


class TestStateRoute:
    def test_returns_both_outputs_with_their_modes(self, client):
        body = client.get(f"{BASE}/state").json()
        assert body["available"] is True
        assert [o["name"] for o in body["outputs"]] == ["HDMI-A-1", "DP-3"]
        assert body["outputs"][1]["modes"]

    def test_the_two_levels_are_separate_fields(self, client):
        output = client.get(f"{BASE}/state").json()["outputs"][0]
        assert "selected" in output and "lit" in output
        assert "enabled" not in output

    def test_a_mode_carries_id_name_and_unrounded_rate(self, client):
        dp3 = client.get(f"{BASE}/state").json()["outputs"][1]
        mode = next(m for m in dp3["modes"] if m["id"] == "58")
        assert mode["name"] == "3840x2160@120"
        assert mode["refresh_rate"] == pytest.approx(119.87999725, rel=1e-9)


class TestApplyRoute:
    def test_a_valid_change_succeeds(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "HDMI-A-1", "selected": True, "mode_id": "1", "mode_name": "2560x1440@144"},
        ]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_an_unknown_output_is_400(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-99", "selected": True},
        ]})
        assert resp.status_code == 400

    def test_a_foreign_mode_is_400(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "HDMI-A-1", "selected": True,
             "mode_id": "57", "mode_name": "3840x2160@120"},
        ]})
        assert resp.status_code == 400

    def test_a_stale_mode_name_is_409(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-3", "selected": True,
             "mode_id": "58", "mode_name": "1920x1080@60"},
        ]})
        assert resp.status_code == 409

    def test_deselecting_everything_is_400(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "HDMI-A-1", "selected": False},
            {"name": "DP-3", "selected": False},
        ]})
        assert resp.status_code == 400

    def test_an_empty_body_is_422(self, client):
        assert client.post(f"{BASE}/apply", json={"outputs": []}).status_code == 422

    def test_a_raw_dict_body_is_rejected(self, client):
        assert client.post(f"{BASE}/apply", json={"nonsense": 1}).status_code == 422


class TestFailureMapping:
    def test_an_unreachable_session_reads_as_available_false_not_an_error(self, monkeypatch):
        class _Dead:
            async def get_layout(self):
                return DisplayLayout(available=False, detail="KWin nicht erreichbar")

            async def apply(self, wanted, live_outputs):
                raise AssertionError("darf nicht laufen")

        service = DisplayService(backend=_Dead())
        monkeypatch.setattr(service_module, "get_display_service", lambda: service)
        resp = _app(service).get(f"{BASE}/state")
        # Lesen liefert available=false statt eines Fehlers: die UI soll den
        # Zustand anzeigen koennen, nicht nur eine Fehlermeldung.
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_an_unreachable_session_is_502_on_write(self, monkeypatch):
        class _Dead:
            async def get_layout(self):
                return DisplayLayout(available=False, detail="KWin nicht erreichbar")

            async def apply(self, wanted, live_outputs):
                raise AssertionError("darf nicht laufen")

        service = DisplayService(backend=_Dead())
        monkeypatch.setattr(service_module, "get_display_service", lambda: service)
        resp = _app(service).post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-3", "selected": True},
        ]})
        assert resp.status_code == 502

    def test_no_kscreen_output_reaches_the_client(self, monkeypatch):
        secret = "/sys/devices/pci0000:00/EDID-Geheimnis"

        class _Chatty:
            async def get_layout(self):
                return (await DevDisplayBackend().get_layout())

            async def apply(self, wanted, live_outputs):
                return False, secret

        service = DisplayService(backend=_Chatty())
        monkeypatch.setattr(service_module, "get_display_service", lambda: service)
        resp = _app(service).post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-3", "selected": True},
        ]})
        assert resp.status_code == 502
        assert secret not in resp.text


class TestPermission:
    def test_the_read_route_is_gated_too(self):
        # Die Ausgangsliste verraet die angeschlossene Hardware.
        app = FastAPI()
        app.include_router(DisplayOutputPlugin().get_router(), prefix=BASE)
        # Ohne dependency_overrides greift die echte Abhaengigkeit und
        # scheitert mangels Token.
        assert TestClient(app).get(f"{BASE}/state").status_code in (401, 403)
```

Create `backend/tests/plugins/test_display_output_ui_manifest.py`:

```python
"""Ohne diese Ueberschreibung ist das Plugin im Frontend unsichtbar."""
from app.plugins.installed.display_output import DisplayOutputPlugin


class TestUiManifest:
    def test_the_manifest_is_present_and_enabled(self):
        manifest = DisplayOutputPlugin().get_ui_manifest()
        assert manifest is not None
        assert manifest.enabled is True

    def test_it_contributes_no_nav_item(self):
        # Ein Nav-Eintrag erzeugte eine Route und damit einen bundle.js-Abruf.
        # Die Bedienung sitzt in der Topbar.
        assert DisplayOutputPlugin().get_ui_manifest().nav_items == []

    def test_the_metadata_name_matches_the_route_prefix(self):
        assert DisplayOutputPlugin().metadata.name == "display_output"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_routes.py tests/plugins/test_display_output_ui_manifest.py -q --no-cov`
Expected: FAIL — `ImportError: cannot import name 'DisplayOutputPlugin'`

- [ ] **Step 4: Router und Plugin-Klasse schreiben**

`backend/app/plugins/installed/display_output/__init__.py` **vollständig
ersetzen** durch:

```python
"""Displaysteuerung — bundled Plugin.

Enumeriert die KWin-Ausgaenge und setzt Auswahl und Video-Modus ueber
kscreen-doctor. Laeuft als bundled Plugin im Host-Prozess und damit unter
derselben UID wie die Desktop-Session; ein Sandbox-Plugin kaeme nicht an den
Wayland-Socket.
"""
# NB: kein ``from __future__ import annotations`` hier (vgl. audio_control).
# Zusammen mit Pydantic v2 + FastAPIs Body-Erkennung durch slowapis
# ``@user_limiter.limit``-Wrapper werden aufgeschobene Annotationen zu
# ForwardRefs, die FastAPI nicht mehr als Pydantic-Modell aufloest — der
# Request-Body wuerde als Query-Parameter fehlinterpretiert und jedes
# POST liefert 422.
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import require_power_manage_displays
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.base import PluginBase, PluginMetadata, PluginUIManifest
from app.plugins.installed.display_output import service as service_module
from app.plugins.installed.display_output.models import DisplayApplyRequest, DisplayLayout
from app.plugins.installed.display_output.service import (
    DisplayUnavailable,
    InvalidRequest,
    ModeMismatch,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()

_LIMIT = get_limit("display_output")


def _audit(user: UserPublic, success: bool, wanted: dict) -> None:
    """Schreibt einen Audit-Eintrag fuer jede Aenderung der Ausgangswahl.

    Anders als bei den Pegeln der Audiosteuerung ist hier jeder Vorgang
    interessant: ein apply schaltet Bildschirme.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action="display_apply",
        user=user.username,
        resource="displays",
        success=success,
        details={"wanted": {k: list(v) for k, v in wanted.items()}},
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="manage_displays",
            details={"action": "display_apply"},
            success=True,
        )


@router.get("/state", response_model=DisplayLayout)
@user_limiter.limit(_LIMIT)
async def get_display_state(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_displays),
) -> DisplayLayout:
    """Liefert alle Ausgaenge, ihre Modi und den globalen DPMS-Zustand.

    Hinter derselben Berechtigung wie die Schreibroute: die Ausgangsliste
    verraet die angeschlossene Hardware samt EDID-Groessenangaben.

    Eine unerreichbare Session ist hier **kein** Fehler, sondern
    ``available=false`` — die UI soll das anzeigen koennen, statt nur eine
    Fehlermeldung zu bekommen.
    """
    return await service_module.get_display_service().get_layout()


@router.post("/apply")
@user_limiter.limit(_LIMIT)
async def apply_display_layout(
    body: DisplayApplyRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_displays),
) -> dict:
    """Setzt Auswahl und Modus in genau einem kscreen-doctor-Aufruf.

    Jeder Name und jede Mode-ID aus dem Rumpf wird zuvor gegen die live
    enumerierten Werte **dieses** Ausgangs geprueft (im Service). Was dort
    nicht steht, wird nie zu einem argv-Element.
    """
    service = service_module.get_display_service()
    wanted = {o.name: (o.selected, o.mode_id) for o in body.outputs}
    try:
        ok, message = await service.apply(body)
    except InvalidRequest as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ModeMismatch as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except DisplayUnavailable:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Displays nicht erreichbar"
        )

    _audit(current_user, ok, wanted)

    if ok:
        return {"success": True}

    # `message` stammt roh aus kscreen-doctor und kann EDID-Namen und Pfade
    # enthalten. Es wird geloggt, aber nie ausgeliefert.
    logger.warning("Display-Anwendung fehlgeschlagen: %s", message)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY, detail="Aktion fehlgeschlagen"
    )


class DisplayOutputPlugin(PluginBase):
    """Bundled Plugin fuer die Displaysteuerung."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="display_output",
            version="1.0.0",
            display_name="Displaysteuerung",
            description=(
                "Angeschlossene Bildschirme erkennen, den Ausgang waehlen und "
                "Aufloesung samt Bildwiederholrate setzen."
            ),
            author="Xveyn",
            category="system",
        )

    def get_router(self) -> APIRouter:
        return router

    def get_ui_manifest(self) -> PluginUIManifest:
        """Meldet das Plugin ans Frontend, ohne einen Nav-Eintrag beizusteuern.

        **Ohne diese Ueberschreibung ist das Feature unsichtbar.**
        ``PluginBase`` liefert hier ``None``, und
        ``PluginManager.get_ui_manifest()`` nimmt nur Plugins mit einem aktiven
        Manifest in ``/api/plugins/ui/manifest`` auf — genau die Liste, aus der
        ``usePluginEnabled`` speist. Ohne Manifest gilt das Plugin dort
        dauerhaft als abgeschaltet, und die Topbar rendert das Monitor-Symbol
        nie: kein Fehler, keine Logzeile.

        ``nav_items`` bleibt leer: die Bedienung sitzt in der Topbar. Ein
        leeres ``nav_items`` erzeugt keine Route, also wird auch kein
        ``bundle.js`` nachgeladen.
        """
        return PluginUIManifest(enabled=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend ; python -m pytest tests/plugins/test_display_output_routes.py tests/plugins/test_display_output_ui_manifest.py -q --no-cov`
Expected: PASS

- [ ] **Step 6: Gesamte Plugin-Suite auf Regressionen**

Run: `cd backend ; python -m pytest tests/plugins -q --no-cov`
Expected: PASS, keine neuen Fehler.

- [ ] **Step 7: Lint und Commit**

```bash
cd backend && python -m ruff check app/plugins/installed/display_output app/core/rate_limiter.py tests/plugins/test_display_output_routes.py tests/plugins/test_display_output_ui_manifest.py
git add backend/app/plugins/installed/display_output/__init__.py backend/app/core/rate_limiter.py backend/tests/plugins/test_display_output_routes.py backend/tests/plugins/test_display_output_ui_manifest.py
git commit -m "feat(display-output): Router, Plugin-Klasse und Fehlerabbildung (400/409/502)"
```

---

## Task 8: API-Client und i18n

**Files:**
- Create: `client/src/api/displayOutput.ts`
- Create: `client/src/i18n/locales/de/display.json`
- Create: `client/src/i18n/locales/en/display.json`
- Modify: `client/src/i18n/index.ts` (3 Stellen)

**Interfaces:**
- Consumes: die Backend-Routen aus Task 7.
- Produces:
```ts
export interface DisplayMode { id, name, width, height, refresh_rate }
export interface DisplayOutput { name, connected, selected, lit, current_mode_id, preferred_mode_id, scale, priority, modes }
export interface DisplayLayout { outputs, displays_powered, available, detail }
export interface DisplayOutputWish { name, selected, mode_id?, mode_name? }
export async function getDisplayLayout(): Promise<DisplayLayout>
export async function applyDisplayLayout(outputs: DisplayOutputWish[]): Promise<void>
export function formatMode(mode: DisplayMode, locale: string): string
```

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/api/displayOutput.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { formatMode } from '../../api/displayOutput';

const MODE_120 = { id: '57', name: '3840x2160@120', width: 3840, height: 2160, refresh_rate: 120 };
const MODE_11988 = {
  id: '58', name: '3840x2160@120', width: 3840, height: 2160,
  refresh_rate: 119.87999725341797,
};

describe('formatMode', () => {
  it('trennt das Paar, das denselben Namen traegt', () => {
    // Genau hier scheitert die Adressierung ueber den Namen: beide heissen
    // "3840x2160@120". Zwei Nachkommastellen machen sie unterscheidbar.
    expect(formatMode(MODE_120, 'de')).not.toBe(formatMode(MODE_11988, 'de'));
  });

  it('rundet auf zwei Nachkommastellen', () => {
    expect(formatMode(MODE_11988, 'en')).toContain('119.88');
    expect(formatMode(MODE_120, 'en')).toContain('120.00');
  });

  it('nutzt das Dezimaltrennzeichen der Sprache', () => {
    expect(formatMode(MODE_11988, 'de')).toContain('119,88');
  });

  it('nennt Aufloesung und Einheit', () => {
    expect(formatMode(MODE_120, 'en')).toBe('3840 × 2160 @ 120.00 Hz');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/api/displayOutput.test.ts`
Expected: FAIL — Modul nicht gefunden.

- [ ] **Step 3: API-Client schreiben**

Create `client/src/api/displayOutput.ts`:

```ts
/**
 * API-Client der Displaysteuerung (bundled Plugin `display_output`).
 *
 * Alle Routen liegen hinter dem Recht `can_manage_displays` — auch die
 * lesende, weil die Ausgangsliste die angeschlossene Hardware verrät.
 *
 * Modi werden über `id` adressiert, nie über `name`: KWin bildet den Namen mit
 * gerundeter Bildwiederholrate, weshalb 119,88 und 120,00 Hz beide
 * „3840x2160@120" heißen. `mode_name` reist nur als Gegenprobe mit.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/display_output';

export interface DisplayMode {
  /** Lebende KWin-Mode-ID. Nie speichern — sie gilt nur für diesen Abruf. */
  id: string;
  /** "3840x2160@120" — NICHT eindeutig. */
  name: string;
  width: number;
  height: number;
  /** Ungerundet, z. B. 119.87999725341797. */
  refresh_rate: number;
}

export interface DisplayOutput {
  name: string;
  connected: boolean;
  /** KWin-Ebene: ist dieser Ausgang gewählt? */
  selected: boolean;
  /** DRM-Ebene: werden Pixel getrieben? null = nicht zuordenbar. */
  lit: boolean | null;
  current_mode_id: string | null;
  preferred_mode_id: string | null;
  scale: number;
  priority: number;
  modes: DisplayMode[];
}

export interface DisplayLayout {
  outputs: DisplayOutput[];
  displays_powered: boolean;
  available: boolean;
  detail: string | null;
}

export interface DisplayOutputWish {
  name: string;
  selected: boolean;
  mode_id?: string;
  /** Pflicht, sobald mode_id gesetzt ist. */
  mode_name?: string;
}

/** Liest Ausgänge, Modi und den globalen DPMS-Zustand in einem Rundlauf. */
export async function getDisplayLayout(): Promise<DisplayLayout> {
  const { data } = await apiClient.get<DisplayLayout>(`${BASE}/state`);
  return data;
}

/** Setzt Auswahl und Modus — ein Aufruf, den das Backend atomar anwendet. */
export async function applyDisplayLayout(outputs: DisplayOutputWish[]): Promise<void> {
  await apiClient.post(`${BASE}/apply`, { outputs });
}

/**
 * Beschriftet einen Modus für das Auswahlfeld.
 *
 * Zwei Nachkommastellen sind nicht Kosmetik: sie sind das Einzige, woran ein
 * Mensch die beiden 4K-Modi von DP-3 auseinanderhält. Formatiert wird hier und
 * nicht im Backend, weil das Dezimaltrennzeichen sprachabhängig ist.
 */
export function formatMode(mode: DisplayMode, locale: string): string {
  const hz = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(mode.refresh_rate);
  return `${mode.width} × ${mode.height} @ ${hz} Hz`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/api/displayOutput.test.ts`
Expected: PASS

- [ ] **Step 5: i18n-Dateien anlegen**

Create `client/src/i18n/locales/de/display.json`:

```json
{
  "title": "Displays",
  "outputs": "Ausgänge",
  "mode": "Auflösung",
  "selected": "gewählt",
  "notSelected": "nicht gewählt",
  "lit": "leuchtet",
  "dark": "dunkel",
  "litUnknown": "Zustand unbekannt",
  "allDark": "Alle Bildschirme sind dunkel. Im Systemmenü lassen sie sich einschalten.",
  "apply": "Anwenden",
  "applying": "Wird angewendet …",
  "applied": "Übernommen",
  "unavailable": "Die Displaysteuerung ist nicht erreichbar. Läuft die Desktop-Sitzung?",
  "loadError": "Displayzustand konnte nicht geladen werden",
  "saveError": "Änderung konnte nicht übernommen werden",
  "conflictError": "Die Modusliste hat sich geändert. Bitte erneut versuchen.",
  "keepOneSelected": "Mindestens ein Ausgang muss gewählt bleiben."
}
```

Create `client/src/i18n/locales/en/display.json`:

```json
{
  "title": "Displays",
  "outputs": "Outputs",
  "mode": "Resolution",
  "selected": "selected",
  "notSelected": "not selected",
  "lit": "lit",
  "dark": "dark",
  "litUnknown": "state unknown",
  "allDark": "All screens are dark. Turn them on from the system menu.",
  "apply": "Apply",
  "applying": "Applying …",
  "applied": "Applied",
  "unavailable": "Display control is unreachable. Is the desktop session running?",
  "loadError": "Could not load display state",
  "saveError": "Could not apply the change",
  "conflictError": "The mode list changed. Please try again.",
  "keepOneSelected": "At least one output must stay selected."
}
```

- [ ] **Step 6: Namensraum registrieren**

In `client/src/i18n/index.ts` drei Stellen ergänzen — nach den beiden
`audio`-Importzeilen (Z. 44–45):

```ts
import displayDe from './locales/de/display.json';
import displayEn from './locales/en/display.json';
```

im deutschen Ressourcenblock nach `audio: audioDe,`:

```ts
    display: displayDe,
```

im englischen nach `audio: audioEn,`:

```ts
    display: displayEn,
```

und in der `ns`-Liste `'audio'` zu `'audio', 'display'` erweitern.

- [ ] **Step 7: Build und Lint**

```
cd client ; npx eslint src/api/displayOutput.ts src/i18n/index.ts
```
Expected: keine Fehler.

```
cd client ; npm run build
```
Expected: Erfolg. (`npm run build` fährt `tsc -b` über alle Projekte — ein reines
`tsc --noEmit` würde den Fehler übersehen, an dem die CI dann scheitert.)

- [ ] **Step 8: Commit**

```bash
git add client/src/api/displayOutput.ts client/src/i18n/locales/de/display.json client/src/i18n/locales/en/display.json client/src/i18n/index.ts client/src/__tests__/api/displayOutput.test.ts
git commit -m "feat(display-output): API-Client mit sprachrichtiger Modus-Beschriftung und i18n"
```

---

## Task 9: Topbar-Popover

**Files:**
- Create: `client/src/components/topbar/DisplayMenu.tsx`
- Modify: `client/src/components/layout/LayoutHeader.tsx` (3 Zeilen)
- Test: `client/src/__tests__/components/topbar/DisplayMenu.test.tsx`

**Interfaces:**
- Consumes: `getDisplayLayout`, `applyDisplayLayout`, `formatMode` (Task 8); `getMyPowerPermissions` (Task 6).
- Produces: `export function DisplayMenu()`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/topbar/DisplayMenu.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const values = options ? Object.values(options).join('/') : '';
      return values ? `${ns}:${key}:${values}` : `${ns}:${key}`;
    },
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/displayOutput', async () => {
  const actual = await vi.importActual<typeof import('../../../api/displayOutput')>(
    '../../../api/displayOutput',
  );
  return {
    ...actual,
    getDisplayLayout: vi.fn(),
    applyDisplayLayout: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn(),
}));

import { DisplayMenu } from '../../../components/topbar/DisplayMenu';
import { getDisplayLayout, applyDisplayLayout } from '../../../api/displayOutput';
import { getMyPowerPermissions } from '../../../api/powerPermissions';

const LAYOUT = {
  available: true,
  detail: null,
  displays_powered: false,
  outputs: [
    {
      name: 'HDMI-A-1', connected: true, selected: false, lit: false,
      current_mode_id: '1', preferred_mode_id: '1', scale: 1, priority: 0,
      modes: [{ id: '1', name: '2560x1440@144', width: 2560, height: 1440, refresh_rate: 143.999 }],
    },
    {
      name: 'DP-3', connected: true, selected: true, lit: false,
      current_mode_id: '57', preferred_mode_id: '56', scale: 2.5, priority: 1,
      modes: [
        { id: '57', name: '3840x2160@120', width: 3840, height: 2160, refresh_rate: 120 },
        { id: '58', name: '3840x2160@120', width: 3840, height: 2160, refresh_rate: 119.87999725 },
      ],
    },
  ],
};

beforeEach(() => {
  vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_displays: true } as never);
  vi.mocked(getDisplayLayout).mockResolvedValue(structuredClone(LAYOUT) as never);
});

async function open() {
  render(<DisplayMenu />);
  const button = await screen.findByLabelText('display:title');
  fireEvent.click(button);
  await waitFor(() => expect(getDisplayLayout).toHaveBeenCalled());
}

describe('DisplayMenu', () => {
  it('bleibt unsichtbar ohne das Recht', async () => {
    vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_displays: false } as never);
    const { container } = render(<DisplayMenu />);
    await waitFor(() => expect(getMyPowerPermissions).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it('fragt erst ab, wenn das Popover offen ist', async () => {
    render(<DisplayMenu />);
    await screen.findByLabelText('display:title');
    expect(getDisplayLayout).not.toHaveBeenCalled();
  });

  it('listet beide Ausgaenge', async () => {
    await open();
    expect(await screen.findByText('DP-3')).toBeTruthy();
    expect(screen.getByText('HDMI-A-1')).toBeTruthy();
  });

  it('zeigt gewaehlt und leuchtet als getrennte Aussagen', async () => {
    // Der mehrdeutige Zustand von BaluNode: KWin haelt DP-3 fuer gewaehlt,
    // DRM meldet dunkel. Beides muss sichtbar sein, sonst widerspricht sich
    // die Oberflaeche.
    await open();
    expect(screen.getAllByText('display:selected').length).toBe(1);
    expect(screen.getAllByText('display:dark').length).toBe(2);
  });

  it('unterscheidet die beiden namensgleichen 4K-Modi im Auswahlfeld', async () => {
    await open();
    const select = screen.getByLabelText('display:mode:DP-3') as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels.some((l) => l?.includes('119,88'))).toBe(true);
  });

  it('schickt id und name zusammen', async () => {
    await open();
    const select = screen.getByLabelText('display:mode:DP-3') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: '58' } });
    fireEvent.click(screen.getByText('display:apply'));
    await waitFor(() => expect(applyDisplayLayout).toHaveBeenCalled());
    const wishes = vi.mocked(applyDisplayLayout).mock.calls[0][0];
    const dp3 = wishes.find((w) => w.name === 'DP-3');
    expect(dp3).toEqual({
      name: 'DP-3', selected: true, mode_id: '58', mode_name: '3840x2160@120',
    });
  });

  it('sperrt Anwenden, wenn nichts mehr gewaehlt waere', async () => {
    await open();
    fireEvent.click(screen.getByLabelText('display:outputs:DP-3'));
    const apply = screen.getByText('display:apply').closest('button') as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
  });

  it('meldet eine unerreichbare Sitzung statt einer leeren Liste', async () => {
    vi.mocked(getDisplayLayout).mockResolvedValue({
      ...LAYOUT, available: false, outputs: [],
    } as never);
    await open();
    expect(await screen.findByText('display:unavailable')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/topbar/DisplayMenu.test.tsx`
Expected: FAIL — Modul nicht gefunden.

- [ ] **Step 3: Popover schreiben**

Create `client/src/components/topbar/DisplayMenu.tsx`:

```tsx
/**
 * Displaysteuerung in der Topbar.
 *
 * Zeigt ein Monitor-Symbol; im Popover steht pro Ausgang die KWin-Wahl und
 * ein Auswahlfeld für den Video-Modus.
 *
 * Drei Eigenheiten, die Absicht sind:
 * - Der Zustand wird nur abgefragt, solange das Popover offen ist. Eine
 *   Fernbedienung, die im Hintergrund pollt, kostet Anfragen ohne Gegenwert.
 * - „gewählt" (KWin) und „leuchtet" (DRM) sind getrennte Aussagen. Beides in
 *   ein Abzeichen zu falten, ist die Verwechslung, die dieses Feature auflöst.
 * - Der globale Ein/Aus-Schalter fehlt bewusst: er steht zwei Symbole weiter
 *   im Systemmenü, und zwei Komponenten für denselben Zustand driften.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Monitor, MonitorOff } from 'lucide-react';
import {
  applyDisplayLayout,
  formatMode,
  getDisplayLayout,
  type DisplayLayout,
  type DisplayOutputWish,
} from '../../api/displayOutput';
import { getMyPowerPermissions } from '../../api/powerPermissions';

/** Abfragetakt, solange das Popover offen ist. */
const POLL_MS = 5000;

/** Der bearbeitete Wunsch je Ausgang, bevor „Anwenden" ihn abschickt. */
interface Draft {
  selected: boolean;
  modeId: string | null;
}

export function DisplayMenu() {
  const { t, i18n } = useTranslation('display');
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [layout, setLayout] = useState<DisplayLayout | null>(null);
  const [draft, setDraft] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);
  const dirty = useRef(false);

  useEffect(() => {
    let active = true;
    getMyPowerPermissions()
      .then((perms) => active && setAllowed(perms.can_manage_displays))
      .catch(() => active && setAllowed(false));
    return () => {
      active = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const next = await getDisplayLayout();
      setLayout(next);
      // Einen angefangenen Entwurf NICHT überschreiben — sonst springt die
      // Auswahl beim nächsten Takt auf den Serverwert zurück.
      if (!dirty.current) {
        setDraft(
          Object.fromEntries(
            next.outputs.map((o) => [o.name, { selected: o.selected, modeId: o.current_mode_id }]),
          ),
        );
      }
      setError(null);
    } catch {
      setError(t('loadError'));
    } finally {
      inFlight.current = false;
    }
  }, [t]);

  useEffect(() => {
    if (!isOpen) return;
    void refresh();
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(id);
  }, [isOpen, refresh]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        dirty.current = false;
      }
    };
    if (isOpen) document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [isOpen]);

  const wishes: DisplayOutputWish[] = useMemo(() => {
    if (!layout) return [];
    return layout.outputs.map((output) => {
      const entry = draft[output.name] ?? { selected: output.selected, modeId: output.current_mode_id };
      const mode = output.modes.find((m) => m.id === entry.modeId);
      const wish: DisplayOutputWish = { name: output.name, selected: entry.selected };
      // id und name reisen immer gemeinsam — das Backend lehnt eine einzelne
      // Hälfte ab, weil die Gegenprobe sonst abschaltbar wäre.
      if (entry.selected && mode) {
        wish.mode_id = mode.id;
        wish.mode_name = mode.name;
      }
      return wish;
    });
  }, [layout, draft]);

  const nothingSelected =
    layout !== null &&
    layout.outputs.some((o) => o.connected) &&
    !layout.outputs.some((o) => o.connected && (draft[o.name]?.selected ?? o.selected));

  const handleApply = async () => {
    setBusy(true);
    setError(null);
    try {
      await applyDisplayLayout(wishes);
      dirty.current = false;
      await refresh();
    } catch (err: unknown) {
      const statusCode = (err as { response?: { status?: number } })?.response?.status;
      setError(statusCode === 409 ? t('conflictError') : t('saveError'));
      if (statusCode === 409) {
        dirty.current = false;
        await refresh();
      }
    } finally {
      setBusy(false);
    }
  };

  if (!allowed) return null;

  const anyLit = layout?.outputs.some((o) => o.lit === true) ?? false;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        aria-label={t('title')}
        onClick={() => setIsOpen((open) => !open)}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
      >
        {anyLit ? <Monitor className="h-5 w-5" /> : <MonitorOff className="h-5 w-5" />}
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-96 rounded-xl border border-slate-800 bg-slate-900/95 p-4 shadow-xl backdrop-blur-xl">
          {layout && !layout.available && (
            <p className="text-sm text-slate-400">{t('unavailable')}</p>
          )}

          {layout?.available && (
            <>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{t('outputs')}</p>

              {layout.outputs.map((output) => {
                const entry = draft[output.name] ?? {
                  selected: output.selected,
                  modeId: output.current_mode_id,
                };
                return (
                  <div key={output.name} className="mb-4 border-b border-slate-800 pb-3 last:border-0">
                    <div className="mb-1 flex items-center gap-2">
                      <input
                        type="checkbox"
                        id={`display-${output.name}`}
                        aria-label={t('outputs') + ':' + output.name}
                        checked={entry.selected}
                        onChange={(e) => {
                          dirty.current = true;
                          setDraft((prev) => ({
                            ...prev,
                            [output.name]: { ...entry, selected: e.target.checked },
                          }));
                        }}
                      />
                      <label htmlFor={`display-${output.name}`} className="text-sm text-slate-200">
                        {output.name}
                      </label>
                      <span className="ml-auto text-xs text-slate-500">
                        {output.selected ? t('selected') : t('notSelected')}
                      </span>
                      <span className="text-xs text-slate-500">
                        {output.lit === null ? t('litUnknown') : output.lit ? t('lit') : t('dark')}
                      </span>
                    </div>

                    <select
                      aria-label={t('mode', { output: output.name })}
                      value={entry.modeId ?? ''}
                      disabled={!entry.selected}
                      onChange={(e) => {
                        dirty.current = true;
                        setDraft((prev) => ({
                          ...prev,
                          [output.name]: { ...entry, modeId: e.target.value },
                        }));
                      }}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 disabled:opacity-50"
                    >
                      {output.modes.map((mode) => (
                        <option key={mode.id} value={mode.id}>
                          {formatMode(mode, i18n.language)}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}

              {!layout.displays_powered && (
                <p className="mb-2 text-xs text-amber-400">{t('allDark')}</p>
              )}
              {nothingSelected && (
                <p className="mb-2 text-xs text-amber-400">{t('keepOneSelected')}</p>
              )}
              {error && <p className="mb-2 text-xs text-rose-400">{error}</p>}

              <button
                type="button"
                onClick={() => void handleApply()}
                disabled={busy || nothingSelected}
                className="w-full rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:opacity-50"
              >
                {busy ? t('applying') : t('apply')}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: In die Topbar einhängen**

In `client/src/components/layout/LayoutHeader.tsx` drei Änderungen.

Nach Zeile 5 (`import { AudioMenu } ...`):

```tsx
import { DisplayMenu } from '../topbar/DisplayMenu';
```

In der Komponente nach `const audioEnabled = usePluginEnabled('audio_control');`:

```tsx
  const displaysEnabled = usePluginEnabled('display_output');
```

Und in „Header Right" **vor** der `AudioMenu`-Zeile:

```tsx
          {!isPi && displaysEnabled && <DisplayMenu />}
```

- [ ] **Step 5: Run tests to verify they pass**

```
cd client ; npx vitest run src/__tests__/components/topbar/DisplayMenu.test.tsx src/__tests__/components/layout/LayoutHeader.test.tsx
```
Expected: PASS. Die bestehende `LayoutHeader`-Suite muss grün bleiben; bricht sie
mit „usePlugins must be used within a PluginProvider", fehlt in ihr der Mock für
den neuen `usePluginEnabled`-Aufruf — dort ergänzen, nicht die Komponente ändern.

- [ ] **Step 6: Lint und Build**

```
cd client ; npx eslint .
```
Expected: 0 Fehler (die CI setzt hier ein hartes Gate).

```
cd client ; npm run build
```
Expected: Erfolg.

- [ ] **Step 7: Commit**

```bash
git add client/src/components/topbar/DisplayMenu.tsx client/src/components/layout/LayoutHeader.tsx client/src/__tests__/components/topbar/DisplayMenu.test.tsx
git commit -m "feat(display-output): Topbar-Popover mit getrennter KWin-/DRM-Anzeige"
```

---

## Task 10: Recht in der Nutzerverwaltung

**Files:**
- Modify: `client/src/api/powerPermissions.ts` (3 Schnittstellen)
- Modify: `client/src/components/user-management/PowerPermissionsSection.tsx` (2 Stellen)
- Modify: `client/src/i18n/locales/de/admin.json`, `client/src/i18n/locales/en/admin.json`
- Test: `client/src/__tests__/components/user-management/PowerPermissionsSection.displays.test.tsx`

**Interfaces:**
- Consumes: das Backend-Recht aus Task 6.
- Produces: nichts, worauf spätere Tasks aufbauen.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/user-management/PowerPermissionsSection.displays.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string) => `${ns}:${key}`,
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/powerPermissions', () => ({
  getUserPowerPermissions: vi.fn(),
  updateUserPowerPermissions: vi.fn().mockResolvedValue(undefined),
}));

// Die Komponente zieht beides unbedingt herein; ohne Mock scheitert der
// Import, nicht die Zusicherung.
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../lib/errorHandling', () => ({
  handleApiError: vi.fn(),
}));

import { PowerPermissionsSection } from '../../../components/user-management/PowerPermissionsSection';
import { getUserPowerPermissions } from '../../../api/powerPermissions';

const PERMS = {
  user_id: 7,
  can_soft_sleep: false, can_wake: false, can_suspend: false, can_wol: false,
  can_toggle_desktop: false, can_unlock_session: false, can_control_audio: false,
  can_manage_displays: false,
  granted_by: null, granted_by_username: null, granted_at: null,
};

beforeEach(() => {
  vi.mocked(getUserPowerPermissions).mockResolvedValue(structuredClone(PERMS) as never);
});

describe('PowerPermissionsSection — Displays', () => {
  it('bietet den Schalter fuer can_manage_displays an', async () => {
    render(<PowerPermissionsSection userId={7} userRole="user" />);
    await waitFor(() => expect(getUserPowerPermissions).toHaveBeenCalled());
    expect(
      await screen.findByText('admin:users.systemPermissions.items.manageDisplays.label'),
    ).toBeTruthy();
  });
});
```

Nachgeprüft am 2026-09-08: die Komponente nimmt genau
`{ userId: number; userRole: string }`, und der i18n-Pfad der Einträge lautet
`users.systemPermissions.items.*` im Namensraum `admin`. Für diese Komponente
existiert bisher **keine** Testdatei — dies ist die erste, das Verzeichnis
`client/src/__tests__/components/user-management/` wird mit angelegt.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/user-management/PowerPermissionsSection.displays.test.tsx`
Expected: FAIL — der Eintrag fehlt.

- [ ] **Step 3: Typen ergänzen**

In `client/src/api/powerPermissions.ts` in allen drei Schnittstellen nach der
`can_control_audio`-Zeile ergänzen:

```ts
  can_manage_displays: boolean;
```

(in `UserPowerPermissionsUpdate` als `can_manage_displays?: boolean;`)

- [ ] **Step 4: Schalter ergänzen**

In `client/src/components/user-management/PowerPermissionsSection.tsx`:

`FIELD_TO_I18N` um einen Eintrag nach `can_control_audio: 'controlAudio',`:

```ts
  can_manage_displays: 'manageDisplays',
```

`PERMISSION_TOGGLES` um einen Eintrag nach der `can_control_audio`-Zeile:

```tsx
  { key: 'can_manage_displays', icon: <Monitor className="h-4 w-4" /> },
```

und `Monitor` zum `lucide-react`-Import der Datei hinzufügen.

- [ ] **Step 5: i18n ergänzen**

In `client/src/i18n/locales/de/admin.json` in
`users.systemPermissions.items` nach dem `controlAudio`-Eintrag:

```json
        "manageDisplays": { "label": "Displays", "desc": "Bildschirm-Ausgang und Auflösung wählen" }
```

In `client/src/i18n/locales/en/admin.json` an der entsprechenden Stelle:

```json
        "manageDisplays": { "label": "Displays", "desc": "Choose the display output and resolution" }
```

Auf das Komma am Ende der vorherigen Zeile achten.

- [ ] **Step 6: Run tests to verify they pass**

```
cd client ; npx vitest run src/__tests__/components/user-management
```
Expected: PASS.

- [ ] **Step 7: Lint, Build, Commit**

```
cd client ; npx eslint . ; npm run build
```
Expected: 0 eslint-Fehler, Build erfolgreich.

```bash
git add client/src/api/powerPermissions.ts client/src/components/user-management/PowerPermissionsSection.tsx client/src/i18n/locales/de/admin.json client/src/i18n/locales/en/admin.json client/src/__tests__/components/user-management/PowerPermissionsSection.displays.test.tsx
git commit -m "feat(display-output): can_manage_displays in der Nutzerverwaltung"
```

---

## Task 11: Dokumentation

**Files:**
- Create: `backend/app/plugins/installed/display_output/CLAUDE.md`
- Modify: `backend/app/plugins/CLAUDE.md` (Verzeichnisbaum unter `installed/`)
- Modify: `.claude/rules/architecture.md` (API-Liste)
- Modify: `CLAUDE.md` (Quick Reference)

**Interfaces:**
- Consumes: alles Vorige.
- Produces: nichts.

- [ ] **Step 1: Plugin-CLAUDE.md schreiben**

Create `backend/app/plugins/installed/display_output/CLAUDE.md`:

```markdown
# Display Output Plugin

Bundled (in-process, fully trusted) plugin: enumerates the KWin outputs, picks
which one is active and sets its video mode, driven from a popover in the topbar.
Ships its own FastAPI router; the UI is a **core** component, not a sandbox bundle.

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md` —
this file only covers what is specific to this plugin.

## Layout

| File | Contents |
|---|---|
| `__init__.py` | `DisplayOutputPlugin`, the router, the audit helper, the error mapping |
| `kscreen.py` | The **only** module that knows `kscreen-doctor` exists: parser, runner, argv builder |
| `backend.py` | `DisplayBackend` protocol, `DevDisplayBackend`, `KWinDisplayBackend` |
| `service.py` | `DisplayService` — backend choice, the whole validation, module singleton |
| `models.py` | Pydantic models; the field names are the API contract to the frontend |

Frontend counterparts: `client/src/components/topbar/DisplayMenu.tsx`,
`client/src/api/displayOutput.ts`, `client/src/i18n/locales/{de,en}/display.json`.

## Why it must be a bundled plugin

Same reason as `audio_control`: the plugin runs in the host process and therefore
under the same UID as the desktop session, which is what gets it to the KWin
socket through `wayland_session_env()` alone — no sudo, no wrapper. A **sandbox
plugin would not reach the socket at all**: it runs as `baluhost-plugin` in its
own network namespace.

Measured proof of the env's necessity: `kscreen-doctor -j` from an SSH session
without `XDG_RUNTIME_DIR`/`WAYLAND_DISPLAY` aborts — Qt falls back to the `xcb`
platform plugin and finds no display.

## Mode names are ambiguous — address modes by ID

`libkscreen`'s `findMode()` builds a mode's name with `qRound(refreshRate)`:

    "%1x%2@%3".arg(width, height, qRound(mode->refreshRate()))
    if (mode->id() == query || name == query) return mode;

So 119.88 and 120.000 are **both** called `3840x2160@120`, and the function
returns the first match and stops. Measured on BaluNode: HDMI-A-1 has 55 modes
but only 45 distinct names; DP-3's ids 57 and 58 are exactly that pair.

Addressing by name would therefore set an arbitrary member of the group, with no
error. The same code line proves the ID **is** a valid argument, so that is what
is used.

**But never a stored ID.** That is the defect in #589, where a hard-coded id in
`deploy/scripts/display-switch` outlives the reboot that renumbered it. Here the
id comes from the enumeration of the same request cycle and `apply` re-reads and
cross-checks it against the client-supplied `mode_name` — a mismatch is a 409,
not a silently wrong mode. `mode_id` and `mode_name` are all-or-nothing on the
wire; accepting one without the other would make the cross-check optional.

## Two levels of "on"

| Level | Source | Field |
|---|---|---|
| KWin | `kscreen-doctor -j`, `enabled` | `selected` |
| DRM | sysfs `enabled` per connector | `lit` |

With DPMS off **every** DRM connector is `disabled` while KWin keeps its choice —
that is why `DesktopTogglePanel` can say "stopped" while KWin holds DP-3 active.
Not a bug, two truths about different things. They are never folded into one
field, and a name that maps to no connector yields `lit=None`, not `False`:
reporting an unknown answer as "off" would be a false statement.

`get_connector_states()` lives in `services/power/gpu/display_detector.py`, not
here — `desktop_backend` and `steam_gaming` already read that sysfs tree.

## `kscreen-doctor` lists only connected outputs

`/sys/class/drm/` shows `card0-DP-1` and `card0-DP-2` on BaluNode; the JSON does
not mention them. `connected` stays in the schema but is true in practice, and
`DevDisplayBackend` deliberately serves **no** disconnected output — it would be
a state the real backend never produces.

Field presence also varies between outputs: HDMI-A-1 carries `vrrPolicy`, DP-3
does not. Every field access goes through `.get()`.

## Security invariants

- **Every route** carries `require_power_manage_displays` — the reading one
  included. The output list reveals the attached hardware, EDID sizes included.
- **Every route** carries `@user_limiter.limit(get_limit("display_output"))`,
  its own category at `60/minute`: the popover polls only while open, every 5 s.
- **Nothing from the request becomes an argv element without having appeared in
  the live enumeration first.** Names and mode ids are matched against measured
  values, not escaped or filtered. List-args already rule out shell injection —
  this is the belt to that suspender.
- **`kscreen-doctor` output never reaches a client.** stdout/stderr carry EDID
  names and paths; they are logged, and a success answers `{"success": true}`.
- **An `apply` after which no connected output would be selected is rejected.**
  "Nothing should be lit" belongs on the DPMS switch in `PowerMenu` — reversible,
  and it does not throw the KWin configuration away.
- One `apply` is exactly **one** `kscreen-doctor` invocation; the tool applies
  all arguments together, so there is no partial state on failure. The argument
  order follows the enumeration, not the request — deterministic and beyond
  client influence.

## The two traps inherited from `audio_control`

**No `from __future__ import annotations` in `__init__.py`.** With Pydantic v2
and FastAPI's body detection through slowapi's `@user_limiter.limit` wrapper,
deferred annotations become ForwardRefs FastAPI no longer resolves — the request
body is mistaken for query parameters and every `POST` answers 422.

**`get_ui_manifest()` must be overridden.** `PluginBase` returns `None`, and only
plugins with a truthy manifest appear in `GET /api/plugins/ui/manifest` — exactly
the list `usePluginEnabled('display_output')` reads. Without it the plugin counts
as disabled forever and the topbar stays empty, with no error and no log line.

## Routes

| Method | Path | Body |
|---|---|---|
| GET | `/state` | — (returns outputs, `displays_powered`, `available`, `detail`) |
| POST | `/apply` | `{"outputs": [{"name", "selected", "mode_id"?, "mode_name"?}]}` |

Failure mapping: validation → 400, stale `mode_name` for a live `mode_id` → 409,
KWin unreachable on a write → 502. A **read** with an unreachable session is not
an error — it answers 200 with `available: false` so the UI can show that state.

Because the plugin contributes a router, it is mounted **once at startup**
(`core/lifespan.py`). Enabling it at runtime leaves these paths at 404 until
`baluhost-backend` restarts.

## Permission

`can_manage_displays` (table `user_power_permissions`, migration `b8c41d92e7f5`,
`server_default="0"` — denied by default). It stands **beside** the sleep/suspend
chains and is deliberately absent from `_apply_implications`; admins get it
implicitly.

## Tests

`backend/tests/plugins/test_display_output_{parser,kscreen,backend,service,routes,ui_manifest}.py`
plus `backend/tests/test_display_detector_connector_states.py`.

The fixture `backend/tests/plugins/fixtures/kscreen_balunode.json` is a
**measured** `kscreen-doctor -j` recording from BaluNode (2026-09-08), not an
invented payload. The duplicate and ambiguous modes in it are the test subject —
re-measure rather than hand-edit. No test invokes real `kscreen-doctor`; the CI
runner has no Wayland session.
```

- [ ] **Step 2: Verzeichnisbaum nachziehen**

In `backend/app/plugins/CLAUDE.md` im Baum unter `installed/` nach der
`audio_control`-Zeile einfügen:

```
    ├── display_output/      # KWin-Ausgangswahl und Video-Modus (kscreen-doctor)
```

- [ ] **Step 3: API-Liste und Quick Reference**

In `.claude/rules/architecture.md` in der API-Liste nach der
`/api/plugins/audio_control/*`-Zeile:

```
- `/api/plugins/display_output/*` - Displaysteuerung (Ausgangswahl, Video-Modus)
```

In `CLAUDE.md` unter „Quick Reference: Finding Things" nach der
`**Audio control**`-Zeile:

```
**Display outputs**: `backend/app/plugins/installed/display_output/` (bundled Plugin; `kscreen.py` kapselt den gesamten kscreen-doctor-Kontakt)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/plugins/installed/display_output/CLAUDE.md backend/app/plugins/CLAUDE.md .claude/rules/architecture.md CLAUDE.md
git commit -m "docs(display-output): Plugin-CLAUDE.md und Verweise im Kontext-Baum"
```

---

## Task 12: Abnahme auf BaluNode

**Files:** keine.

**Interfaces:**
- Consumes: alles Vorige.
- Produces: die Bestätigung, dass wirklich ein Bild kommt.

Bis hierhin belegen grüne Tests die Logik, nicht das Bild. Diese Aufgabe braucht
physischen Blick auf die Schirme und läuft **nach** dem Deploy des Branches.

- [ ] **Step 1: Migration und Neustart**

Das Plugin bringt einen Router mit, der nur beim Start gemountet wird. Nach dem
Deploy:

```
sudo systemctl restart baluhost-backend
```

- [ ] **Step 2: Plugin aktivieren und Recht vergeben**

In der Webapp unter Plugins `display_output` aktivieren. Als Admin ist das Recht
implizit da; für einen delegierten Test einem Nicht-Admin `can_manage_displays`
in der Nutzerverwaltung geben.

- [ ] **Step 3: Enumeration prüfen**

Popover öffnen. Erwartet: **zwei** Ausgänge (`HDMI-A-1`, `DP-3`), kein DP-1/DP-2.
Bei DP-3 müssen im Auswahlfeld zwei unterscheidbare 4K-Einträge stehen —
`3840 × 2160 @ 120,00 Hz` und `3840 × 2160 @ 119,88 Hz`. Stehen sie identisch da,
greift `formatMode` nicht.

- [ ] **Step 4: Die `lit`-Annahme bestätigen**

Vergleiche für jeden Ausgang das Abzeichen „leuchtet"/„dunkel" mit dem, was
wirklich auf den Schirmen zu sehen ist. Steht dort dauerhaft „Zustand unbekannt",
hält die Präfix-Annahme `card0-DP-3` → `DP-3` auf diesem Host nicht und der Fund
gehört gemeldet — **nicht** durch Raten geschlossen.

- [ ] **Step 5: Umschalten und zurück**

HDMI-A-1 wählen, DP-3 abwählen, Anwenden. Das Bild muss auf dem Monitor
erscheinen. Dann Modus auf einen anderen Eintrag setzen, Anwenden. Danach zurück
auf DP-3 mit `3840 × 2160 @ 120,00 Hz`.

- [ ] **Step 6: Die Invariante prüfen**

Beide Ausgänge abwählen — „Anwenden" muss gesperrt sein. Wird der Aufruf doch
abgesetzt (etwa direkt gegen die API), muss er 400 liefern.

- [ ] **Step 7: Audit-Eintrag prüfen**

Unter Logging muss je Anwendung ein `display_apply`-Eintrag stehen, und bei einem
Nicht-Admin zusätzlich ein `delegated_power_action`.

- [ ] **Step 8: Ergebnis festhalten**

Das Ergebnis in #590 kommentieren, insbesondere ob Schritt 4 die
Präfix-Annahme bestätigt hat.

---

## Reihenfolge und Abhängigkeiten

```
T1 (Fixture, Modelle, Parser)
 └─ T2 (Runner, argv)
     └─ T4 (Backends) ← T3 (DRM-Connector-Zustände)
         └─ T5 (Service, Validierung)
             └─ T7 (Router) ← T6 (Recht can_manage_displays)
                 └─ T8 (API-Client, i18n)
                     └─ T9 (Popover)   T10 (Nutzerverwaltung)
                         └─ T11 (Doku)
                             └─ T12 (Abnahme auf BaluNode)
```

T3, T6 und T10 hängen an nichts aus dem Plugin und können vorgezogen werden.
