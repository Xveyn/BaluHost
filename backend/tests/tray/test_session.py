"""Tests for token lifecycle in the tray session."""

from unittest.mock import MagicMock

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


def test_refresh_429_keeps_the_pairing():
    session = _session(_response(429))
    with pytest.raises(TemporaryFailure):
        session.refresh_access()
    assert tray_config.load_tokens() is not None


def test_forget_clears_tokens():
    session = _session(_response(200))
    session.forget()
    assert tray_config.load_tokens() is None
