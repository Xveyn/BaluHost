"""Routen-Tests der Audiosteuerung: Berechtigung, Validierung, Fehlerfaelle."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_power_control_audio
from app.plugins.installed.audio_control import AudioControlPlugin
from app.plugins.installed.audio_control.backend import DevAudioBackend
from app.plugins.installed.audio_control.service import AudioService
from app.plugins.installed.audio_control import service as service_module
import app.plugins.installed.audio_control as plugin_module


class _User:
    username = "admin"
    role = "admin"
    id = 1


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """App nur mit dem Plugin-Router, Dev-Backend, Berechtigung erfuellt."""
    monkeypatch.setattr(
        service_module, "get_audio_service", lambda: AudioService(backend=DevAudioBackend())
    )
    app = FastAPI()
    app.include_router(AudioControlPlugin().get_router(), prefix="/api/plugins/audio_control")
    app.dependency_overrides[require_power_control_audio] = lambda: _User()
    return TestClient(app)


class TestStateRoute:
    def test_returns_sinks_and_streams(self, client):
        resp = client.get("/api/plugins/audio_control/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert len(body["sinks"]) == 2
        assert len(body["streams"]) == 2

    def test_stream_carries_application_and_title(self, client):
        body = client.get("/api/plugins/audio_control/state").json()
        stream = body["streams"][0]
        assert stream["application"] == "Firefox"
        assert "title" in stream
        assert "corked" in stream


class TestWriteRoutes:
    def test_setting_sink_volume_succeeds(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": 40})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_setting_sink_mute_succeeds(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/mute", json={"muted": True})
        assert resp.status_code == 200

    def test_setting_default_sink_succeeds(self, client):
        resp = client.put(
            "/api/plugins/audio_control/default-sink",
            json={"name": "alsa_output.dev-gpu.hdmi-stereo"},
        )
        assert resp.status_code == 200

    def test_setting_stream_volume_succeeds(self, client):
        resp = client.put("/api/plugins/audio_control/streams/789/volume", json={"percent": 20})
        assert resp.status_code == 200


class TestBackendOutputNeverReachesTheClient:
    """pactl-Ausgaben enthalten Geraetenamen und Pfade — sie bleiben im Log."""

    def test_a_successful_write_returns_no_backend_message(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": 40})
        body = resp.json()
        assert body == {"success": True}
        assert "message" not in body

    def test_a_successful_default_sink_switch_returns_no_backend_message(self, client):
        resp = client.put(
            "/api/plugins/audio_control/default-sink",
            json={"name": "alsa_output.dev-gpu.hdmi-stereo"},
        )
        assert resp.json() == {"success": True}


class TestDefaultSinkNameIsValidatedBeforeTheCall:
    """Die einzige Stelle, an der eine Client-Zeichenkette ein pactl-Argument wird."""

    def test_an_unknown_name_never_reaches_the_backend(self, monkeypatch, client):
        from app.plugins.installed.audio_control.backend import DevAudioBackend

        called: list[str] = []

        async def _spy(self, name: str):
            called.append(name)
            return True, "sollte nie passieren"

        monkeypatch.setattr(DevAudioBackend, "set_default_sink", _spy)

        resp = client.put(
            "/api/plugins/audio_control/default-sink", json={"name": "gibt.es.nicht"}
        )

        assert resp.status_code == 404
        assert called == [], "unbekannter Name darf das Backend nie erreichen"


class TestValidation:
    def test_volume_above_the_cap_is_rejected(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": 1000})
        assert resp.status_code == 422

    def test_negative_volume_is_rejected(self, client):
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": -1})
        assert resp.status_code == 422

    def test_empty_default_sink_name_is_rejected(self, client):
        resp = client.put("/api/plugins/audio_control/default-sink", json={"name": ""})
        assert resp.status_code == 422


class TestUnknownIds:
    def test_unknown_sink_is_a_404(self, client):
        """Ein veralteter Index ist ein Normalfall, kein Serverfehler."""
        resp = client.put("/api/plugins/audio_control/sinks/9999/volume", json={"percent": 10})
        assert resp.status_code == 404

    def test_unknown_stream_is_a_404(self, client):
        resp = client.put("/api/plugins/audio_control/streams/9999/mute", json={"muted": True})
        assert resp.status_code == 404

    def test_unknown_default_sink_is_a_404(self, client):
        resp = client.put("/api/plugins/audio_control/default-sink", json={"name": "gibt.es.nicht"})
        assert resp.status_code == 404


class TestBrokenAudioStack:
    """Eine Stoerung darf nicht als 'nicht gefunden' gemeldet werden."""

    @pytest.fixture
    def broken_client(self, monkeypatch) -> TestClient:
        from app.plugins.installed.audio_control.models import AudioState

        class _BrokenBackend:
            async def get_state(self) -> AudioState:
                return AudioState(available=False, detail="PipeWire nicht erreichbar")

            async def set_sink_volume(self, sink_id, percent):
                return False, "Zeitueberschreitung"

            async def set_sink_mute(self, sink_id, muted):
                return False, "Zeitueberschreitung"

            async def set_default_sink(self, name):
                return False, "Zeitueberschreitung"

            async def set_stream_volume(self, stream_id, percent):
                return False, "Zeitueberschreitung"

            async def set_stream_mute(self, stream_id, muted):
                return False, "Zeitueberschreitung"

        monkeypatch.setattr(
            service_module, "get_audio_service", lambda: AudioService(backend=_BrokenBackend())
        )
        app = FastAPI()
        app.include_router(AudioControlPlugin().get_router(), prefix="/api/plugins/audio_control")
        app.dependency_overrides[require_power_control_audio] = lambda: _User()
        return TestClient(app)

    def test_state_reports_unavailable_instead_of_failing(self, broken_client):
        resp = broken_client.get("/api/plugins/audio_control/state")
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_a_write_against_a_broken_stack_is_a_502_not_a_404(self, broken_client):
        resp = broken_client.put(
            "/api/plugins/audio_control/sinks/61/volume", json={"percent": 10}
        )
        assert resp.status_code == 502

    def test_a_broken_default_sink_write_is_a_502(self, broken_client):
        resp = broken_client.put(
            "/api/plugins/audio_control/default-sink", json={"name": "egal"}
        )
        assert resp.status_code == 502


class TestPermissionIsRequired:
    def test_every_route_depends_on_the_audio_permission(self):
        """Auch die lesende Route — media.name verraet den laufenden Titel."""
        router = AudioControlPlugin().get_router()
        # Ohne diese Zahl liefe die Schleife unten grün, wenn die Routenliste
        # (versehentlich) leer waere — die falsche Ausfallrichtung fuer einen
        # Test, der eine Sicherheitsgrenze absichert.
        assert len(router.routes) == 6
        for route in router.routes:
            dependencies = [d.call for d in route.dependant.dependencies]
            assert require_power_control_audio in dependencies, route.path


class TestAuditLogging:
    """Nur Geraetewechsel und Stummschaltung landen im Audit-Log.

    Pegeländerungen duerfen keinen Audit-Eintrag erzeugen — ein Schieberegler
    wuerde das Log sonst mit Dutzenden Eintraegen zumuellen und die
    interessanten Vorgaenge darin begraben. Ersetzt ``get_audit_logger_db`` im
    Namensraum des Plugin-Moduls durch einen mitschreibenden Stub, statt nur
    auf den HTTP-Statuscode zu schauen — sonst waere eine spaeter versehentlich
    in eine Pegel-Route eingefuegte ``_audit(...)``-Zeile lautlos.
    """

    @pytest.fixture
    def audit_client(self, monkeypatch):
        events: list[dict] = []

        class _RecordingAuditLogger:
            def log_event(self, **kwargs):
                events.append(kwargs)

            def log_security_event(self, **kwargs):
                # In diesen Tests immer admin — wird nicht erwartet, aber die
                # Stub-Methode muss existieren, falls sie doch aufgerufen wird.
                pass

        monkeypatch.setattr(plugin_module, "get_audit_logger_db", lambda: _RecordingAuditLogger())
        monkeypatch.setattr(
            service_module, "get_audio_service", lambda: AudioService(backend=DevAudioBackend())
        )
        app = FastAPI()
        app.include_router(AudioControlPlugin().get_router(), prefix="/api/plugins/audio_control")
        app.dependency_overrides[require_power_control_audio] = lambda: _User()
        return TestClient(app), events

    def test_sink_volume_writes_no_audit_entry(self, audit_client):
        client, events = audit_client
        resp = client.put("/api/plugins/audio_control/sinks/61/volume", json={"percent": 40})
        assert resp.status_code == 200
        assert events == []

    def test_stream_volume_writes_no_audit_entry(self, audit_client):
        client, events = audit_client
        resp = client.put("/api/plugins/audio_control/streams/789/volume", json={"percent": 20})
        assert resp.status_code == 200
        assert events == []

    def test_sink_mute_writes_exactly_one_audit_entry(self, audit_client):
        client, events = audit_client
        resp = client.put("/api/plugins/audio_control/sinks/61/mute", json={"muted": True})
        assert resp.status_code == 200
        assert len(events) == 1
        assert events[0]["action"] == "audio_sink_mute"

    def test_default_sink_writes_exactly_one_audit_entry(self, audit_client):
        client, events = audit_client
        resp = client.put(
            "/api/plugins/audio_control/default-sink",
            json={"name": "alsa_output.dev-gpu.hdmi-stereo"},
        )
        assert resp.status_code == 200
        assert len(events) == 1
        assert events[0]["action"] == "audio_default_sink"

    def test_stream_mute_writes_exactly_one_audit_entry(self, audit_client):
        client, events = audit_client
        resp = client.put("/api/plugins/audio_control/streams/789/mute", json={"muted": True})
        assert resp.status_code == 200
        assert len(events) == 1
        assert events[0]["action"] == "audio_stream_mute"
