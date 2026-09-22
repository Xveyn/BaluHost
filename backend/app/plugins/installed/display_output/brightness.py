"""Der einzige Ort, der weiss, dass es ``org.kde.ScreenBrightness`` gibt.

Dieselbe Rolle wie ``kscreen.py`` fuer ``kscreen-doctor``: Aufruf, Auswertung
und Argumentbau leben hier, ein spaeterer Wechsel auf eine Bibliothek beruehrt
nur diese Datei.

**Warum nicht kscreen-doctor.** Es kennt keine Helligkeit. Sein
``sdr-brightness`` (100-1000) ist die Leuchtdichte, mit der SDR-Inhalte in
einen HDR-Bildschirm gerechnet werden — nicht das, was ein Mensch mit
"Helligkeit" meint. Gesetzt wird ueber den Session-Bus-Dienst von powerdevil.

**Warum qdbus6 und nicht dbus_next.** Jede KDE-Interaktion im Haus laeuft so
(``services/power/desktop_windows.py``, ``os_auto_suspend.py``); ``dbus_next``
ist hier nur fuer den System-Bus im Einsatz (``bluetooth/bluez.py``). Ein
Unterprozess hat ueber vier Uvicorn-Worker hinweg keine Verbindung zu pflegen,
und ``GetAll`` holt alle vier Eigenschaften eines Bildschirms in einem Aufruf —
die Enumeration kostet damit ``1 + n`` Aufrufe.

**Warum die Umgebung aus ``wayland_session_env()`` genuegt.** Gemessen: mit
gesetztem ``XDG_RUNTIME_DIR`` und ohne ``DBUS_SESSION_BUS_ADDRESS`` findet
libdbus den Bus unter ``$XDG_RUNTIME_DIR/bus``; ohne ``XDG_RUNTIME_DIR``
scheitert derselbe Aufruf mit "Unable to autolaunch a dbus-daemon". Die
Backend-Unit setzt die Variable nicht — der Helfer tut es.

**Die Objekt-IDs sind so fluechtig wie eine Mode-ID.** ``display13`` haengt am
KWin-Output; nur eingeschaltete, steuerbare Bildschirme erscheinen ueberhaupt
(gemessen: zwei Ausgaenge verbunden, einer abgeschaltet, ein Objekt). Sie wird
nie gespeichert, sondern in jedem Request neu enumeriert — und ``object_path``
laesst ohnehin nur reine Pfadbestandteile durch.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

SERVICE = "org.kde.ScreenBrightness"
ROOT_PATH = "/org/kde/ScreenBrightness"
ROOT_IFACE = "org.kde.ScreenBrightness"
DISPLAY_IFACE = "org.kde.ScreenBrightness.Display"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"

QDBUS_BINARY = "qdbus6"
# Ein haengender Aufruf darf keinen Worker blockieren.
QDBUS_TIMEOUT_SECONDS = 10

# Die Introspektion dokumentiert die Bedeutung der ``flags``-Bits nicht.
# Deshalb wird das neutrale 0 geschickt und nichts geraten.
_NEUTRAL_FLAGS = "0"

# Was ein D-Bus-Objektpfad-Bestandteil sein darf. Kein Punkt, kein Schraegstrich,
# kein Leerzeichen — alles andere wird verworfen, nicht maskiert.
_ID = re.compile(r"[A-Za-z0-9_]{1,64}")


@dataclass(frozen=True)
class Properties:
    """Die vier Eigenschaften eines Bildschirms, wie ``GetAll`` sie liefert."""

    raw: int
    maximum: int
    label: str
    internal: bool


@dataclass(frozen=True)
class DisplayBrightness:
    """Ein steuerbarer Bildschirm samt seiner Geraeteskala.

    ``raw`` und ``maximum`` bleiben absichtlich beieinander: ohne das obere
    Ende laesst sich weder ein Prozentwert bilden noch einer zurueckrechnen,
    und ``maximum`` ist geraeteabhaengig (gemessen 10000; Notebook-Panels
    melden oft zweistellige Werte).
    """

    id: str
    label: str
    internal: bool
    raw: int
    maximum: int

    @property
    def percent(self) -> int:
        return to_percent(self.raw, self.maximum)


def parse_display_ids(output: str) -> List[str]:
    """Liest die Objektliste aus der Ausgabe von ``DisplaysDBusNames``.

    Args:
        output: stdout des Property-Aufrufs, ein Name je Zeile.

    Returns:
        Die Namen in ihrer gemeldeten Reihenfolge. Was kein reiner
        Pfadbestandteil ist, wird uebersprungen und protokolliert — powerdevil
        baut diese Namen, aber sie werden zu einem Objektpfad zusammengesetzt.
    """
    ids: List[str] = []
    for line in output.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if not _ID.fullmatch(candidate):
            logger.warning("Unbrauchbarer Helligkeits-Objektname uebersprungen: %r", candidate)
            continue
        ids.append(candidate)
    return ids


def object_path(display_id: str) -> str:
    """Setzt den Objektpfad eines Bildschirms zusammen.

    Raises:
        ValueError: Die ID ist kein reiner Pfadbestandteil. Das ist die zweite
            Haelfte der Absicherung — die erste ist die Pruefung gegen die
            Live-Enumeration im Service.
    """
    if not _ID.fullmatch(display_id):
        raise ValueError(f"Kein gueltiger Objektname: {display_id!r}")
    return f"{ROOT_PATH}/{display_id}"


def _key_values(output: str) -> Dict[str, str]:
    """Zerlegt die ``Key: Value``-Zeilen von ``GetAll``.

    Getrennt wird am ERSTEN Doppelpunkt: ein Modellname wie ``Dell Inc.:
    U2720Q`` behaelt so seinen Rest.
    """
    values: Dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        values[key.strip()] = value.strip()
    return values


def parse_properties(output: str) -> Optional[Properties]:
    """Wandelt eine ``GetAll``-Ausgabe in die vier Eigenschaften.

    Returns:
        ``None``, wenn die Antwort unvollstaendig oder unbrauchbar ist — ein
        fehlender Wert wird nicht geraten. Auch ein ``MaxBrightness`` von 0
        ergibt ``None``: ohne obere Grenze gibt es weder Prozent noch Zielwert,
        und ein solcher Eintrag als "0 %" in der Liste waere eine Erfindung.
    """
    values = _key_values(output)
    try:
        raw = int(values["Brightness"])
        maximum = int(values["MaxBrightness"])
    except (KeyError, ValueError):
        logger.debug("Unbrauchbare Helligkeits-Eigenschaften: %r", output)
        return None
    if maximum <= 0:
        logger.debug("Bildschirm ohne Helligkeitsspanne uebersprungen")
        return None
    return Properties(
        raw=raw,
        maximum=maximum,
        label=values.get("Label", ""),
        internal=values.get("IsInternal") == "true",
    )


def to_percent(raw: int, maximum: int) -> int:
    """Rechnet einen Geraetewert in Prozent (0-100).

    Gerundet wird kaufmaennisch (``+ 0.5``), nicht mit ``round()``: dessen
    Rundung zur geraden Zahl liesse 2,5 % zu 2 werden und 3,5 % zu 4.
    """
    if maximum <= 0:
        return 0
    return int(raw * 100 / maximum + 0.5)


def to_raw(percent: int, maximum: int) -> int:
    """Rechnet Prozent in den Geraetewert und klammert ihn in die Spanne.

    Die Route begrenzt bereits auf ``MIN_BRIGHTNESS_PERCENT``..100; diese
    Klammer ist die zweite Haelfte davon und haelt auch, wenn das Modell sich
    aendert.
    """
    clamped = max(0, min(100, percent))
    return max(0, min(maximum, int(clamped * maximum / 100 + 0.5)))


def run_qdbus(args: List[str]) -> tuple[bool, str]:
    """Fuehrt qdbus6 mit Listen-Argumenten aus.

    Args:
        args: Argumente ohne den Programmnamen, beginnend mit dem Dienstnamen.

    Returns:
        (Erfolg, stdout bzw. Fehlertext). **stderr entscheidet nicht ueber
        Erfolg** — gemessen: bei einem Locale ohne UTF-8 schreibt qdbus6 vier
        Zeilen Warnung nach stderr und liefert trotzdem rc=0. Die Ausgabe ist
        roh und traegt EDID-Namen; Aufrufer duerfen sie **nicht** in eine
        Client-Antwort uebernehmen.
    """
    try:
        completed = subprocess.run(
            [QDBUS_BINARY, *args],
            capture_output=True,
            text=True,
            timeout=QDBUS_TIMEOUT_SECONDS,
            env=wayland_session_env(),
        )
    except FileNotFoundError:
        logger.warning("%s ist nicht installiert", QDBUS_BINARY)
        return False, f"{QDBUS_BINARY} nicht gefunden"
    except subprocess.TimeoutExpired:
        logger.warning("%s-Zeitueberschreitung: %s", QDBUS_BINARY, args)
        return False, "Zeitueberschreitung"
    except OSError as exc:
        logger.warning("%s-Aufruf fehlgeschlagen: %s", QDBUS_BINARY, exc)
        return False, "Aufruf fehlgeschlagen"

    if completed.returncode != 0:
        logger.warning(
            "%s %s endete mit %s: %s",
            QDBUS_BINARY, args, completed.returncode, completed.stderr.strip(),
        )
        return False, completed.stderr.strip() or "qdbus-Fehler"
    return True, completed.stdout.strip()


def read_displays() -> Optional[List[DisplayBrightness]]:
    """Enumeriert die steuerbaren Bildschirme.

    Returns:
        Die Liste, oder ``None``, wenn der Dienst nicht erreichbar ist. Die
        Unterscheidung traegt: ``None`` heisst "keine Auskunft", ``[]`` heisst
        "erreichbar, aber nichts steuerbar" — die UI zeigt beides verschieden.
        Ein einzelner Bildschirm, dessen Eigenschaften nicht zu lesen sind,
        wird uebersprungen und nimmt die anderen nicht mit.
    """
    ok, output = run_qdbus(
        [SERVICE, ROOT_PATH, f"{PROPERTIES_IFACE}.Get", ROOT_IFACE, "DisplaysDBusNames"]
    )
    if not ok:
        return None

    displays: List[DisplayBrightness] = []
    for display_id in parse_display_ids(output):
        ok, properties_output = run_qdbus(
            [SERVICE, object_path(display_id), f"{PROPERTIES_IFACE}.GetAll", DISPLAY_IFACE]
        )
        if not ok:
            continue
        props = parse_properties(properties_output)
        if props is None:
            continue
        displays.append(
            DisplayBrightness(
                id=display_id,
                # Ein leerer EDID-Name ergaebe einen Regler ohne Beschriftung.
                label=props.label or display_id,
                internal=props.internal,
                raw=props.raw,
                maximum=props.maximum,
            )
        )
    return displays


def write_brightness(display_id: str, raw: int) -> tuple[bool, str]:
    """Setzt den Geraetewert eines Bildschirms.

    Raises:
        ValueError: ``display_id`` ist kein gueltiger Objektname (aus
            ``object_path``).
    """
    return run_qdbus(
        [
            SERVICE,
            object_path(display_id),
            f"{DISPLAY_IFACE}.SetBrightness",
            str(raw),
            _NEUTRAL_FLAGS,
        ]
    )
