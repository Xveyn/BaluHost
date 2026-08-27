# Audiosteuerung (bundled Plugin `audio_control`) — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein optionales bundled Plugin, mit dem sich aus einem Popover in der Topbar der Master-Pegel, das Ausgabegerät und die Lautstärke einzelner Anwendungen der KDE-Session fernsteuern lassen.

**Architecture:** Das Plugin liegt unter `backend/app/plugins/installed/audio_control/` und läuft als bundled Plugin im Host-Prozess, also unter `sven` — dadurch erreicht es den PipeWire-Socket allein über `XDG_RUNTIME_DIR`, ohne Sudo. Sämtlicher Kontakt zu `pactl` ist in einer einzigen Datei gekapselt; darüber liegen ein Protocol mit Dev- und PipeWire-Implementierung, ein dünner Service und die Routen. Im Frontend kommt eine Core-Komponente in die Topbar, die nur erscheint, wenn das Plugin aktiv ist und der Benutzer das neue Recht `can_control_audio` besitzt.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, pytest — React 18, TypeScript, Tailwind, i18next, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-27-audio-control-design.md`

## Global Constraints

- **Nur `pactl`.** `wpctl`, `pw-cli` und `pw-dump` dürfen im Produktionscode nicht vorkommen. `pactl` und `wpctl` haben getrennte ID-Räume (derselbe Ausgang ist bei `pactl` 61, bei `wpctl` 35); ein Mischen erzeugt Verwechslungen.
- **Kein `shell=True`.** Ausschließlich Listen-Argumente, Timeout 5 s.
- **Pegelbereich 0–150 %**, serverseitig erzwungen.
- **Jede Route** trägt `require_power_control_audio` — auch die lesende — sowie `@user_limiter.limit(get_limit("audio_control"))`.
- **Neue Alembic-Migration kettet an `16ea14ef13bb`** (aktueller einziger Head), niemals an den Kopf der Dev-Datenbank.
- **Standard ist Verweigerung:** neue Spalte mit `server_default="0"`.
- **Kommentare und Doku auf Deutsch**, dem Repo-Stil folgend; Bezeichner im Code englisch.
- **Type Hints auf allen Funktionen**, Docstrings auf allen Services (`.claude/rules/backend/coding-style.md`).
- Dateien bleiben unter 500 Zeilen.

---

## Datenlage

Beide JSON-Formen sind an der Produktionsmaschine gemessen (PipeWire 1.4.2), die Fixtures in Task 2 sind wörtliche Auszüge daraus — keine Annahmen.

`pactl -f json list sinks` liefert je Gerät unter anderem `index`, `state`, `name`, `description`, `mute`, `volume` (kanalweise, mit `value_percent` als **String**), `base_volume`, `ports`, `active_port` und einen umfangreichen `properties`-Block. Der Parser liest daraus nur `index`, `name`, `description`, `mute` und `volume`; alle übrigen Felder werden bewusst ignoriert und sind in den Fixtures gekürzt.

**Indizes sind flüchtig.** Derselbe GPU-Ausgang trug innerhalb einer Stunde nacheinander die Indizes 655, 90 und 731. Kein Index darf über einen Abfragezyklus hinaus als gültig angenommen werden — deshalb ist ein 404 auf einen unbekannten Index ein Normalfall.

---

## Task 1: Recht `can_control_audio` im Backend

**Files:**
- Modify: `backend/app/models/power_permissions.py`
- Create: `backend/alembic/versions/a7d3c9f18e42_add_can_control_audio_permission.py`
- Modify: `backend/app/schemas/power_permissions.py`
- Modify: `backend/app/services/power_permissions.py`
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/routes/sleep.py`
- Test: `backend/tests/api/test_power_permissions_routes.py` (erweitern)

**Interfaces:**
- Produces: Spalte `UserPowerPermission.can_control_audio`; Feld `can_control_audio` in `UserPowerPermissionsResponse`, `UserPowerPermissionsUpdate`, `MyPowerPermissionsResponse`; Aktionsschlüssel `"control_audio"` in `_ACTION_FIELD_MAP`; Abhängigkeit `require_power_control_audio` in `app.api.deps` (Signatur wie die übrigen `require_power_*`: liefert `UserPublic`, wirft 403).

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

**Zuerst** `backend/tests/api/test_power_permissions_routes.py` ganz lesen und die dort tatsächlich vorhandenen Fixtures notieren. Der folgende Testcode nimmt `client`, `admin_headers` und `regular_user` an; heißen sie anders oder liefern sie etwas anderes (etwa ein Token statt fertiger Header), sind die Aufrufe daran anzupassen. Der Testinhalt bleibt derselbe, nur die Fixture-Namen folgen der Datei — keine neuen Fixtures anlegen, die es schon gibt.

Dann anhängen:

```python
class TestAudioControlPermission:
    """Das Recht can_control_audio verhält sich wie can_toggle_desktop."""

    def test_get_permissions_includes_audio_field(self, client, admin_headers, regular_user):
        resp = client.get(
            f"/api/users/{regular_user.id}/power-permissions", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["can_control_audio"] is False

    def test_put_grants_audio_permission(self, client, admin_headers, regular_user):
        resp = client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            headers=admin_headers,
            json={"can_control_audio": True},
        )
        assert resp.status_code == 200
        assert resp.json()["can_control_audio"] is True

    def test_audio_permission_does_not_imply_anything(self, client, admin_headers, regular_user):
        """Es steht unabhängig neben den Sleep-/Suspend-Ketten."""
        resp = client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            headers=admin_headers,
            json={"can_control_audio": True},
        )
        body = resp.json()
        assert body["can_control_audio"] is True
        assert body["can_soft_sleep"] is False
        assert body["can_wake"] is False
        assert body["can_suspend"] is False
        assert body["can_wol"] is False

    def test_my_permissions_reports_audio_for_admin(self, client, admin_headers):
        resp = client.get("/api/system/sleep/my-permissions", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["can_control_audio"] is True
```

> Die Fixtures `client`, `admin_headers` und `regular_user` existieren in dieser Datei bereits — den vorhandenen Fixture-Namen im Modulkopf folgen und nichts neu erfinden.

- [ ] **Step 2: Test laufen lassen und Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/api/test_power_permissions_routes.py::TestAudioControlPermission -v --no-cov`
Expected: FAIL — `KeyError: 'can_control_audio'`.

- [ ] **Step 3: Spalte im Modell ergänzen**

In `backend/app/models/power_permissions.py` direkt nach der Zeile mit `can_unlock_session` einfügen:

```python
    can_control_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
```

- [ ] **Step 4: Migration anlegen**

Neue Datei `backend/alembic/versions/a7d3c9f18e42_add_can_control_audio_permission.py`:

```python
"""add can_control_audio permission

Revision ID: a7d3c9f18e42
Revises: 16ea14ef13bb
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3c9f18e42'
down_revision: Union[str, Sequence[str], None] = '16ea14ef13bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt can_control_audio zu user_power_permissions hinzu (standardmäßig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_control_audio', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_control_audio."""
    op.drop_column('user_power_permissions', 'can_control_audio')
```

> `16ea14ef13bb` ist der zum Planungszeitpunkt einzige Head. Vor dem Anlegen mit `cd backend ; python -m alembic heads` gegenprüfen; weicht der Wert ab, den tatsächlichen Head eintragen. Ein Verstoß dagegen hat hier schon einmal einen Produktions-Deploy mit mehreren Heads zerlegt.

- [ ] **Step 5: Migration anwenden und einzelnen Head bestätigen**

Run: `cd backend ; python -m alembic upgrade head ; python -m alembic heads`
Expected: Upgrade läuft durch, `heads` gibt **genau eine** Revision aus (`a7d3c9f18e42 (head)`).

- [ ] **Step 6: Schemas erweitern**

In `backend/app/schemas/power_permissions.py`:

In `UserPowerPermissionsResponse` nach `can_unlock_session`:
```python
    can_control_audio: bool = False
```

In `UserPowerPermissionsUpdate` nach `can_unlock_session`:
```python
    can_control_audio: Optional[bool] = Field(default=None, description="Allow controlling desktop audio (volume, output device, per-app mixer)")
```

In `MyPowerPermissionsResponse` nach `can_unlock_session`:
```python
    can_control_audio: bool = False
```

- [ ] **Step 7: Service erweitern**

In `backend/app/services/power_permissions.py`:

`_ACTION_FIELD_MAP` um einen Eintrag ergänzen:
```python
    "control_audio": "can_control_audio",
```

In `get_permissions`, im `UserPowerPermissionsResponse(...)`-Aufruf nach `can_unlock_session=perm.can_unlock_session,`:
```python
        can_control_audio=perm.can_control_audio,
```

In `update_permissions` in **beiden** Wörterbüchern `old_values` und `new_values` jeweils nach der `can_unlock_session`-Zeile:
```python
        "can_control_audio": perm.can_control_audio,
```

Und bei den expliziten Zuweisungen, direkt nach dem `can_unlock_session`-Block:
```python
    if update.can_control_audio is not None:
        perm.can_control_audio = update.can_control_audio
```

> **Nicht** in `_apply_implications` aufnehmen. Das Recht steht unabhängig neben den Sleep-/Suspend-Ketten.

- [ ] **Step 8: Abhängigkeit ergänzen**

In `backend/app/api/deps.py` unter die bestehenden `require_power_*`-Zeilen:

```python
require_power_control_audio = _make_power_dependency("control_audio")
```

- [ ] **Step 9: `my-permissions` erweitern**

In `backend/app/api/routes/sleep.py`, in `get_my_power_permissions`:

Im Admin-Zweig `can_unlock_session=True,` ergänzen um:
```python
            can_control_audio=True,
```

Im Nicht-Admin-Rückgabewert nach `can_unlock_session=perms.can_unlock_session,`:
```python
        can_control_audio=perms.can_control_audio,
```

- [ ] **Step 10: Tests laufen lassen und Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/api/test_power_permissions_routes.py -v --no-cov`
Expected: PASS, einschließlich der vier neuen Tests und aller vorhandenen.

- [ ] **Step 11: Commit**

```bash
git add backend/app/models/power_permissions.py backend/alembic/versions/a7d3c9f18e42_add_can_control_audio_permission.py backend/app/schemas/power_permissions.py backend/app/services/power_permissions.py backend/app/api/deps.py backend/app/api/routes/sleep.py backend/tests/api/test_power_permissions_routes.py
git commit -m "feat(audio): delegierbares Recht can_control_audio ergaenzen"
```

---

## Task 2: Modelle und `pactl`-Parser

**Files:**
- Create: `backend/app/plugins/installed/audio_control/__init__.py` (vorerst leer)
- Create: `backend/app/plugins/installed/audio_control/models.py`
- Create: `backend/app/plugins/installed/audio_control/pactl.py`
- Test: `backend/tests/plugins/test_audio_control_parser.py`

**Interfaces:**
- Produces: `AudioSink`, `AudioStream`, `AudioState`, `VolumeRequest`, `MuteRequest`, `DefaultSinkRequest` aus `models.py`; aus `pactl.py` die reinen Funktionen `parse_percent(raw: object) -> int`, `volume_percent(volume: object) -> int`, `parse_sinks(payload: object, default_name: str | None) -> list[AudioSink]`, `parse_streams(payload: object) -> list[AudioStream]`.

