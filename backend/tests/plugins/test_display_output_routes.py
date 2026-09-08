"""Routen-Tests: Berechtigung, Statuscodes, keine Interna in der Antwort."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_power_manage_displays
from app.plugins.installed.display_output import DisplayOutputPlugin
from app.plugins.installed.display_output import service as service_module
from app.plugins.installed.display_output.backend import DevDisplayBackend
from app.plugins.installed.display_output.models import DisplayLayout
from app.plugins.installed.display_output.service import DisplayService

BASE = "/api/plugins/display_output"


class _User:
    username = "admin"
    role = "admin"
    id = 1


def _app(service: DisplayService) -> TestClient:
    app = FastAPI()
    app.include_router(DisplayOutputPlugin().get_router(), prefix=BASE)
    app.dependency_overrides[require_power_manage_displays] = lambda: _User()
    return TestClient(app)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    service = DisplayService(backend=DevDisplayBackend())
    monkeypatch.setattr(service_module, "get_display_service", lambda: service)
    return _app(service)


class TestStateRoute:
    def test_returns_both_outputs_with_their_modes(self, client):
        body = client.get(f"{BASE}/state").json()
        assert body["available"] is True
        assert [o["name"] for o in body["outputs"]] == ["HDMI-A-1", "DP-3"]
        assert body["outputs"][1]["modes"]

    def test_the_two_levels_are_separate_fields(self, client):
        output = client.get(f"{BASE}/state").json()["outputs"][0]
        assert "selected" in output and "lit" in output
        assert "enabled" not in output

    def test_a_mode_carries_id_name_and_unrounded_rate(self, client):
        dp3 = client.get(f"{BASE}/state").json()["outputs"][1]
        mode = next(m for m in dp3["modes"] if m["id"] == "58")
        assert mode["name"] == "3840x2160@120"
        assert mode["refresh_rate"] == pytest.approx(119.87999725, rel=1e-9)


class TestApplyRoute:
    def test_a_valid_change_succeeds(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "HDMI-A-1", "selected": True, "mode_id": "1", "mode_name": "2560x1440@144"},
        ]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_an_unknown_output_is_400(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-99", "selected": True},
        ]})
        assert resp.status_code == 400

    def test_a_foreign_mode_is_400(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "HDMI-A-1", "selected": True,
             "mode_id": "57", "mode_name": "3840x2160@120"},
        ]})
        assert resp.status_code == 400

    def test_a_stale_mode_name_is_409(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-3", "selected": True,
             "mode_id": "58", "mode_name": "1920x1080@60"},
        ]})
        assert resp.status_code == 409

    def test_deselecting_everything_is_400(self, client):
        resp = client.post(f"{BASE}/apply", json={"outputs": [
            {"name": "HDMI-A-1", "selected": False},
            {"name": "DP-3", "selected": False},
        ]})
        assert resp.status_code == 400

    def test_an_empty_body_is_422(self, client):
        assert client.post(f"{BASE}/apply", json={"outputs": []}).status_code == 422

    def test_a_raw_dict_body_is_rejected(self, client):
        assert client.post(f"{BASE}/apply", json={"nonsense": 1}).status_code == 422


class TestFailureMapping:
    def test_an_unreachable_session_reads_as_available_false_not_an_error(self, monkeypatch):
        class _Dead:
            async def get_layout(self):
                return DisplayLayout(available=False, detail="KWin nicht erreichbar")

            async def apply(self, wanted, live_outputs):
                raise AssertionError("darf nicht laufen")

        service = DisplayService(backend=_Dead())
        monkeypatch.setattr(service_module, "get_display_service", lambda: service)
        resp = _app(service).get(f"{BASE}/state")
        # Lesen liefert available=false statt eines Fehlers: die UI soll den
        # Zustand anzeigen koennen, nicht nur eine Fehlermeldung.
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_an_unreachable_session_is_502_on_write(self, monkeypatch):
        class _Dead:
            async def get_layout(self):
                return DisplayLayout(available=False, detail="KWin nicht erreichbar")

            async def apply(self, wanted, live_outputs):
                raise AssertionError("darf nicht laufen")

        service = DisplayService(backend=_Dead())
        monkeypatch.setattr(service_module, "get_display_service", lambda: service)
        resp = _app(service).post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-3", "selected": True},
        ]})
        assert resp.status_code == 502

    def test_no_kscreen_output_reaches_the_client(self, monkeypatch):
        secret = "/sys/devices/pci0000:00/EDID-Geheimnis"

        class _Chatty:
            async def get_layout(self):
                return (await DevDisplayBackend().get_layout())

            async def apply(self, wanted, live_outputs):
                return False, secret

        service = DisplayService(backend=_Chatty())
        monkeypatch.setattr(service_module, "get_display_service", lambda: service)
        resp = _app(service).post(f"{BASE}/apply", json={"outputs": [
            {"name": "DP-3", "selected": True},
        ]})
        assert resp.status_code == 502
        assert secret not in resp.text


class TestPermission:
    def test_the_read_route_is_gated_too(self):
        # Die Ausgangsliste verraet die angeschlossene Hardware.
        app = FastAPI()
        app.include_router(DisplayOutputPlugin().get_router(), prefix=BASE)
        # Ohne dependency_overrides greift die echte Abhaengigkeit und
        # scheitert mangels Token.
        assert TestClient(app).get(f"{BASE}/state").status_code in (401, 403)
