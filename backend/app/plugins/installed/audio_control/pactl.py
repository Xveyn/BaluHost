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
        return 0
    if isinstance(raw, (int, float)):
        return max(0, int(raw))
    if isinstance(raw, str):
        try:
            return max(0, int(float(raw.strip().rstrip("%"))))
        except ValueError:
            logger.debug("Prozentwert nicht auswertbar: %r", raw)
            return 0
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
            continue
        props = entry.get("properties")
        if not isinstance(props, dict):
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