> Dieser Task enthält **keinen** Subprozess-Aufruf. Nur reine Funktionen, damit sie ohne PipeWire testbar sind. Der Aufruf folgt in Task 3.

- [ ] **Step 1: Paketverzeichnis anlegen**

```bash
mkdir -p backend/app/plugins/installed/audio_control
```

`backend/app/plugins/installed/audio_control/__init__.py` mit vorläufigem Inhalt anlegen:

```python
"""Audiosteuerung — bundled Plugin (Aufbau folgt in Task 4)."""
```

> Solange keine `PluginBase`-Unterklasse darin liegt, überspringt der `PluginManager` das Verzeichnis bei der Erkennung. Das ist beabsichtigt: Tasks 2 und 3 sollen die Anwendung nicht verändern.

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

Neue Datei `backend/tests/plugins/test_audio_control_parser.py`:

```python
"""Parser-Tests gegen die an der Produktionsmaschine gemessene pactl-Ausgabe."""
import json

import pytest

from app.plugins.installed.audio_control.pactl import (
    parse_percent,
    parse_sinks,
    parse_streams,
    volume_percent,
)

# Wörtlich gemessen auf BaluNode (PipeWire 1.4.2), gekürzt um irrelevante Felder.
REAL_SINK_INPUT = {
    "index": 789,
    "driver": "PipeWire",
    "owner_module": None,
    "client": "788",
    "sink": 61,
    "corked": False,
    "mute": False,
    "volume": {
        "front-left": {"value": 36305, "value_percent": "55%", "db": "-15.39 dB"},
        "front-right": {"value": 36305, "value_percent": "55%", "db": "-15.39 dB"},
    },
    "balance": 0.00,
    "properties": {
        "client.api": "pipewire-pulse",
        "application.name": "Firefox",
        "application.process.id": "367248",
        "application.process.binary": "firefox-esr",
        "media.name": "(10) Caller Broke Into a Smoke Shop — YouTube",
        "media.class": "Stream/Output/Audio",
        "node.name": "Firefox",
    },
}

REAL_SINK = {
    "index": 61,
    "state": "SUSPENDED",
    "name": "alsa_output.pci-0000_0e_00.6.iec958-stereo",
    "description": "Ryzen HD Audio Controller Digitales Stereo (IEC958)",
    "driver": "PipeWire",
    "mute": False,
    "volume": {
        "front-left": {"value": 62259, "value_percent": "95%", "db": "-1.34 dB"},
        "front-right": {"value": 62259, "value_percent": "95%", "db": "-1.34 dB"},
    },
    "balance": 0.00,
    "base_volume": {"value": 65536, "value_percent": "100%", "db": "0.00 dB"},
    "active_port": "iec958-stereo-output",
    "properties": {"device.description": "Ryzen HD Audio Controller"},
}

REAL_SINK_GPU = {
    "index": 731,
    "state": "SUSPENDED",
    "name": "alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3",
    "description": "Navi 31 HDMI/DP Audio Digital Stereo (HDMI 4)",
    "mute": False,
    "volume": {
        "front-left": {"value": 65536, "value_percent": "100%", "db": "0.00 dB"},
        "front-right": {"value": 65536, "value_percent": "100%", "db": "0.00 dB"},
    },
    "properties": {"device.description": "Navi 31 HDMI/DP Audio"},
}


class TestParsePercent:
    def test_strips_the_percent_sign(self):
        assert parse_percent("55%") == 55

    def test_accepts_a_plain_number(self):
        assert parse_percent(42) == 42

    def test_unparsable_input_becomes_zero(self):
        """Ein defekter Wert darf niemals eine Ausnahme nach oben werfen."""
        assert parse_percent("laut") == 0
        assert parse_percent(None) == 0
        assert parse_percent({}) == 0

    def test_negative_is_clamped_to_zero(self):
        assert parse_percent("-5%") == 0


class TestVolumePercent:
    def test_takes_the_maximum_across_channels(self):
        volume = {
            "front-left": {"value_percent": "40%"},
            "front-right": {"value_percent": "60%"},
        }
        assert volume_percent(volume) == 60

    def test_missing_volume_is_zero(self):
        assert volume_percent(None) == 0
        assert volume_percent({}) == 0


class TestParseStreams:
    def test_parses_the_measured_firefox_stream(self):
        streams = parse_streams([REAL_SINK_INPUT])
        assert len(streams) == 1
        stream = streams[0]
        assert stream.id == 789
        assert stream.sink_id == 61
        assert stream.application == "Firefox"
        assert stream.binary == "firefox-esr"
        assert stream.title == "(10) Caller Broke Into a Smoke Shop — YouTube"
        assert stream.volume_percent == 55
        assert stream.muted is False
        assert stream.corked is False

    def test_falls_back_to_node_name_then_placeholder(self):
        """Spiele über Proton fuellen application.name nicht zwingend."""
        without_app = json.loads(json.dumps(REAL_SINK_INPUT))
        del without_app["properties"]["application.name"]
        assert parse_streams([without_app])[0].application == "Firefox"

        without_both = json.loads(json.dumps(without_app))
        del without_both["properties"]["node.name"]
        assert parse_streams([without_both])[0].application == "Unbekannt"

    def test_filters_out_non_output_streams(self):
        recording = json.loads(json.dumps(REAL_SINK_INPUT))
        recording["properties"]["media.class"] = "Stream/Input/Audio"
        assert parse_streams([recording]) == []

    def test_empty_payload_is_an_empty_list(self):
        assert parse_streams([]) == []

    def test_garbage_entries_are_skipped_not_fatal(self):
        assert parse_streams([{"nonsense": True}, REAL_SINK_INPUT]) == parse_streams(
            [REAL_SINK_INPUT]
        )


class TestParseSinks:
    def test_parses_a_sink_and_marks_the_default(self):
        sinks = parse_sinks([REAL_SINK], "alsa_output.pci-0000_0e_00.6.iec958-stereo")
        assert len(sinks) == 1
        sink = sinks[0]
        assert sink.id == 61
        assert sink.name == "alsa_output.pci-0000_0e_00.6.iec958-stereo"
        assert sink.description == "Ryzen HD Audio Controller Digitales Stereo (IEC958)"
        assert sink.volume_percent == 95
        assert sink.muted is False
        assert sink.is_default is True

    def test_an_absent_default_marks_nothing(self):
        """Das konfigurierte Bluetooth-Geraet fehlt meist — das ist zulaessig."""
        sinks = parse_sinks([REAL_SINK], "bluez_output.C8_2B_6B_35_0D_B3.1")
        assert sinks[0].is_default is False

    def test_no_default_name_marks_nothing(self):
        assert parse_sinks([REAL_SINK], None)[0].is_default is False

    def test_exactly_one_of_two_sinks_is_default(self):
        sinks = parse_sinks(
            [REAL_SINK, REAL_SINK_GPU], "alsa_output.pci-0000_0e_00.6.iec958-stereo"
        )
        assert [s.id for s in sinks] == [61, 731]
        assert [s.is_default for s in sinks] == [True, False]

    def test_a_sink_without_description_falls_back_to_its_name(self):
        bare = {k: v for k, v in REAL_SINK.items() if k != "description"}
        assert parse_sinks([bare], None)[0].description == bare["name"]
```

- [ ] **Step 3: Test laufen lassen und Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_audio_control_parser.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.installed.audio_control.pactl'`.

- [ ] **Step 4: `models.py` schreiben**

Neue Datei `backend/app/plugins/installed/audio_control/models.py`:

```python
"""Pydantic-Modelle der Audiosteuerung.

Die Feldnamen sind zugleich der API-Vertrag zum Frontend.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# PipeWire laesst Uebersteuerung zu. Ohne Deckel koennte ein Aufrufer 1000 %
# setzen und die Boxen beschaedigen.
MAX_VOLUME_PERCENT = 150


class AudioSink(BaseModel):
    """Ein Ausgabegeraet."""

    id: int = Field(..., description="pactl-Index des Sinks")
    name: str = Field(..., description="Technischer Name, z. B. alsa_output.pci-...")
    description: str = Field(..., description="Anzeigename")
    volume_percent: int = Field(..., description="Pegel in Prozent")
    muted: bool
    is_default: bool = Field(..., description="Das aktive Standardgeraet")


class AudioStream(BaseModel):
    """Ein laufender Wiedergabe-Stream (in pactl: sink-input)."""

    id: int = Field(..., description="pactl-Index des Sink-Inputs")
    sink_id: int = Field(..., description="Sink, auf dem der Stream liegt")
    application: str = Field(..., description="Anzeigename der Anwendung")
    binary: Optional[str] = Field(default=None, description="Programmdatei, fuer die Icon-Zuordnung")
    title: Optional[str] = Field(default=None, description="media.name — nur als Tooltip verwenden")
    volume_percent: int
    muted: bool
    corked: bool = Field(..., description="True, wenn die Wiedergabe pausiert ist")


class AudioState(BaseModel):
    """Gesamtzustand, wie ihn GET /state liefert."""

    sinks: List[AudioSink] = Field(default_factory=list)
    streams: List[AudioStream] = Field(default_factory=list)
    available: bool = Field(default=True, description="False, wenn PipeWire nicht erreichbar ist")
    detail: Optional[str] = Field(default=None, description="Kurzer Hinweis fuer die UI")


class VolumeRequest(BaseModel):
    """Rumpf der Pegel-Routen."""

    percent: int = Field(..., ge=0, le=MAX_VOLUME_PERCENT)


class MuteRequest(BaseModel):
    """Rumpf der Mute-Routen."""

    muted: bool


class DefaultSinkRequest(BaseModel):
    """Rumpf der Standardgeraet-Route."""

    name: str = Field(..., min_length=1, max_length=256)
```

- [ ] **Step 5: Den Parserteil von `pactl.py` schreiben**

Neue Datei `backend/app/plugins/installed/audio_control/pactl.py`:

