"""Launch routes: right, LAN gate, validation order, status codes, audit hygiene.

Driven through TestClient on purpose - only a real request exercises FastAPI's
body/param detection behind slowapi, which a future-annotations import breaks.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_power_launch_games
from app.core.database import get_db
from app.core.exception_handlers import register_exception_handlers
from app.plugins.installed.steam_gaming import SteamGamingPlugin, routes
from app.plugins.installed.steam_gaming.launch import GamingModeStart
from app.plugins.installed.steam_gaming.library import InstalledGame, LibraryUnavailable

BASE = "/api/plugins/steam_gaming"
PORTAL = InstalledGame("400", "Portal")


class _Admin:
    id = 1
    username = "admin"
    role = "admin"


class _User:
    id = 2
    username = "someone"
    role = "user"


class _State:
    lan = True
    running: object = None
    order: list = []


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    _State.lan = True
    _State.running = None
    _State.order = []
    monkeypatch.setattr(routes, "is_private_or_local_ip", lambda host: _State.lan)
    monkeypatch.setattr(routes.library, "list_installed_games", lambda: [PORTAL])
    monkeypatch.setattr(
        routes.library, "find_installed_game", lambda app_id: PORTAL if app_id == "400" else None
    )
    monkeypatch.setattr(
        routes.detection, "current_app_id", lambda *, dev_stand_in=True: _State.running
    )
    monkeypatch.setattr(routes.detection, "resolve_game_name", lambda app_id: "Metro Exodus")
    monkeypatch.setattr(routes, "current_lock_state", AsyncMock(return_value=False))

    async def _start(**kwargs):
        _State.order.append(("start", kwargs["client_host"]))
        return GamingModeStart(ok=True, failed_step=None, detail="requested")

    monkeypatch.setattr(routes.launch, "start_gaming_mode", _start)

    def _launch_game(app_id):
        _State.order.append(("game", app_id))
        return True, "game requested"

    monkeypatch.setattr(routes.launch, "launch_game", _launch_game)


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


def _client(user=_Admin) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(SteamGamingPlugin().get_router(), prefix=BASE)
    app.dependency_overrides[require_power_launch_games] = lambda: user()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


class TestPermission:
    def test_both_routes_are_gated(self):
        app = FastAPI()
        app.include_router(SteamGamingPlugin().get_router(), prefix=BASE)
        client = TestClient(app)
        assert client.get(f"{BASE}/games").status_code in (401, 403)
        assert client.post(f"{BASE}/games/400/launch").status_code in (401, 403)

    def test_a_delegated_user_may_launch(self, audit):
        _events, security = audit
        assert _client(_User).post(f"{BASE}/games/400/launch").status_code == 202
        assert security and security[0]["resource"] == "launch_games"


class TestList:
    def test_lists_games_and_running_state(self):
        _State.running = "1449560"
        body = _client().get(f"{BASE}/games").json()
        assert body["games"] == [{"app_id": "400", "name": "Portal"}]
        assert body["running"] == {"app_id": "1449560", "name": "Metro Exodus"}
        assert body["can_launch_here"] is True

    def test_says_when_launching_is_not_possible_from_here(self):
        _State.lan = False
        assert _client().get(f"{BASE}/games").json()["can_launch_here"] is False

    def test_an_unreadable_library_is_503(self, monkeypatch):
        def _raise():
            raise LibraryUnavailable("gone")

        monkeypatch.setattr(routes.library, "list_installed_games", _raise)
        resp = _client().get(f"{BASE}/games")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Game library unavailable"


class TestLaunchGates:
    def test_outside_the_lan_is_403_even_for_an_admin_and_audited_with_ip(self, audit):
        events, _ = audit
        _State.lan = False
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 403
        assert events[-1]["action"] == "steam_game_launch_denied"
        assert events[-1]["success"] is False
        assert events[-1]["ip_address"] == "testclient"
        assert _State.order == []

    @pytest.mark.parametrize("app_id", ["abc", "400%0A", "%D9%A4%D9%A0%D9%A0", "12345678901", "401"])
    def test_invalid_or_unknown_ids_are_404_without_audit(self, app_id, audit):
        events, _ = audit
        resp = _client().post(f"{BASE}/games/{app_id}/launch")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Game not installed"
        assert events == []
        assert _State.order == []

    def test_an_encoded_slash_never_reaches_the_launcher(self):
        assert _client().post(f"{BASE}/games/400%2F1/launch").status_code == 404
        assert _State.order == []

    def test_an_unreadable_library_is_503(self, monkeypatch):
        def _raise(app_id):
            raise LibraryUnavailable("gone")

        monkeypatch.setattr(routes.library, "find_installed_game", _raise)
        assert _client().post(f"{BASE}/games/400/launch").status_code == 503
        assert _State.order == []

    def test_a_running_game_is_409_without_audit(self, audit):
        events, _ = audit
        _State.running = "1449560"
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "A game is already running"
        assert events == []
        assert _State.order == []


class TestLaunchSequence:
    def test_starts_gaming_mode_then_the_library_id(self, audit):
        events, _ = audit
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 202
        assert resp.json() == {"status": "requested", "session_locked": False}
        assert _State.order == [("start", "testclient"), ("game", "400")]
        assert events[-1]["action"] == "steam_game_launch"
        assert events[-1]["success"] is True
        assert events[-1]["details"] == {"app_id": "400", "failed_step": None}

    def test_uses_the_id_from_the_library_entry(self, monkeypatch):
        monkeypatch.setattr(
            routes.library, "find_installed_game", lambda app_id: InstalledGame("400", "Portal")
        )
        _client().post(f"{BASE}/games/400/launch")
        assert ("game", "400") in _State.order

    @pytest.mark.parametrize("locked", [True, False, None])
    def test_reports_the_lock_state_afterwards(self, monkeypatch, locked):
        monkeypatch.setattr(routes, "current_lock_state", AsyncMock(return_value=locked))
        assert _client().post(f"{BASE}/games/400/launch").json()["session_locked"] is locked

    def test_dark_displays_are_502_and_no_game(self, monkeypatch, audit):
        events, _ = audit

        async def _start(**_kwargs):
            return GamingModeStart(ok=False, failed_step="displays", detail="kscreen-doctor: /secret")

        monkeypatch.setattr(routes.launch, "start_gaming_mode", _start)
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Displays could not be turned on"
        assert _State.order == []
        assert events[-1]["details"] == {"app_id": "400", "failed_step": "displays"}
        assert "secret" not in repr(events)

    def test_steam_failure_is_502_and_no_game(self, monkeypatch):
        async def _start(**_kwargs):
            return GamingModeStart(ok=False, failed_step="steam", detail="x")

        monkeypatch.setattr(routes.launch, "start_gaming_mode", _start)
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Steam could not be started"
        assert not any(step == "game" for step, _ in _State.order)

    def test_a_failed_game_start_is_502_and_audited(self, monkeypatch, audit):
        events, _ = audit
        monkeypatch.setattr(routes.launch, "launch_game", lambda app_id: (False, "steam could not be started"))
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 502
        assert events[-1]["details"] == {"app_id": "400", "failed_step": "game"}
        assert events[-1]["success"] is False

    def test_the_game_name_never_reaches_the_audit_trail(self, audit):
        events, security = audit
        _client(_User).post(f"{BASE}/games/400/launch")
        assert "Portal" not in repr(events) + repr(security)


class TestRouter:
    def test_the_plugin_contributes_one_stable_router(self):
        plugin = SteamGamingPlugin()
        assert plugin.get_router() is plugin.get_router()
