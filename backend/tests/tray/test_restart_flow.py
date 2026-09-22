"""Tests für den Ablauf: proben, fragen, Weg wählen, wiederholen."""
from unittest.mock import MagicMock

from baluhost_tray import restart


def _facts(is_admin=True, totp=False):
    return lambda client, on_auth_expired=None: restart.AccountFacts(
        is_admin=is_admin, totp_enabled=totp
    )


def _prompts(*answers):
    seen = []

    def prompt(mode):
        seen.append(mode)
        return answers[len(seen) - 1]

    prompt.seen = seen
    return prompt


def _never_local(**kwargs):
    raise AssertionError("der Notweg darf hier nicht laufen")


def test_reachable_api_asks_for_a_password_and_calls_the_api():
    prompt = _prompts("geheim")
    called = {}

    def api(client, secret, totp, on_auth_expired=None):
        called.update(secret=secret, totp=totp)
        return restart.RestartOutcome(True, "ok")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
    )

    assert outcome.ok is True
    assert prompt.seen == ["password"]
    assert called == {"secret": "geheim", "totp": False}


def test_totp_account_is_asked_for_a_code():
    prompt = _prompts("123456")

    restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(totp=True),
        api=lambda client, secret, totp, on_auth_expired=None: restart.RestartOutcome(True, "ok"),
        local=_never_local,
    )

    assert prompt.seen == ["totp"]


def test_wrong_password_is_asked_again_up_to_three_times():
    prompt = _prompts("falsch1", "falsch2", "falsch3")
    attempts = []

    def api(client, secret, totp, on_auth_expired=None):
        attempts.append(secret)
        return restart.RestartOutcome(False, "nope", retry_secret=True)

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
    )

    assert attempts == ["falsch1", "falsch2", "falsch3"]
    assert prompt.seen == ["password", "password_retry", "password_retry"]
    assert outcome.ok is False


def test_backend_can_switch_the_flow_to_a_code():
    """Der 401 weiss besser als wir, was die Route will."""
    prompt = _prompts("geheim", "123456")
    seen_totp = []

    def api(client, secret, totp, on_auth_expired=None):
        seen_totp.append(totp)
        if len(seen_totp) == 1:
            return restart.RestartOutcome(
                False, "nope", retry_secret=True, totp_required=True
            )
        return restart.RestartOutcome(True, "ok")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
    )

    assert prompt.seen == ["password", "totp_retry"]
    assert seen_totp == [False, True]
    assert outcome.ok is True


def test_cancelled_dialog_stops_without_calling_anything():
    prompt = _prompts(None)

    def api(client, secret, totp, on_auth_expired=None):
        raise AssertionError("darf nicht gerufen werden")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
    )

    assert outcome.ok is False
    assert "Abgebrochen" in outcome.message


def test_non_admin_is_told_without_being_asked_for_a_password():
    prompt = _prompts()

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(is_admin=False),
        api=lambda **kw: restart.RestartOutcome(True, "ok"), local=_never_local,
    )

    assert outcome.ok is False
    assert prompt.seen == []
    assert "Admin" in outcome.message


def test_dead_api_confirms_and_uses_systemctl():
    prompt = _prompts("ja")
    ran = []

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: False, facts=_facts(),
        api=lambda **kw: restart.RestartOutcome(False, "darf nicht laufen"),
        local=lambda: ran.append(True) or restart.RestartOutcome(True, "ok"),
    )

    assert prompt.seen == ["local"]
    assert ran == [True]
    assert outcome.ok is True


def test_declined_confirmation_does_not_restart_anything():
    prompt = _prompts(None)

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: False, facts=_facts(),
        api=lambda **kw: restart.RestartOutcome(False, "nein"), local=_never_local,
    )

    assert outcome.ok is False


def test_api_dying_mid_flight_switches_to_the_fallback():
    prompt = _prompts("geheim", "ja")
    ran = []

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(),
        api=lambda client, secret, totp, on_auth_expired=None: restart.RestartOutcome(
            False, "weg", offer_local=True
        ),
        local=lambda: ran.append(True) or restart.RestartOutcome(True, "ok"),
    )

    assert prompt.seen == ["password", "local"]
    assert ran == [True]
    assert outcome.ok is True


def test_timeout_does_not_switch_to_the_fallback():
    prompt = _prompts("geheim")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(),
        api=lambda client, secret, totp, on_auth_expired=None: restart.RestartOutcome(
            False, "dauert länger"
        ),
        local=_never_local,
    )

    assert prompt.seen == ["password"]
    assert outcome.ok is False
