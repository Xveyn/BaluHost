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

        monkeypatch.setattr(svc.settings, "is_dev_mode", False, raising=False)
        monkeypatch.setattr(svc.platform, "system", lambda: "Windows")
        service = svc.AudioService()
        assert isinstance(service._backend, DevAudioBackend)
