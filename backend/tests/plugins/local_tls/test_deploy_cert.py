"""Tests fuer Pruefung, atomaren Tausch und nginx-Verifikation (ohne echtes sudo)."""
import hashlib
import os
import stat
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.core.config import settings
from app.plugins.installed.local_tls import deploy_cert, paths
from app.plugins.installed.local_tls.deploy_cert import (
    CertInvalid,
    DeployFailed,
    DeployOutcome,
    deploy,
    inspect,
    reload_nginx,
)

DOMAIN = "box.duckdns.org"
NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)


def _make_pair(domain=DOMAIN, not_before=None, not_after=None):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or NOW - timedelta(days=1))
        .not_valid_after(not_after or NOW + timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fp = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return cert_pem, key_pem, fp


def _make_chain(domain=DOMAIN, ca_cn="Test CA"):
    """CA-ausgestelltes Leaf: liefert (leaf_pem, ca_pem, key_pem)."""
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ca_cn)])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - timedelta(days=10))
        .not_valid_after(NOW + timedelta(days=900))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - timedelta(days=1))
        .not_valid_after(NOW + timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    key_pem = key.private_bytes(
        pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return leaf.public_bytes(pem), ca.public_bytes(pem), key_pem


def _write_pair(tmp_path, name, **kw):
    cert_pem, key_pem, fp = _make_pair(**kw)
    src = tmp_path / "src" / name
    src.mkdir(parents=True)
    (src / "cert.pem").write_bytes(cert_pem)
    (src / "key.pem").write_bytes(key_pem)
    return src / "cert.pem", src / "key.pem", fp


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    """Kein echtes Warten beim Abfragen nach dem Reload: Schlaf rueckt die Uhr vor."""
    clock = {"t": 0.0, "sleeps": []}

    def sleep(seconds):
        clock["sleeps"].append(seconds)
        clock["t"] += seconds

    monkeypatch.setattr(deploy_cert, "_sleep", sleep)
    monkeypatch.setattr(deploy_cert, "_monotonic", lambda: clock["t"])
    return clock


class FakeReload:
    def __init__(self, fail_on=()):
        self.calls = 0
        self.fail_on = set(fail_on)

    def __call__(self):
        self.calls += 1
        if self.calls in self.fail_on:
            raise DeployFailed("nginx reload not permitted or failed")


def _served_live(data_dir):
    """Liefert den Fingerabdruck dessen, worauf live gerade zeigt (wie nginx)."""
    def served(domain):
        path = data_dir / "live" / "fullchain.pem"
        if not path.exists():
            return None
        pem = path.read_bytes()
        cert = x509.load_pem_x509_certificate(pem)
        return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return served


def _served_then(data_dir, after):
    """Vor dem Tausch: was live zeigt (nginx liefert Plugin-Zertifikat); danach ``after``."""
    live = _served_live(data_dir)
    calls = []

    def served(domain):
        calls.append(domain)
        return live(domain) if len(calls) == 1 else after

    return served


# --- inspect ---------------------------------------------------------------


def test_inspect_accepts_matching_pair():
    cert_pem, key_pem, fp = _make_pair()
    info = inspect(cert_pem, key_pem, DOMAIN.upper(), NOW)
    assert info.fingerprint == fp
    assert info.sans == (DOMAIN,)
    assert info.not_after > NOW


def test_inspect_rejects_mismatched_key():
    cert_pem, _, _ = _make_pair()
    _, other_key, _ = _make_pair()
    with pytest.raises(CertInvalid):
        inspect(cert_pem, other_key, DOMAIN, NOW)


def test_inspect_rejects_wrong_domain():
    cert_pem, key_pem, _ = _make_pair()
    with pytest.raises(CertInvalid):
        inspect(cert_pem, key_pem, "other.duckdns.org", NOW)


def test_inspect_rejects_expired():
    cert_pem, key_pem, _ = _make_pair(
        not_before=NOW - timedelta(days=100), not_after=NOW - timedelta(days=1)
    )
    with pytest.raises(CertInvalid):
        inspect(cert_pem, key_pem, DOMAIN, NOW)


def test_inspect_accepts_complete_chain():
    leaf, ca, key = _make_chain()
    info = inspect(leaf + ca, key, DOMAIN, NOW)
    assert info.sans == (DOMAIN,)


def test_inspect_rejects_leaf_only_chain():
    leaf, _, key = _make_chain()
    with pytest.raises(CertInvalid, match="incomplete chain"):
        inspect(leaf, key, DOMAIN, NOW)


def test_inspect_rejects_out_of_order_chain():
    leaf, ca, key = _make_chain()
    _, other_ca, _ = _make_chain(ca_cn="Other CA")
    with pytest.raises(CertInvalid):
        inspect(leaf + other_ca, key, DOMAIN, NOW)
    with pytest.raises(CertInvalid):
        inspect(leaf + ca + other_ca, key, DOMAIN, NOW)


def test_inspect_requires_aware_now():
    cert_pem, key_pem, _ = _make_pair()
    with pytest.raises(ValueError):
        inspect(cert_pem, key_pem, DOMAIN, NOW.replace(tzinfo=None))


def test_inspect_rejects_broken_pem():
    with pytest.raises(CertInvalid):
        inspect(b"not a pem", b"nope", DOMAIN, NOW)


# --- deploy ----------------------------------------------------------------


def test_deploy_switches_live_atomically(tmp_path):
    data = tmp_path / "data"
    cert, key, fp = _write_pair(tmp_path, "a")
    reload = FakeReload()
    outcome = deploy(cert, key, DOMAIN, data, NOW, reload=reload, served_fingerprint=_served_live(data))

    assert isinstance(outcome, DeployOutcome)
    assert outcome.info.fingerprint == fp
    assert outcome.served is True
    live = data / "live"
    assert live.is_symlink()
    assert os.readlink(live) == "releases/20261125T120000Z"
    for name in ("fullchain.pem", "privkey.pem"):
        assert stat.S_IMODE((live / name).stat().st_mode) == 0o600
    assert stat.S_IMODE((data / "releases" / "20261125T120000Z").stat().st_mode) == 0o700
    assert reload.calls == 1
    assert not any(p.name.startswith(".live") for p in data.iterdir())


def test_rolls_back_when_served_cert_differs(tmp_path):
    data = tmp_path / "data"
    c1, k1, _ = _write_pair(tmp_path, "a")
    deploy(c1, k1, DOMAIN, data, NOW, reload=FakeReload(), served_fingerprint=_served_live(data))
    old_target = os.readlink(data / "live")

    c2, k2, _ = _write_pair(tmp_path, "b")
    reload = FakeReload()
    with pytest.raises(DeployFailed) as exc:
        deploy(c2, k2, DOMAIN, data, NOW + timedelta(days=60), reload=reload,
               served_fingerprint=_served_then(data, "deadbeef"))
    assert "served" in exc.value.reason
    assert not (data / "releases" / "20270124T120000Z").exists()
    assert os.readlink(data / "live") == old_target
    assert reload.calls == 2


def _served_sequence(data_dir, after_values):
    """Vor dem Tausch: was live zeigt; danach nacheinander ``after_values``
    (der letzte Wert bleibt stehen) -- wie nginx' sanfter Reload, bei dem alte
    Worker noch kurz das alte Zertifikat ausliefern."""
    live = _served_live(data_dir)
    calls = []

    def served(domain):
        calls.append(domain)
        if len(calls) == 1:
            return live(domain)
        i = min(len(calls) - 2, len(after_values) - 1)
        value = after_values[i]
        return live(domain) if value == "live" else value

    served.calls = calls
    return served


def test_graceful_reload_old_cert_briefly_is_not_rolled_back(tmp_path, fake_clock):
    data = tmp_path / "data"
    c1, k1, _ = _write_pair(tmp_path, "a")
    deploy(c1, k1, DOMAIN, data, NOW, reload=FakeReload(), served_fingerprint=_served_live(data))
    old_fp = _served_live(data)(DOMAIN)

    c2, k2, new_fp = _write_pair(tmp_path, "b")
    reload = FakeReload()
    served = _served_sequence(data, [old_fp, old_fp, new_fp])
    outcome = deploy(c2, k2, DOMAIN, data, NOW + timedelta(days=60), reload=reload,
                     served_fingerprint=served)
    assert outcome.served is True
    assert outcome.info.fingerprint == new_fp
    assert os.readlink(data / "live") == "releases/20270124T120000Z"
    assert reload.calls == 1
    assert len(served.calls) == 4  # pre + drei Abfragen
    assert fake_clock["sleeps"] and all(s <= 0.5 for s in fake_clock["sleeps"])


def test_served_never_matches_rolls_back_after_deadline(tmp_path, fake_clock):
    data = tmp_path / "data"
    c1, k1, _ = _write_pair(tmp_path, "a")
    deploy(c1, k1, DOMAIN, data, NOW, reload=FakeReload(), served_fingerprint=_served_live(data))
    old_fp = _served_live(data)(DOMAIN)
    old_target = os.readlink(data / "live")
    fake_clock["t"] = 0.0

    c2, k2, _ = _write_pair(tmp_path, "b")
    with pytest.raises(DeployFailed, match="served"):
        deploy(c2, k2, DOMAIN, data, NOW + timedelta(days=60), reload=FakeReload(),
               served_fingerprint=_served_sequence(data, [old_fp]))
    assert os.readlink(data / "live") == old_target
    assert 15 <= fake_clock["t"] <= 16


def test_not_served_without_plugin_before_waits_then_keeps(tmp_path, fake_clock):
    data = tmp_path / "data"
    cert, key, _ = _write_pair(tmp_path, "a")
    outcome = deploy(cert, key, DOMAIN, data, NOW, reload=FakeReload(),
                     served_fingerprint=lambda d: "certbot-fp")
    assert outcome.served is False
    assert 15 <= fake_clock["t"] <= 16


def test_rolls_back_when_reload_fails(tmp_path):
    data = tmp_path / "data"
    c1, k1, _ = _write_pair(tmp_path, "a")
    deploy(c1, k1, DOMAIN, data, NOW, reload=FakeReload(), served_fingerprint=_served_live(data))
    old_target = os.readlink(data / "live")

    c2, k2, _ = _write_pair(tmp_path, "b")
    reload = FakeReload(fail_on={1})
    with pytest.raises(DeployFailed) as exc:
        deploy(c2, k2, DOMAIN, data, NOW + timedelta(days=60), reload=reload,
               served_fingerprint=_served_live(data))
    assert "reload" in exc.value.reason
    assert os.readlink(data / "live") == old_target
    assert reload.calls == 2


def test_first_deploy_keeps_cert_when_nginx_not_switched_yet(tmp_path):
    data = tmp_path / "data"
    cert, key, fp = _write_pair(tmp_path, "a")
    reload = FakeReload()
    outcome = deploy(cert, key, DOMAIN, data, NOW, reload=reload,
                     served_fingerprint=lambda d: "certbot-fp")
    assert outcome.served is False
    assert outcome.info.fingerprint == fp
    assert os.readlink(data / "live") == "releases/20261125T120000Z"
    assert (data / "live" / "fullchain.pem").exists()
    assert reload.calls == 1


def test_renew_while_site_not_switched_keeps_new_cert(tmp_path):
    data = tmp_path / "data"
    c1, k1, _ = _write_pair(tmp_path, "a")
    deploy(c1, k1, DOMAIN, data, NOW, reload=FakeReload(),
           served_fingerprint=lambda d: "certbot-fp")
    c2, k2, _ = _write_pair(tmp_path, "b")
    reload = FakeReload()
    outcome = deploy(c2, k2, DOMAIN, data, NOW + timedelta(days=60), reload=reload,
                     served_fingerprint=lambda d: "certbot-fp")
    assert outcome.served is False
    assert os.readlink(data / "live") == "releases/20270124T120000Z"
    assert (data / "releases" / "20261125T120000Z").exists()
    assert reload.calls == 1


def test_first_deploy_reload_failure_keeps_live_and_raises(tmp_path):
    data = tmp_path / "data"
    cert, key, _ = _write_pair(tmp_path, "a")
    reload = FakeReload(fail_on={1})
    with pytest.raises(DeployFailed) as exc:
        deploy(cert, key, DOMAIN, data, NOW, reload=reload,
               served_fingerprint=lambda d: None)
    assert "reload" in exc.value.reason
    assert os.readlink(data / "live") == "releases/20261125T120000Z"
    assert reload.calls == 1


def test_naive_now_is_rejected(tmp_path):
    cert, key, _ = _write_pair(tmp_path, "a")
    with pytest.raises(ValueError):
        deploy(cert, key, DOMAIN, tmp_path / "data", NOW.replace(tzinfo=None),
               reload=FakeReload(), served_fingerprint=lambda d: None)


def test_stale_tmp_symlinks_are_cleaned(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    os.symlink("releases/old", data / ".live.tmp.99999")
    cert, key, _ = _write_pair(tmp_path, "a")
    deploy(cert, key, DOMAIN, data, NOW, reload=FakeReload(),
           served_fingerprint=_served_live(data))
    assert not os.path.lexists(data / ".live.tmp.99999")


def test_write_error_becomes_deploy_failed_and_keeps_live(tmp_path, monkeypatch):
    data = tmp_path / "data"
    c1, k1, _ = _write_pair(tmp_path, "a")
    deploy(c1, k1, DOMAIN, data, NOW, reload=FakeReload(), served_fingerprint=_served_live(data))
    old_target = os.readlink(data / "live")

    real_write = deploy_cert._write_private

    def write_then_fail(path, data_bytes):
        if path.name == "privkey.pem":
            raise OSError("disk full")
        real_write(path, data_bytes)

    monkeypatch.setattr(deploy_cert, "_write_private", write_then_fail)
    c2, k2, _ = _write_pair(tmp_path, "b")
    reload = FakeReload()
    with pytest.raises(DeployFailed):
        deploy(c2, k2, DOMAIN, data, NOW + timedelta(days=1), reload=reload,
               served_fingerprint=_served_live(data))
    assert os.readlink(data / "live") == old_target
    assert reload.calls == 0
    assert sorted(p.name for p in (data / "releases").iterdir()) == ["20261125T120000Z"]


def test_invalid_cert_is_not_deployed(tmp_path):
    data = tmp_path / "data"
    cert, _, _ = _write_pair(tmp_path, "a")
    _, other_key, _ = _write_pair(tmp_path, "b")
    reload = FakeReload()
    with pytest.raises(CertInvalid):
        deploy(cert, other_key, DOMAIN, data, NOW, reload=reload,
               served_fingerprint=_served_live(data))
    assert reload.calls == 0
    assert not os.path.lexists(data / "live")


def test_keeps_last_three_releases(tmp_path):
    data = tmp_path / "data"
    for i in range(5):
        c, k, _ = _write_pair(tmp_path, f"p{i}")
        deploy(c, k, DOMAIN, data, NOW + timedelta(days=i), reload=FakeReload(),
               served_fingerprint=_served_live(data))
    releases = sorted(p.name for p in (data / "releases").iterdir())
    assert releases == ["20261127T120000Z", "20261128T120000Z", "20261129T120000Z"]
    assert os.readlink(data / "live") == "releases/20261129T120000Z"


def test_prune_never_deletes_live_target(tmp_path):
    data = tmp_path / "data"
    c, k, _ = _write_pair(tmp_path, "p0")
    deploy(c, k, DOMAIN, data, NOW, reload=FakeReload(), served_fingerprint=_served_live(data))
    # Drei neuere Versuche scheitern -> live bleibt auf dem aeltesten Release.
    for i in range(1, 4):
        c, k, _ = _write_pair(tmp_path, f"p{i}")
        with pytest.raises(DeployFailed):
            deploy(c, k, DOMAIN, data, NOW + timedelta(days=i), reload=FakeReload(),
                   served_fingerprint=_served_then(data, "deadbeef"))
    target = os.readlink(data / "live")
    assert target == "releases/20261125T120000Z"
    assert (data / target / "fullchain.pem").exists()


# --- reload_nginx -----------------------------------------------------------


@pytest.fixture
def prod_mode(monkeypatch):
    monkeypatch.setattr(settings, "is_dev_mode", False)


def test_reload_uses_existing_sudo_rule_only(prod_mode):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    reload_nginx(run=run)
    assert calls[0][0] == ["sudo", "-n", "/usr/bin/systemctl", "reload", "nginx"]
    assert calls[0][1]["timeout"] == 30
    assert "shell" not in calls[0][1]


def test_reload_failure_raises_deploy_failed(prod_mode):
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="sudo: a password is required")

    with pytest.raises(DeployFailed) as exc:
        reload_nginx(run=run)
    assert exc.value.reason == "nginx reload not permitted or failed"


def test_reload_timeout_raises_deploy_failed(prod_mode):
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 30)

    with pytest.raises(DeployFailed):
        reload_nginx(run=run)


# --- served_fingerprint ------------------------------------------------------


def test_served_fingerprint_network_error_returns_none(monkeypatch, prod_mode):
    def boom(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(deploy_cert.socket, "create_connection", boom)
    assert deploy_cert.served_fingerprint(DOMAIN) is None


# --- Entwicklungsmodus -------------------------------------------------------


def test_dev_mode_reload_is_a_noop(monkeypatch):
    monkeypatch.setattr(settings, "is_dev_mode", True)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    reload_nginx(run=run)
    assert calls == []


def test_dev_mode_served_fingerprint_is_unknown(monkeypatch):
    monkeypatch.setattr(settings, "is_dev_mode", True)

    def boom(*a, **kw):
        raise AssertionError("no handshake in dev mode")

    monkeypatch.setattr(deploy_cert.socket, "create_connection", boom)
    assert deploy_cert.served_fingerprint(DOMAIN) is None


def test_data_dir_dev_vs_prod(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "is_dev_mode", True)
    monkeypatch.setattr(settings, "nas_storage_path", str(tmp_path / "dev-storage"))
    assert paths.default_data_dir() == (tmp_path / "dev-storage" / ".system" / "local_tls")
    monkeypatch.setattr(settings, "is_dev_mode", False)
    assert paths.default_data_dir() == paths.PROD_DATA_DIR
    assert str(paths.PROD_DATA_DIR) == "/var/lib/baluhost/plugins/local_tls"


def test_probe_context_requires_tls12():
    """CodeQL py/insecure-protocol: the served-fingerprint probe must not allow TLS < 1.2."""
    import ssl

    ctx = deploy_cert._probe_context()
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False
