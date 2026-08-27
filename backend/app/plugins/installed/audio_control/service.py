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
        logger.info("Sink-Pegel angefordert: sink=%s percent=%s", sink_id, percent)
        return await self._backend.set_sink_volume(sink_id, percent)

    async def set_sink_mute(self, sink_id: int, muted: bool) -> Tuple[bool, str]:
        """Schaltet ein Ausgabegeraet stumm oder wieder laut."""
        logger.info("Sink-Stummschaltung angefordert: sink=%s muted=%s", sink_id, muted)
        return await self._backend.set_sink_mute(sink_id, muted)

    async def set_default_sink(self, name: str) -> Tuple[bool, str]:
        """Macht ein Geraet zum Standardausgang."""
        logger.info("Standardgeraet-Wechsel angefordert: name=%s", name)
        return await self._backend.set_default_sink(name)

    async def set_stream_volume(self, stream_id: int, percent: int) -> Tuple[bool, str]:
        """Setzt den Pegel eines einzelnen Streams."""
        logger.info("Stream-Pegel angefordert: stream=%s percent=%s", stream_id, percent)
        return await self._backend.set_stream_volume(stream_id, percent)

    async def set_stream_mute(self, stream_id: int, muted: bool) -> Tuple[bool, str]:
        """Schaltet einen einzelnen Stream stumm oder wieder laut."""
        logger.info("Stream-Stummschaltung angefordert: stream=%s muted=%s", stream_id, muted)
        return await self._backend.set_stream_mute(stream_id, muted)


def get_audio_service() -> AudioService:
    """Liefert die Service-Instanz und legt sie beim ersten Aufruf an."""
    global _service
    if _service is None:
        _service = AudioService()
    return _service
