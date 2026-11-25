"""Tests fuer "BaluHost oeffnen" mit Auto-Login (#847). Ohne Qt, ohne Backend."""
import logging
import threading
from unittest.mock import MagicMock

import httpx

from baluhost_tray import handoff

WEB = "http://box.local/"
SECRET_CODE = "s3cr3t-handoff-code-xyz"


def _resp(status, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    return r


def _session(*responses):
    session = MagicMock()
    session.current_refresh_token.return_value = "refresh-token"
    client = MagicMock()
    if responses and isinstance(responses[0], Exception):
        client.post.side_effect = responses[0]
    else:
        client.post.side_effect = list(responses)
    session.client.return_value = client
    return session, client


def _ok():
    return _resp(200, {"code": SECRET_CODE, "expires_in": 30})


def _err(status, error):
    return _resp(status, {"detail": {"error": error}})


def _asker(*answers):
    calls = []
    it = iter(answers)

    def ask(retry):
        calls.append(retry)
        return next(it)

    ask.calls = calls
    return ask


def test_success_opens_login_with_fragment():
    session, client = _session(_ok())
    result = handoff.open_url_for(session, WEB, False, _asker())
    assert result == handoff.HandoffResult(
        url=f"http://box.local/login#handoff={SECRET_CODE}"
    )
    assert client.post.call_args.args[0] == handoff.HANDOFF_PATH
    assert client.post.call_args.kwargs["json"] == {
        "refresh_token": "refresh-token", "pin": None,
    }


def test_no_pin_dialog_without_account_pin():
    session, _ = _session(_ok())
    ask = _asker()
    handoff.open_url_for(session, WEB, False, ask)
    assert ask.calls == []


def test_pin_is_sent_when_account_has_one():
    session, client = _session(_ok())
    handoff.open_url_for(session, WEB, True, _asker("1234"))
    assert client.post.call_args.kwargs["json"]["pin"] == "1234"


def test_pin_required_without_known_pin_asks_once():
    session, client = _session(_err(401, "pin_required"), _ok())
    ask = _asker("1234")
    result = handoff.open_url_for(session, WEB, False, ask)
    assert ask.calls == [False]
    assert result.url.endswith(f"#handoff={SECRET_CODE}")


def test_cancelled_pin_opens_plain_url():
    session, client = _session(_ok())
    result = handoff.open_url_for(session, WEB, True, _asker(None))
    assert result == handoff.HandoffResult(url=WEB)
    client.post.assert_not_called()


def test_wrong_pin_asks_once_more():
    session, _ = _session(_err(401, "pin_invalid"), _ok())
    ask = _asker("1111", "2222")
    result = handoff.open_url_for(session, WEB, True, ask)
    assert ask.calls == [False, True]
    assert result.url.endswith(f"#handoff={SECRET_CODE}")


def test_wrong_pin_twice_opens_plain_with_notice():
    session, _ = _session(_err(401, "pin_invalid"), _err(401, "pin_invalid"))
    ask = _asker("1111", "2222")
    result = handoff.open_url_for(session, WEB, True, ask)
    assert result == handoff.HandoffResult(
        url=WEB, notice="PIN stimmt nicht — bitte normal anmelden."
    )
    assert ask.calls == [False, True]


def test_locked_pin_opens_plain_with_notice():
    session, _ = _session(_err(401, "pin_locked"))
    result = handoff.open_url_for(session, WEB, True, _asker("1111"))
    assert result == handoff.HandoffResult(
        url=WEB, notice="PIN gesperrt — bitte mit Passwort anmelden."
    )


def test_server_error_opens_plain_url():
    session, _ = _session(_resp(500))
    assert handoff.open_url_for(session, WEB, False, _asker()) == handoff.HandoffResult(url=WEB)


def test_network_error_opens_plain_url():
    session, _ = _session(httpx.ConnectError("down"))
    assert handoff.open_url_for(session, WEB, False, _asker()) == handoff.HandoffResult(url=WEB)


def test_missing_refresh_token_opens_plain_url():
    session, client = _session(_ok())
    session.current_refresh_token.return_value = None
    assert handoff.open_url_for(session, WEB, False, _asker()).url == WEB
    client.post.assert_not_called()


def test_code_never_logged(caplog):
    session, _ = _session(_ok())
    with caplog.at_level(logging.DEBUG):
        handoff.open_url_for(session, WEB, False, _asker())
    assert SECRET_CODE not in caplog.text


def test_single_flight_ignores_second_start_while_running():
    gate = threading.Event()
    started = []
    flight = handoff.SingleFlight()

    def work():
        started.append(1)
        gate.wait(2)

    assert flight.start(work) is True
    assert flight.start(work) is False
    gate.set()
    for _ in range(100):
        if not flight.running:
            break
        threading.Event().wait(0.02)
    assert flight.start(lambda: None) is True
    assert started == [1]
