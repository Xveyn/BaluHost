"""Zertifikat pruefen, atomar tauschen, nginx neu laden und Auslieferung verifizieren.

nginx liest dauerhaft ``<data>/live/fullchain.pem`` und ``<data>/live/privkey.pem``.
``live`` ist ein relativer Symlink auf ``releases/<UTC-Zeitstempel>/``; der Tausch
ist ein ``os.replace`` eines temporaeren Symlinks. Neu geladen wird nginx nur ueber
die bestehende sudoers-Regel (``sudo -n /usr/bin/systemctl reload nginx``).
"""
import hashlib
import os
import shutil
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization

RELOAD_ARGS = ["sudo", "-n", "/usr/bin/systemctl", "reload", "nginx"]
RELOAD_TIMEOUT = 30
HANDSHAKE_TIMEOUT = 5
KEEP_RELEASES = 3
# nginx laedt sanft neu: alte Worker liefern das alte Zertifikat noch einige
# hundert Millisekunden aus. Daher nach dem Reload bis VERIFY_TIMEOUT abfragen.
VERIFY_TIMEOUT = 15.0
VERIFY_INTERVAL = 0.5

# Indirektionen, damit Tests das Warten ohne echte Pausen pruefen.
_sleep = time.sleep
_monotonic = time.monotonic


class CertInvalid(Exception):
    """Zertifikat/Schluessel bestehen die Pruefung nicht; es wird nichts getauscht."""


class DeployFailed(Exception):
    """Tausch oder Verifikation gescheitert; ``reason`` ist fuer Status/Benachrichtigung."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CertInfo:
    fingerprint: str  # sha256 hex des DER-Leaf-Zertifikats
    not_after: datetime
    sans: tuple[str, ...]


@dataclass(frozen=True)
class DeployOutcome:
    info: CertInfo
    served: bool  # liefert nginx nach dem Reload das neue Zertifikat aus?


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(timezone.utc)


def _fingerprint(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _public_bytes(public_key) -> bytes:
    return public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def inspect(cert_pem: bytes, key_pem: bytes, domain: str, now: datetime) -> CertInfo:
    """Prueft PEM, Schluesselpaar, SAN, Gueltigkeit und Vollstaendigkeit der Kette."""
    now = _utc(now)
    try:
        chain = x509.load_pem_x509_certificates(cert_pem)
    except ValueError:
        raise CertInvalid("certificate is not valid PEM") from None
    if not chain:
        raise CertInvalid("certificate is not valid PEM")
    leaf = chain[0]
    try:
        key = serialization.load_pem_private_key(key_pem, password=None)
    except (ValueError, TypeError):
        # Keine Details weitergeben: die Meldung koennte Schluesselmaterial beruehren.
        raise CertInvalid("private key is not valid PEM") from None
    if _public_bytes(key.public_key()) != _public_bytes(leaf.public_key()):
        raise CertInvalid("private key does not match certificate")

    try:
        san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        sans = tuple(san.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        sans = ()
    if domain.lower() not in {s.lower() for s in sans}:
        raise CertInvalid("domain not in certificate SAN")

    if now < leaf.not_valid_before_utc:
        raise CertInvalid("certificate not yet valid")
    if now >= leaf.not_valid_after_utc:
        raise CertInvalid("certificate expired")

    # Kette vollstaendig und in Reihenfolge: jedes Glied vom naechsten ausgestellt;
    # ein nicht selbst ausgestelltes Leaf ohne Zwischenzertifikat ist unvollstaendig.
    if len(chain) == 1 and leaf.issuer != leaf.subject:
        raise CertInvalid("incomplete chain")
    for child, parent in zip(chain, chain[1:]):
        if child.issuer != parent.subject:
            raise CertInvalid("certificate chain is out of order")

    return CertInfo(fingerprint=_fingerprint(leaf), not_after=leaf.not_valid_after_utc, sans=sans)


def reload_nginx(*, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
    """Laedt nginx ueber die bestehende sudoers-Regel neu (ohne Passwortabfrage)."""
    try:
        result = run(
            RELOAD_ARGS, capture_output=True, text=True, errors="replace", timeout=RELOAD_TIMEOUT
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DeployFailed("nginx reload not permitted or failed") from None
    if result.returncode != 0:
        raise DeployFailed("nginx reload not permitted or failed")


def served_fingerprint(domain: str, host: str = "127.0.0.1", port: int = 443) -> Optional[str]:
    """sha256 des Zertifikats, das ``host:port`` fuer SNI=``domain`` ausliefert; Netzfehler -> None."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=HANDSHAKE_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as tls:
                der = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError, ValueError):
        return None
    if not der:
        return None
    return hashlib.sha256(der).hexdigest()


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _point_live(data_dir: Path, target: str) -> None:
    """Biegt ``live`` atomar auf ``target`` (relativ, z. B. ``releases/<ts>``) um."""
    tmp = data_dir / f".live.tmp.{os.getpid()}"
    if os.path.lexists(tmp):
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, data_dir / "live")


def _prune(data_dir: Path) -> None:
    """Behaelt die neuesten KEEP_RELEASES Releases und nie das Ziel von ``live``."""
    releases = data_dir / "releases"
    live = data_dir / "live"
    current = os.readlink(live) if live.is_symlink() else None
    names = sorted((p.name for p in releases.iterdir() if p.is_dir()), reverse=True)
    for name in names[KEEP_RELEASES:]:
        if current == f"releases/{name}":
            continue
        shutil.rmtree(releases / name, ignore_errors=True)


