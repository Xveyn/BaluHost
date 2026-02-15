"""
Samba (SMB/CIFS) integration service for BaluHost.

Manages Samba user passwords (password-sync with BaluHost credentials),
per-user share configuration, and runtime status queries.

In dev mode all system commands are no-ops.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

SAMBA_SHARES_CONF = "/etc/samba/baluhost-shares.conf"


def _get_shares_conf_path() -> str:
    """Return the path used for the generated shares config file."""
    return getattr(settings, "samba_shares_conf_path", SAMBA_SHARES_CONF)


async def _run_cmd(cmd: list[str], stdin_data: Optional[str] = None) -> tuple[int, str, str]:
    """Run a system command asynchronously, returning (returncode, stdout, stderr).

    Uses asyncio.create_subprocess_exec (no shell) to avoid injection risks.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(
        input=stdin_data.encode() if stdin_data else None
    )
    return proc.returncode, stdout_bytes.decode(errors="replace"), stderr_bytes.decode(errors="replace")


# ──────────────────────────────────────────────────────────────
# User / password management
# ──────────────────────────────────────────────────────────────

async def _ensure_system_user(username: str) -> None:
    """Create a Linux system user (nologin) if it doesn't exist.

    The user is added to the same group as the BaluHost service user
    so Samba can access files owned by that group.
    """
    if settings.is_dev_mode:
        logger.info("[DEV] Mock _ensure_system_user('%s')", username)
        return

    # Check if user already exists
    rc, _, _ = await _run_cmd(["id", username])
    if rc == 0:
        return  # already exists

    service_user = os.getenv("USER", "sven")
    rc, stdout, stderr = await _run_cmd([
        "sudo", "useradd",
        "--system",
        "--no-create-home",
        "--shell", "/usr/sbin/nologin",
        "--group", service_user,
        username,
    ])
    if rc != 0:
        logger.error("useradd failed for '%s': %s", username, stderr)
    else:
        logger.info("Created system user '%s'", username)


async def sync_smb_password(username: str, plaintext_password: str) -> bool:
    """Set or update the Samba password for a user (password-sync).

    This creates the Samba account if it doesn't exist yet (smbpasswd -a).
    """
    if settings.is_dev_mode:
        logger.info("[DEV] Mock sync_smb_password('%s')", username)
        return True

    await _ensure_system_user(username)

    # smbpasswd -a -s reads new password twice from stdin
    stdin_data = f"{plaintext_password}\n{plaintext_password}\n"
    rc, stdout, stderr = await _run_cmd(
        ["sudo", "smbpasswd", "-a", "-s", username],
        stdin_data=stdin_data,
    )
    if rc != 0:
        logger.error("smbpasswd -a failed for '%s': %s", username, stderr)
        return False

    logger.info("Samba password synced for user '%s'", username)
    return True


async def remove_smb_user(username: str) -> bool:
    """Remove a user from the Samba password database."""
    if settings.is_dev_mode:
        logger.info("[DEV] Mock remove_smb_user('%s')", username)
        return True

    rc, _, stderr = await _run_cmd(["sudo", "smbpasswd", "-x", username])
    if rc != 0:
        logger.error("smbpasswd -x failed for '%s': %s", username, stderr)
        return False

    logger.info("Removed Samba user '%s'", username)
    return True


async def enable_smb_user(username: str) -> bool:
    """Enable a Samba user account."""
    if settings.is_dev_mode:
        logger.info("[DEV] Mock enable_smb_user('%s')", username)
        return True

    rc, _, stderr = await _run_cmd(["sudo", "smbpasswd", "-e", username])
    if rc != 0:
        logger.error("smbpasswd -e failed for '%s': %s", username, stderr)
        return False

    logger.info("Enabled Samba user '%s'", username)
    return True


async def disable_smb_user(username: str) -> bool:
    """Disable a Samba user account."""
    if settings.is_dev_mode:
        logger.info("[DEV] Mock disable_smb_user('%s')", username)
        return True

    rc, _, stderr = await _run_cmd(["sudo", "smbpasswd", "-d", username])
    if rc != 0:
        logger.error("smbpasswd -d failed for '%s': %s", username, stderr)
        return False

    logger.info("Disabled Samba user '%s'", username)
    return True


# ──────────────────────────────────────────────────────────────
# Share config generation
# ──────────────────────────────────────────────────────────────

