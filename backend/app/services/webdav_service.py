"""
WebDAV Worker Service for BaluHost.

Runs a cheroot WSGI server hosting the WsgiDAV application in a separate
process, analogous to how scheduler_worker_service.py runs APScheduler jobs.

IPC with the web process is done via the database:
- Worker writes webdav_state row → Web API reads it for status
- Heartbeat updated every 10s so the web process can detect staleness
"""

import datetime
import ipaddress
import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Optional

from cheroot import wsgi

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.webdav_state import WebdavState

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 10  # seconds


def get_local_ip() -> str:
    """Detect the primary local IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _ensure_ssl_cert(local_ip: str) -> tuple[Path, Path]:
    """Generate a self-signed certificate if it doesn't exist yet.

    The cert includes the server's LAN IP as a SAN so Windows WebClient
    accepts it when connecting via IP address.
    """
    cert_dir = Path(__file__).parent.parent.parent / "webdav-certs"
    cert_file = cert_dir / "webdav.crt"
    key_file = cert_dir / "webdav.key"

    if cert_file.exists() and key_file.exists():
        logger.info("Reusing existing SSL certificate: %s", cert_file)
        return cert_file, key_file

    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    logger.info("Generating self-signed SSL certificate for %s ...", local_ip)
    cert_dir.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"BaluHost WebDAV ({local_ip})"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BaluHost"),
    ])

    san_entries = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    try:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(local_ip)))
    except ValueError:
        pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
        )
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_file.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    logger.info("SSL certificate written to %s", cert_dir)
    return cert_file, key_file


class WebdavWorker:
    """Manages the cheroot WSGI server hosting the WsgiDAV application."""

    def __init__(self):
        self.running = False
        self.pid = os.getpid()
        self._server: Optional[wsgi.Server] = None
        self._server_thread: Optional[threading.Thread] = None
        self._last_heartbeat = 0.0

    def start(self) -> None:
        """Create and start the cheroot WSGI server in a daemon thread."""
        port = settings.webdav_port
        ssl_enabled = settings.webdav_ssl_enabled
        local_ip = get_local_ip()

        logger.info(
            "WebDAV worker starting (PID=%d, port=%d, ssl=%s)",
            self.pid, port, ssl_enabled,
        )

        # Create the WsgiDAV application
        from app.compat.webdav_asgi import create_webdav_standalone_app
        app = create_webdav_standalone_app()

        # Create cheroot server
        self._server = wsgi.Server(
            bind_addr=("0.0.0.0", port),
            wsgi_app=app,
        )

        # Optionally enable SSL
        if ssl_enabled:
            cert_path, key_path = _ensure_ssl_cert(local_ip)
            from cheroot.ssl.builtin import BuiltinSSLAdapter
            self._server.ssl_adapter = BuiltinSSLAdapter(
                certificate=str(cert_path),
                private_key=str(key_path),
            )

        # Start server in a daemon thread (server.start() blocks)
        self._server_thread = threading.Thread(
            target=self._run_server, daemon=True, name="cheroot-webdav"
        )
        self._server_thread.start()
        self.running = True

        # Write initial state
        self._update_state(is_running=True, error_message=None)

        scheme = "https" if ssl_enabled else "http"
        logger.info(
            "WebDAV server started: %s://%s:%d/  (storage: %s)",
            scheme, local_ip, port, settings.nas_storage_path,
        )

    def _run_server(self) -> None:
        """Run the cheroot server (blocks until stopped)."""
        try:
            self._server.start()
        except Exception as e:
            logger.exception("cheroot server crashed")
            self._update_state(is_running=False, error_message=str(e))
            self.running = False

    def run_loop(self) -> None:
        """Main heartbeat loop — runs until self.running is False."""
        while self.running:
            now = time.monotonic()

            if now - self._last_heartbeat >= HEARTBEAT_INTERVAL:
                try:
                    self._update_heartbeat()
                except Exception:
                    logger.exception("Error updating heartbeat")
                self._last_heartbeat = now

            time.sleep(2)

    def shutdown(self) -> None:
        """Stop the cheroot server and clear DB state."""
        logger.info("WebDAV worker shutting down...")
        self.running = False

        if self._server:
            try:
                self._server.stop()
            except Exception:
                logger.debug("Error stopping cheroot server")

        self._clear_state()
        logger.info("WebDAV worker shutdown complete")

    # ─── State Management ─────────────────────────────────────────

    def _update_state(
        self,
        is_running: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Write or update the single webdav_state row."""
        db = SessionLocal()
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            state = db.query(WebdavState).first()

            if state is None:
                state = WebdavState(
                    is_running=is_running,
                    port=settings.webdav_port,
                    ssl_enabled=settings.webdav_ssl_enabled,
                    last_heartbeat=now,
                    worker_pid=self.pid,
                    started_at=now if is_running else None,
                    error_message=error_message,
                )
                db.add(state)
            else:
                state.is_running = is_running
                state.port = settings.webdav_port
                state.ssl_enabled = settings.webdav_ssl_enabled
                state.last_heartbeat = now
                state.worker_pid = self.pid
                if is_running and not state.started_at:
                    state.started_at = now
                state.error_message = error_message

            db.commit()
        finally:
            db.close()

    def _update_heartbeat(self) -> None:
        """Update the heartbeat timestamp."""
        db = SessionLocal()
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            state = db.query(WebdavState).first()
            if state:
                state.last_heartbeat = now
                state.worker_pid = self.pid
                state.is_running = True
                db.commit()
            else:
                # State row doesn't exist yet — create it
                self._update_state(is_running=True)
        finally:
            db.close()

    def _clear_state(self) -> None:
        """Mark state as stopped on shutdown."""
        db = SessionLocal()
        try:
            state = db.query(WebdavState).first()
            if state:
                state.is_running = False
                state.last_heartbeat = None
                state.worker_pid = None
                state.started_at = None
                state.error_message = None
                db.commit()
        finally:
            db.close()
