"""Tests fuer PipeWireAudioBackend: legt das pactl-Befehlsvokabular fest.

``run_pactl``/``run_pactl_json`` werden im Namensraum von ``backend.py``
gepatcht, damit kein echtes ``pactl`` gebraucht wird. Jeder Test nagelt die
exakte Argumentliste fest — ein Vertipper wie ``set-sink-volume`` statt
``set-sink-input-volume`` (oder umgekehrt) faellt sonst durch keinen Test auf,
weil der Dev-Modus davon unberuehrt bleibt.
"""
import pytest

import app.plugins.installed.audio_control.backend as backend_module
from app.plugins.installed.audio_control.backend import PipeWireAudioBackend

# Minimal gueltige pactl-JSON-Eintraege, genug fuer parse_sinks/parse_streams.
FAKE_SINK_JSON = [
    {
        "index": 61,
        "name": "alsa_output.test.iec958-stereo",
        "description": "Test Sink",
        "volume": {"front-left": {"value_percent": "50%"}},
        "mute": False,
    }
]

FAKE_STREAM_JSON = [
    {
        "index": 789,
        "sink": 61,
        "corked": False,
        "mute": False,
        "volume": {"front-left": {"value_percent": "20%"}},
        "properties": {
            "application.name": "Testapp",
            "media.class": "Stream/Output/Audio",
        },
    }
]


@pytest.fixture
def backend() -> PipeWireAudioBackend:
    return PipeWireAudioBackend()


class TestSinkCommands:
    @pytest.mark.asyncio
    async def test_set_sink_volume_uses_correct_command(self, monkeypatch, backend):
        calls = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: (calls.append(list(args)), (True, "ok"))[1]
        )

        ok, _ = await backend.set_sink_volume(61, 40)

        assert ok is True
        assert calls == [["set-sink-volume", "61", "40%"]]

    @pytest.mark.asyncio
    async def test_set_sink_mute_true_uses_correct_command(self, monkeypatch, backend):
        calls = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: (calls.append(list(args)), (True, "ok"))[1]
        )

        await backend.set_sink_mute(61, True)

        assert calls == [["set-sink-mute", "61", "1"]]

    @pytest.mark.asyncio
    async def test_set_sink_mute_false_uses_correct_command(self, monkeypatch, backend):
        calls = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: (calls.append(list(args)), (True, "ok"))[1]
        )

        await backend.set_sink_mute(61, False)

        assert calls == [["set-sink-mute", "61", "0"]]

    @pytest.mark.asyncio
    async def test_set_default_sink_uses_correct_command(self, monkeypatch, backend):
        calls = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: (calls.append(list(args)), (True, "ok"))[1]
        )

        await backend.set_default_sink("alsa_output.test")

        assert calls == [["set-default-sink", "alsa_output.test"]]


class TestStreamCommands:
    @pytest.mark.asyncio
    async def test_set_stream_volume_uses_correct_command(self, monkeypatch, backend):
        calls = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: (calls.append(list(args)), (True, "ok"))[1]
        )

        ok, _ = await backend.set_stream_volume(789, 20)

        assert ok is True
        assert calls == [["set-sink-input-volume", "789", "20%"]]

    @pytest.mark.asyncio
    async def test_set_stream_mute_true_uses_correct_command(self, monkeypatch, backend):
        calls = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: (calls.append(list(args)), (True, "ok"))[1]
        )

        await backend.set_stream_mute(789, True)

        assert calls == [["set-sink-input-mute", "789", "1"]]

    @pytest.mark.asyncio
    async def test_set_stream_mute_false_uses_correct_command(self, monkeypatch, backend):
        calls = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: (calls.append(list(args)), (True, "ok"))[1]
        )

        await backend.set_stream_mute(789, False)

        assert calls == [["set-sink-input-mute", "789", "0"]]


class TestGetState:
    @pytest.mark.asyncio
    async def test_reads_sinks_default_and_sink_inputs_in_order(self, monkeypatch, backend):
        json_calls = []
        plain_calls = []

        def fake_run_pactl_json(args):
            args = list(args)
            json_calls.append(args)
            if args == ["list", "sinks"]:
                return FAKE_SINK_JSON
            if args == ["list", "sink-inputs"]:
                return FAKE_STREAM_JSON
            raise AssertionError(f"unerwarteter run_pactl_json-Aufruf: {args}")

        def fake_run_pactl(args):
            args = list(args)
            plain_calls.append(args)
            return True, "alsa_output.test.iec958-stereo"

        monkeypatch.setattr(backend_module, "run_pactl_json", fake_run_pactl_json)
        monkeypatch.setattr(backend_module, "run_pactl", fake_run_pactl)

        state = await backend.get_state()

        # Reihenfolge und Exaktheit sind der Punkt: sinks vor sink-inputs,
        # kein "list sinks" statt "list sink-inputs" vertauscht.
        assert json_calls == [["list", "sinks"], ["list", "sink-inputs"]]
        assert plain_calls == [["get-default-sink"]]
        assert state.available is True
        assert len(state.sinks) == 1
        assert state.sinks[0].id == 61
        assert state.sinks[0].is_default is True
        assert len(state.streams) == 1
        assert state.streams[0].id == 789

    @pytest.mark.asyncio
    async def test_available_false_when_sink_query_fails(self, monkeypatch, backend):
        monkeypatch.setattr(backend_module, "run_pactl_json", lambda args: None)
        # Wenn die Sink-Abfrage bereits scheitert, darf gar kein weiterer
        # Aufruf erfolgen (frueher Ausstieg in _read_state).
        called_run_pactl = []
        monkeypatch.setattr(
            backend_module, "run_pactl", lambda args: called_run_pactl.append(list(args))
        )

        state = await backend.get_state()

        assert state.available is False
        assert called_run_pactl == []
