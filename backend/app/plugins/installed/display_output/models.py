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

    # max_length=16: kein Host meldet gleichzeitig mehr als 16 Ausgaenge
    # (gemessen: BaluNode hat zwei). Ohne obere Grenze koennte ein
    # berechtigter Aufrufer einen beliebig grossen Rumpf schicken, den ein
    # Worker parsen muss, bevor die erste inhaltliche Pruefung greift.
    outputs: List[DisplayOutputRequest] = Field(..., min_length=1, max_length=16)
