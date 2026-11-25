"""Always Awake im Tray-Menue: Payloads, Anzeige, Abruf und Setzen."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from baluhost_tray import awake
from baluhost_tray.awake import AwakeChoice, AwakeError, AwakeState

NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)


def _response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    return response


def test_path_is_bound_in_backend():
    """Gegen die echten Routen pruefen, nicht gegen einen abgeschriebenen String:
    der alte Test legte "/api/sleep/config" fest, das Backend antwortete 404."""
    from app.main import app

    # Ueber das OpenAPI-Schema: app.routes listet eingebundene Router nicht flach.
    operations = app.openapi()["paths"].get(awake.SLEEP_CONFIG_PATH, {})
    assert {"get", "put"} <= operations.keys()


def test_payload_off():
    assert awake.payload_for(AwakeChoice.OFF, NOW) == {
        "always_awake_enabled": False,
        "always_awake_until": None,
    }


def test_payload_hour():
    assert awake.payload_for(AwakeChoice.HOUR, NOW) == {
        "always_awake_enabled": True,
        "always_awake_until": (NOW + timedelta(hours=1)).isoformat(),
    }


def test_payload_eight_hours():
    assert awake.payload_for(AwakeChoice.EIGHT_HOURS, NOW) == {
        "always_awake_enabled": True,
        "always_awake_until": (NOW + timedelta(hours=8)).isoformat(),
    }


def test_payload_permanent():
    assert awake.payload_for(AwakeChoice.PERMANENT, NOW) == {
        "always_awake_enabled": True,
        "always_awake_until": None,
    }


@pytest.mark.parametrize("stamp", ["2026-11-25T13:00:00Z", "2026-11-25T13:00:00+00:00"])
def test_parse_state_accepts_z_and_offset(stamp):
    state = awake.parse_state(
        {"always_awake_enabled": True, "always_awake_until": stamp}
    )
    assert state == AwakeState(True, datetime(2026, 11, 25, 13, 0, tzinfo=timezone.utc))


def test_parse_state_without_until():
    assert awake.parse_state({"always_awake_enabled": False}) == AwakeState(False, None)


def test_parse_state_garbage_raises():
    with pytest.raises(AwakeError):
        awake.parse_state({"always_awake_enabled": True, "always_awake_until": "kaputt"})


def test_checked_choice():
    assert awake.checked_choice(AwakeState(False, None)) is AwakeChoice.OFF
    assert awake.checked_choice(AwakeState(True, None)) is AwakeChoice.PERMANENT
    assert awake.checked_choice(AwakeState(True, NOW)) is None


def test_submenu_title():
    assert awake.submenu_title(AwakeState(False, None)) == "Always Awake"
    assert awake.submenu_title(AwakeState(True, None)) == "Always Awake"
    local = NOW.astimezone()
    assert (
        awake.submenu_title(AwakeState(True, NOW))
        == f"Always Awake — bis {local:%H:%M}"
    )


def test_fetch_state_ok():
    client = MagicMock()
    client.get.return_value = _response(
        200, {"always_awake_enabled": True, "always_awake_until": None}
    )
    assert awake.fetch_state(client, MagicMock()) == AwakeState(True, None)
    assert client.get.call_args.args[0] == awake.SLEEP_CONFIG_PATH


def test_apply_uses_the_response_not_the_assumption():
    """Das Backend kuerzt die Frist auf das Kernzeitfenster."""
    shortened = NOW + timedelta(minutes=20)
    client = MagicMock()
    client.put.return_value = _response(
        200,
        {"always_awake_enabled": True, "always_awake_until": shortened.isoformat()},
    )
    state = awake.apply(client, AwakeChoice.EIGHT_HOURS, NOW, MagicMock())
    assert state == AwakeState(True, shortened)
    assert client.put.call_args.kwargs["json"] == awake.payload_for(
        AwakeChoice.EIGHT_HOURS, NOW
    )


def test_401_refreshes_once_then_succeeds():
    client = MagicMock()
    client.put.side_effect = [
        _response(401),
        _response(200, {"always_awake_enabled": False, "always_awake_until": None}),
    ]
    refresh = MagicMock()
    assert awake.apply(client, AwakeChoice.OFF, NOW, refresh) == AwakeState(False, None)
    refresh.assert_called_once()


def test_401_twice_is_an_error_with_one_refresh():
    client = MagicMock()
    client.get.return_value = _response(401)
    refresh = MagicMock()
    with pytest.raises(AwakeError):
        awake.fetch_state(client, refresh)
    refresh.assert_called_once()


def test_refresh_failure_is_an_error():
    client = MagicMock()
    client.get.return_value = _response(401)
    with pytest.raises(AwakeError):
        awake.fetch_state(client, MagicMock(side_effect=RuntimeError("weg")))


@pytest.mark.parametrize("status", [403, 422, 500])
def test_other_status_is_an_error(status):
    client = MagicMock()
    client.put.return_value = _response(status)
    with pytest.raises(AwakeError):
        awake.apply(client, AwakeChoice.HOUR, NOW, MagicMock())


def test_network_error_is_an_error():
    client = MagicMock()
    client.put.side_effect = httpx.ConnectError("down")
    with pytest.raises(AwakeError):
        awake.apply(client, AwakeChoice.HOUR, NOW, MagicMock())
