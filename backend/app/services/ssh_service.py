"""SSH Service for remote server connectivity.

Host-key handling uses Trust-On-First-Use (TOFU): the first connection to a
host pins its key into a BaluHost-managed ``known_hosts`` file; every later
connection verifies against it with ``RejectPolicy`` (genuine MITM protection,
no blind ``AutoAddPolicy``).

The managed file lives under the storage tree's ``.system`` directory by
default. That location is writable by the service user and persists across
production deploys (the deploy hard-resets tracked files but never git-cleans
untracked files under the storage tree). Override via ``SSH_KNOWN_HOSTS_PATH``.
"""

import io
import logging
import os
import socket
from pathlib import Path
from typing import Optional, Tuple

import paramiko
from paramiko.ssh_exception import (
    AuthenticationException,
    BadHostKeyException,
    NoValidConnectionsError,
    SSHException,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


def _known_hosts_path() -> Path:
    """Resolve the managed known_hosts file path (configurable)."""
    configured = (getattr(settings, "ssh_known_hosts_path", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    base = Path(settings.nas_storage_path).expanduser()
    return base / ".system" / "ssh" / "known_hosts"


def _hostkey_entry(host: str, port: int) -> str:
    """known_hosts entry name. Paramiko uses ``[host]:port`` for non-22 ports."""
    return host if port == 22 else f"[{host}]:{port}"


def _ensure_host_pinned(host: str, port: int) -> None:
    """Trust-On-First-Use: pin the host's key on first contact.

    If the host is already present in the managed known_hosts file, do nothing
    (the subsequent RejectPolicy connect verifies it). Otherwise fetch the
    server's host key once and append it.

    Appending (not rewriting) keeps this safe across the 4 Uvicorn workers:
    a concurrent first-connect at worst writes a duplicate line, which paramiko
    tolerates — it never clobbers another host's entry.
    """
    kh_path = _known_hosts_path()
    entry = _hostkey_entry(host, port)

    existing = paramiko.HostKeys()
    if kh_path.exists():
        try:
            existing.load(str(kh_path))
        except Exception:
            logger.warning(
                "Could not parse managed known_hosts at %s; treating as empty",
                kh_path,
            )
    if existing.lookup(entry):
        return  # already pinned

    # First contact: fetch and pin the remote host key.
    transport = paramiko.Transport((host, port))
    try:
        transport.start_client(timeout=SSHService.SSH_TIMEOUT)
        remote_key = transport.get_remote_server_key()
    finally:
        transport.close()

    kh_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{entry} {remote_key.get_name()} {remote_key.get_base64()}\n"
    with open(kh_path, "a", encoding="utf-8") as fh:
        fh.write(line)
    try:
        os.chmod(kh_path, 0o600)
    except (OSError, NotImplementedError):
        pass  # best-effort (e.g. Windows dev)
    logger.info(
        "Pinned SSH host key for %s (%s) to managed known_hosts", entry, remote_key.get_name()
    )


def _connect(
    host: str, port: int, username: str, private_key: paramiko.PKey
) -> paramiko.SSHClient:
    """Open a verified SSH connection (TOFU pin + RejectPolicy)."""
    _ensure_host_pinned(host, port)

    client = paramiko.SSHClient()
    kh_path = _known_hosts_path()
    if kh_path.exists():
        client.load_host_keys(str(kh_path))
    # Reject unknown / changed host keys — no AutoAddPolicy.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        host,
        port=port,
        username=username,
        pkey=private_key,
        timeout=SSHService.SSH_TIMEOUT,
        banner_timeout=SSHService.SSH_BANNER_TIMEOUT,
    )
    return client


def _load_private_key(private_key_str: str) -> paramiko.RSAKey:
    """Parse an RSA private key from a file path or an inline PEM string."""
    try:
        return paramiko.RSAKey.from_private_key_file(private_key_str, password=None)
    except (TypeError, AttributeError, FileNotFoundError, OSError):
        return paramiko.RSAKey.from_private_key(io.StringIO(private_key_str))


class SSHService:
    """Service for SSH operations on remote servers."""

    SSH_TIMEOUT = 10  # seconds
    SSH_BANNER_TIMEOUT = 10

    @staticmethod
    def test_connection(
        host: str,
        port: int,
        username: str,
        private_key_str: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Test SSH connection to a remote server.

        Args:
            host: SSH hostname or IP
            port: SSH port
            username: SSH username
            private_key_str: Private key as string

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            private_key = _load_private_key(private_key_str)
            client = _connect(host, port, username, private_key)
            client.close()
            return True, None

        except AuthenticationException:
            logger.warning(f"SSH authentication failed for {username}@{host}:{port}")
            return False, "SSH authentication failed - check credentials"
        except BadHostKeyException:
            logger.error(f"SSH host key mismatch for {host}:{port} (possible MITM)")
            return False, (
                "SSH host key does not match the pinned key - connection refused. "
                "If the server was reinstalled, remove its entry from the managed "
                "known_hosts file and retry."
            )
        except NoValidConnectionsError:
            logger.warning(f"SSH connection refused for {host}:{port}")
            return False, "SSH connection refused - check host and port"
        except socket.timeout:
            logger.warning(f"SSH connection timeout for {host}:{port}")
            return False, "SSH connection timeout - check host availability"
        except SSHException as e:
            logger.error(f"SSH error: {str(e)}")
            return False, f"SSH error: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error during SSH test: {str(e)}")
            return False, f"Unexpected error: {str(e)}"

    @staticmethod
    def execute_command(
        host: str,
        port: int,
        username: str,
        private_key_str: str,
        command: str,
    ) -> Tuple[bool, str]:
        """
        Execute a command on remote server via SSH.

        Args:
            host: SSH hostname or IP
            port: SSH port
            username: SSH username
            private_key_str: Private key as string
            command: Command to execute

        Returns:
            Tuple of (success: bool, output: str)
        """
        try:
            private_key = _load_private_key(private_key_str)
            client = _connect(host, port, username, private_key)

            # Execute command
            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            output = stdout.read().decode("utf-8")
            error = stderr.read().decode("utf-8")

            client.close()

            if error:
                logger.warning(f"Command error on {host}: {error}")
                return False, error

            return True, output

        except BadHostKeyException:
            logger.error(f"SSH host key mismatch for {host}:{port} (possible MITM)")
            return False, "SSH host key does not match the pinned key - connection refused"
        except Exception as e:
            logger.error(f"Error executing command on {host}: {str(e)}")
            return False, str(e)

    @staticmethod
    def start_server(
        host: str,
        port: int,
        username: str,
        private_key_str: str,
        power_on_command: str,
    ) -> Tuple[bool, str]:
        """
        Start a remote BaluHost server via SSH.

        Args:
            host: SSH hostname or IP
            port: SSH port
            username: SSH username
            private_key_str: Private key as string
            power_on_command: Command to start the server

        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Starting remote server at {username}@{host}:{port}")

        # First test connection
        connected, error = SSHService.test_connection(host, port, username, private_key_str)
        if not connected:
            return False, f"Cannot connect to server: {error}"

        # Execute startup command
        if not power_on_command:
            return False, "No power on command configured"

        success, output = SSHService.execute_command(
            host, port, username, private_key_str, power_on_command
        )

        if success:
            logger.info(f"Server startup command sent to {host}")
            return True, "Server startup command sent successfully"
        else:
            logger.error(f"Failed to execute startup command: {output}")
            return False, f"Startup command failed: {output}"
