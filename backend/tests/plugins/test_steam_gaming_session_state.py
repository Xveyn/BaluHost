"""The gaming gate the tray asks before it shows a popup.

Driven through TestClient on purpose: the route carries @user_limiter.limit,
and slowapi rejects anything that is not a real starlette Request.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.plugins.installed.steam_gaming import routes

BASE = "/api/plugins/steam_gaming"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router, prefix=BASE)
    app.dependency_overrides[deps.get_current_user] = lambda: object()
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
