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

from app.plugins.installed.local_tls import deploy_cert
from app.plugins.installed.local_tls.deploy_cert import (
    CertInvalid,
    DeployFailed,
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


def _write_pair(tmp_path, name, **kw):
    cert_pem, key_pem, fp = _make_pair(**kw)
    src = tmp_path / "src" / name
    src.mkdir(parents=True)
    (src / "cert.pem").write_bytes(cert_pem)
    (src / "key.pem").write_bytes(key_pem)
    return src / "cert.pem", src / "key.pem", fp


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
        pem = (data_dir / "live" / "fullchain.pem").read_bytes()
        cert = x509.load_pem_x509_certificate(pem)
        return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
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


def test_inspect_rejects_broken_pem():
    with pytest.raises(CertInvalid):
        inspect(b"not a pem", b"nope", DOMAIN, NOW)


# --- deploy ----------------------------------------------------------------


def test_deploy_switches_live_atomically(tmp_path):
    data = tmp_path / "data"
    cert, key, fp = _write_pair(tmp_path, "a")
    reload = FakeReload()
    info = deploy(cert, key, DOMAIN, data, NOW, reload=reload, served_fingerprint=_served_live(data))

    assert info.fingerprint == fp
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
               served_fingerprint=lambda d: "deadbeef")
    assert "served" in exc.value.reason
    assert os.readlink(data / "live") == old_target
    assert reload.calls == 2


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


def test_first_deploy_without_previous_release_fails_cleanly(tmp_path):
    data = tmp_path / "data"
    cert, key, _ = _write_pair(tmp_path, "a")
    with pytest.raises(DeployFailed):
        deploy(cert, key, DOMAIN, data, NOW, reload=FakeReload(),
               served_fingerprint=lambda d: None)
    assert not os.path.lexists(data / "live")


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
                   served_fingerprint=lambda d: "deadbeef")
    target = os.readlink(data / "live")
    assert target == "releases/20261125T120000Z"
    assert (data / target / "fullchain.pem").exists()


# --- reload_nginx -----------------------------------------------------------


def test_reload_uses_existing_sudo_rule_only():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    reload_nginx(run=run)
    assert calls[0][0] == ["sudo", "-n", "/usr/bin/systemctl", "reload", "nginx"]
    assert calls[0][1]["timeout"] == 30
    assert "shell" not in calls[0][1]


def test_reload_failure_raises_deploy_failed():
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="sudo: a password is required")

    with pytest.raises(DeployFailed) as exc:
        reload_nginx(run=run)
    assert exc.value.reason == "nginx reload not permitted or failed"


def test_reload_timeout_raises_deploy_failed():
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 30)

    with pytest.raises(DeployFailed):
        reload_nginx(run=run)


# --- served_fingerprint ------------------------------------------------------


def test_served_fingerprint_network_error_returns_none(monkeypatch):
    def boom(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(deploy_cert.socket, "create_connection", boom)
    assert deploy_cert.served_fingerprint(DOMAIN) is None
