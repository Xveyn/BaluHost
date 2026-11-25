"""Tests fuer die Ablaeufe des Plugins local_tls (Adress- und Zertifikats-Check).

Alle Fremdkontakte sind ersetzt: LAN-IP, Anbieter, lego, Deploy und die
Zustellung der Benachrichtigungen. Nichts ruft echtes lego, nginx oder duckdns.org.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import settings
from app.plugins.installed.local_tls import (
    address,
    deploy_cert,
    lego,
    paths,
    providers,
    service,
    state,
)
from app.plugins.installed.local_tls.config import LocalTlsConfig
from app.plugins.installed.local_tls.deploy_cert import CertInfo, DeployFailed, DeployOutcome
from app.plugins.installed.local_tls.providers.base import ProviderError
from app.plugins.installed.local_tls.providers.duckdns import DuckDnsProvider

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
DOMAIN = "box.duckdns.org"
TOKEN = "0123abcd-0123-4567-89ab-0123456789ab"
IP = "192.168.1.20"
OLD_IP = "192.168.1.10"


@pytest.fixture(autouse=True)
def _clear_cooldown():
    from app.services.notifications import events as ev

    def _reset():
        ev._cooldown_cache.clear()
        for key in [k for k in ev._COOLDOWN_SECONDS if k.startswith("plugin:")]:
            del ev._COOLDOWN_SECONDS[key]

    _reset()
    yield
    _reset()


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(settings, "vpn_encryption_key", Fernet.generate_key().decode())


class FakeProvider(DuckDnsProvider):
    def __init__(self, fail: bool = False):
        self.calls: list[tuple[str, str, dict]] = []
        self.fail = fail

    def update_address(self, domain, ip, credentials, *, client=None):
        self.calls.append((domain, ip, credentials))
        if self.fail:
            raise ProviderError("duckdns rejected the update")


class World:
    """Sammelt alle Fremdaufrufe der Ablaeufe."""

    def __init__(self, monkeypatch, tmp_path):
        self.data_dir = tmp_path / "data"
        self.ip = IP
        self.ip_error: Exception | None = None
        self.ip_calls = 0
        self.provider = FakeProvider()
        self.lego_version: tuple[int, int, int] | Exception = (4, 35, 2)
        self.version_calls = 0
        self.lego_new = True
        self.lego_error: Exception | None = None
        self.lego_calls: list[dict] = []
        self.deploy_calls: list[tuple] = []
        self.deploy_error: Exception | None = None
        self.not_after = NOW + timedelta(days=90)
        self.served = True
        self.served_fp: str | None = "f" * 64
        self.lego_fp = "f" * 64  # Leaf-Fingerabdruck des Zertifikats in lego/
        self.inspect_calls = 0

        def _inspect(cert_pem, key_pem, domain, now):
            self.inspect_calls += 1
            return CertInfo(fingerprint=self.lego_fp, not_after=self.not_after, sans=(domain,))

        monkeypatch.setattr(deploy_cert, "inspect", _inspect)

        monkeypatch.setattr(paths, "DATA_DIR", self.data_dir)
        monkeypatch.setattr(address, "current_lan_ip", self._current_lan_ip)
        monkeypatch.setattr(providers, "get_provider", lambda pid: self.provider)
        monkeypatch.setattr(lego, "version", self._version)
        monkeypatch.setattr(lego, "obtain_or_renew", self._obtain)
        monkeypatch.setattr(deploy_cert, "deploy", self._deploy)
        monkeypatch.setattr(deploy_cert, "served_fingerprint", lambda d: self.served_fp)

    def _current_lan_ip(self, interface=None):
        self.ip_calls += 1
        if self.ip_error:
            raise self.ip_error
        return self.ip

    def _version(self):
        self.version_calls += 1
        if isinstance(self.lego_version, Exception):
            raise self.lego_version
        return self.lego_version

    def _obtain(self, domain, provider_lego_name, env, data_dir, *, email, staging):
        self.lego_calls.append(
            {"domain": domain, "provider": provider_lego_name, "env": env,
             "data_dir": data_dir, "email": email, "staging": staging}
        )
        if self.lego_error:
            raise self.lego_error
        crt, keyp = lego.cert_paths(domain, data_dir, staging=staging)
        crt.parent.mkdir(parents=True, exist_ok=True)
        crt.write_bytes(b"cert")
        keyp.write_bytes(b"key")
        return self.lego_new

    def _deploy(self, cert_path, key_path, domain, data_dir, now):
        self.deploy_calls.append((cert_path, key_path, domain, data_dir, now))
        if self.deploy_error:
            raise self.deploy_error
        info = CertInfo(fingerprint=self.lego_fp, not_after=self.not_after, sans=(domain,))
        return DeployOutcome(info=info, served=self.served)

    @property
    def any_call(self) -> bool:
        return bool(
            self.ip_calls or self.provider.calls or self.version_calls
            or self.lego_calls or self.deploy_calls
        )


@pytest.fixture
def world(monkeypatch, tmp_path):
    return World(monkeypatch, tmp_path)


@pytest.fixture
def configured(db_session, key):
    state.set_token(db_session, TOKEN)
    return LocalTlsConfig(domain=DOMAIN)


def _ids(events):
    return [e.event_id for e in events]


# --- nicht konfiguriert ---------------------------------------------------

def test_unconfigured_plugin_stays_quiet(db_session, key, world):
    # Keine Domain, aber Token
    state.set_token(db_session, TOKEN)
    cfg = LocalTlsConfig()
    assert service.run_address_check(db_session, cfg, NOW) == []
    assert service.run_cert_check(db_session, cfg, NOW) == []
    # Domain, aber kein Token
    state.clear_token(db_session)
    cfg = LocalTlsConfig(domain=DOMAIN)
    assert service.run_address_check(db_session, cfg, NOW, force=True) == []
    assert service.run_cert_check(db_session, cfg, NOW, force=True) == []
    assert not world.any_call


# --- Adress-Check ---------------------------------------------------------

def test_address_unchanged_no_update_within_day(db_session, configured, world):
    state.record_ip(db_session, IP, NOW - timedelta(hours=23))
    events = service.run_address_check(db_session, configured, NOW)
    assert events == []
    assert world.provider.calls == []


def test_address_changed_updates_and_notifies(db_session, configured, world):
    state.record_ip(db_session, OLD_IP, NOW - timedelta(minutes=5))
    events = service.run_address_check(db_session, configured, NOW)
    assert world.provider.calls == [(DOMAIN, IP, {"token": TOKEN})]
    assert _ids(events) == ["address_changed"]
    assert events[0].entity_id == DOMAIN
    assert events[0].kwargs == {"domain": DOMAIN, "ip": IP}
    row = state.get_state(db_session)
    assert row.last_ip == IP


def test_first_address_is_set_without_change_event(db_session, configured, world):
    events = service.run_address_check(db_session, configured, NOW)
    assert world.provider.calls == [(DOMAIN, IP, {"token": TOKEN})]
    assert events == []
    assert state.get_state(db_session).last_ip == IP


def test_daily_reconfirm(db_session, configured, world):
    state.record_ip(db_session, IP, NOW - timedelta(seconds=86400))
    events = service.run_address_check(db_session, configured, NOW)
    assert world.provider.calls == [(DOMAIN, IP, {"token": TOKEN})]
    assert events == []  # gleiche IP: bestaetigt, aber keine Aenderung
    assert service.run_address_check(db_session, configured, NOW + timedelta(minutes=5)) == []
    assert len(world.provider.calls) == 1


def test_force_updates_unchanged_address(db_session, configured, world):
    state.record_ip(db_session, IP, NOW - timedelta(minutes=1))
    service.run_address_check(db_session, configured, NOW, force=True)
    assert len(world.provider.calls) == 1


def test_dns_failure_notifies(db_session, configured, world):
    world.provider.fail = True
    events = service.run_address_check(db_session, configured, NOW)
    assert _ids(events) == ["dns_update_failed"]
    assert events[0].kwargs["reason"] == "duckdns rejected the update"
    assert events[0].kwargs["domain"] == DOMAIN
    assert state.get_state(db_session).last_ip is None


def test_address_error_notifies_without_update(db_session, configured, world):
    world.ip_error = address.AddressError("address is not a private IPv4 address")
    events = service.run_address_check(db_session, configured, NOW)
    assert _ids(events) == ["dns_update_failed"]
    assert world.provider.calls == []


def test_unreadable_token_is_reported_not_raised(db_session, configured, world, monkeypatch):
    # Schluessel rotiert: der gespeicherte Token ist nicht mehr lesbar.
    monkeypatch.setattr(settings, "vpn_encryption_key", Fernet.generate_key().decode())
    events = service.run_address_check(db_session, configured, NOW)
    assert _ids(events) == ["dns_update_failed"]
    assert "credentials" in events[0].kwargs["reason"]
    assert world.provider.calls == []

    events = service.run_cert_check(db_session, configured, NOW)
    assert "renew_failed" in _ids(events)
    row = state.get_state(db_session)
    assert row.last_renew_ok is False
    assert "credentials" in row.last_renew_reason
    assert world.lego_calls == []


def test_address_check_while_locked_skips_or_raises(db_session, configured, world):
    paths.ensure_dirs(world.data_dir)
    with paths.lock(world.data_dir):
        assert service.run_address_check(db_session, configured, NOW) == []
        with pytest.raises(paths.AlreadyRunning):
            service.run_address_check(db_session, configured, NOW, raise_if_running=True)
    assert world.provider.calls == []


# --- Zertifikats-Check ----------------------------------------------------

def test_cert_renewed_is_deployed_and_recorded(db_session, configured, world):
    events = service.run_cert_check(db_session, configured, NOW)
    assert events == []
    call = world.lego_calls[0]
    assert call["domain"] == DOMAIN
    assert call["provider"] == "duckdns"
    assert call["env"] == {"DUCKDNS_TOKEN": TOKEN}
    assert call["data_dir"] == world.data_dir
    assert call["email"] is None and call["staging"] is False
    crt, keyp, domain, data_dir, now = world.deploy_calls[0]
    assert (crt, keyp) == lego.cert_paths(DOMAIN, world.data_dir)
    assert domain == DOMAIN and data_dir == world.data_dir and now == NOW
    row = state.get_state(db_session)
    assert row.last_renew_ok is True
    assert row.last_renew_reason is None
    assert row.cert_fingerprint == "f" * 64
    assert row.cert_not_after is not None


def test_staging_deploys_the_staging_certificate(db_session, configured, world):
    cfg = configured.model_copy(update={"staging": True, "email": "a@example.org"})
    service.run_cert_check(db_session, cfg, NOW)
    assert world.lego_calls[0]["staging"] is True
    assert world.lego_calls[0]["email"] == "a@example.org"
    crt, keyp, *_ = world.deploy_calls[0]
    assert (crt, keyp) == lego.cert_paths(DOMAIN, world.data_dir, staging=True)


def test_installed_but_not_served_counts_as_success(db_session, configured, world):
    world.served = False
    events = service.run_cert_check(db_session, configured, NOW)
    assert events == []
    row = state.get_state(db_session)
    assert row.last_renew_ok is True
    assert "nginx" in row.last_renew_reason


def test_no_new_cert_no_deploy(db_session, configured, world):
    state.record_renew(db_session, True, None, "a" * 64, NOW + timedelta(days=60), NOW - timedelta(days=1))
    world.lego_new = False
    world.lego_fp = "a" * 64  # lego haelt dasselbe Zertifikat, das installiert ist
    events = service.run_cert_check(db_session, configured, NOW)
    assert events == []
    assert len(world.lego_calls) == 1
    assert world.deploy_calls == []
    row = state.get_state(db_session)
    assert row.last_renew_ok is True
    assert row.cert_fingerprint == "a" * 64  # bleibt erhalten


def test_force_deploys_even_without_new_cert(db_session, configured, world):
    world.lego_new = False
    service.run_cert_check(db_session, configured, NOW, force=True)
    assert len(world.deploy_calls) == 1


def test_deploy_failure_records_reason_and_notifies(db_session, configured, world):
    state.record_renew(db_session, True, None, "a" * 64, NOW + timedelta(days=60), NOW - timedelta(days=1))
    world.deploy_error = DeployFailed("nginx reload not permitted or failed")
    events = service.run_cert_check(db_session, configured, NOW)
    assert _ids(events) == ["renew_failed"]
    assert events[0].kwargs == {"domain": DOMAIN, "reason": "nginx reload not permitted or failed"}
    row = state.get_state(db_session)
    assert row.last_renew_ok is False
    assert row.last_renew_reason == "nginx reload not permitted or failed"
    # Das installierte Zertifikat ist weiterhin das alte
    assert row.cert_fingerprint == "a" * 64
    assert row.cert_not_after is not None


@pytest.mark.parametrize(
    "error, reason",
    [
        (lego.LegoError("acme: error 429"), "acme: error 429"),
        (deploy_cert.CertInvalid("domain not in certificate SAN"), "domain not in certificate SAN"),
    ],
)
def test_lego_and_cert_errors_are_failures(db_session, configured, world, error, reason):
    if isinstance(error, lego.LegoError):
        world.lego_error = error
    else:
        world.deploy_error = error
    events = service.run_cert_check(db_session, configured, NOW)
    assert _ids(events) == ["renew_failed"]
    assert state.get_state(db_session).last_renew_reason == reason


def test_lego_too_old_is_reported(db_session, configured, world):
    world.lego_version = (4, 9, 1)
    events = service.run_cert_check(db_session, configured, NOW)
    assert _ids(events) == ["renew_failed"]
    assert world.lego_calls == []
    assert "too old" in state.get_state(db_session).last_renew_reason


async def test_lego_missing_records_status_once_per_day(db_session, configured, world):
    """Zweimal pruefen -> Status beide Male gesetzt, Benachrichtigung nur einmal
    (Cooldown aus PluginEventSpec, durchgesetzt von emit_plugin_event)."""
    from app.plugins.installed.local_tls import LocalTlsPlugin
    from app.services.notifications import plugin_events

    world.lego_version = lego.LegoMissing("lego is not installed")
    emitter = AsyncMock()
    with patch.object(
        plugin_events, "_iter_enabled_plugins", return_value=[("local_tls", LocalTlsPlugin())]
    ), patch.object(plugin_events, "get_event_emitter", return_value=emitter):
        for i in range(2):
            events = service.run_cert_check(db_session, configured, NOW + timedelta(hours=i))
            assert _ids(events) == ["renew_failed"]
            row = state.get_state(db_session)
            assert row.last_renew_ok is False
            assert row.last_renew_reason == "lego is not installed"
            await service.deliver(events)

    assert emitter.emit_for_admins.await_count == 1
    args, kwargs = emitter.emit_for_admins.await_args
    assert args[0] == "plugin:local_tls:renew_failed"
    assert kwargs == {"domain": DOMAIN, "reason": "lego is not installed"}
    assert world.lego_calls == []


@pytest.mark.parametrize("days, expected", [(20, True), (21, True), (22, False)])
def test_expiry_warning_at_21_days(db_session, configured, world, days, expected):
    world.lego_new = False
    world.lego_fp = "a" * 64
    state.record_renew(db_session, True, None, "a" * 64, NOW + timedelta(days=days), NOW)
    events = service.run_cert_check(db_session, configured, NOW)
    if expected:
        assert _ids(events) == ["cert_expiring"]
        assert events[0].kwargs == {"domain": DOMAIN, "days": days}
    else:
        assert events == []


def test_expiry_warning_also_after_failure(db_session, configured, world):
    world.lego_error = lego.LegoError("acme: error")
    state.record_renew(db_session, True, None, "a" * 64, NOW + timedelta(days=5), NOW)
    events = service.run_cert_check(db_session, configured, NOW)
    assert _ids(events) == ["renew_failed", "cert_expiring"]


def test_cert_check_while_locked_skips_or_raises(db_session, configured, world):
    paths.ensure_dirs(world.data_dir)
    with paths.lock(world.data_dir):
        assert service.run_cert_check(db_session, configured, NOW) == []
        with pytest.raises(paths.AlreadyRunning):
            service.run_cert_check(db_session, configured, NOW, raise_if_running=True)
    assert world.lego_calls == []


# --- Hintergrundlauf ------------------------------------------------------

async def test_run_check_delivers_and_never_propagates(db_session, configured, world, caplog):
    emitted = []

    async def emit(plugin, event_id, entity_id="", **kwargs):
        emitted.append((plugin, event_id, entity_id, kwargs))

    class _NoClose:
        def __init__(self, s):
            self._s = s

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    world.provider.fail = True
    events = await service.run_check(
        service.run_address_check, lambda db: configured,
        session_factory=lambda: _NoClose(db_session), emit=emit, clock=lambda: NOW,
    )
    assert _ids(events) == ["dns_update_failed"]
    assert emitted == [("local_tls", "dns_update_failed", DOMAIN,
                        {"domain": DOMAIN, "reason": "duckdns rejected the update"})]

    def boom(db, config, now, **kw):
        raise RuntimeError(f"unexpected {TOKEN}")

    caplog.clear()
    events = await service.run_check(
        boom, lambda db: configured,
        session_factory=lambda: _NoClose(db_session), emit=emit, clock=lambda: NOW,
    )
    assert events == []
    assert "RuntimeError" in caplog.text
    assert TOKEN not in caplog.text


# --- Status ---------------------------------------------------------------

def test_status(db_session, configured, world):
    service.run_address_check(db_session, configured, NOW)
    service.run_cert_check(db_session, configured, NOW)
    st = service.get_status(db_session, configured, NOW)
    assert st.configured is True
    assert st.lego == "ok" and st.lego_version == "4.35.2"
    assert st.current_ip == IP and st.last_ip == IP
    assert st.cert_fingerprint == "f" * 64
    assert st.served_matches is True
    assert st.last_renew_ok is True
    assert st.running is False

    world.served_fp = "0" * 64
    assert service.get_status(db_session, configured, NOW).served_matches is False
    world.served_fp = None
    assert service.get_status(db_session, configured, NOW).served_matches is None


def test_status_unconfigured_and_lego_states(db_session, key, world):
    world.lego_version = lego.LegoMissing("lego is not installed")
    world.ip_error = address.AddressError("no route / interface found")
    st = service.get_status(db_session, LocalTlsConfig(), NOW)
    assert st.configured is False
    assert st.lego == "missing" and st.lego_version is None
    assert st.current_ip is None
    assert st.served_matches is None
    world.lego_version = (4, 9, 1)
    st = service.get_status(db_session, LocalTlsConfig(), NOW)
    assert st.lego == "too_old" and st.lego_version == "4.9.1"


def test_status_reports_running(db_session, configured, world):
    paths.ensure_dirs(world.data_dir)
    with paths.lock(world.data_dir):
        assert service.get_status(db_session, configured, NOW).running is True
    assert service.get_status(db_session, configured, NOW).running is False


# --- Konfiguration --------------------------------------------------------

def test_config_rejects_foreign_domain_for_duckdns():
    with pytest.raises(ValidationError):
        LocalTlsConfig(domain="evil.example.com")
    with pytest.raises(ValidationError):
        LocalTlsConfig(domain="-box.duckdns.org")
    assert LocalTlsConfig(domain=" Box.DuckDNS.org ").domain == DOMAIN
    assert LocalTlsConfig().domain == ""


def test_config_rejects_unknown_provider_and_bad_fields():
    with pytest.raises(ValidationError):
        LocalTlsConfig(provider="nope")
    with pytest.raises(ValidationError):
        LocalTlsConfig(interface="-eth0")
    with pytest.raises(ValidationError):
        LocalTlsConfig(email="--server=x")
    assert LocalTlsConfig(interface="", email="").interface is None
    assert LocalTlsConfig(interface="", email="").email is None
    assert LocalTlsConfig(interface="enp3s0").interface == "enp3s0"


# --- Fix-Runde 1: gescheiterte Uebernahme wird wiederholt -----------------

def test_failed_deploy_is_retried_on_next_run(db_session, configured, world):
    state.record_renew(db_session, True, None, "a" * 64, NOW + timedelta(days=30), NOW - timedelta(days=1))
    world.deploy_error = DeployFailed("nginx reload not permitted or failed")
    service.run_cert_check(db_session, configured, NOW)
    assert state.get_state(db_session).last_renew_ok is False

    # Naechster Tag: lego renew ist ein No-op, das neue Zertifikat liegt aber
    # noch nicht installiert vor -> erneut uebernehmen.
    world.deploy_error = None
    world.lego_new = False
    events = service.run_cert_check(db_session, configured, NOW + timedelta(days=1))
    assert events == []
    assert len(world.deploy_calls) == 2
    row = state.get_state(db_session)
    assert row.last_renew_ok is True
    assert row.cert_fingerprint == "f" * 64


def test_failed_first_deploy_is_retried_after_noop_renew(db_session, configured, world):
    world.deploy_error = deploy_cert.CertInvalid("domain not in certificate SAN")
    service.run_cert_check(db_session, configured, NOW)
    row = state.get_state(db_session)
    assert row.last_renew_ok is False and row.cert_fingerprint is None

    world.lego_new = False
    world.deploy_error = DeployFailed("nginx reload not permitted or failed")
    events = service.run_cert_check(db_session, configured, NOW + timedelta(days=1))
    assert len(world.deploy_calls) == 2
    assert _ids(events) == ["renew_failed"]
    # Kein ok=True ueber dem Fehler, solange nichts uebernommen ist
    assert state.get_state(db_session).last_renew_ok is False


def test_matching_fingerprint_is_not_redeployed(db_session, configured, world):
    service.run_cert_check(db_session, configured, NOW)
    assert len(world.deploy_calls) == 1
    world.lego_new = False
    service.run_cert_check(db_session, configured, NOW + timedelta(days=1))
    assert len(world.deploy_calls) == 1
    assert state.get_state(db_session).last_renew_ok is True


def test_switching_to_staging_with_old_staging_cert_deploys(db_session, configured, world):
    service.run_cert_check(db_session, configured, NOW)
    world.lego_new = False
    world.lego_fp = "b" * 64  # altes Staging-Zertifikat in lego-staging/
    cfg = configured.model_copy(update={"staging": True})
    service.run_cert_check(db_session, cfg, NOW + timedelta(days=1))
    assert len(world.deploy_calls) == 2
    crt, keyp, *_ = world.deploy_calls[1]
    assert (crt, keyp) == lego.cert_paths(DOMAIN, world.data_dir, staging=True)


# --- Fix-Runde 1: Start-Wettlauf um den Lock -------------------------------

def test_cert_check_waits_for_lock(db_session, configured, world, monkeypatch):
    from contextlib import ExitStack

    paths.ensure_dirs(world.data_dir)
    held = ExitStack()
    held.enter_context(paths.lock(world.data_dir))
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        held.close()  # der Adress-Check ist fertig

    monkeypatch.setattr(service, "_sleep", fake_sleep)
    service.run_cert_check(db_session, configured, NOW, lock_wait=60)
    assert len(sleeps) == 1
    assert len(world.lego_calls) == 1


def test_cert_check_gives_up_after_lock_wait(db_session, configured, world, monkeypatch):
    paths.ensure_dirs(world.data_dir)
    clock = [0.0]
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(service, "_sleep", fake_sleep)
    monkeypatch.setattr(service, "_monotonic", lambda: clock[0])
    with paths.lock(world.data_dir):
        assert service.run_cert_check(db_session, configured, NOW, lock_wait=60) == []
        with pytest.raises(paths.AlreadyRunning):
            service.run_cert_check(
                db_session, configured, NOW, lock_wait=5, raise_if_running=True
            )
    assert world.lego_calls == []
    assert 60 <= clock[0] <= 66
    assert all(s <= 5 for s in sleeps)


def test_expiry_warning_even_when_skipped(db_session, configured, world):
    state.record_renew(db_session, True, None, "a" * 64, NOW + timedelta(days=5), NOW)
    paths.ensure_dirs(world.data_dir)
    with paths.lock(world.data_dir):
        events = service.run_cert_check(db_session, configured, NOW)
    assert _ids(events) == ["cert_expiring"]
    assert world.lego_calls == []
