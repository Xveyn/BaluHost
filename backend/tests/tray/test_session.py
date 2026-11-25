"""Tests for token lifecycle in the tray session."""

from unittest.mock import MagicMock

import httpx
import pytest

from baluhost_tray import config as tray_config
from baluhost_tray.session import AuthExpired, PairingLost, Session, TemporaryFailure


@pytest.fixture(autouse=True)
def tmp_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(tray_config, "TOKEN_DIR", tmp_path)
    monkeypatch.setattr(tray_config, "TOKEN_FILE", tmp_path / "tray-tokens.json")
    tray_config.save_tokens(tray_config.Tokens(access="old", refresh="rt"))


def _response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    return response


def _session(response: MagicMock) -> Session:
    session = Session("http://localhost:8000")
    session._client = MagicMock()
    session._client.post.return_value = response
    return session


def _session_with_transport_error() -> Session:
    """A session whose client raises a real httpx transport error on post().

    Not a status code — the request never got a response at all (backend
    restarting, connection refused, DNS gone, timeout).
    """
    session = Session("http://localhost:8000")
    session._client = MagicMock()
    session._client.post.side_effect = httpx.ConnectError("connection refused")
    return session


@pytest.mark.parametrize(
    "base,expected",
    [
        ("http://localhost:8000", "ws://localhost:8000/api/notifications/ws"),
        ("https://baluhost.local", "wss://baluhost.local/api/notifications/ws"),
        ("http://localhost:8000/", "ws://localhost:8000/api/notifications/ws"),
    ],
)
def test_ws_url(base, expected):
    assert Session(base).ws_url() == expected


def test_ws_token_returned():
    assert _session(_response(200, {"token": "wt"})).ws_token() == "wt"


def test_ws_token_401_is_recoverable():
    with pytest.raises(AuthExpired):
        _session(_response(401)).ws_token()


def test_ws_token_429_is_temporary_not_fatal():
    """Ein Ratelimit darf keine Entkopplung ausloesen."""
    with pytest.raises(TemporaryFailure):
        _session(_response(429)).ws_token()


def test_ws_token_500_is_temporary():
    with pytest.raises(TemporaryFailure):
        _session(_response(503)).ws_token()


def test_ws_token_403_loses_the_pairing():
    """Ein ausdrueckliches Verbot ist der eine Fall, der die Kopplung kostet."""
    with pytest.raises(PairingLost):
        _session(_response(403)).ws_token()


@pytest.mark.parametrize("code", [400, 404, 422])
def test_ws_token_unexpected_codes_are_temporary(code):
    """Falsche --base-url, ein Proxy ohne diesen Pfad, ein Schema-Wechsel.

    Alles davon sah frueher aus wie ein Widerruf und loeschte die Token —
    danach meldet die Unit wegen `ConditionPathExists` nur noch
    "condition failed", und es braucht einen Menschen.
    """
    with pytest.raises(TemporaryFailure):
        _session(_response(code)).ws_token()


def test_ws_token_network_error_is_temporary():
    """A transport error (no response at all) must not escape as httpx.HTTPError."""
    with pytest.raises(TemporaryFailure):
        _session_with_transport_error().ws_token()


def test_refresh_updates_access_and_keeps_refresh():
    """Der Server rotiert das Refresh-Token nicht — es muss erhalten bleiben."""
    session = _session(_response(200, {"access_token": "new", "token_type": "bearer"}))
    session.refresh_access()

    assert tray_config.load_tokens().access == "new"
    assert tray_config.load_tokens().refresh == "rt"
    session._client.set_token.assert_called_with("new")


def test_refresh_401_forgets_pairing():
    session = _session(_response(401))
    with pytest.raises(PairingLost):
        session.refresh_access()
    assert tray_config.load_tokens() is None


def test_refresh_403_forgets_pairing():
    session = _session(_response(403))
    with pytest.raises(PairingLost):
        session.refresh_access()
    assert tray_config.load_tokens() is None


@pytest.mark.parametrize("code", [400, 404, 422])
def test_refresh_unexpected_codes_keep_the_tokens(code):
    """Eine umbenannte Route oder ein geaendertes Schema ist kein Widerruf.

    `if code != 200: self.forget()` machte aus jedem 404 und jedem 422 eine
    aufgehobene Kopplung — der teuerste denkbare Fehlschluss, weil nur ein
    Mensch mit `--pair` wieder herauskommt.
    """
    session = _session(_response(code))
    with pytest.raises(TemporaryFailure):
        session.refresh_access()
    assert tray_config.load_tokens() is not None
    assert tray_config.load_tokens().refresh == "rt"


def test_refresh_429_keeps_the_pairing():
    session = _session(_response(429))
    with pytest.raises(TemporaryFailure):
        session.refresh_access()
    assert tray_config.load_tokens() is not None


def test_refresh_network_error_is_temporary_and_keeps_tokens():
    """A network outage must not cost the pairing any more than a 429 does."""
    session = _session_with_transport_error()
    with pytest.raises(TemporaryFailure):
        session.refresh_access()
    assert tray_config.load_tokens() is not None
    assert tray_config.load_tokens().refresh == "rt"


def test_refresh_without_tokens_raises_pairing_lost():
    tray_config.clear_tokens()
    session = Session("http://localhost:8000")
    session._client = MagicMock()
    with pytest.raises(PairingLost):
        session.refresh_access()


def test_forget_clears_tokens():
    session = _session(_response(200))
    session.forget()
    assert tray_config.load_tokens() is None


def test_refresh_sends_rotate_flag():
    session = _session(_response(200, {"access_token": "new"}))
    session.refresh_access()
    session._client.post.assert_called_once()
    assert session._client.post.call_args.kwargs["json"] == {
        "refresh_token": "rt",
        "rotate": True,
    }


def test_rotated_refresh_token_is_stored():
    session = _session(
        _response(200, {"access_token": "new", "refresh_token": "rt2"})
    )
    session.refresh_access()
    assert tray_config.load_tokens() == tray_config.Tokens(access="new", refresh="rt2")


def test_missing_refresh_token_keeps_the_old_one():
    session = _session(
        _response(200, {"access_token": "new", "refresh_token": None})
    )
    session.refresh_access()
    assert tray_config.load_tokens() == tray_config.Tokens(access="new", refresh="rt")


def test_concurrent_refreshes_are_serialized():
    import threading
    import time

    state = {"active": 0, "max": 0, "sent": []}
    guard = threading.Lock()

    def _post(path, json=None):
        with guard:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
            state["sent"].append(json["refresh_token"])
        time.sleep(0.1)
        with guard:
            state["active"] -= 1
        n = len(state["sent"])
        return _response(200, {"access_token": f"a{n}", "refresh_token": f"rt{n}"})

    session = Session("http://localhost:8000")
    session._client = MagicMock()
    session._client.post.side_effect = _post

    threads = [threading.Thread(target=session.refresh_access) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["max"] == 1
    assert state["sent"] == ["rt", "rt1"]


def test_reload_picks_up_a_new_pairing():
    session = _session(_response(200))
    tray_config.save_tokens(tray_config.Tokens(access="fresh", refresh="r9"))
    assert session.reload() is True
    session._client.set_token.assert_called_with("fresh")
    assert session.current_refresh_token() == "r9"

    tray_config.clear_tokens()
    assert session.reload() is False
    session._client.clear_token.assert_called()
    assert session.current_refresh_token() is None
