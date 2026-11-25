"""Tests fuer den lego-Aufruf und den Lauf-Lock (ohne echtes lego)."""
import subprocess

import pytest

from app.plugins.installed.local_tls import lego
from app.plugins.installed.local_tls.lego import LegoError, LegoMissing
from app.plugins.installed.local_tls.paths import AlreadyRunning, ensure_dirs, lock

TOKEN = "s3cret-token-value"
DOMAIN = "box.duckdns.org"


def _recorder(returncode=0, stdout="", stderr="", effect=None):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if effect:
            effect()
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)

    return run, calls


def test_missing_lego_is_reported_not_raised_as_filenotfound():
    def run(args, **kwargs):
        raise FileNotFoundError("lego")

    with pytest.raises(LegoMissing):
        lego.version(run=run)


def test_old_lego_detected():
    run, calls = _recorder(stdout="lego version 4.9.1 linux/amd64\n")
    v = lego.version(run=run)
    assert v == (4, 9, 1)
    assert v < lego.MIN_VERSION
    assert calls[0][0] == ["lego", "--version"]


def test_current_lego_parsed():
    run, _ = _recorder(stdout="lego version 4.35.2 linux/amd64\n")
    assert lego.version(run=run) >= lego.MIN_VERSION


def test_unparsable_version_is_lego_error():
    run, _ = _recorder(stdout="garbage")
    with pytest.raises(LegoError):
        lego.version(run=run)


def _write_cert(data_dir, content=b"cert"):
    crt, key = lego.cert_paths(DOMAIN, data_dir)
    crt.parent.mkdir(parents=True, exist_ok=True)
    crt.write_bytes(content)
    key.write_bytes(b"key")


def test_cert_paths(tmp_path):
    crt, key = lego.cert_paths(DOMAIN, tmp_path)
    assert crt == tmp_path / "lego" / "certificates" / f"{DOMAIN}.crt"
    assert key == tmp_path / "lego" / "certificates" / f"{DOMAIN}.key"


def test_first_run_uses_run_then_renew(tmp_path):
    base = [
        "lego", "--accept-tos", "--path", str(tmp_path / "lego"),
        "--dns", "duckdns", "--domains", DOMAIN,
    ]
    run1, calls1 = _recorder(effect=lambda: _write_cert(tmp_path))
    created = lego.obtain_or_renew(
        DOMAIN, "duckdns", {"DUCKDNS_TOKEN": TOKEN}, tmp_path,
        email=None, staging=False, run=run1,
    )
    assert created is True
    args, kwargs = calls1[0]
    assert args == base + ["run"]
    assert TOKEN not in " ".join(args)
    assert kwargs["env"]["DUCKDNS_TOKEN"] == TOKEN
    assert kwargs["timeout"] == 300
    assert not kwargs.get("shell")

    run2, calls2 = _recorder()
    created = lego.obtain_or_renew(
        DOMAIN, "duckdns", {"DUCKDNS_TOKEN": TOKEN}, tmp_path,
        email=None, staging=False, run=run2,
    )
    assert created is False
    assert calls2[0][0] == base + ["renew", "--days", "30"]


def test_renew_that_replaces_cert_returns_true(tmp_path):
    _write_cert(tmp_path, b"old")
    run, _ = _recorder(effect=lambda: _write_cert(tmp_path, b"new"))
    assert lego.obtain_or_renew(
        DOMAIN, "duckdns", {}, tmp_path, email=None, staging=False, run=run
    ) is True


def test_staging_and_email_flags(tmp_path):
    run, calls = _recorder()
    lego.obtain_or_renew(
        DOMAIN, "duckdns", {}, tmp_path,
        email="a@example.org", staging=True, run=run,
    )
    args = calls[0][0]
    assert args[-1] == "run"
    assert ["--email", "a@example.org"] == args[args.index("--email"):args.index("--email") + 2]
    i = args.index("--server")
    assert args[i + 1] == "https://acme-staging-v02.api.letsencrypt.org/directory"


