"""Ablaeufe des Plugins local_tls: Adress-Check, Zertifikats-Check, Status.

Die beiden Checks sind synchron (Datenbank, subprocess, HTTP) und liefern die
faelligen Benachrichtigungen als ``PendingEvent``-Liste zurueck, statt sie
selbst zu senden: gesendet wird asynchron (``deliver``), und zwar erst nach dem
Buchen -- wie beim Steam-Poller. So laufen die Checks in ``asyncio.to_thread``
und koennen trotzdem ``emit_plugin_event`` nutzen, das die Cooldowns aus den
``PluginEventSpec`` durchsetzt.

Beide Checks nehmen denselben Datei-Lock (``paths.lock``). Haelt ihn schon ein
anderer Lauf, ueberspringt der Hintergrundlauf (``raise_if_running=False``);
ein Knopfdruck uebergibt ``True`` und bekommt ``AlreadyRunning`` (-> 409).

Der Anbieter-Token erscheint nie in Rueckgaben, Gruenden oder Logs. Ein nicht
entschluesselbarer Token (Schluessel fehlt oder wurde getauscht) ist ein
gemeldeter Fehler, kein Absturz.
"""
import asyncio
import logging
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Iterator, Optional

from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.plugins.installed.local_tls import (
    address,
    deploy_cert,
    lego,
    paths,
    providers,
    state,
)
from app.plugins.installed.local_tls.config import LocalTlsConfig
from app.plugins.installed.local_tls.providers import ProviderError
from app.services.notifications.plugin_events import emit_plugin_event

logger = logging.getLogger(__name__)

PLUGIN_NAME = "local_tls"

EVENT_CERT_EXPIRING = "cert_expiring"
EVENT_RENEW_FAILED = "renew_failed"
EVENT_DNS_UPDATE_FAILED = "dns_update_failed"
EVENT_ADDRESS_CHANGED = "address_changed"

RECONFIRM_SECONDS = 86400
EXPIRY_WARNING = timedelta(days=21)

REASON_CREDENTIALS_UNREADABLE = (
    "credentials unreadable (encryption key missing or changed) - set the token again"
)
REASON_NOT_SERVED = "installiert, nginx liefert es noch nicht aus"
REASON_DATA_DIR = "data directory not writable"


def _unexpected(exc: BaseException) -> str:
    """Grund fuer eine unerwartete Exception: nur der Typ -- die Meldung
    koennte den Token enthalten."""
    return f"unexpected error ({type(exc).__name__})"


@dataclass(frozen=True)
class PendingEvent:
    """Eine faellige Benachrichtigung; ``entity_id`` ist die Domain (Cooldown-Schluessel)."""

    event_id: str
    entity_id: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Status:
    configured: bool
    lego: str  # "ok" | "missing" | "too_old"
    lego_version: Optional[str]
    current_ip: Optional[str]
    last_ip: Optional[str]
    last_ip_set_at: Optional[datetime]
    cert_not_after: Optional[datetime]
    cert_fingerprint: Optional[str]
    served_matches: Optional[bool]
    last_renew_at: Optional[datetime]
    last_renew_ok: Optional[bool]
    last_renew_reason: Optional[str]
    running: bool


