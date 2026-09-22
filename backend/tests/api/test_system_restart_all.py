"""Tests für POST /api/system/restart-all (Admin + LAN + Step-up)."""
import pytest

from app.core.config import settings
from app.services import system_restart

PATH = "/api/system/restart-all"


@pytest.fixture(autouse=True)
def no_real_restart(monkeypatch):
    """Ohne das würde der Timer den Testlauf selbst per SIGINT beenden."""
    scheduled = []
    monkeypatch.setattr(
        "app.api.routes.system._schedule_backend_restart",
        lambda eta=1.0: scheduled.append(eta),
    )
    return scheduled


@pytest.fixture(autouse=True)
def local_client(monkeypatch):
    """Das LAN-Gate durchlassen, außer wo ein Test es ausdrücklich schließt.

    Der TestClient meldet `request.client.host == "testclient"`, und das ist
    keine IP — `is_private_or_local_ip` gibt dafür False zurück. Ohne diese
    Vorgabe bekäme jeder Happy-Path-Test 403. Muster übernommen aus
    tests/api/test_recovery_codes.py:132.
    """
    from app.api.routes import system as system_module

    monkeypatch.setattr(system_module, "is_private_or_local_ip", lambda ip: True)


@pytest.fixture
def fake_units(monkeypatch):
    """Alle Support-Units melden Erfolg, ohne systemctl anzufassen."""
    calls = []

    def fake_restart_support_units(runner=None):
        calls.append(True)
        return [
            system_restart.UnitResult(name, True)
            for name in system_restart.SUPPORT_UNITS
        ]

    monkeypatch.setattr(
        system_restart, "restart_support_units", fake_restart_support_units
    )
    monkeypatch.setattr(settings, "is_dev_mode", False)
    return calls


def test_requires_authentication(client):
    assert client.post(PATH, json={"current_password": "x"}).status_code == 401


def test_regular_user_is_rejected(client, user_headers):
    r = client.post(PATH, json={"current_password": "Testpass123!"}, headers=user_headers)
    assert r.status_code == 403


def test_non_local_client_is_rejected(client, admin_headers, fake_units, monkeypatch):
    """:8000 lauscht auf 0.0.0.0 ohne Paketfilter (#698) — das Gate ist real."""
    monkeypatch.setattr(
        "app.api.routes.system.is_private_or_local_ip", lambda ip: False
    )

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "local_network_required"
    assert fake_units == []


def test_api_key_is_rejected(client, admin_headers, fake_units, monkeypatch):
    """Ein Step-up soll Anwesenheit belegen; ein Schlüssel kann das nicht.

    Nebenbei: ein Key-Aufrufer fiele in get_user_identifier auf den
    IP-Schlüssel zurück und könnte das Rate-Limit aufweichen.
    """
    from app.api.routes import system as system_module

    # deps.get_current_user setzt request.state.auth_method = "api_key";
    # hier wird der Leser dieses Markers ersetzt, nicht die halbe Auth-Kette.
    monkeypatch.setattr(system_module, "_is_api_key_request", lambda request: True)

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "api_key_not_allowed"
    assert fake_units == []


def test_wrong_password_returns_structured_401(client, admin_headers, fake_units):
    r = client.post(PATH, json={"current_password": "falsch"}, headers=admin_headers)

    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["error"] == "step_up_failed"
    assert detail["totp_required"] is False
    assert fake_units == []          # ohne Nachweis wird nichts neu gestartet


def test_empty_body_is_a_failed_step_up_not_a_422(client, admin_headers, fake_units):
    r = client.post(PATH, json={}, headers=admin_headers)

    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "step_up_failed"


def test_failed_step_up_is_audited(client, admin_headers, fake_units, monkeypatch):
    events = []
    from app.services.audit import logger_db

    real = logger_db.AuditLoggerDB.log_security_event

    def spy(self, *args, **kwargs):
        events.append(kwargs.get("action") or (args[0] if args else None))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(logger_db.AuditLoggerDB, "log_security_event", spy)

    client.post(PATH, json={"current_password": "falsch"}, headers=admin_headers)

    assert "restart_all_step_up_failed" in events


def test_correct_password_restarts_support_units(client, admin_headers, fake_units, no_real_restart):
    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 200
    body = r.json()
    assert [u["name"] for u in body["units"]] == list(system_restart.SUPPORT_UNITS)
    assert all(u["success"] for u in body["units"])
    assert body["backend_restart_scheduled"] is True
    assert body["initiated_by"] == settings.admin_username
    assert fake_units == [True]
    assert no_real_restart == [1.0]          # Backend zuletzt, per Timer


def test_backend_unit_is_not_in_the_result_list(client, admin_headers, fake_units):
    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )
    assert "baluhost-backend" not in [u["name"] for u in r.json()["units"]]


def test_failing_unit_is_reported_without_blocking_the_rest(
    client, admin_headers, monkeypatch, no_real_restart
):
    monkeypatch.setattr(settings, "is_dev_mode", False)
    monkeypatch.setattr(
        system_restart,
        "restart_support_units",
        lambda runner=None: [
            system_restart.UnitResult("baluhost-scheduler", True),
            system_restart.UnitResult("baluhost-monitoring", False, "boom"),
            system_restart.UnitResult("baluhost-webdav", True),
            system_restart.UnitResult("baluhost-backend-local", True),
        ],
    )

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 200
    failed = [u for u in r.json()["units"] if not u["success"]]
    assert [u["name"] for u in failed] == ["baluhost-monitoring"]
    assert r.json()["backend_restart_scheduled"] is True   # trotzdem
    assert no_real_restart == [1.0]


def test_dev_mode_touches_no_units(client, admin_headers, monkeypatch, no_real_restart):
    monkeypatch.setattr(settings, "is_dev_mode", True)

    def explode(runner=None):
        raise AssertionError("systemctl darf im Dev-Mode nicht laufen")

    monkeypatch.setattr(system_restart, "restart_support_units", explode)

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 200
    assert r.json()["units"] == []
    assert no_real_restart == [1.0]


def test_totp_account_needs_a_code_and_the_body_says_so(
    client, admin_headers, fake_units, monkeypatch
):
    """Mit 2FA öffnet das Passwort nichts — und der 401 sagt dem Client, warum."""
    from app.api.routes import system as system_module

    monkeypatch.setattr(system_module, "_totp_enabled_for", lambda user_record: True)
    monkeypatch.setattr(
        "app.services.step_up.verify_step_up",
        lambda db, user_record, current_password, code: code == "123456",
    )

    rejected = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )
    assert rejected.status_code == 401
    assert rejected.json()["detail"]["totp_required"] is True

    assert client.post(
        PATH, json={"code": "123456"}, headers=admin_headers
    ).status_code == 200


def test_rate_limit_decorator_is_actually_attached():
    """Der Wert in RATE_LIMITS nützt nichts, wenn der Dekorator fehlt.

    slowapi trägt jede dekorierte Route unter `<modul>.<funktionsname>` in
    `_route_limits` ein — das ist der Nachweis, dass der Dekorator hängt, und
    nicht bloß, dass irgendetwas die Funktion umhüllt hat. Im Testmodus
    liefert get_limit() für diesen Schlüssel ein sehr hohes Limit, gebremst
    wird hier also nichts.
    """
    import app.main  # noqa: F401 — registriert die Routen
    from app.core.rate_limiter import user_limiter

    assert (
        "app.api.routes.system.restart_all_services" in user_limiter._route_limits
    ), "kein Rate-Limit an der Route registriert"
