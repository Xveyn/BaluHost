"""Tests für den ausgehenden Pfad des Trays.

Alles hier läuft ohne Qt, ohne systemd und ohne Backend.
"""
from unittest.mock import MagicMock

import httpx
import pytest

from baluhost_tray import restart


def _response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    return response


def _client(**behaviour) -> MagicMock:
    client = MagicMock()
    for name, value in behaviour.items():
        if isinstance(value, Exception):
            getattr(client, name).side_effect = value
        else:
            getattr(client, name).return_value = value
    return client


# --- Unit-Liste ----------------------------------------------------------

def test_units_match_the_backend():
    """Zwei Listen im Repo, eine Wahrheit.

    Das Tray kann die Liste nicht vom Backend holen — auf dem Notweg ist es
    tot. Also diese Prüfung, damit sie nicht auseinanderlaufen.
    """
    from app.services.system_restart import BALUHOST_UNITS

    assert restart.UNITS == BALUHOST_UNITS


# --- Probe ---------------------------------------------------------------

def test_probe_true_on_200():
    client = _client(get=_response(200))
    assert restart.probe_api(client) is True
    assert client.get.call_args.kwargs["timeout"] == restart.PROBE_TIMEOUT


def test_probe_false_on_error_status():
    assert restart.probe_api(_client(get=_response(502))) is False


def test_probe_false_on_transport_error():
    """Kein Statuscode, gar keine Antwort — genau der Notfall."""
    assert restart.probe_api(_client(get=httpx.ConnectError("refused"))) is False


def test_probe_false_on_timeout():
    assert restart.probe_api(_client(get=httpx.ReadTimeout("slow"))) is False


# --- Kontodaten ----------------------------------------------------------

def test_facts_report_admin_and_totp():
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"role": "admin"}),
        _response(200, {"enabled": True}),
    ]

    assert restart.fetch_account_facts(client) == restart.AccountFacts(
        is_admin=True, totp_enabled=True
    )


def test_facts_report_non_admin():
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"role": "user"}),
        _response(200, {"enabled": False}),
    ]
    assert restart.fetch_account_facts(client).is_admin is False


def test_facts_unknown_when_me_is_unreachable():
    """Unbekannt ist nicht dasselbe wie 'kein Admin' — siehe menu_visible."""
    client = _client(get=httpx.ConnectError("down"))

    facts = restart.fetch_account_facts(client)

    assert facts.is_admin is None
    assert facts.totp_enabled is False


def test_facts_refresh_once_on_401_and_retry():
    """Der Normalfall beim Tray-Start ist ein abgelaufener Access-Token (#692).

    Ohne Refresh liefe ein 2FA-Konto in drei Passwortabfragen, die die Route
    gar nicht akzeptiert.
    """
    client = MagicMock()
    client.get.side_effect = [
        _response(401),                              # /me, Token abgelaufen
        _response(200, {"role": "admin"}),           # /me nach dem Refresh
        _response(200, {"enabled": True}),           # /2fa/status
    ]
    refreshed = []

    facts = restart.fetch_account_facts(
        client, on_auth_expired=lambda: refreshed.append(True)
    )

    assert refreshed == [True]
    assert facts == restart.AccountFacts(is_admin=True, totp_enabled=True)


def test_facts_give_up_after_one_refresh():
    client = MagicMock()
    client.get.side_effect = [_response(401), _response(401)]

    facts = restart.fetch_account_facts(client, on_auth_expired=lambda: None)

    assert facts.is_admin is None


def test_facts_survive_a_failing_refresh():
    """refresh_access wirft PairingLost/TemporaryFailure — das darf nicht durch."""
    client = MagicMock()
    client.get.side_effect = [_response(401)]

    def boom():
        raise RuntimeError("refresh kaputt")

    facts = restart.fetch_account_facts(client, on_auth_expired=boom)

    assert facts.is_admin is None


def test_facts_totp_defaults_to_false_when_status_fails():
    client = MagicMock()
    client.get.side_effect = [_response(200, {"role": "admin"}), _response(500)]

    facts = restart.fetch_account_facts(client)

    assert facts.is_admin is True
    assert facts.totp_enabled is False


# --- Sichtbarkeit --------------------------------------------------------

@pytest.mark.parametrize(
    "is_admin,reachable,expected",
    [
        (True, True, True),
        (True, False, True),
        (None, True, True),     # Rolle nie erfahren
        (None, False, True),
        (False, True, False),   # bekannt: kein Admin
        (False, False, True),   # ... aber die API ist tot, polkit entscheidet
    ],
)
def test_menu_visible(is_admin, reachable, expected):
    assert restart.menu_visible(is_admin, reachable) is expected
