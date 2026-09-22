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


# Untergrenze, die die Weboberflaeche setzen darf. KDE selbst erlaubt 0
# (gemessen: ``knownSafeBrightnessMin`` = 0) — hier ist es bewusst enger: ein
# Regler aus der Ferne darf den Menschen am Schreibtisch nicht vor einem
# schwarzen Bildschirm sitzen lassen. Derselbe Gedanke wie das Verbot, alle
# Ausgaenge abzuwaehlen.
MIN_BRIGHTNESS_PERCENT = 5


class BrightnessDisplay(BaseModel):
    """Ein Bildschirm, dessen Helligkeit gesetzt werden kann.

    Nicht deckungsgleich mit einem ``DisplayOutput``: powerdevil meldet nur
    eingeschaltete, steuerbare Bildschirme und vergibt eigene Objektnamen. Die
    Zuordnung zu einem Connector-Namen gibt die D-Bus-Schnittstelle nicht her —
    deshalb gibt es hier kein ``output``-Feld, das sie behaupten wuerde.
    """

    id: str = Field(..., description="Lebender powerdevil-Objektname, z. B. 'display13'; nie speichern")
    label: str = Field(..., description="EDID-Name; faellt auf die ID zurueck, wenn er leer ist")
    internal: bool = Field(..., description="Eingebautes Panel statt externem Bildschirm")
    # ge=0, obwohl geschrieben erst ab MIN_BRIGHTNESS_PERCENT werden darf:
    # Plasmas eigener Regler kennt diese Grenze nicht, ein gemeldeter Wert von
    # 2 % ist also moeglich — und ihn auf 5 zu heben waere eine Falschaussage.
    percent: int = Field(..., ge=0, le=100, description="Die Geraeteskala bleibt serverseitig")


class BrightnessInfo(BaseModel):
    """Der Helligkeitsteil von ``GET /state``.

    ``available`` ist getrennt von dem der Ausgaenge: KWin kann laufen, waehrend
    powerdevil fehlt. Der Vorgabewert ist ``False`` — ohne Messung wird keine
    Erreichbarkeit behauptet.
    """

    available: bool = Field(default=False, description="False, wenn powerdevil keine Auskunft gab")
    displays: List[BrightnessDisplay] = Field(default_factory=list)
    detail: Optional[str] = Field(default=None, description="Kurzer Hinweis fuer die UI")


class DisplayLayout(BaseModel):
    """Gesamtzustand, wie ihn GET /state liefert."""

    outputs: List[DisplayOutput] = Field(default_factory=list)
    displays_powered: bool = Field(
        default=False, description="Globaler DPMS-Zustand: leuchtet mindestens ein Ausgang?"
    )
    available: bool = Field(default=True, description="False, wenn KWin nicht erreichbar ist")
    detail: Optional[str] = Field(default=None, description="Kurzer Hinweis fuer die UI")
    brightness: BrightnessInfo = Field(
        default_factory=BrightnessInfo,
        description=(
            "Helligkeit reist im Zustand mit, statt in einer zweiten Route zu liegen: "
            "das Popover pollt alle 5 s gegen ein Limit von 60/min"
        ),
    )


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

    # max_length=16: kein Host meldet gleichzeitig mehr als 16 Ausgaenge
    # (gemessen: BaluNode hat zwei). Ohne obere Grenze koennte ein
    # berechtigter Aufrufer einen beliebig grossen Rumpf schicken, den ein
    # Worker parsen muss, bevor die erste inhaltliche Pruefung greift.
    outputs: List[DisplayOutputRequest] = Field(..., min_length=1, max_length=16)


class BrightnessRequest(BaseModel):
    """Rumpf von ``POST /brightness`` — ein Bildschirm, ein Prozentwert."""

    id: str = Field(..., min_length=1, max_length=64, description="Aus der letzten Enumeration")
    percent: int = Field(..., ge=MIN_BRIGHTNESS_PERCENT, le=100)