```python
"""Der einzige Ort, der weiss, dass es pactl gibt.

Dieses Modul kapselt Aufruf und Auswertung von ``pactl``. Ein spaeterer
Wechsel auf eine PipeWire-Bibliothek beruehrt nur diese Datei.

Bewusst ausschliesslich ``pactl``: ``wpctl`` fuehrt einen eigenen ID-Raum
(derselbe Ausgang ist bei pactl 61 und bei wpctl 35), und ein Mischen beider
Werkzeuge erzeugt Verwechslungen, die erst im Betrieb auffallen.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.plugins.installed.audio_control.models import AudioSink, AudioStream

logger = logging.getLogger(__name__)

# Nur Wiedergabe-Streams gehoeren in den Ausgabe-Mixer.
_OUTPUT_MEDIA_CLASS = "Stream/Output/Audio"

# Wenn weder application.name noch node.name gesetzt sind.
_UNKNOWN_APPLICATION = "Unbekannt"


def parse_percent(raw: object) -> int:
    """Wandelt einen pactl-Prozentwert in eine Zahl.

    pactl liefert Prozente als Zeichenkette mit Zeichen, etwa ``"55%"``.

    Args:
        raw: Der Rohwert aus der JSON-Ausgabe.

    Returns:
        Der Prozentwert, mindestens 0. Nicht auswertbare Eingaben ergeben 0 —
        ein defekter Wert darf die gesamte Zustandsabfrage nicht scheitern
        lassen.
    """
    if isinstance(raw, bool):
        logger.debug("Prozentwert war ein Wahrheitswert: %r", raw)
        return 0
    if isinstance(raw, (int, float)):
        try:
            return max(0, int(raw))
        except (ValueError, OverflowError):
            # int(float("inf")) wirft OverflowError, keinen ValueError.
            logger.debug("Prozentwert nicht in eine Ganzzahl wandelbar: %r", raw)
            return 0
    if isinstance(raw, str):
        try:
            return max(0, int(float(raw.strip().rstrip("%"))))
        except (ValueError, OverflowError):
            # "inf%" laesst float() passieren und bringt erst int() zu Fall.
            logger.debug("Prozentwert nicht auswertbar: %r", raw)
            return 0
    logger.debug("Prozentwert von unerwartetem Typ %s: %r", type(raw).__name__, raw)
    return 0


def volume_percent(volume: object) -> int:
    """Reduziert die kanalweise Lautstaerke auf einen Wert.

    pactl gibt den Pegel je Kanal aus. Die UI kennt nur einen Regler, deshalb
    wird das Maximum ueber alle Kanaele gelesen.

    Args:
        volume: Das ``volume``-Objekt aus der JSON-Ausgabe.

    Returns:
        Der hoechste Kanalpegel in Prozent, 0 wenn nichts auswertbar ist.
    """
    if not isinstance(volume, dict) or not volume:
        logger.debug("Lautstaerke fehlt oder hat unerwartete Form: %r", volume)
        return 0
    values = [
        parse_percent(channel.get("value_percent"))
        for channel in volume.values()
        if isinstance(channel, dict)
    ]
    return max(values) if values else 0


def parse_sinks(payload: object, default_name: Optional[str]) -> List[AudioSink]:
    """Wertet die Ausgabe von ``pactl -f json list sinks`` aus.

    Args:
        payload: Die geparste JSON-Liste.
        default_name: Name des aktiven Standardgeraets aus
            ``pactl get-default-sink``, oder None.

    Returns:
        Die Geraeteliste. Eintraege, die sich nicht auswerten lassen, werden
        uebersprungen statt die ganze Liste scheitern zu lassen.
    """
    if not isinstance(payload, list):
        logger.warning("Unerwartete Sink-Ausgabe: %s", type(payload).__name__)
        return []

    sinks: List[AudioSink] = []
    for entry in payload:
        if not isinstance(entry, dict):
            logger.debug("Sink-Eintrag ist kein Objekt, uebersprungen: %r", entry)
            continue
        try:
            name = str(entry["name"])
            sinks.append(
                AudioSink(
                    id=int(entry["index"]),
                    name=name,
                    description=str(entry.get("description") or name),
                    volume_percent=volume_percent(entry.get("volume")),
                    muted=bool(entry.get("mute", False)),
                    is_default=bool(default_name) and name == default_name,
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.debug("Sink-Eintrag uebersprungen", exc_info=True)
    return sinks


def parse_streams(payload: object) -> List[AudioStream]:
    """Wertet die Ausgabe von ``pactl -f json list sink-inputs`` aus.

    Args:
        payload: Die geparste JSON-Liste.

    Returns:
        Die Wiedergabe-Streams. Aufnahme-Streams werden ausgefiltert.
    """
    if not isinstance(payload, list):
        logger.warning("Unerwartete Stream-Ausgabe: %s", type(payload).__name__)
        return []

    streams: List[AudioStream] = []
    for entry in payload:
        if not isinstance(entry, dict):
            logger.debug("Stream-Eintrag ist kein Objekt, uebersprungen: %r", entry)
            continue
        props = entry.get("properties")
        if not isinstance(props, dict):
            logger.debug("Stream ohne auswertbare properties, uebersprungen")
            continue
        if props.get("media.class") != _OUTPUT_MEDIA_CLASS:
            continue
        try:
            streams.append(
                AudioStream(
                    id=int(entry["index"]),
                    sink_id=int(entry["sink"]),
                    application=str(
                        props.get("application.name")
                        or props.get("node.name")
                        or _UNKNOWN_APPLICATION
                    ),
                    binary=_optional_str(props.get("application.process.binary")),
                    title=_optional_str(props.get("media.name")),
                    volume_percent=volume_percent(entry.get("volume")),
                    muted=bool(entry.get("mute", False)),
                    corked=bool(entry.get("corked", False)),
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.debug("Stream-Eintrag uebersprungen", exc_info=True)
    return streams


def _optional_str(raw: object) -> Optional[str]:
    """Gibt eine nicht-leere Zeichenkette zurueck, sonst None."""
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None
```

- [ ] **Step 6: Tests laufen lassen und Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_audio_control_parser.py -v --no-cov`
Expected: PASS (alle Tests der vier Klassen).

- [ ] **Step 7: Lint**

Run: `cd backend ; python -m ruff check app/plugins/installed/audio_control tests/plugins/test_audio_control_parser.py`
Expected: keine Befunde.

- [ ] **Step 8: Commit**

```bash
git add backend/app/plugins/installed/audio_control backend/tests/plugins/test_audio_control_parser.py
git commit -m "feat(audio): Modelle und pactl-Parser mit gemessener JSON-Fixture"
```

---

## Task 3: Backends und Service

**Files:**
- Modify: `backend/app/plugins/installed/audio_control/pactl.py` (Aufrufteil anfügen)
- Create: `backend/app/plugins/installed/audio_control/backend.py`
- Create: `backend/app/plugins/installed/audio_control/service.py`
- Test: `backend/tests/plugins/test_audio_control_backend.py`

**Interfaces:**
- Consumes: aus Task 2 `parse_sinks`, `parse_streams`, `AudioSink`, `AudioStream`, `AudioState`.
- Produces: `run_pactl(args: list[str]) -> tuple[bool, str]` und `run_pactl_json(args: list[str]) -> object | None` in `pactl.py`; das Protocol `AudioBackend` mit `get_state() -> AudioState`, `set_sink_volume(sink_id: int, percent: int) -> tuple[bool, str]`, `set_sink_mute(sink_id: int, muted: bool) -> tuple[bool, str]`, `set_default_sink(name: str) -> tuple[bool, str]`, `set_stream_volume(stream_id: int, percent: int) -> tuple[bool, str]`, `set_stream_mute(stream_id: int, muted: bool) -> tuple[bool, str]`; die Klassen `DevAudioBackend` und `PipeWireAudioBackend`; `AudioService` mit derselben Methodenmenge und `get_audio_service() -> AudioService`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Neue Datei `backend/tests/plugins/test_audio_control_backend.py`:

```python
"""Tests fuer Dev-Backend und Service-Auswahl."""
import pytest

from app.plugins.installed.audio_control.backend import DevAudioBackend
from app.plugins.installed.audio_control.service import AudioService


@pytest.fixture
def backend() -> DevAudioBackend:
    return DevAudioBackend()


class TestDevBackendReads:
    @pytest.mark.asyncio
    async def test_reports_available_with_sinks_and_streams(self, backend):
        state = await backend.get_state()
        assert state.available is True
        assert len(state.sinks) == 2
        assert len(state.streams) == 2

    @pytest.mark.asyncio
    async def test_exactly_one_sink_is_default(self, backend):
        state = await backend.get_state()
        assert sum(1 for s in state.sinks if s.is_default) == 1


class TestDevBackendWrites:
    @pytest.mark.asyncio
    async def test_setting_sink_volume_is_visible_on_read(self, backend):
        state = await backend.get_state()
        sink_id = state.sinks[0].id

        ok, _ = await backend.set_sink_volume(sink_id, 33)
        assert ok is True

        state = await backend.get_state()
        assert next(s for s in state.sinks if s.id == sink_id).volume_percent == 33

    @pytest.mark.asyncio
    async def test_setting_sink_mute_is_visible_on_read(self, backend):
        state = await backend.get_state()
        sink_id = state.sinks[0].id

        await backend.set_sink_mute(sink_id, True)

        state = await backend.get_state()
        assert next(s for s in state.sinks if s.id == sink_id).muted is True

    @pytest.mark.asyncio
    async def test_changing_the_default_moves_the_marker(self, backend):
        state = await backend.get_state()
        target = next(s for s in state.sinks if not s.is_default)

        await backend.set_default_sink(target.name)

        state = await backend.get_state()
        assert next(s for s in state.sinks if s.id == target.id).is_default is True
        assert sum(1 for s in state.sinks if s.is_default) == 1

    @pytest.mark.asyncio
    async def test_setting_stream_volume_is_visible_on_read(self, backend):
        state = await backend.get_state()
        stream_id = state.streams[0].id

        await backend.set_stream_volume(stream_id, 12)

        state = await backend.get_state()
        assert next(s for s in state.streams if s.id == stream_id).volume_percent == 12

    @pytest.mark.asyncio
    async def test_setting_stream_mute_is_visible_on_read(self, backend):
        state = await backend.get_state()
        stream_id = state.streams[0].id

        await backend.set_stream_mute(stream_id, True)

        state = await backend.get_state()
        assert next(s for s in state.streams if s.id == stream_id).muted is True


class TestDevBackendUnknownIds:
    @pytest.mark.asyncio
    async def test_unknown_sink_reports_failure(self, backend):
        ok, message = await backend.set_sink_volume(9999, 50)
        assert ok is False
        assert message

    @pytest.mark.asyncio
    async def test_unknown_stream_reports_failure(self, backend):
        ok, _ = await backend.set_stream_mute(9999, True)
        assert ok is False

    @pytest.mark.asyncio
    async def test_unknown_default_sink_reports_failure(self, backend):
        ok, _ = await backend.set_default_sink("gibt.es.nicht")
        assert ok is False


class TestServiceSelectsDevBackendOffLinux:
    @pytest.mark.asyncio
    async def test_service_uses_the_injected_backend(self, backend):
        service = AudioService(backend=backend)
        state = await service.get_state()
        assert state.available is True

    @pytest.mark.asyncio
    async def test_service_picks_dev_backend_on_non_linux(self, monkeypatch):
        """Auf Windows darf niemals das PipeWire-Backend gewaehlt werden."""
        import app.plugins.installed.audio_control.service as svc

        monkeypatch.setattr(svc.platform, "system", lambda: "Windows")
        service = svc.AudioService()
        assert isinstance(service._backend, DevAudioBackend)
```

- [ ] **Step 2: Test laufen lassen und Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_audio_control_backend.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.installed.audio_control.backend'`.

- [ ] **Step 3: Aufrufteil an `pactl.py` anhängen**

Am Ende von `backend/app/plugins/installed/audio_control/pactl.py` anfügen, und den Importblock oben um `import json`, `import subprocess` sowie `from app.services.power.session_env import wayland_session_env` ergänzen:

