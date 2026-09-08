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

import json
import logging
import subprocess
from typing import List, Optional

from app.plugins.installed.display_output.models import DisplayMode, DisplayOutput
from app.services.power.session_env import wayland_session_env

logger = logging.getLogger(__name__)

# Auf wie viele Nachkommastellen zwei Bildwiederholraten als gleich gelten.
# Feiner zu unterscheiden hiesse, Gleitkomma-Rauschen zu Modi zu erklaeren.
_RATE_PRECISION = 3


def _collapse_modes(raw_modes: object) -> tuple[List[DisplayMode], dict[str, str]]:
    """Baut die entdoppelte Modenliste UND eine ID-Abbildung fuer den Aufrufer.

    Tut, was frueher in ``parse_modes`` allein stand, gibt aber zusaetzlich
    zurueck, auf welche ueberlebende ID jede rohe ID zeigt (auch die des
    Siegers selbst — die zeigt auf sich). ``parse_outputs`` braucht diese
    Abbildung, um ``currentModeId``/``preferredModes[0]`` umzuhaengen, falls
    KWin ausgerechnet die kollabierte (verworfene) ID meldet.

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
        (sortierte, entdoppelte Modi; rohe ID -> ueberlebende ID). Unbrauchbare
        Eintraege werden uebersprungen, nicht als Fehler gemeldet — ein
        defekter Modus darf die Enumeration nicht scheitern lassen.
    """
    if not isinstance(raw_modes, list):
        return [], {}

    seen: dict[tuple, DisplayMode] = {}
    raw_ids_by_key: dict[tuple, List[str]] = {}
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
        raw_ids_by_key.setdefault(key, []).append(mode.id)

    remap = {
        raw_id: seen[key].id
        for key, raw_ids in raw_ids_by_key.items()
        for raw_id in raw_ids
    }
    modes = sorted(seen.values(), key=lambda m: (-(m.width * m.height), -m.refresh_rate, m.id))
    return modes, remap


def parse_modes(raw_modes: object) -> List[DisplayMode]:
    """Wandelt die Modenliste eines Ausgangs in eine anzeigbare Liste.

    Duennwrapper um ``_collapse_modes`` fuer Aufrufer, die nur die Liste
    brauchen (das oeffentliche Format dieser Funktion bleibt unveraendert).

    Args:
        raw_modes: Die ``modes``-Liste eines Ausgangs aus ``kscreen-doctor -j``.

    Returns:
        Sortierte, entdoppelte Modi.
    """
    modes, _ = _collapse_modes(raw_modes)
    return modes


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

    ``currentModeId`` und ``preferredModes[0]`` werden ueber die
    Kollaps-Abbildung aus ``_collapse_modes`` gejagt: zeigt KWin auf die
    groessere (verworfene) ID eines exakt-gleichen Modus-Paares, existiert
    diese ID in der zurueckgegebenen Modenliste nicht mehr, und das
    Frontend-Auswahlfeld faende kein passendes ``<option>`` — die Anzeige
    zeigte dann gar keine aktuelle Aufloesung.
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

        modes, id_remap = _collapse_modes(raw.get("modes"))

        preferred = raw.get("preferredModes")
        preferred_id: Optional[str] = None
        if isinstance(preferred, list) and preferred:
            preferred_id = id_remap.get(str(preferred[0]), str(preferred[0]))
        current = raw.get("currentModeId")
        current_id: Optional[str] = None
        if current is not None:
            current_id = id_remap.get(str(current), str(current))

        outputs.append(
            DisplayOutput(
                name=name,
                connected=bool(raw.get("connected", False)),
                selected=bool(raw.get("enabled", False)),
                lit=None,
                current_mode_id=current_id,
                preferred_mode_id=preferred_id,
                scale=float(raw.get("scale", 1.0) or 1.0),
                priority=int(raw.get("priority", 0) or 0),
                modes=modes,
            )
        )
    return outputs


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
