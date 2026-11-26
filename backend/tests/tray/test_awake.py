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


def _status(enabled=False, until=None, core=None) -> dict:
    """Antwort von /api/system/sleep/status, nur die Teile, die das Tray liest."""
    return {
        "current_state": "awake",
        "always_awake": {"enabled": enabled, "until": until, "expires_in_seconds": None},
        "core_uptime": core or {"enabled": False, "active": False},
    }


@pytest.mark.parametrize("stamp", ["2026-11-25T13:00:00Z", "2026-11-25T13:00:00+00:00"])
def test_parse_state_accepts_z_and_offset(stamp):
    state = awake.parse_state(_status(True, stamp))
    assert state == AwakeState(True, datetime(2026, 11, 25, 13, 0, tzinfo=timezone.utc))


def test_parse_state_without_until():
    assert awake.parse_state(_status(False)) == AwakeState(False, None)


def test_parse_state_reads_active_core_window():
    state = awake.parse_state(_status(core={
        "enabled": True,
        "active": True,
        "current_window_label": "Arbeitszeit",
        "current_window_ends_at": "2026-11-25T18:00:00",   # Ortszeit, ohne Zone
    }))
    assert state.core_active is True
    assert state.core_label == "Arbeitszeit"
    assert state.core_until == datetime(2026, 11, 25, 18, 0)


def test_parse_state_ignores_inactive_core_window():
    state = awake.parse_state(_status(core={
        "enabled": True,
        "active": False,
        "current_window_label": None,
        "current_window_ends_at": None,
        "next_start": "2026-11-26T08:00:00",
    }))
    assert (state.core_active, state.core_label, state.core_until) == (False, None, None)


def test_parse_state_garbage_raises():
    with pytest.raises(AwakeError):
        awake.parse_state(_status(True, "kaputt"))


def test_checked_choice():
    assert awake.checked_choice(AwakeState(False, None)) is AwakeChoice.OFF
    assert awake.checked_choice(AwakeState(True, None)) is AwakeChoice.PERMANENT
    assert awake.checked_choice(AwakeState(True, NOW)) is None


def test_deadline_text_for_any_deadline():
    """Auch eine frei gewaehlte Frist aus der Web-UI bekommt einen Eintrag."""
    custom = NOW + timedelta(hours=3, minutes=17)
    assert awake.deadline_text(AwakeState(True, custom), NOW) == (
        f"Bis {custom.astimezone():%H:%M}"
    )
    assert awake.deadline_text(AwakeState(True, None), NOW) is None
    assert awake.deadline_text(AwakeState(False, None), NOW) is None


def test_deadline_text_on_another_day_names_the_date():
    later = NOW + timedelta(days=3)
    assert awake.deadline_text(AwakeState(True, later), NOW) == (
        f"Bis {later.astimezone():%d.%m. %H:%M}"
    )


def test_core_text():
    ends = datetime(2026, 11, 25, 18, 0)        # naiv = Ortszeit
    now = ends.astimezone() - timedelta(hours=2)
    assert awake.core_text(AwakeState(False, None), now) is None
    assert awake.core_text(
        AwakeState(False, None, core_active=True, core_until=ends), now
    ) == "Kernzeit bis 18:00"
    assert awake.core_text(
        AwakeState(False, None, core_active=True, core_label="Büro", core_until=ends), now
    ) == "Kernzeit „Büro“ bis 18:00"
    assert awake.core_text(AwakeState(False, None, core_active=True), now) == "Kernzeit aktiv"


def test_submenu_title():
    assert awake.submenu_title(AwakeState(False, None), NOW) == "Always Awake"
    assert awake.submenu_title(AwakeState(True, None), NOW) == "Always Awake"
    local = NOW.astimezone()
    assert (
        awake.submenu_title(AwakeState(True, NOW), NOW)
        == f"Always Awake — bis {local:%H:%M}"
    )


def test_submenu_title_shows_core_window_when_off():
    ends = NOW + timedelta(hours=2)
    state = AwakeState(False, None, core_active=True, core_until=ends)
    assert awake.submenu_title(state, NOW) == (
        f"Always Awake — Kernzeit bis {ends.astimezone():%H:%M}"
    )
    # Eine eigene Frist hat Vorrang im Titel, die Kernzeit steht dann im Menue.
    own = NOW + timedelta(hours=1)
    assert awake.submenu_title(
        AwakeState(True, own, core_active=True, core_until=ends), NOW
    ) == f"Always Awake — bis {own.astimezone():%H:%M}"


def test_fetch_state_reads_the_status():
    client = MagicMock()
    client.get.return_value = _response(200, _status(True))
    assert awake.fetch_state(client, MagicMock()) == AwakeState(True, None)
    assert client.get.call_args.args[0] == awake.SLEEP_STATUS_PATH


def test_apply_uses_the_status_not_the_assumption():
    """Das Backend kuerzt die Frist auf das Kernzeitfenster; angezeigt wird der
    Status nach dem Setzen."""
    shortened = NOW + timedelta(minutes=20)
    client = MagicMock()
    client.put.return_value = _response(
        200,
        {"always_awake_enabled": True, "always_awake_until": shortened.isoformat()},
    )
    client.get.return_value = _response(200, _status(True, shortened.isoformat()))
    state = awake.apply(client, AwakeChoice.EIGHT_HOURS, NOW, MagicMock())
    assert state == AwakeState(True, shortened)
    assert client.put.call_args.args[0] == awake.SLEEP_CONFIG_PATH
    assert client.put.call_args.kwargs["json"] == awake.payload_for(
        AwakeChoice.EIGHT_HOURS, NOW
    )
    assert client.get.call_args.args[0] == awake.SLEEP_STATUS_PATH


def test_401_refreshes_once_then_succeeds():
    client = MagicMock()
    client.put.side_effect = [
        _response(401),
        _response(200, {"always_awake_enabled": False, "always_awake_until": None}),
    ]
    client.get.return_value = _response(200, _status(False))
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