```python
# pactl darf niemals haengen bleiben und dabei einen Worker blockieren.
PACTL_TIMEOUT_SECONDS = 5
PACTL_BINARY = "pactl"


def run_pactl(args: List[str]) -> tuple[bool, str]:
    """Fuehrt pactl mit Listen-Argumenten aus.

    Args:
        args: Argumente ohne den Programmnamen, etwa ``["set-sink-mute", "61", "1"]``.

    Returns:
        (Erfolg, Ausgabe bzw. Fehlertext). Die Ausgabe ist fuer Log und
        Auswertung gedacht und wird nicht an Clients weitergereicht — sie
        enthaelt Geraetenamen und Pfade.
    """
    try:
        completed = subprocess.run(
            [PACTL_BINARY, *args],
            capture_output=True,
            text=True,
            timeout=PACTL_TIMEOUT_SECONDS,
            env=wayland_session_env(),
        )
    except FileNotFoundError:
        logger.warning("pactl ist nicht installiert")
        return False, "pactl nicht gefunden"
    except subprocess.TimeoutExpired:
        logger.warning("pactl-Zeitueberschreitung: %s", args)
        return False, "Zeitueberschreitung"
    except OSError as exc:
        logger.warning("pactl-Aufruf fehlgeschlagen: %s", exc)
        return False, "Aufruf fehlgeschlagen"

    if completed.returncode != 0:
        logger.warning("pactl %s endete mit %s: %s", args, completed.returncode, completed.stderr.strip())
        return False, completed.stderr.strip() or "pactl-Fehler"
    return True, completed.stdout.strip()


def run_pactl_json(args: List[str]) -> Optional[object]:
    """Fuehrt pactl mit ``-f json`` aus und gibt die geparste Struktur zurueck.

    Args:
        args: Argumente ohne Programmnamen und ohne ``-f json``.

    Returns:
        Die geparste JSON-Struktur, oder None bei Fehler oder ungueltigem JSON.
    """
    ok, output = run_pactl(["-f", "json", *args])
    if not ok:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        logger.warning("pactl lieferte ungueltiges JSON fuer %s", args)
        return None
```

- [ ] **Step 4: `backend.py` schreiben**

Neue Datei `backend/app/plugins/installed/audio_control/backend.py`:

```python
"""Audio-Backends: ein Protokoll, eine Attrappe, eine echte Umsetzung.

Der Aufbau spiegelt ``services/power/desktop_backend.py``: ein Protocol, ein
Dev-Backend fuer Windows und Entwicklungsbetrieb, ein Linux-Backend, das mit
der realen Session spricht.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Protocol, Tuple

from app.plugins.installed.audio_control.models import AudioSink, AudioState, AudioStream
from app.plugins.installed.audio_control.pactl import (
    parse_sinks,
    parse_streams,
    run_pactl,
    run_pactl_json,
)

logger = logging.getLogger(__name__)


class AudioBackend(Protocol):
    async def get_state(self) -> AudioState: ...
    async def set_sink_volume(self, sink_id: int, percent: int) -> Tuple[bool, str]: ...
    async def set_sink_mute(self, sink_id: int, muted: bool) -> Tuple[bool, str]: ...
    async def set_default_sink(self, name: str) -> Tuple[bool, str]: ...
    async def set_stream_volume(self, stream_id: int, percent: int) -> Tuple[bool, str]: ...
    async def set_stream_mute(self, stream_id: int, muted: bool) -> Tuple[bool, str]: ...


class DevAudioBackend:
    """Zustand im Speicher, damit das Feature auf Windows entwickelbar ist."""

    def __init__(self) -> None:
        self._sinks: List[AudioSink] = [
            AudioSink(
                id=61,
                name="alsa_output.dev-onboard.iec958-stereo",
                description="Onboard Digital (Dev)",
                volume_percent=95,
                muted=False,
                is_default=True,
            ),
            AudioSink(
                id=90,
                name="alsa_output.dev-gpu.hdmi-stereo",
                description="GPU HDMI (Dev)",
                volume_percent=100,
                muted=False,
                is_default=False,
            ),
        ]
        self._streams: List[AudioStream] = [
            AudioStream(
                id=789,
                sink_id=61,
                application="Firefox",
                binary="firefox-esr",
                title="Beispielvideo (Dev)",
                volume_percent=55,
                muted=False,
                corked=False,
            ),
            AudioStream(
                id=790,
                sink_id=61,
                application="Steam",
                binary="steam",
                title=None,
                volume_percent=80,
                muted=False,
                corked=True,
            ),
        ]

    async def get_state(self) -> AudioState:
        return AudioState(
            sinks=list(self._sinks),
            streams=list(self._streams),
            available=True,
            detail="Dev-Backend (im Speicher)",
        )

    async def set_sink_volume(self, sink_id: int, percent: int) -> Tuple[bool, str]:
        for sink in self._sinks:
            if sink.id == sink_id:
                sink.volume_percent = percent
                return True, "Pegel gesetzt (Dev)"
        return False, "Unbekanntes Geraet"

    async def set_sink_mute(self, sink_id: int, muted: bool) -> Tuple[bool, str]:
        for sink in self._sinks:
            if sink.id == sink_id:
                sink.muted = muted
                return True, "Stummschaltung gesetzt (Dev)"
        return False, "Unbekanntes Geraet"

    async def set_default_sink(self, name: str) -> Tuple[bool, str]:
        if not any(sink.name == name for sink in self._sinks):
            return False, "Unbekanntes Geraet"
        for sink in self._sinks:
            sink.is_default = sink.name == name
        return True, "Standardgeraet gesetzt (Dev)"

    async def set_stream_volume(self, stream_id: int, percent: int) -> Tuple[bool, str]:
        for stream in self._streams:
            if stream.id == stream_id:
                stream.volume_percent = percent
                return True, "Pegel gesetzt (Dev)"
        return False, "Unbekannter Stream"

    async def set_stream_mute(self, stream_id: int, muted: bool) -> Tuple[bool, str]:
        for stream in self._streams:
            if stream.id == stream_id:
                stream.muted = muted
                return True, "Stummschaltung gesetzt (Dev)"
        return False, "Unbekannter Stream"


class PipeWireAudioBackend:
    """Spricht ueber pactl mit der PipeWire-Instanz der Desktop-Session.

    Das Backend laeuft unter derselben UID wie die Session, deshalb genuegt die
    Umgebung aus ``wayland_session_env()``; es wird kein Sudo benoetigt.
    """

    async def get_state(self) -> AudioState:
        return await asyncio.to_thread(self._read_state)

    def _read_state(self) -> AudioState:
        sinks_payload = run_pactl_json(["list", "sinks"])
        if sinks_payload is None:
            return AudioState(available=False, detail="PipeWire nicht erreichbar")

        ok, default_name = run_pactl(["get-default-sink"])
        streams_payload = run_pactl_json(["list", "sink-inputs"])

        return AudioState(
            sinks=parse_sinks(sinks_payload, default_name if ok else None),
            streams=parse_streams(streams_payload if streams_payload is not None else []),
            available=True,
        )

    async def set_sink_volume(self, sink_id: int, percent: int) -> Tuple[bool, str]:
        return await asyncio.to_thread(
            run_pactl, ["set-sink-volume", str(int(sink_id)), f"{int(percent)}%"]
        )

    async def set_sink_mute(self, sink_id: int, muted: bool) -> Tuple[bool, str]:
        return await asyncio.to_thread(
            run_pactl, ["set-sink-mute", str(int(sink_id)), "1" if muted else "0"]
        )

    async def set_default_sink(self, name: str) -> Tuple[bool, str]:
        return await asyncio.to_thread(run_pactl, ["set-default-sink", name])

    async def set_stream_volume(self, stream_id: int, percent: int) -> Tuple[bool, str]:
        return await asyncio.to_thread(
            run_pactl, ["set-sink-input-volume", str(int(stream_id)), f"{int(percent)}%"]
        )

    async def set_stream_mute(self, stream_id: int, muted: bool) -> Tuple[bool, str]:
        return await asyncio.to_thread(
            run_pactl, ["set-sink-input-mute", str(int(stream_id)), "1" if muted else "0"]
        )
```

> `asyncio.to_thread` ist Pflicht: `subprocess.run` blockiert, und ein blockierender Aufruf im Event-Loop legt den ganzen Worker lahm.

- [ ] **Step 5: `service.py` schreiben**

Neue Datei `backend/app/plugins/installed/audio_control/service.py`:

```python
"""Service-Schicht der Audiosteuerung.

Waehlt das Backend und haelt die Auswahl als Singleton, wie es
``services/power/desktop.py`` fuer die Displaysteuerung tut.
"""
from __future__ import annotations

import logging
import platform
from typing import Optional, Tuple

from app.core.config import settings
from app.plugins.installed.audio_control.backend import (
    AudioBackend,
    DevAudioBackend,
    PipeWireAudioBackend,
)
from app.plugins.installed.audio_control.models import AudioState

logger = logging.getLogger(__name__)

_service: Optional["AudioService"] = None


class AudioService:
    """Duenne Huelle um das gewaehlte Backend."""

    def __init__(self, backend: Optional[AudioBackend] = None) -> None:
        if backend is not None:
            self._backend: AudioBackend = backend
        elif getattr(settings, "is_dev_mode", False) or platform.system() != "Linux":
            # pactl gibt es auf Windows nicht, und im Dev-Modus soll nichts
            # an einer echten Session herumstellen.
            self._backend = DevAudioBackend()
        else:
            self._backend = PipeWireAudioBackend()

    async def get_state(self) -> AudioState:
        """Liest Geraete, Streams und das aktive Standardgeraet."""
        return await self._backend.get_state()

    async def set_sink_volume(self, sink_id: int, percent: int) -> Tuple[bool, str]:
        """Setzt den Pegel eines Ausgabegeraets."""
        return await self._backend.set_sink_volume(sink_id, percent)

    async def set_sink_mute(self, sink_id: int, muted: bool) -> Tuple[bool, str]:
        """Schaltet ein Ausgabegeraet stumm oder wieder laut."""
        return await self._backend.set_sink_mute(sink_id, muted)

    async def set_default_sink(self, name: str) -> Tuple[bool, str]:
        """Macht ein Geraet zum Standardausgang."""
        return await self._backend.set_default_sink(name)

    async def set_stream_volume(self, stream_id: int, percent: int) -> Tuple[bool, str]:
        """Setzt den Pegel eines einzelnen Streams."""
        return await self._backend.set_stream_volume(stream_id, percent)

    async def set_stream_mute(self, stream_id: int, muted: bool) -> Tuple[bool, str]:
        """Schaltet einen einzelnen Stream stumm oder wieder laut."""
        return await self._backend.set_stream_mute(stream_id, muted)


def get_audio_service() -> AudioService:
    """Liefert die Service-Instanz und legt sie beim ersten Aufruf an."""
    global _service
    if _service is None:
        _service = AudioService()
    return _service
```

- [ ] **Step 6: Tests laufen lassen und Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_audio_control_backend.py -v --no-cov`
Expected: PASS.

- [ ] **Step 7: Lint und Commit**

```bash
cd backend ; python -m ruff check app/plugins/installed/audio_control tests/plugins/test_audio_control_backend.py
```

```bash
git add backend/app/plugins/installed/audio_control backend/tests/plugins/test_audio_control_backend.py
git commit -m "feat(audio): Dev- und PipeWire-Backend samt Service"
```

---

## Task 4: Plugin, Routen und Rate-Limit-Kategorie

**Files:**
- Modify: `backend/app/plugins/installed/audio_control/__init__.py`
- Modify: `backend/app/core/rate_limiter.py`
- Test: `backend/tests/plugins/test_audio_control_routes.py`

**Interfaces:**
- Consumes: `get_audio_service()`, `AudioState`, `VolumeRequest`, `MuteRequest`, `DefaultSinkRequest` aus Tasks 2 und 3; `require_power_control_audio` aus Task 1.
- Produces: Plugin-Klasse `AudioControlPlugin` mit `metadata.name == "audio_control"`; Routen unter `/api/plugins/audio_control/`; Rate-Limit-Kategorie `"audio_control"`.

- [ ] **Step 1: Rate-Limit-Kategorie ergänzen**

In `backend/app/core/rate_limiter.py`, im Wörterbuch `RATE_LIMITS` vor der schliessenden Klammer:

```python
    # Audiosteuerung — Popover-Abfrage alle 2s plus entprellte Schieberegler.
    # admin_operations (30/Minute) waere hier falsch: die Abfrage allein
    # verbraucht schon 30 Anfragen pro Minute.
    "audio_control": "240/minute",