class _CredentialsUnreadable(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Indirektionen, damit Tests das Warten auf den Lock ohne echte Pausen pruefen.
_sleep = time.sleep
_monotonic = time.monotonic
_LOCK_POLL_SECONDS = 2.0


@contextmanager
def _lock(data_dir: Path, wait: float) -> Iterator[None]:
    """``paths.lock`` mit optionalem Warten: nicht blockierende Versuche bis
    ``wait`` Sekunden, dazwischen kurze Pausen; danach ``AlreadyRunning``."""
    deadline = _monotonic() + wait
    with ExitStack() as stack:
        while True:
            try:
                stack.enter_context(paths.lock(data_dir))
                break
            except paths.AlreadyRunning:
                remaining = deadline - _monotonic()
                if remaining <= 0:
                    raise
                _sleep(min(_LOCK_POLL_SECONDS, remaining))
        yield


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite liefert naive Werte (gespeichert als UTC), PostgreSQL aware."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _data_dir(data_dir: Optional[Path]) -> Path:
    # Zur Laufzeit gelesen, damit Tests paths.DATA_DIR ersetzen koennen.
    return data_dir if data_dir is not None else paths.DATA_DIR


def _is_configured(db: Session, config: LocalTlsConfig) -> bool:
    return bool(config.domain) and state.has_token(db)


def _credentials(db: Session, provider: providers.DnsProvider) -> dict[str, str]:
    """Anbieter-Zugangsdaten; v1: der eine geheime Wert ist der gespeicherte Token."""
    try:
        token = state.get_token(db)
    except (InvalidToken, ValueError, TypeError):
        # Keine Ursache weiterreichen -- sie kann Schluesselmaterial beruehren.
        raise _CredentialsUnreadable() from None
    if not token:
        raise _CredentialsUnreadable()
    return {f.name: token for f in provider.credential_fields if f.secret}


def _version_str(v: tuple[int, int, int]) -> str:
    return ".".join(str(p) for p in v)


# --- Adress-Check ---------------------------------------------------------

def run_address_check(
    db: Session,
    config: LocalTlsConfig,
    now: datetime,
    *,
    force: bool = False,
    raise_if_running: bool = False,
    data_dir: Optional[Path] = None,
) -> list[PendingEvent]:
    """Setzt den DNS-Eintrag auf die LAN-IP, wenn sie sich geaendert hat,
    ``force`` gesetzt ist oder das letzte Setzen einen Tag zurueckliegt."""
    if not _is_configured(db, config):
        return []
    domain = config.domain
    now = _as_utc(now)

    def failed(reason: str) -> list[PendingEvent]:
        return [PendingEvent(EVENT_DNS_UPDATE_FAILED, domain, {"domain": domain, "reason": reason})]

    try:
        ip = address.current_lan_ip(config.interface)
    except address.AddressError as exc:
        return failed(str(exc))

    row = state.get_state(db)
    previous = row.last_ip
    set_at = _as_utc(row.last_ip_set_at)
    due = (
        force
        or ip != previous
        or set_at is None
        or (now - set_at).total_seconds() >= RECONFIRM_SECONDS
    )
    if not due:
        return []

    provider = providers.get_provider(config.provider)
    try:
        credentials = _credentials(db, provider)
    except _CredentialsUnreadable:
        return failed(REASON_CREDENTIALS_UNREADABLE)

    directory = _data_dir(data_dir)
    try:
        paths.ensure_dirs(directory)
    except OSError:
        return failed(REASON_DATA_DIR)

    try:
        with paths.lock(directory):
            provider.update_address(domain, ip, credentials)
    except paths.AlreadyRunning:
        if raise_if_running:
            raise
        logger.info("local_tls: address check skipped, another run holds the lock")
        return []
    except ProviderError as exc:
        return failed(str(exc))
    except Exception as exc:  # noqa: BLE001 - als DNS-Fehler buchen statt abbrechen
        return failed(_unexpected(exc))

    state.record_ip(db, ip, now)
    if previous is not None and previous != ip:
        return [PendingEvent(EVENT_ADDRESS_CHANGED, domain, {"domain": domain, "ip": ip})]
    return []


# --- Zertifikats-Check ----------------------------------------------------

def run_cert_check(
    db: Session,
    config: LocalTlsConfig,
    now: datetime,
    *,
    force: bool = False,
    raise_if_running: bool = False,
    data_dir: Optional[Path] = None,
    lock_wait: float = 0,
) -> list[PendingEvent]:
    """Stellt aus bzw. erneuert ueber lego, installiert ein neues Zertifikat und
    warnt, wenn das installierte in hoechstens 21 Tagen ablaeuft.

    ``lock_wait``: so lange wird auf einen fremden Lauf gewartet (der
    Hintergrundlauf beim Start nutzt 60 s, weil der Adress-Check gleichzeitig
    startet und der Zertifikats-Check sonst einen ganzen Tag ausfiele). Die
    Ablaufwarnung wird auch bei uebersprungenem Lauf geprueft.
    """
    if not _is_configured(db, config):
        return []
    domain = config.domain
    now = _as_utc(now)
    events: list[PendingEvent] = []

    def fail(reason: str) -> None:
        row = state.get_state(db)
        # Das installierte Zertifikat bleibt das bisherige.
        state.record_renew(
            db, False, reason, row.cert_fingerprint, _as_utc(row.cert_not_after), now
        )
        events.append(
            PendingEvent(EVENT_RENEW_FAILED, domain, {"domain": domain, "reason": reason})
        )

    try:
        _renew(
            db, config, now,
            force=force, data_dir=_data_dir(data_dir), lock_wait=lock_wait, fail=fail,
        )
    except paths.AlreadyRunning:
        if raise_if_running:
            raise
        logger.info("local_tls: certificate check skipped, another run holds the lock")
    except Exception as exc:  # noqa: BLE001 - buchen, melden, Ablauf trotzdem pruefen
        logger.error("local_tls: certificate check failed with %s", type(exc).__name__)
        fail(_unexpected(exc))

    not_after = _as_utc(state.get_state(db).cert_not_after)
    if not_after is not None and not_after - now <= EXPIRY_WARNING:
        days = max(0, (not_after - now).days)
        events.append(
            PendingEvent(EVENT_CERT_EXPIRING, domain, {"domain": domain, "days": days})
        )
    return events


def _renew(
    db: Session,
    config: LocalTlsConfig,
    now: datetime,
    *,
    force: bool,
    data_dir: Path,
    lock_wait: float,
    fail: Callable[[str], None],
) -> None:
    domain = config.domain
    try:
        v = lego.version()
    except lego.LegoError as exc:  # LegoMissing eingeschlossen
        return fail(str(exc))
    if v < lego.MIN_VERSION:
        return fail(
            f"lego too old ({_version_str(v)} < {_version_str(lego.MIN_VERSION)})"
        )

    provider = providers.get_provider(config.provider)
    try:
        credentials = _credentials(db, provider)
    except _CredentialsUnreadable:
        return fail(REASON_CREDENTIALS_UNREADABLE)

    try:
        paths.ensure_dirs(data_dir)
    except OSError:
        return fail(REASON_DATA_DIR)

    with _lock(data_dir, lock_wait):  # AlreadyRunning geht an den Aufrufer
        try:
            created = lego.obtain_or_renew(
                domain,
                provider.lego_provider,
                provider.lego_env(credentials),
                data_dir,
                email=config.email,
                staging=config.staging,
            )
        except lego.LegoError as exc:
            return fail(str(exc))

        cert_path, key_path = lego.cert_paths(domain, data_dir, staging=config.staging)
        row = state.get_state(db)
        # Nicht nur bei neuem Zertifikat uebernehmen: ist ein frueherer Deploy
        # gescheitert (oder liegt nach einem Wechsel Staging/Produktion ein
        # anderes Zertifikat in lego), meldet ``renew`` nichts Neues, das
        # installierte ist aber ein anderes. Unbestimmbar (None) -> uebernehmen;
        # deploy() meldet dann den eigentlichen Grund.
        if not (created or force):
            leaf = _leaf_fingerprint(cert_path, key_path, domain, now)
            if leaf is not None and leaf == row.cert_fingerprint:
                state.record_renew(
                    db, True, None, row.cert_fingerprint, _as_utc(row.cert_not_after), now
                )
                return None

        try:
            outcome = deploy_cert.deploy(cert_path, key_path, domain, data_dir, now)
        except deploy_cert.DeployFailed as exc:
            return fail(exc.reason)
        except deploy_cert.CertInvalid as exc:
            return fail(str(exc))
        except OSError:
            return fail("certificate could not be installed (file error)")

    reason = None if outcome.served else REASON_NOT_SERVED
    state.record_renew(
        db, True, reason, outcome.info.fingerprint, outcome.info.not_after, now
    )
    return None


def _leaf_fingerprint(cert_path: Path, key_path: Path, domain: str, now: datetime) -> Optional[str]:
    """DER-Leaf-Fingerabdruck von lego's Zertifikat, vergleichbar mit
    ``cert_fingerprint`` (``lego._fingerprint`` hasht PEM-Bytes und ist es nicht)."""
    try:
        info = deploy_cert.inspect(
            Path(cert_path).read_bytes(), Path(key_path).read_bytes(), domain, now
        )
    except (OSError, deploy_cert.CertInvalid):
        return None
    return info.fingerprint


# --- Zustellung und Hintergrundlauf ---------------------------------------

async def deliver(
    events: Iterable[PendingEvent],
    *,
    emit: Callable[..., Awaitable[None]] = emit_plugin_event,
) -> None:
    """Sendet die Benachrichtigungen; Cooldowns setzt ``emit_plugin_event`` durch."""
    for event in events:
        await emit(PLUGIN_NAME, event.event_id, entity_id=event.entity_id, **event.kwargs)


async def run_check(
    check: Callable[..., list[PendingEvent]],
    load_config: Callable[[Session], LocalTlsConfig],
    *,
    force: bool = False,
    raise_if_running: bool = False,
    session_factory: Callable[[], Session] = SessionLocal,
    emit: Callable[..., Awaitable[None]] = emit_plugin_event,
    clock: Callable[[], datetime] = _utc_now,
    **check_kwargs: Any,
) -> list[PendingEvent]:
    """Fuehrt einen Check in einem Thread mit eigener DB-Session aus und sendet danach.

    Ausser ``AlreadyRunning`` bei ``raise_if_running=True`` wird nichts
    weitergereicht: jede andere Exception wird geloggt -- nur mit ihrem Typ,
    weil die Meldung einer unerwarteten Exception den Token enthalten koennte.
    """
    def _work() -> list[PendingEvent]:
        db = session_factory()
        try:
            config = load_config(db)
            return check(
                db, config, clock(),
                force=force, raise_if_running=raise_if_running, **check_kwargs,
            )
        finally:
            db.close()

    try:
        events = await asyncio.to_thread(_work)
    except paths.AlreadyRunning:
        if raise_if_running:
            raise
        return []
    except Exception as exc:  # noqa: BLE001 - ein Hintergrundlauf darf nie abbrechen
        logger.error(
            "local_tls: %s failed with %s",
            getattr(check, "__name__", "check"), type(exc).__name__,
        )
        return []

    try:
        await deliver(events, emit=emit)
    except Exception as exc:  # noqa: BLE001
        logger.error("local_tls: delivering notifications failed with %s", type(exc).__name__)
    return events


# --- Status ---------------------------------------------------------------

def _is_running(data_dir: Path) -> bool:
    if not (data_dir / ".lock").exists():
        return False
    try:
        with paths.lock(data_dir):
            return False
    except paths.AlreadyRunning:
        return True
    except OSError:
        return False


def get_status(
    db: Session,
    config: LocalTlsConfig,
    now: datetime,
    *,
    data_dir: Optional[Path] = None,
) -> Status:
    """Momentaufnahme fuer die Statuskarte; nie mit Token."""
    try:
        v = lego.version()
        lego_state = "ok" if v >= lego.MIN_VERSION else "too_old"
        lego_version: Optional[str] = _version_str(v)
    except lego.LegoError:
        lego_state, lego_version = "missing", None

    try:
        current_ip: Optional[str] = address.current_lan_ip(config.interface)
    except address.AddressError:
        current_ip = None

    row = state.get_state(db)
    configured = _is_configured(db, config)

    served_matches: Optional[bool] = None
    if configured and row.cert_fingerprint:
        served = deploy_cert.served_fingerprint(config.domain)
        if served is not None:
            served_matches = served == row.cert_fingerprint

    return Status(
        configured=configured,
        lego=lego_state,
        lego_version=lego_version,
        current_ip=current_ip,
        last_ip=row.last_ip,
        last_ip_set_at=_as_utc(row.last_ip_set_at),
        cert_not_after=_as_utc(row.cert_not_after),
        cert_fingerprint=row.cert_fingerprint,
        served_matches=served_matches,
        last_renew_at=_as_utc(row.last_renew_at),
        last_renew_ok=row.last_renew_ok,
        last_renew_reason=row.last_renew_reason,
        running=_is_running(_data_dir(data_dir)),
    )