def _release_fingerprint(data_dir: Path, target: Optional[str]) -> Optional[str]:
    """Fingerabdruck des Leafs in ``<data>/<target>/fullchain.pem``; unlesbar -> None."""
    if target is None:
        return None
    try:
        pem = (data_dir / target / "fullchain.pem").read_bytes()
        return _fingerprint(x509.load_pem_x509_certificates(pem)[0])
    except (OSError, ValueError, IndexError):
        return None


def _clean_stale_tmp(data_dir: Path) -> None:
    for p in data_dir.glob(".live.tmp.*"):
        try:
            p.unlink()
        except OSError:
            pass


def _await_served(
    domain: str, expected: str, served_fingerprint: Callable[[str], Optional[str]]
) -> bool:
    """Fragt ab, bis nginx ``expected`` ausliefert oder VERIFY_TIMEOUT verstrichen ist."""
    deadline = _monotonic() + VERIFY_TIMEOUT
    while True:
        if served_fingerprint(domain) == expected:
            return True
        remaining = deadline - _monotonic()
        if remaining <= 0:
            return False
        _sleep(min(VERIFY_INTERVAL, remaining))


def deploy(
    cert_path: Path,
    key_path: Path,
    domain: str,
    data_dir: Path,
    now: datetime,
    *,
    reload: Callable[[], None] = reload_nginx,
    served_fingerprint: Callable[[str], Optional[str]] = served_fingerprint,
) -> DeployOutcome:
    """Prueft, legt einen Release an, tauscht ``live``, laedt nginx neu und verifiziert.

    Vor dem Tausch wird gemessen, was nginx gerade ausliefert ("pre"). Verhalten:

    - Ungueltiges Zertifikat -> ``CertInvalid``, nichts wird angefasst.
    - Reload scheitert -> der Zustand von nginx ist unklar: gab es einen vorigen
      Release, wird ``live`` darauf zurueckgesetzt (erneuter Reload, neuer Release
      geloescht); sonst bleibt ``live`` auf dem neuen Release (nginx referenziert
      ihn noch nicht). In beiden Faellen ``DeployFailed`` mit dem Reload-Grund.
    - nginx lieferte vorher den vorigen Release des Plugins aus (pre == dessen
      Fingerabdruck) und liefert nach dem Reload auch nach VERIFY_TIMEOUT
      Sekunden Abfragen nicht den neuen -> Rueckabwicklung wie oben,
      ``DeployFailed`` ("served ..."). Abgefragt wird wiederholt, weil nginx'
      alte Worker nach dem Reload noch kurz das alte Zertifikat ausliefern.
    - Sonst (Erstinstallation, oder die nginx-Site zeigt noch nicht auf ``live``)
      bleiben neuer Release und ``live`` stehen; ``DeployOutcome.served`` sagt,
      ob nginx ihn bereits ausliefert.
    """
    now = _utc(now)
    try:
        cert_pem = Path(cert_path).read_bytes()
        key_pem = Path(key_path).read_bytes()
    except OSError:
        raise DeployFailed("certificate files not readable") from None
    info = inspect(cert_pem, key_pem, domain, now)

    name = now.strftime("%Y%m%dT%H%M%SZ")
    target = f"releases/{name}"
    release = data_dir / target
    live = data_dir / "live"

    try:
        for d in (data_dir, data_dir / "releases"):
            d.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(d, 0o700)
        _clean_stale_tmp(data_dir)
    except OSError:
        raise DeployFailed("data directory not writable") from None

    previous = os.readlink(live) if live.is_symlink() else None
    if previous == target or os.path.lexists(release):
        raise DeployFailed("release for this timestamp already exists")
    previous_fp = _release_fingerprint(data_dir, previous)
    pre = served_fingerprint(domain)
    was_serving_plugin = previous_fp is not None and pre == previous_fp

    try:
        release.mkdir(mode=0o700)
        os.chmod(release, 0o700)
        _write_private(release / "fullchain.pem", cert_pem)
        _write_private(release / "privkey.pem", key_pem)
        _point_live(data_dir, target)
    except OSError:
        if previous is not None and os.path.lexists(live) and os.readlink(live) != previous:
            try:
                _point_live(data_dir, previous)
            except OSError:
                pass
        _clean_stale_tmp(data_dir)
        shutil.rmtree(release, ignore_errors=True)
        raise DeployFailed("could not write release or switch live") from None

    def _roll_back(reason: str) -> DeployFailed:
        try:
            _point_live(data_dir, previous)
        except OSError:
            return DeployFailed(f"{reason}; rollback failed")
        try:
            reload()
        except DeployFailed as exc:
            reason = f"{reason}; rollback reload failed: {exc.reason}"
        shutil.rmtree(release, ignore_errors=True)
        _prune(data_dir)
        return DeployFailed(reason)

    try:
        reload()
    except DeployFailed as exc:
        if previous is not None:
            raise _roll_back(exc.reason) from None
        raise DeployFailed(exc.reason) from None

    served = _await_served(domain, info.fingerprint, served_fingerprint)
    if not served and was_serving_plugin:
        raise _roll_back("served certificate does not match new certificate")

    _prune(data_dir)
    return DeployOutcome(info=info, served=served)
