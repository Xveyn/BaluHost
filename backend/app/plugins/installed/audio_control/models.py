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
