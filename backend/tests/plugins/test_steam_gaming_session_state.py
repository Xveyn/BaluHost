"""The gaming gate the tray asks before it shows a popup.

Driven through TestClient on purpose: the route carries @user_limiter.limit,
and slowapi rejects anything that is not a real starlette Request.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.core.exception_handlers import register_exception_handlers
from app.core.network_utils import is_private_or_local_ip as real_is_private_or_local_ip
from app.plugins.installed.steam_gaming import routes

BASE = "/api/plugins/steam_gaming"


class _User:
    id = 2
    username = "someone"
    role = "user"


class _State:
    lan = True


@pytest.fixture(autouse=True)
def _lan(monkeypatch):
    """Ohne diesen Stub waere jeder Test ein 403: TestClient meldet sich als
    Host "testclient", und das ist keine private Adresse."""
    _State.lan = True
    monkeypatch.setattr(routes, "is_private_or_local_ip", lambda host: _State.lan)


@pytest.fixture
def audit(monkeypatch):
    events: list[dict] = []
    security: list[dict] = []

    class _Recorder:
        def log_event(self, **kwargs):
            events.append(kwargs)

        def log_security_event(self, **kwargs):
            security.append(kwargs)

    monkeypatch.setattr(routes, "get_audit_logger_db", lambda: _Recorder())
    return events, security


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(routes.router, prefix=BASE)
    app.dependency_overrides[deps.get_current_user] = lambda: _User()
    return TestClient(app)


@pytest.mark.parametrize(
    "running,marker,displays,expected",
    [
        (True, False, True, True),    # direkt in Steam gestartet
        (False, True, True, True),    # ueber BaluHost gestartet
        (True, False, False, False),  # Spiel laeuft, Bildschirm aus
        (False, True, False, False),  # verwaister Marker, Bildschirm aus
        (False, False, True, False),  # nichts laeuft
    ],
)
def test_session_state(client, running, marker, displays, expected):
    with patch(
        "app.services.power.gaming_presence.game_is_running", return_value=running
    ), patch(
        "app.services.power.gaming_presence._marker_is_active", return_value=marker
    ), patch(
        "app.services.power.gaming_presence.displays_on", return_value=displays
    ):
        response = client.get(f"{BASE}/session-state")

    assert response.status_code == 200
    assert response.json()["gaming_active"] is expected


def test_unreadable_presence_counts_as_not_gaming(client):
    """Fail open: lieber eine Meldung zu viel als eine verschluckte."""
    with patch(
        "app.services.power.gaming_presence.game_is_running",
        side_effect=OSError("sysfs gone"),
    ):
        response = client.get(f"{BASE}/session-state")

    assert response.status_code == 200
    assert response.json()["gaming_active"] is False


def test_requires_authentication():
    """Ohne Override statt mit — sonst beweist der Test nichts.

    Die uebrigen Tests setzen `dependency_overrides[get_current_user]`. Faelle
    jemand `Depends(deps.get_current_user)` aus der Route heraus, liefe die
    Override ins Leere und alle blieben gruen. Nur ein Aufruf *ohne* Override
    sieht, ob die Route ueberhaupt noch nach einem Token fragt.
    """
    app = FastAPI()
    app.include_router(routes.router, prefix=BASE)
    assert TestClient(app).get(f"{BASE}/session-state").status_code in (401, 403)


class TestLanGate:
    def test_outside_the_lan_is_403_and_audited_with_the_ip(self, client, audit):
        """Ein Anwesenheits-Orakel gehoert nicht ins Internet.

        Die Antwort sagt, ob gerade jemand physisch an der Maschine spielt.
        Fuer jedes Konto und jeden API-Key von ueberall abfragbar ist das eine
        Auskunft ueber die Anwesenheit des Besitzers — die Nachbarroute
        `launch` zieht dieselbe Grenze.
        """
        events, _ = audit
        _State.lan = False

        response = client.get(f"{BASE}/session-state")

        assert response.status_code == 403
        assert events[-1]["action"] == "steam_session_state_denied"
        assert events[-1]["success"] is False
        assert events[-1]["ip_address"] == "testclient"

    def test_inside_the_lan_answers_without_an_audit_entry(self, client, audit):
        """Die Gegenrichtung: der Normalfall ist kein Vorfall.

        Das Tray fragt alle 30 Sekunden — ein Eintrag pro Probe waere ein
        zugemuelltes Audit-Log statt einer Spur."""
        events, security = audit
        with patch(
            "app.services.power.gaming_presence.game_is_running", return_value=False
        ), patch(
            "app.services.power.gaming_presence._marker_is_active", return_value=False
        ):
            response = client.get(f"{BASE}/session-state")

        assert response.status_code == 200
        assert events == []
        assert security == []

    def test_fails_closed_with_the_real_lan_check(self, client, monkeypatch, audit):
        """Ohne den Stub entscheidet die echte Funktion — und "testclient" ist
        keine IP. Das haelt die Vorgabe fest, nicht die Attrappe."""
        monkeypatch.setattr(routes, "is_private_or_local_ip", real_is_private_or_local_ip)
        assert client.get(f"{BASE}/session-state").status_code == 403
