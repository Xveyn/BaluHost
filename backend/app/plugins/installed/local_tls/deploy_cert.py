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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization

RELOAD_ARGS = ["sudo", "-n", "/usr/bin/systemctl", "reload", "nginx"]
RELOAD_TIMEOUT = 30
HANDSHAKE_TIMEOUT = 5
KEEP_RELEASES = 3


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


def _fingerprint(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _public_bytes(public_key) -> bytes:
    return public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def inspect(cert_pem: bytes, key_pem: bytes, domain: str, now: datetime) -> CertInfo:
    """Prueft PEM, Schluesselpaar, SAN, Gueltigkeit und Kettenreihenfolge."""
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

    # Kette vollstaendig und in Reihenfolge: jedes Glied vom naechsten ausgestellt.
    for child, parent in zip(chain, chain[1:]):
        if child.issuer != parent.subject:
            raise CertInvalid("certificate chain is incomplete or out of order")

    return CertInfo(fingerprint=_fingerprint(leaf), not_after=leaf.not_valid_after_utc, sans=sans)


def reload_nginx(*, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> None:
    """Laedt nginx ueber die bestehende sudoers-Regel neu (ohne Passwortabfrage)."""
    try:
        result = run(RELOAD_ARGS, capture_output=True, text=True, timeout=RELOAD_TIMEOUT)
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


def deploy(
    cert_path: Path,
    key_path: Path,
    domain: str,
    data_dir: Path,
    now: datetime,
    *,
    reload: Callable[[], None] = reload_nginx,
    served_fingerprint: Callable[[str], Optional[str]] = served_fingerprint,
) -> CertInfo:
    """Prueft, legt einen Release an, tauscht ``live``, laedt nginx neu und verifiziert.

    Bei Reload-Fehler oder abweichendem ausgeliefertem Zertifikat wird ``live``
    auf die vorige Version zurueckgesetzt und nginx erneut geladen; ohne vorige
    Version wird ``live`` entfernt. In beiden Faellen: ``DeployFailed``.
    """
    cert_pem = Path(cert_path).read_bytes()
    key_pem = Path(key_path).read_bytes()
    info = inspect(cert_pem, key_pem, domain, now)

    for d in (data_dir, data_dir / "releases"):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(d, 0o700)

    name = now.strftime("%Y%m%dT%H%M%SZ")
    target = f"releases/{name}"
    release = data_dir / target
    live = data_dir / "live"
    previous = os.readlink(live) if live.is_symlink() else None
    if previous == target or os.path.lexists(release):
        raise DeployFailed("release for this timestamp already exists")

    release.mkdir(mode=0o700)
    os.chmod(release, 0o700)
    _write_private(release / "fullchain.pem", cert_pem)
    _write_private(release / "privkey.pem", key_pem)

    _point_live(data_dir, target)

    reason: Optional[str] = None
    try:
        reload()
    except DeployFailed as exc:
        reason = exc.reason
    else:
        served = served_fingerprint(domain)
        if served != info.fingerprint:
            reason = "served certificate does not match new certificate"

    if reason is None:
        _prune(data_dir)
        return info

    # Rueckabwicklung
    if previous is not None:
        _point_live(data_dir, previous)
        try:
            reload()
        except DeployFailed as exc:
            reason = f"{reason}; rollback reload failed: {exc.reason}"
    else:
        if os.path.lexists(live):
            live.unlink()
        reason = f"{reason}; no previous release to roll back to"
    shutil.rmtree(release, ignore_errors=True)
    _prune(data_dir)
    raise DeployFailed(reason)