async def regenerate_shares_config() -> bool:
    """Generate the Samba shares config from the database.

    Admin users get a share exposing the entire RAID mount.
    Regular users get a share scoped to their home directory.
    """
    if settings.is_dev_mode:
        logger.info("[DEV] Mock regenerate_shares_config()")
        return True

    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(User.smb_enabled == True, User.is_active == True)  # noqa: E712
            .all()
        )
    finally:
        db.close()

    storage_root = Path(settings.nas_storage_path).expanduser().resolve()
    service_user = os.getenv("USER", "sven")

    lines: list[str] = [
        "# Auto-generated by BaluHost — do not edit manually",
        "",
    ]

    admin_share_written = False
    for user in users:
        if user.role == "admin":
            if not admin_share_written:
                lines.extend([
                    "[BaluHost]",
                    f"   path = {storage_root}",
                    f"   valid users = {' '.join(u.username for u in users if u.role == 'admin')}",
                    "   read only = no",
                    "   browseable = yes",
                    f"   force user = {service_user}",
                    f"   force group = {service_user}",
                    "   create mask = 0664",
                    "   directory mask = 0775",
                    "   strict locking = auto",
                    "",
                ])
                admin_share_written = True
        else:
            user_path = storage_root / user.username
            lines.extend([
                f"[BaluHost-{user.username}]",
                f"   path = {user_path}",
                f"   valid users = {user.username}",
                "   read only = no",
                "   browseable = yes",
                f"   force user = {service_user}",
                f"   force group = {service_user}",
                "   create mask = 0664",
                "   directory mask = 0775",
                "   strict locking = auto",
                "",
            ])

    conf_path = _get_shares_conf_path()
    content = "\n".join(lines)

    # Atomic write via temp file + rename
    try:
        dir_path = os.path.dirname(conf_path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".baluhost-shares-", suffix=".conf")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp_path, conf_path)
        logger.info("Regenerated Samba shares config (%d users)", len(users))
        return True
    except OSError as exc:
        logger.error("Failed to write shares config: %s", exc)
        return False


# ──────────────────────────────────────────────────────────────
# Samba control
# ──────────────────────────────────────────────────────────────

async def reload_samba() -> bool:
    """Reload the smbd configuration without restarting the service."""
    if settings.is_dev_mode:
        logger.info("[DEV] Mock reload_samba()")
        return True

    rc, _, stderr = await _run_cmd(["sudo", "smbcontrol", "smbd", "reload-config"])
    if rc != 0:
        logger.error("smbcontrol reload-config failed: %s", stderr)
        return False

    logger.info("Samba config reloaded")
    return True


# ──────────────────────────────────────────────────────────────
# Status queries
# ──────────────────────────────────────────────────────────────

async def get_samba_status() -> dict:
    """Query Samba runtime status.

    Returns dict with keys: is_running, version, active_connections, smb_users_count.
    """
    if settings.is_dev_mode:
        # Count SMB-enabled users from DB
        db = SessionLocal()
        try:
            count = db.query(User).filter(User.smb_enabled == True, User.is_active == True).count()  # noqa: E712
        finally:
            db.close()

        return {
            "is_running": False,
            "version": "dev-mode",
            "active_connections": [],
            "smb_users_count": count,
        }

    # Check if smbd is running
    rc, _, _ = await _run_cmd(["pgrep", "smbd"])
    is_running = rc == 0

    # Get version
    version = None
    if is_running:
        rc, stdout, _ = await _run_cmd(["smbd", "--version"])
        if rc == 0:
            version = stdout.strip()

    # Get active connections
    active_connections: list[dict] = []
    if is_running:
        rc, stdout, _ = await _run_cmd(["sudo", "smbstatus", "--brief", "--numeric"])
        if rc == 0:
            # Parse smbstatus output — skip header lines
            for line in stdout.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("-") or line.startswith("Service") or line.startswith("PID") or line.startswith("Samba version"):
                    continue
                # smbstatus --brief format: PID  Username  Group  Machine  Protocol
                parts = line.split()
                if len(parts) >= 4 and parts[0].isdigit():
                    active_connections.append({
                        "pid": parts[0],
                        "username": parts[1],
                        "machine": parts[3],
                    })

    # Count SMB-enabled users
    db = SessionLocal()
    try:
        smb_users_count = db.query(User).filter(User.smb_enabled == True, User.is_active == True).count()  # noqa: E712
    finally:
        db.close()

    return {
        "is_running": is_running,
        "version": version,
        "active_connections": active_connections,
        "smb_users_count": smb_users_count,
    }
