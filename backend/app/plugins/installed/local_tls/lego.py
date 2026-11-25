"""Einziger Kontakt zu lego (subprocess, Listen-Args, kein Root)."""
import hashlib
import os
import re
import subprocess
from pathlib import Path

MIN_VERSION = (4, 35, 0)
_TIMEOUT = 300
_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
_SAFE_ENV = ("PATH", "HOME", "LANG")


class LegoError(Exception):
    """lego-Fehler. Meldung enthaelt nie Werte aus der Anbieter-Umgebung."""


class LegoMissing(LegoError):
    pass


class LegoTooOld(LegoError):
    pass


def version(*, run=subprocess.run) -> tuple[int, int, int]:
    try:
        proc = run(["lego", "--version"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        raise LegoMissing("lego is not installed") from None
    except subprocess.TimeoutExpired:
        raise LegoError("lego --version timed out") from None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", proc.stdout or "")
    if proc.returncode != 0 or not m:
        raise LegoError("could not determine lego version")
    return (int(m[1]), int(m[2]), int(m[3]))


def lego_dir(data_dir: Path, *, staging: bool = False) -> Path:
    """lego-Zustand; Staging getrennt, damit der Wechsel auf Produktion neu ausstellt."""
    return data_dir / ("lego-staging" if staging else "lego")


def cert_paths(domain: str, data_dir: Path, *, staging: bool = False) -> tuple[Path, Path]:
    base = lego_dir(data_dir, staging=staging) / "certificates"
    return base / f"{domain}.crt", base / f"{domain}.key"


def _fingerprint(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        text = text.replace(s, "***")
    return text


def obtain_or_renew(
    domain: str,
    provider_lego_name: str,
    env: dict[str, str],
    data_dir: Path,
    *,
    email: str | None,
    staging: bool,
    run=subprocess.run,
) -> bool:
    """Stellt aus oder erneuert; True, wenn ein neues Zertifikat entstanden ist."""
    crt, _ = cert_paths(domain, data_dir, staging=staging)
    before = _fingerprint(crt)
    args = [
        "lego", "--accept-tos", "--path", str(lego_dir(data_dir, staging=staging)),
        "--dns", provider_lego_name, "--domains", domain,
    ]
    if email:
        args += ["--email", email]
    if staging:
        args += ["--server", _STAGING]
    args += ["run"] if before is None else ["renew", "--days", "30"]

    # Minimale Umgebung: das Backend-env enthaelt SECRET_KEY u. a.
    full_env = {k: os.environ[k] for k in _SAFE_ENV if k in os.environ}
    full_env.update(env)
    try:
        proc = run(args, capture_output=True, text=True, timeout=_TIMEOUT, env=full_env)
    except FileNotFoundError:
        raise LegoMissing("lego is not installed") from None
    except subprocess.TimeoutExpired:
        raise LegoError("lego timed out") from None
    if proc.returncode != 0:
        lines = [ln for ln in (proc.stderr or "").strip().splitlines() if ln.strip()]
        last = lines[-1].strip() if lines else f"lego exited with {proc.returncode}"
        raise LegoError(_redact(last, [v for v in env.values() if v]))
    return _fingerprint(crt) != before