```

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

Neue Datei `backend/tests/plugins/test_audio_control_routes.py`:

```python
"""Routen-Tests der Audiosteuerung: Berechtigung, Validierung, Fehlerfaelle."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_power_control_audio
from app.plugins.installed.audio_control import AudioControlPlugin
from app.plugins.installed.audio_control.backend import DevAudioBackend
from app.plugins.installed.audio_control.service import AudioService
from app.plugins.installed.audio_control import service as service_module


class _User:
    username = "admin"
    role = "admin"
    id = 1


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """App nur mit dem Plugin-Router, Dev-Backend, Berechtigung erfuellt."""
    monkeypatch.setattr(
        service_module, "get_audio_service", lambda: AudioService(backend=DevAudioBackend())
    )
    app = FastAPI()
    app.include_router(AudioControlPlugin().get_router(), prefix="/api/plugins/audio_control")
    app.dependency_overrides[require_power_control_audio] = lambda: _User()
    return TestClient(app)


class TestStateRoute:
    def test_returns_sinks_and_streams(self, client):
        resp = client.get("/api/plugins/audio_control/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert len(body["sinks"]) == 2
        assert len(body["streams"]) == 2

    def test_stream_carries_application_and_title(self, client):
        body = client.get("/api/plugins/audio_control/state").json()
        stream = body["streams"][0]
        assert stream["application"] == "Firefox"
        assert "title" in stream
        assert "corked" in stream


class TestWriteRoutes:
    def test_setting_sink_volume_succeeds(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": 40})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_setting_sink_mute_succeeds(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/mute", json={"muted": True})
        assert resp.status_code == 200

    def test_setting_default_sink_succeeds(self, client):
        resp = client.put(
            "/api/plugins/audio_control/default-sink",
            json={"name": "alsa_output.dev-gpu.hdmi-stereo"},
        )
        assert resp.status_code == 200

    def test_setting_stream_volume_succeeds(self, client):
        resp = client.put("/api/plugins/audio_control/streams/789/volume", json={"percent": 20})
        assert resp.status_code == 200


class TestBackendOutputNeverReachesTheClient:
    """pactl-Ausgaben enthalten Geraetenamen und Pfade — sie bleiben im Log."""

    def test_a_successful_write_returns_no_backend_message(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": 40})
        body = resp.json()
        assert body == {"success": True}
        assert "message" not in body

    def test_a_successful_default_sink_switch_returns_no_backend_message(self, client):
        resp = client.put(
            "/api/plugins/audio_control/default-sink",
            json={"name": "alsa_output.dev-gpu.hdmi-stereo"},
        )
        assert resp.json() == {"success": True}


class TestDefaultSinkNameIsValidatedBeforeTheCall:
    """Die einzige Stelle, an der eine Client-Zeichenkette ein pactl-Argument wird."""

    def test_an_unknown_name_never_reaches_the_backend(self, monkeypatch, client):
        from app.plugins.installed.audio_control.backend import DevAudioBackend

        called: list[str] = []

        async def _spy(self, name: str):
            called.append(name)
            return True, "sollte nie passieren"

        monkeypatch.setattr(DevAudioBackend, "set_default_sink", _spy)

        resp = client.put(
            "/api/plugins/audio_control/default-sink", json={"name": "gibt.es.nicht"}
        )

        assert resp.status_code == 404
        assert called == [], "unbekannter Name darf das Backend nie erreichen"


class TestValidation:
    def test_volume_above_the_cap_is_rejected(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": 1000})
        assert resp.status_code == 422

    def test_negative_volume_is_rejected(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": -1})
        assert resp.status_code == 422

    def test_empty_default_sink_name_is_rejected(self, client):
        resp = client.put("/api/plugins/audio_control/default-sink", json={"name": ""})
        assert resp.status_code == 422


class TestUnknownIds:
    def test_unknown_sink_is_a_404(self, client):
        """Ein veralteter Index ist ein Normalfall, kein Serverfehler."""
        resp = client.put("/api/plugins/audio_control/sinks/9999/volume", json={"percent": 10})
        assert resp.status_code == 404

    def test_unknown_stream_is_a_404(self, client):
        resp = client.put("/api/plugins/audio_control/streams/9999/mute", json={"muted": True})
        assert resp.status_code == 404

    def test_unknown_default_sink_is_a_404(self, client):
        resp = client.put("/api/plugins/audio_control/default-sink", json={"name": "gibt.es.nicht"})
        assert resp.status_code == 404


class TestBrokenAudioStack:
    """Eine Stoerung darf nicht als 'nicht gefunden' gemeldet werden."""

    @pytest.fixture
    def broken_client(self, monkeypatch) -> TestClient:
        from app.plugins.installed.audio_control.models import AudioState

        class _BrokenBackend:
            async def get_state(self) -> AudioState:
                return AudioState(available=False, detail="PipeWire nicht erreichbar")

            async def set_sink_volume(self, sink_id, percent):
                return False, "Zeitueberschreitung"

            async def set_sink_mute(self, sink_id, muted):
                return False, "Zeitueberschreitung"

            async def set_default_sink(self, name):
                return False, "Zeitueberschreitung"

            async def set_stream_volume(self, stream_id, percent):
                return False, "Zeitueberschreitung"

            async def set_stream_mute(self, stream_id, muted):
                return False, "Zeitueberschreitung"

        monkeypatch.setattr(
            service_module, "get_audio_service", lambda: AudioService(backend=_BrokenBackend())
        )
        app = FastAPI()
        app.include_router(AudioControlPlugin().get_router(), prefix="/api/plugins/audio_control")
        app.dependency_overrides[require_power_control_audio] = lambda: _User()
        return TestClient(app)

    def test_state_reports_unavailable_instead_of_failing(self, broken_client):
        resp = broken_client.get("/api/plugins/audio_control/state")
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_a_write_against_a_broken_stack_is_a_502_not_a_404(self, broken_client):
        resp = broken_client.put(
            "/api/plugins/audio_control/sinks/61/volume", json={"percent": 10}
        )
        assert resp.status_code == 502

    def test_a_broken_default_sink_write_is_a_502(self, broken_client):
        resp = broken_client.put(
            "/api/plugins/audio_control/default-sink", json={"name": "egal"}
        )
        assert resp.status_code == 502


class TestPermissionIsRequired:
    def test_every_route_depends_on_the_audio_permission(self):
        """Auch die lesende Route — media.name verraet den laufenden Titel."""
        router = AudioControlPlugin().get_router()
        for route in router.routes:
            dependencies = [d.call for d in route.dependant.dependencies]
            assert require_power_control_audio in dependencies, route.path
```

- [ ] **Step 3: Test laufen lassen und Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_audio_control_routes.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'AudioControlPlugin'`.

- [ ] **Step 4: Plugin und Routen schreiben**

`backend/app/plugins/installed/audio_control/__init__.py` vollständig ersetzen:

```python
"""Audiosteuerung — bundled Plugin.

Steuert Pegel, Ausgabegeraet und einzelne Wiedergabe-Streams der KDE-Session
ueber pactl. Laeuft als bundled Plugin im Host-Prozess und damit unter
derselben UID wie die Desktop-Session; ein Sandbox-Plugin kaeme nicht an den
PipeWire-Socket.
"""
# NB: hier NICHT ``from __future__ import annotations`` ergaenzen. Zusammen mit
# Pydantic v2 und FastAPIs Body-Erkennung durch den ``@limiter.limit``-Wrapper
# von slowapi werden aufgeschobene Annotationen zu ForwardRefs, die FastAPI
# nicht mehr als Pydantic-Modelle aufloest — der Rumpf gilt dann als
# Query-Parameter und jedes PUT antwortet mit 422. Dieselbe Warnung steht in
# ``api/routes/gpu_power.py``.
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import require_power_control_audio
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.base import PluginBase, PluginMetadata
from app.plugins.installed.audio_control.models import (
    AudioState,
    DefaultSinkRequest,
    MuteRequest,
    VolumeRequest,
)
from app.plugins.installed.audio_control import service as service_module
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()

_LIMIT = get_limit("audio_control")


def _audit(action: str, user: UserPublic, success: bool, detail: str) -> None:
    """Schreibt einen Audit-Eintrag fuer Zustandsspruenge.

    Bewusst nur fuer Geraetewechsel und Stummschaltung. Pegelaenderungen
    erzeugen selbst mit Entprellung Dutzende Schreibvorgaenge und wuerden das
    Log so zumuellen, dass die interessanten Eintraege darin untergehen.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action=action,
        user=user.username,
        resource="audio",
        success=success,
        details={"detail": detail},
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="control_audio",
            details={"action": action},
            success=True,
        )


async def _apply(ok: bool, message: str, kind: str, target_id: int) -> dict:
    """Uebersetzt ein Backend-Ergebnis in die Antwort.

    Unterscheidet zwei sehr verschiedene Fehlschlaege, die das Backend beide
    nur als ``False`` meldet:

    - **Der Index existiert nicht mehr** — ein Normalfall, weil Streams
      verschwinden, sobald die Wiedergabe endet. Das ist ein 404, damit die UI
      ihre Liste neu laedt.
    - **Der Audio-Stack ist gestoert** — pactl fehlt, laeuft in eine
      Zeitueberschreitung oder PipeWire ist weg. Das ist ein 502.

    Beides als 404 zu melden waere eine Falschaussage: die UI wuerde eine
    Stoerung als veraltete Liste behandeln, und bei der Fehlersuche fuehrt der
    Statuscode auf die falsche Spur. Der zusaetzliche Lesevorgang faellt nur
    auf dem Fehlerpfad an und ist dort billig.
    """
    if ok:
        # `message` stammt roh aus pactl (stdout/stderr) und kann Geraetenamen
        # und Pfade enthalten. Es wird geloggt, aber nie ausgeliefert.
        return {"success": True}

    state = await service_module.get_audio_service().get_state()
    if not state.available:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Audio nicht erreichbar"
        )

    known = state.sinks if kind == "sink" else state.streams
    if not any(item.id == target_id for item in known):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden")

    logger.warning("Audio-Schreibvorgang fehlgeschlagen (%s %s): %s", kind, target_id, message)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Aktion fehlgeschlagen")


async def _apply_default_sink(ok: bool, message: str, name: str) -> dict:
    """Wie ``_apply``, aber fuer das Standardgeraet (Name statt Index)."""
    if ok:
        return {"success": True}

    state = await service_module.get_audio_service().get_state()
    if not state.available:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Audio nicht erreichbar"
        )
    if not any(sink.name == name for sink in state.sinks):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden")

    logger.warning("Standardgeraet konnte nicht gesetzt werden (%s): %s", name, message)
    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Aktion fehlgeschlagen")


