"""Routen: Recht, LAN-Pruefung, Statuscodes, Audit, keine Interna, kein Code im Log."""
import asyncio
import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.plugins.installed.bluetooth as plugin_module
from app.api.deps import require_power_manage_bluetooth
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.plugins.installed.bluetooth import BluetoothPlugin, pairing
from app.plugins.installed.bluetooth import service as service_module
from app.plugins.installed.bluetooth.backend import DEV_ADAPTER_PATH, DevBluetoothBackend
from app.plugins.installed.bluetooth.bluez import BlueZError
from app.plugins.installed.bluetooth.service import BluetoothService
from app.services.monitoring import shm

BASE = "/api/plugins/bluetooth"
KEYBOARD = "AA:AA:AA:AA:AA:04"
PASSKEY = 482913


class _Admin:
    id = 1
    username = "admin"
    role = "admin"


class _Other:
    id = 2
    username = "someone"
    role = "user"


class _Lan:
    value = True


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(shm, "SHM_DIR", tmp_path / "shm")
    monkeypatch.setattr(pairing, "LOCK_PATH", tmp_path / "pairing.lock")
    monkeypatch.setattr(pairing, "ANSWER_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pairing, "RESULT_DISPLAY_SECONDS", 60.0)
    monkeypatch.setattr(settings, "bluetooth_adapter_address", "")
    _Lan.value = True
    monkeypatch.setattr(service_module, "is_private_or_local_ip", lambda host: _Lan.value)


@pytest.fixture
def audit(monkeypatch):
    events: list[dict] = []
    security: list[dict] = []

    class _Recorder:
        def log_event(self, **kwargs):
            events.append(kwargs)

        def log_security_event(self, **kwargs):
            security.append(kwargs)

    monkeypatch.setattr(plugin_module, "get_audit_logger_db", lambda: _Recorder())
    return events, security


def _make(monkeypatch, backend=None, user=_Admin):
    backend = backend or DevBluetoothBackend(step_seconds=0.01, passkey=PASSKEY)
    service = BluetoothService(backend=backend, scan_seconds=300)
    monkeypatch.setattr(service_module, "get_bluetooth_service", lambda: service)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(BluetoothPlugin().get_router(), prefix=BASE)
    app.dependency_overrides[require_power_manage_bluetooth] = lambda: user()
    return app, service, backend


def _poll(client, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BASE}/pairing").json()
        if predicate(body):
            return body
        time.sleep(0.02)
    raise AssertionError("Zustand nicht erreicht")


class TestPermission:
    def test_the_read_route_is_gated(self):
        app = FastAPI()
        app.include_router(BluetoothPlugin().get_router(), prefix=BASE)
        assert TestClient(app).get(f"{BASE}/state").status_code in (401, 403)

    def test_the_pair_route_is_gated(self):
        app = FastAPI()
        app.include_router(BluetoothPlugin().get_router(), prefix=BASE)
        resp = TestClient(app).post(f"{BASE}/devices/{KEYBOARD}/pair")
        assert resp.status_code in (401, 403)


class TestState:
    def test_state_lists_the_dev_devices(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        body = TestClient(app).get(f"{BASE}/state").json()
        assert body["available"] is True
        assert {d["kind"] for d in body["devices"]} == {"controller", "audio"}
        assert body["can_pair_here"] is True


class TestPairRoute:
    def test_outside_the_lan_is_403_even_for_an_admin_and_is_audited(self, monkeypatch, audit):
        events, _ = audit
        _Lan.value = False
        app, _, _ = _make(monkeypatch)
        resp = TestClient(app).post(f"{BASE}/devices/{KEYBOARD}/pair")
        assert resp.status_code == 403
        assert events[-1]["action"] == "bluetooth_pair_denied"
        assert events[-1]["success"] is False

    def test_a_malformed_address_is_400(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/devices/nonsense/pair").status_code == 400

    def test_an_unknown_address_is_404(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/devices/AA:AA:AA:AA:AA:77/pair").status_code == 404

    def test_an_already_paired_device_is_409(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/devices/AA:AA:AA:AA:AA:02/pair").status_code == 409

    def test_a_keyboard_pairs_and_the_code_never_reaches_log_or_audit(self, monkeypatch, audit, caplog):
        caplog.set_level(logging.DEBUG)
        events, _ = audit
        # 0,2 s pro Ziffer: die Code-Anzeige steht ~1,4 s — lang genug, dass
        # die HTTP-Abfrage sie sicher sieht, bevor der Erfolg kommt.
        app, service, _ = _make(monkeypatch, backend=DevBluetoothBackend(step_seconds=0.2, passkey=PASSKEY))
        with TestClient(app) as client:
            assert client.post(f"{BASE}/scan").status_code == 200
            resp = client.post(f"{BASE}/devices/{KEYBOARD}/pair")
            assert resp.status_code == 202
            session_id = resp.json()["session_id"]
            shown = _poll(client, lambda b: b and b["stage"] == "display_passkey")
            assert shown["code"] == f"{PASSKEY:06d}"
            assert shown["session_id"] == session_id
            done = _poll(client, lambda b: b and b["stage"] == "succeeded")
            assert done["code"] is None
            client.portal.call(service.aclose)
        pair_events = [e for e in events if e["action"] == "bluetooth_pair"]
        assert pair_events and pair_events[0]["success"] is True
        assert pair_events[0]["details"]["kind"] == "input"
        assert str(PASSKEY) not in caplog.text
        assert str(PASSKEY) not in repr(events)

    def test_another_user_sees_nothing_and_cannot_answer(self, monkeypatch):
        backend = DevBluetoothBackend(step_seconds=0.01, passkey=PASSKEY)

        async def hold(path, prompter):
            prompter.show_passkey(PASSKEY, 0)
            while path not in backend._cancelled:
                await asyncio.sleep(0.01)
            raise BlueZError("org.bluez.Error.AuthenticationCanceled")

        backend.pair = hold
        app, service, _ = _make(monkeypatch, backend=backend)
        asyncio.run(backend.start_scan(DEV_ADAPTER_PATH))
        with TestClient(app) as client:
            session_id = client.post(f"{BASE}/devices/{KEYBOARD}/pair").json()["session_id"]
            _poll(client, lambda b: b and b["stage"] == "display_passkey")
            app.dependency_overrides[require_power_manage_bluetooth] = lambda: _Other()
            assert client.get(f"{BASE}/pairing").json() is None
            assert client.post(f"{BASE}/pairing/{session_id}/cancel").status_code == 404
            app.dependency_overrides[require_power_manage_bluetooth] = lambda: _Admin()
            assert client.post(f"{BASE}/pairing/{session_id}/cancel").status_code == 200
            _poll(client, lambda b: b and b["stage"] == "cancelled")
            client.portal.call(service.aclose)


class TestOtherRoutes:
    def test_raw_bluez_text_never_reaches_the_client(self, monkeypatch):
        backend = DevBluetoothBackend(step_seconds=0)

        async def chatty(path):
            raise BlueZError("org.bluez.Error.Failed", "/var/lib/bluetooth/geheim")

        backend.connect = chatty
        app, _, _ = _make(monkeypatch, backend=backend)
        resp = TestClient(app).post(f"{BASE}/devices/AA:AA:AA:AA:AA:03/connect")
        assert resp.status_code == 502
        assert "geheim" not in resp.text

    def test_remove_is_audited_with_address_and_kind(self, monkeypatch, audit):
        events, _ = audit
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).delete(f"{BASE}/devices/AA:AA:AA:AA:AA:03").status_code == 200
        entry = next(e for e in events if e["action"] == "bluetooth_remove")
        assert entry["details"] == {"address": "AA:AA:AA:AA:AA:03", "kind": "audio"}

    def test_adapter_power_is_audited_and_a_non_admin_gets_the_delegated_entry(self, monkeypatch, audit):
        events, security = audit
        app, _, _ = _make(monkeypatch, user=_Other)
        assert TestClient(app).post(f"{BASE}/adapter/power", json={"powered": False}).status_code == 200
        assert any(e["action"] == "bluetooth_adapter_power" for e in events)
        assert security and security[0]["resource"] == "manage_bluetooth"

    def test_a_raw_dict_body_is_422(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/adapter/power", json={"nonsense": 1}).status_code == 422
