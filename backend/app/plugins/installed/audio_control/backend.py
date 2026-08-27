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