@router.get("/state", response_model=AudioState)
@user_limiter.limit(_LIMIT)
async def get_audio_state(
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> AudioState:
    """Liefert Geraete, Streams und das aktive Standardgeraet in einer Antwort.

    Hinter derselben Berechtigung wie die Schreibrouten: die Stream-Titel
    verraten, was auf dem Desktop gerade laeuft.
    """
    return await service_module.get_audio_service().get_state()


@router.put("/sinks/{sink_id}/volume")
@user_limiter.limit(_LIMIT)
async def set_sink_volume(
    sink_id: int,
    body: VolumeRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Setzt den Pegel eines Ausgabegeraets."""
    ok, message = await service_module.get_audio_service().set_sink_volume(sink_id, body.percent)
    return await _apply(ok, message, "sink", sink_id)


@router.put("/sinks/{sink_id}/mute")
@user_limiter.limit(_LIMIT)
async def set_sink_mute(
    sink_id: int,
    body: MuteRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Schaltet ein Ausgabegeraet stumm oder wieder laut."""
    ok, message = await service_module.get_audio_service().set_sink_mute(sink_id, body.muted)
    _audit("audio_sink_mute", current_user, ok, message)
    return await _apply(ok, message, "sink", sink_id)


@router.put("/default-sink")
@user_limiter.limit(_LIMIT)
async def set_default_sink(
    body: DefaultSinkRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Macht ein Geraet zum Standardausgang.

    Der Name wird **vor** dem Aufruf gegen die gelesene Geraeteliste geprueft.
    Listen-Argumente verhindern zwar eine Shell-Injektion, aber dies ist die
    einzige Stelle, an der eine Client-Zeichenkette ueberhaupt in ein
    pactl-Argument gelangt — und eine Zusicherung, die nur in der Prosa steht
    und nirgends im Code, ist keine.
    """
    service = service_module.get_audio_service()
    state = await service.get_state()
    if not state.available:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Audio nicht erreichbar"
        )
    if not any(sink.name == body.name for sink in state.sinks):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nicht gefunden")

    ok, message = await service.set_default_sink(body.name)
    _audit("audio_default_sink", current_user, ok, message)
    return await _apply_default_sink(ok, message, body.name)


@router.put("/streams/{stream_id}/volume")
@user_limiter.limit(_LIMIT)
async def set_stream_volume(
    stream_id: int,
    body: VolumeRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Setzt den Pegel eines einzelnen Streams."""
    ok, message = await service_module.get_audio_service().set_stream_volume(
        stream_id, body.percent
    )
    return await _apply(ok, message, "stream", stream_id)


@router.put("/streams/{stream_id}/mute")
@user_limiter.limit(_LIMIT)
async def set_stream_mute(
    stream_id: int,
    body: MuteRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_control_audio),
) -> dict:
    """Schaltet einen einzelnen Stream stumm oder wieder laut."""
    ok, message = await service_module.get_audio_service().set_stream_mute(stream_id, body.muted)
    _audit("audio_stream_mute", current_user, ok, message)
    return await _apply(ok, message, "stream", stream_id)


class AudioControlPlugin(PluginBase):
    """Bundled Plugin fuer die Audiosteuerung."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="audio_control",
            version="1.0.0",
            display_name="Audiosteuerung",
            description=(
                "Pegel, Ausgabegeraet und Lautstaerke einzelner Anwendungen "
                "der Desktop-Session fernsteuern."
            ),
            author="Xveyn",
            category="system",
        )

    def get_router(self) -> APIRouter:
        return router
```

> Der Service wird ueber `service_module.get_audio_service()` geholt, nicht ueber einen direkten Import der Funktion. Nur so kann ein Test die Auswahl per `monkeypatch` ersetzen.

- [ ] **Step 5: Tests laufen lassen und Erfolg bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_audio_control_routes.py -v --no-cov`
Expected: PASS.

- [ ] **Step 6: Plugin-Suite auf Regressionen prüfen**

Run: `cd backend ; python -m pytest tests/plugins -q --no-cov`
Expected: keine neuen Fehler. Das neue Verzeichnis wird jetzt vom `PluginManager` erkannt; sollte ein Test die Anzahl gefundener Plugins fest verdrahten, ist diese Zahl anzupassen.

- [ ] **Step 7: Lint und Commit**

```bash
cd backend ; python -m ruff check app/plugins/installed/audio_control app/core/rate_limiter.py tests/plugins/test_audio_control_routes.py
```

```bash
git add backend/app/plugins/installed/audio_control backend/app/core/rate_limiter.py backend/tests/plugins/test_audio_control_routes.py
git commit -m "feat(audio): Plugin, Routen und eigene Rate-Limit-Kategorie"
```

---

## Task 5: Frontend-API-Client

**Files:**
- Create: `client/src/api/audioControl.ts`
- Modify: `client/src/api/powerPermissions.ts`
- Test: `client/src/__tests__/api/audioControl.test.ts`

**Interfaces:**
- Produces: Typen `AudioSink`, `AudioStream`, `AudioState`; Funktionen `getAudioState()`, `setSinkVolume(id, percent)`, `setSinkMute(id, muted)`, `setDefaultSink(name)`, `setStreamVolume(id, percent)`, `setStreamMute(id, muted)`. Feld `can_control_audio` in den drei Power-Permission-Schnittstellen.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Neue Datei `client/src/__tests__/api/audioControl.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

import { apiClient } from '../../lib/api';
import {
  getAudioState,
  setSinkVolume,
  setSinkMute,
  setDefaultSink,
  setStreamVolume,
  setStreamMute,
} from '../../api/audioControl';

describe('audioControl API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { sinks: [], streams: [], available: true, detail: null },
    });
    (apiClient.put as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { success: true } });
  });

  it('liest den Zustand von einer einzigen Route', async () => {
    const state = await getAudioState();
    expect(apiClient.get).toHaveBeenCalledWith('/api/plugins/audio_control/state');
    expect(state.available).toBe(true);
  });

  it('setzt den Geraetepegel', async () => {
    await setSinkVolume(61, 40);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/sinks/61/volume', {
      percent: 40,
    });
  });

  it('setzt die Geraete-Stummschaltung', async () => {
    await setSinkMute(61, true);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/sinks/61/mute', {
      muted: true,
    });
  });

  it('setzt das Standardgeraet', async () => {
    await setDefaultSink('alsa_output.test');
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/default-sink', {
      name: 'alsa_output.test',
    });
  });

  it('setzt den Streampegel', async () => {
    await setStreamVolume(789, 20);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/streams/789/volume', {
      percent: 20,
    });
  });

  it('setzt die Stream-Stummschaltung', async () => {
    await setStreamMute(789, true);
    expect(apiClient.put).toHaveBeenCalledWith('/api/plugins/audio_control/streams/789/mute', {
      muted: true,
    });
  });
});
```

- [ ] **Step 2: Test laufen lassen und Fehlschlag bestätigen**

Run: `cd client ; npx vitest run src/__tests__/api/audioControl.test.ts`
Expected: FAIL — Modul `../../api/audioControl` nicht gefunden.

- [ ] **Step 3: Den API-Client schreiben**

Neue Datei `client/src/api/audioControl.ts`:

```ts
/**
 * API-Client der Audiosteuerung (bundled Plugin `audio_control`).
 *
 * Alle Routen liegen hinter dem Recht `can_control_audio` — auch die lesende,
 * weil die Stream-Titel verraten, was auf dem Desktop gerade laeuft.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/audio_control';

export interface AudioSink {
  id: number;
  name: string;
  description: string;
  volume_percent: number;
  muted: boolean;
  is_default: boolean;
}

export interface AudioStream {
  id: number;
  sink_id: number;
  application: string;
  binary: string | null;
  /** media.name — nur als Tooltip anzeigen, nie als Beschriftung. */
  title: string | null;
  volume_percent: number;
  muted: boolean;
  corked: boolean;
}

export interface AudioState {
  sinks: AudioSink[];
  streams: AudioStream[];
  available: boolean;
  detail: string | null;
}

/** Liest Geraete, Streams und Standardgeraet in einem Rundlauf. */
export async function getAudioState(): Promise<AudioState> {
  const { data } = await apiClient.get<AudioState>(`${BASE}/state`);
  return data;
}

/** Setzt den Pegel eines Ausgabegeraets (0-150). */
export async function setSinkVolume(sinkId: number, percent: number): Promise<void> {
  await apiClient.put(`${BASE}/sinks/${sinkId}/volume`, { percent });
}

/** Schaltet ein Ausgabegeraet stumm oder wieder laut. */
export async function setSinkMute(sinkId: number, muted: boolean): Promise<void> {
  await apiClient.put(`${BASE}/sinks/${sinkId}/mute`, { muted });
}

/** Macht ein Geraet zum Standardausgang. */
export async function setDefaultSink(name: string): Promise<void> {
  await apiClient.put(`${BASE}/default-sink`, { name });
}

/** Setzt den Pegel eines einzelnen Streams (0-150). */
export async function setStreamVolume(streamId: number, percent: number): Promise<void> {
  await apiClient.put(`${BASE}/streams/${streamId}/volume`, { percent });
}

/** Schaltet einen einzelnen Stream stumm oder wieder laut. */
export async function setStreamMute(streamId: number, muted: boolean): Promise<void> {
  await apiClient.put(`${BASE}/streams/${streamId}/mute`, { muted });
}
```

- [ ] **Step 4: Power-Permission-Typen erweitern**

In `client/src/api/powerPermissions.ts` jeweils nach der `can_unlock_session`-Zeile ergänzen:

In `UserPowerPermissions`:
```ts
  can_control_audio: boolean;
```

In `UserPowerPermissionsUpdate`:
```ts
  can_control_audio?: boolean;
```

In `MyPowerPermissions`:
```ts
  can_control_audio: boolean;
```

- [ ] **Step 5: Tests laufen lassen und Erfolg bestätigen**

Run: `cd client ; npx vitest run src/__tests__/api/audioControl.test.ts`
Expected: PASS (6 Tests).

- [ ] **Step 6: Commit**

```bash
git add client/src/api/audioControl.ts client/src/api/powerPermissions.ts client/src/__tests__/api/audioControl.test.ts
git commit -m "feat(audio): API-Client und can_control_audio in den Permission-Typen"
```

---

## Task 6: Topbar-Komponente `AudioMenu`

**Files:**
- Create: `client/src/components/topbar/AudioMenu.tsx`
- Create: `client/src/i18n/locales/de/audio.json`
- Create: `client/src/i18n/locales/en/audio.json`
- Modify: `client/src/i18n/index.ts`
- Modify: `client/src/components/layout/LayoutHeader.tsx`
- Test: `client/src/__tests__/components/topbar/AudioMenu.test.tsx`

**Interfaces:**
- Consumes: `getAudioState`, `setSinkVolume`, `setSinkMute`, `setDefaultSink`, `setStreamVolume`, `setStreamMute` aus Task 5; `getMyPowerPermissions` aus `api/powerPermissions`; `usePluginEnabled` aus `contexts/PluginContext`.
- Produces: benannter Export `AudioMenu` (keine Props).

> **Abweichung von der Spec, bewusst:** Die Spec skizziert `{!isPi && audioEnabled && canControlAudio && <AudioMenu />}`. Umgesetzt wird `{!isPi && audioEnabled && <AudioMenu />}`, wobei die Komponente die Berechtigung selbst prueft und bei fehlendem Recht `null` liefert. Sonst wuerde `LayoutHeader` fuer **jeden** Benutzer bei **jedem** Seitenaufruf `my-permissions` abfragen, auch wenn das Plugin gar nicht aktiv ist. Das Verhalten nach aussen ist identisch.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

Neue Datei `client/src/__tests__/components/topbar/AudioMenu.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

// Der Mock muss den Namensraum mit ausgeben, sonst liefert t('title') nur
// 'title' und die Erwartungen auf 'audio:title' schlagen fehl.
vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string) => `${ns}:${key}`,
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/audioControl', () => ({
  getAudioState: vi.fn(),
  setSinkVolume: vi.fn().mockResolvedValue(undefined),
  setSinkMute: vi.fn().mockResolvedValue(undefined),
  setDefaultSink: vi.fn().mockResolvedValue(undefined),
  setStreamVolume: vi.fn().mockResolvedValue(undefined),
  setStreamMute: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn(),
}));

import { AudioMenu } from '../../../components/topbar/AudioMenu';
import { getAudioState, setSinkVolume } from '../../../api/audioControl';
import { getMyPowerPermissions } from '../../../api/powerPermissions';

const STATE = {
  available: true,
  detail: null,
  sinks: [
    {
      id: 61,
      name: 'onboard',
      description: 'Onboard Digital',
      volume_percent: 95,
      muted: false,
      is_default: true,
    },
    {
      id: 90,
      name: 'gpu',
      description: 'GPU HDMI',
      volume_percent: 100,
      muted: false,
      is_default: false,
    },
  ],
  streams: [
    {
      id: 789,
      sink_id: 61,
      application: 'Firefox',
      binary: 'firefox-esr',
      title: 'Ein sehr privater Videotitel',
      volume_percent: 55,
      muted: false,
      corked: false,
    },
  ],
};

const allowed = { can_control_audio: true };

beforeEach(() => {
  vi.clearAllMocks();
  (getMyPowerPermissions as ReturnType<typeof vi.fn>).mockResolvedValue(allowed);
  (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue(STATE);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('AudioMenu', () => {
  it('rendert nichts ohne die Berechtigung', async () => {
    (getMyPowerPermissions as ReturnType<typeof vi.fn>).mockResolvedValue({
      can_control_audio: false,
    });
    const { container } = render(<AudioMenu />);
    await waitFor(() => expect(getMyPowerPermissions).toHaveBeenCalled());
    expect(container.querySelector('button')).toBeNull();
  });

  it('zeigt den Knopf mit der Berechtigung', async () => {
    render(<AudioMenu />);
    expect(await screen.findByRole('button', { name: 'audio:title' })).toBeTruthy();
  });

  it('fragt den Zustand erst beim Oeffnen ab', async () => {
    render(<AudioMenu />);
    const button = await screen.findByRole('button', { name: 'audio:title' });
    expect(getAudioState).not.toHaveBeenCalled();

    fireEvent.click(button);
    await waitFor(() => expect(getAudioState).toHaveBeenCalledTimes(1));
  });

  it('zeigt die Anwendung, nicht den Titel', async () => {
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    expect(await screen.findByText('Firefox')).toBeTruthy();
    expect(screen.queryByText('Ein sehr privater Videotitel')).toBeNull();
  });

  it('meldet einen nicht erreichbaren Audio-Stack statt leerer Regler', async () => {
    (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue({
      available: false,
      detail: null,
      sinks: [],
      streams: [],
    });
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    expect(await screen.findByText('audio:unavailable')).toBeTruthy();
  });

  it('weist auf eine leere Stream-Liste hin', async () => {
    (getAudioState as ReturnType<typeof vi.fn>).mockResolvedValue({ ...STATE, streams: [] });
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));

    expect(await screen.findByText('audio:noStreams')).toBeTruthy();
  });

  it('entprellt den Regler auf eine einzige Anfrage', async () => {
    render(<AudioMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'audio:title' }));
    const slider = await screen.findByLabelText('audio:sinkVolume');

    vi.useFakeTimers();
    fireEvent.change(slider, { target: { value: '40' } });
    fireEvent.change(slider, { target: { value: '41' } });
    fireEvent.change(slider, { target: { value: '42' } });
    vi.advanceTimersByTime(300);
    vi.useRealTimers();

    await waitFor(() => expect(setSinkVolume).toHaveBeenCalledTimes(1));
    expect(setSinkVolume).toHaveBeenCalledWith(61, 42);
  });
});
```

- [ ] **Step 2: Test laufen lassen und Fehlschlag bestätigen**

Run: `cd client ; npx vitest run src/__tests__/components/topbar/AudioMenu.test.tsx`
Expected: FAIL — Modul `AudioMenu` nicht gefunden.

- [ ] **Step 3: Übersetzungen anlegen**

Neue Datei `client/src/i18n/locales/de/audio.json`:

```json
{
  "title": "Audio",
  "output": "Ausgabegerät",
  "sinkVolume": "Lautstärke",
  "streamVolume": "Lautstärke der Anwendung",
  "mute": "Stummschalten",
  "unmute": "Ton einschalten",
  "apps": "Anwendungen",
  "noStreams": "Gerade spielt nichts.",
  "unavailable": "Audio ist nicht erreichbar. Läuft die Desktop-Sitzung?",
  "paused": "pausiert",
  "loadError": "Audiozustand konnte nicht geladen werden",
  "saveError": "Änderung konnte nicht übernommen werden"
}
```

Neue Datei `client/src/i18n/locales/en/audio.json`:

```json
{
  "title": "Audio",
  "output": "Output device",
  "sinkVolume": "Volume",
  "streamVolume": "Application volume",
  "mute": "Mute",
  "unmute": "Unmute",
  "apps": "Applications",
  "noStreams": "Nothing is playing right now.",
  "unavailable": "Audio is unavailable. Is the desktop session running?",
  "paused": "paused",
  "loadError": "Could not load the audio state",
  "saveError": "Could not apply the change"
}
```

- [ ] **Step 4: Namensraum registrieren**

In `client/src/i18n/index.ts`:

Bei den Importen nach den `statusBar`-Zeilen:
```ts
import audioDe from './locales/de/audio.json';
import audioEn from './locales/en/audio.json';
```

Im `resources`-Objekt im `de`-Block nach `statusBar: statusBarDe,`:
```ts
    audio: audioDe,
```

Im `en`-Block nach `statusBar: statusBarEn,`:
```ts
    audio: audioEn,
```

> Enthält die Datei zusätzlich eine `ns`-Liste oder eine `defaultNS`-Angabe, dort `'audio'` ebenfalls ergänzen. Die Datei vor dem Ändern ganz lesen.

- [ ] **Step 5: Die Komponente schreiben**

Neue Datei `client/src/components/topbar/AudioMenu.tsx`:

```tsx
/**
 * Audiosteuerung in der Topbar.
 *
 * Zeigt ein Lautsprecher-Symbol; im Popover stehen Ausgabegerät, Master-Pegel
 * und ein Mixer je laufender Anwendung.
 *
 * Zwei Eigenheiten, die Absicht sind:
 * - Der Zustand wird nur abgefragt, solange das Popover offen ist. Eine
 *   Fernbedienung, die im Hintergrund pollt, kostet Anfragen ohne Gegenwert.
 * - Angezeigt wird der Anwendungsname, nie der Titel. `media.name` verrät,
 *   was gerade läuft; der Titel erscheint nur im Tooltip.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Volume2, VolumeX } from 'lucide-react';
import {
  getAudioState,
  setDefaultSink,
  setSinkMute,
  setSinkVolume,
  setStreamMute,
  setStreamVolume,
  type AudioState,
} from '../../api/audioControl';
import { getMyPowerPermissions } from '../../api/powerPermissions';

/** Wartezeit, bevor eine Reglerbewegung zur Anfrage wird. */
const DEBOUNCE_MS = 200;

/** Abfragetakt, solange das Popover offen ist. */
const POLL_MS = 2000;

export function AudioMenu() {
  const { t } = useTranslation('audio');
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<AudioState | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  useEffect(() => {
    let active = true;
    getMyPowerPermissions()
      .then((perms) => active && setAllowed(perms.can_control_audio))
      .catch(() => active && setAllowed(false));
    return () => {
      active = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    // Läuft noch eine Antwort, wird übersprungen — sonst stauen sich bei
    // langsamer Verbindung die Anfragen.
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      setState(await getAudioState());
    } catch {
      setState({ sinks: [], streams: [], available: false, detail: null });
    } finally {
      inFlight.current = false;
    }
  }, []);

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
      }
    };
    if (isOpen) document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [isOpen]);

  const timersRef = timers.current;
  useEffect(() => () => timersRef.forEach((id) => clearTimeout(id)), [timersRef]);

  /** Verzögert einen Schreibvorgang und verwirft dabei die Zwischenschritte. */
  const debounce = useCallback((key: string, run: () => Promise<void>) => {
    const existing = timers.current.get(key);
    if (existing) clearTimeout(existing);
    timers.current.set(
      key,
      setTimeout(() => {
        timers.current.delete(key);
        void run().then(refresh).catch(() => undefined);
      }, DEBOUNCE_MS),
    );
  }, [refresh]);

  /** Zeigt den neuen Wert sofort, damit der Regler dem Finger folgt. */
  const optimisticSink = (id: number, percent: number) =>
    setState((prev) =>
      prev
        ? { ...prev, sinks: prev.sinks.map((s) => (s.id === id ? { ...s, volume_percent: percent } : s)) }
        : prev,
    );

  const optimisticStream = (id: number, percent: number) =>
    setState((prev) =>
      prev
        ? {
            ...prev,
            streams: prev.streams.map((s) =>
              s.id === id ? { ...s, volume_percent: percent } : s,
            ),
          }
        : prev,
    );

  if (!allowed) return null;

  const defaultSink = state?.sinks.find((s) => s.is_default) ?? null;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        aria-label={t('title')}
        onClick={() => setIsOpen((open) => !open)}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
      >
        {defaultSink?.muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-slate-800 bg-slate-900/95 p-4 shadow-xl backdrop-blur-xl">
          {state && !state.available && (
            <p className="text-sm text-slate-400">{t('unavailable')}</p>
          )}

          {state?.available && (
            <>
              <label className="mb-1 block text-xs uppercase tracking-wide text-slate-500">
                {t('output')}
              </label>
              <select
                aria-label={t('output')}
                value={defaultSink?.name ?? ''}
                onChange={(e) => void setDefaultSink(e.target.value).then(refresh)}
                className="mb-4 w-full rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200"
              >
                {state.sinks.map((sink) => (
                  <option key={sink.id} value={sink.name}>
                    {sink.description}
                  </option>
                ))}
              </select>

              {defaultSink && (
                <div className="mb-4 flex items-center gap-2">
                  <button
                    type="button"
                    aria-label={defaultSink.muted ? t('unmute') : t('mute')}
                    onClick={() =>
                      void setSinkMute(defaultSink.id, !defaultSink.muted).then(refresh)
                    }
                    className="text-slate-400 hover:text-sky-400"
                  >
                    {defaultSink.muted ? (
                      <VolumeX className="h-4 w-4" />
                    ) : (
                      <Volume2 className="h-4 w-4" />
                    )}
                  </button>
                  <input
                    type="range"
                    aria-label={t('sinkVolume')}
                    min={0}
                    max={150}
                    value={defaultSink.volume_percent}
                    onChange={(e) => {
                      const percent = Number(e.target.value);
                      optimisticSink(defaultSink.id, percent);
                      debounce(`sink:${defaultSink.id}`, () =>
                        setSinkVolume(defaultSink.id, percent),
                      );
                    }}
                    className="flex-1"
                  />
                  <span className="w-10 text-right text-xs text-slate-400">
                    {defaultSink.volume_percent}%
                  </span>
                </div>
              )}

              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">{t('apps')}</p>
              {state.streams.length === 0 ? (
                <p className="text-sm text-slate-400">{t('noStreams')}</p>
              ) : (
                state.streams.map((stream) => (
                  <div
                    key={stream.id}
                    className={`mb-3 flex items-center gap-2 ${stream.corked ? 'opacity-50' : ''}`}
                    title={stream.title ?? undefined}
                  >
                    <button
                      type="button"
                      aria-label={stream.muted ? t('unmute') : t('mute')}
                      onClick={() => void setStreamMute(stream.id, !stream.muted).then(refresh)}
                      className="text-slate-400 hover:text-sky-400"
                    >
                      {stream.muted ? (
                        <VolumeX className="h-4 w-4" />
                      ) : (
                        <Volume2 className="h-4 w-4" />
                      )}
                    </button>
                    <div className="flex-1">
                      <p className="truncate text-xs text-slate-300">{stream.application}</p>
                      <input
                        type="range"
                        aria-label={t('streamVolume')}
                        min={0}
                        max={150}
                        value={stream.volume_percent}
                        onChange={(e) => {
                          const percent = Number(e.target.value);
                          optimisticStream(stream.id, percent);
                          debounce(`stream:${stream.id}`, () =>
                            setStreamVolume(stream.id, percent),
                          );
                        }}
                        className="w-full"
                      />
                    </div>
                  </div>
                ))
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: In die Topbar einhängen**

In `client/src/components/layout/LayoutHeader.tsx`:

Import ergänzen:
```tsx
import { AudioMenu } from '../topbar/AudioMenu';
import { usePluginEnabled } from '../../contexts/PluginContext';
```

In der Funktion, vor dem `return`:
```tsx
  const audioEnabled = usePluginEnabled('audio_control');
```

Im Block „Header Right" vor `{!isPi && <NotificationCenter />}`:
```tsx
          {!isPi && audioEnabled && <AudioMenu />}
```

> `usePluginEnabled` vor dem Ändern in `client/src/contexts/PluginContext.tsx` gegenlesen: Wird der Export anders benannt oder erwartet er einen Provider oberhalb von `LayoutHeader`, ist der tatsächliche Vertrag maßgeblich, nicht diese Annahme.

- [ ] **Step 7: Tests laufen lassen und Erfolg bestätigen**

Run: `cd client ; npx vitest run src/__tests__/components/topbar/AudioMenu.test.tsx`
Expected: PASS (7 Tests).

- [ ] **Step 8: Den bestehenden LayoutHeader-Test an den neuen Hook anpassen**

`LayoutHeader` ruft jetzt `usePluginEnabled` auf, das einen `PluginProvider` oberhalb erwartet. Der vorhandene Test rendert die Komponente ohne diesen Provider und **wird deshalb fehlschlagen** — das ist erwartet, nicht überraschend.

Zuerst den Fehlschlag sehen:

Run: `cd client ; npx vitest run src/__tests__/components/layout/LayoutHeader.test.tsx`
Expected: FAIL — `usePlugins must be used within a PluginProvider`.

Dann in `client/src/__tests__/components/layout/LayoutHeader.test.tsx` oben bei den übrigen `vi.mock`-Aufrufen ergänzen:

```tsx
vi.mock('../../../contexts/PluginContext', () => ({
  usePluginEnabled: () => false,
}));
```

`false` ist hier richtig: der Test prüft die Kopfzeile, nicht die Audiosteuerung. Mit `false` bleibt sein bisheriges Verhalten unverändert, statt ihm ein zweites Anliegen aufzubürden. Die Abdeckung des Audio-Falls liegt in `AudioMenu.test.tsx`.

Run erneut: `cd client ; npx vitest run src/__tests__/components/layout/LayoutHeader.test.tsx`
Expected: PASS.

> Sollte der Test die Komponente über einen gemeinsamen Render-Helfer einbinden, der die Provider bereits stellt, entfällt der Mock — dann genügt es, dass der Lauf grün ist.

- [ ] **Step 9: Commit**

```bash
git add client/src/components/topbar/AudioMenu.tsx client/src/components/layout/LayoutHeader.tsx client/src/i18n client/src/__tests__/components/topbar/AudioMenu.test.tsx
git commit -m "feat(audio): AudioMenu in der Topbar samt Uebersetzungen"
```

---

## Task 7: Toggle in den Systemberechtigungen

**Files:**
- Modify: `client/src/components/user-management/PowerPermissionsSection.tsx`
- Modify: `client/src/i18n/locales/de/admin.json`
- Modify: `client/src/i18n/locales/en/admin.json`

**Interfaces:**
- Consumes: `can_control_audio` aus `UserPowerPermissionsUpdate` (Task 5).

- [ ] **Step 1: Komponente erweitern**

In `client/src/components/user-management/PowerPermissionsSection.tsx`:

Den lucide-Import um `Volume2` ergänzen:
```tsx
import { Moon, Sun, Power, Wifi, MonitorOff, LockOpen, Volume2, Loader2 } from 'lucide-react';
```

In `FIELD_TO_I18N` nach `can_unlock_session: 'unlockSession',`:
```tsx
  can_control_audio: 'controlAudio',
```

In `PERMISSION_TOGGLES` als letzten Eintrag:
```tsx
  { key: 'can_control_audio', icon: <Volume2 className="h-4 w-4" /> },
```

> Kein `implies`/`impliedBy` — das Recht steht unabhängig neben den Sleep-/Suspend-Ketten.

- [ ] **Step 2: Übersetzungen ergänzen**

In `client/src/i18n/locales/de/admin.json`, im vorhandenen Block `users.systemPermissions.items`, nach dem `unlockSession`-Eintrag:

```json
        "controlAudio": { "label": "Audio", "desc": "Lautstärke, Ausgabegerät und Anwendungs-Mixer steuern" }
```

In `client/src/i18n/locales/en/admin.json`, an derselben Stelle:

```json
        "controlAudio": { "label": "Audio", "desc": "Control volume, output device and the per-app mixer" }
```

> Beide Dateien vorher lesen und die Einträge **einfügen**, nicht die Datei überschreiben. Auf das Komma nach dem vorherigen Eintrag achten.

- [ ] **Step 3: Prüfen, dass nichts bricht**

Run: `cd client ; npx vitest run`
Expected: PASS — die gesamte Frontend-Suite ohne neue Fehler.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/user-management/PowerPermissionsSection.tsx client/src/i18n/locales/de/admin.json client/src/i18n/locales/en/admin.json
git commit -m "feat(audio): Audio-Toggle in den Systemberechtigungen"
```

---

## Task 8: Dokumentation und Gesamtverifikation

**Files:**
- Modify: `backend/app/plugins/CLAUDE.md`
- Modify: `.claude/rules/architecture.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Plugin-Verzeichnisbaum aktualisieren**

In `backend/app/plugins/CLAUDE.md` im Baum unter `installed/` einfügen (alphabetisch vor `optical_drive/`):

```
    ├── audio_control/   # Lautstärke, Ausgabegerät und Per-App-Mixer der Desktop-Session (pactl)
```

- [ ] **Step 2: Route in der Architekturübersicht ergänzen**

In `.claude/rules/architecture.md`, in der Liste der API-Routen nach der `/api/plugins/*`-Zeile:

```
- `/api/plugins/audio_control/*` - Audiosteuerung (Pegel, Ausgabegerät, Per-App-Mixer)
```

- [ ] **Step 3: Quick Reference ergänzen**

In `CLAUDE.md`, im Abschnitt „Quick Reference: Finding Things" nach der `**Fan control**`-Zeile:

```
**Audio control**: `backend/app/plugins/installed/audio_control/` (bundled Plugin; `pactl.py` kapselt den gesamten pactl-Kontakt)
```

- [ ] **Step 4: Backend-Suite der betroffenen Bereiche**

Run: `cd backend ; python -m pytest tests/plugins tests/api/test_power_permissions_routes.py -q --no-cov`
Expected: PASS.

> Laut Repo-Erfahrung können zwei Auth-/Permission-Delete-Tests nur im vollständigen Windows-Lauf flaky sein und einzeln durchlaufen. Nur genau diese beiden dürfen so behandelt werden; alles andere ist eine echte Regression.

- [ ] **Step 5: Frontend-Gates**

Run: `cd client ; npx eslint .`
Expected: 0 Fehler (der CI-Job ist ein Null-Fehler-Gate).

Run: `cd client ; npm run build`
Expected: Build läuft durch. `npm run build` fährt `tsc -b` über App-, Node- und Test-Projekt und deckt mehr ab als `tsc --noEmit`.

- [ ] **Step 6: Ruff über die geänderten Backend-Pfade**

Run: `cd backend ; python -m ruff check app/plugins/installed/audio_control app/core/rate_limiter.py app/api/deps.py app/services/power_permissions.py app/models/power_permissions.py app/schemas/power_permissions.py app/api/routes/sleep.py`
Expected: keine Befunde.

- [ ] **Step 7: Manueller Rauchtest im Dev-Modus**

Run: `python start_dev.py`

Als Admin einloggen und prüfen:
- Plugin-Verwaltung öffnen, `Audiosteuerung` aktivieren.
- Backend neu starten (Plugin-Routen werden nur beim Start gemountet).
- In der Topbar erscheint links neben der Glocke ein Lautsprecher-Symbol.
- Klick öffnet das Popover mit zwei Geräten und zwei Streams (Dev-Backend).
- Der Master-Regler bewegt sich flüssig, der Wert bleibt nach dem Loslassen stehen.
- Der Steam-Stream ist gedämpft dargestellt (`corked`).
- Über einem Stream zeigt der Tooltip den Titel, die Zeile selbst nur „Firefox".
- Benutzerverwaltung → Nicht-Admin bearbeiten: siebter Toggle „Audio" vorhanden und speicherbar.

- [ ] **Step 8: Vektor-Index aktualisieren**

Das Werkzeug `mcp__vectordb-search__index_update` mit `projectPath: D:/Programme (x86)/Baluhost` ausführen, damit die neuen Symbole auffindbar sind.

- [ ] **Step 9: Commit**

```bash
git add backend/app/plugins/CLAUDE.md .claude/rules/architecture.md CLAUDE.md
git commit -m "docs(audio): Audiosteuerung in Plugin-Baum, Routenliste und Quick Reference"
```

---

## Nach dem Plan: Deployment-Hinweis

Der erste Einsatz in Produktion braucht nach dem Merge einen `baluhost-backend`-Neustart, bevor die Endpunkte existieren — Plugin-Router werden ausschließlich beim Start gemountet. Anschließend das Plugin in der Plugin-Verwaltung aktivieren und das Recht `can_control_audio` den gewünschten Benutzern zuteilen. Admins haben es automatisch.