def test_env_does_not_leak_backend_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "backend-secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    run, calls = _recorder()
    lego.obtain_or_renew(
        DOMAIN, "duckdns", {"DUCKDNS_TOKEN": TOKEN}, tmp_path,
        email=None, staging=False, run=run,
    )
    env = calls[0][1]["env"]
    assert "SECRET_KEY" not in env
    assert env["PATH"] == "/usr/bin"


def test_error_message_never_contains_token(tmp_path):
    run, _ = _recorder(
        returncode=1,
        stderr=f"earlier line\nerror: bad token {TOKEN} for request\n",
    )
    with pytest.raises(LegoError) as exc:
        lego.obtain_or_renew(
            DOMAIN, "duckdns", {"DUCKDNS_TOKEN": TOKEN}, tmp_path,
            email=None, staging=False, run=run,
        )
    assert TOKEN not in str(exc.value)
    assert "bad token" in str(exc.value)


def test_lock_is_exclusive(tmp_path):
    ensure_dirs(tmp_path)
    with lock(tmp_path):
        with pytest.raises(AlreadyRunning):
            with lock(tmp_path):
                pass
    with lock(tmp_path):
        pass


def test_ensure_dirs_mode(tmp_path):
    d = tmp_path / "data"
    ensure_dirs(d)
    assert (d.stat().st_mode & 0o777) == 0o700


def test_staging_uses_separate_lego_path(tmp_path):
    """Staging und Produktion teilen keinen lego-Zustand: ein Staging-Zertifikat
    darf den Wechsel auf Produktion nicht zum No-op-``renew`` machen."""
    crt_prod, _ = lego.cert_paths(DOMAIN, tmp_path)
    crt_stg, key_stg = lego.cert_paths(DOMAIN, tmp_path, staging=True)
    assert crt_stg == tmp_path / "lego-staging" / "certificates" / f"{DOMAIN}.crt"
    assert key_stg == tmp_path / "lego-staging" / "certificates" / f"{DOMAIN}.key"
    assert crt_prod != crt_stg

    # Staging-Zertifikat vorhanden -> Staging erneuert, Produktion stellt neu aus.
    crt_stg.parent.mkdir(parents=True)
    crt_stg.write_bytes(b"staging")
    run, calls = _recorder()
    lego.obtain_or_renew(DOMAIN, "duckdns", {}, tmp_path, email=None, staging=True, run=run)
    args = calls[0][0]
    assert args[args.index("--path") + 1] == str(tmp_path / "lego-staging")
    assert args[-3:] == ["renew", "--days", "30"]

    run, calls = _recorder()
    lego.obtain_or_renew(DOMAIN, "duckdns", {}, tmp_path, email=None, staging=False, run=run)
    args = calls[0][0]
    assert args[args.index("--path") + 1] == str(tmp_path / "lego")
    assert args[-1] == "run"


def test_ensure_dirs_creates_both_lego_paths(tmp_path):
    d = tmp_path / "data"
    ensure_dirs(d)
    for sub in ("lego", "lego-staging"):
        assert ((d / sub).stat().st_mode & 0o777) == 0o700


# --- Fix-Runde final: OSError und Dekodierung ---------------------------------

def test_version_oserror_is_lego_error():
    def run(args, **kwargs):
        raise PermissionError("lego")

    with pytest.raises(LegoError):
        lego.version(run=run)


def test_obtain_oserror_is_lego_error(tmp_path):
    def run(args, **kwargs):
        raise PermissionError("lego")

    with pytest.raises(LegoError):
        lego.obtain_or_renew(
            DOMAIN, "duckdns", {"DUCKDNS_TOKEN": TOKEN}, tmp_path, email=None, staging=False, run=run
        )


def test_subprocess_output_decoded_with_replace(tmp_path):
    run, calls = _recorder(stdout="lego version 4.35.2\n")
    lego.version(run=run)
    lego.obtain_or_renew(
        DOMAIN, "duckdns", {"DUCKDNS_TOKEN": TOKEN}, tmp_path, email=None, staging=False, run=run
    )
    assert all(kw.get("errors") == "replace" for _, kw in calls)
