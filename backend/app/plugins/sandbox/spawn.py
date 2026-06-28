"""Production spawn hook for external plugin workers (Track B, Phase 5a).

Replaces the plain ``_default_spawn`` for external plugins on a provisioned
production Linux box: the worker runs as the unprivileged ``baluhost-plugin``
user, in its own network namespace, under resource limits, with a scrubbed
environment. Selection is automatic; an unprovisioned prod box fails closed
(``select_spawn_hook`` returns ``None``).
"""
import asyncio
import os
import sys
from typing import Optional

from app.core.config import settings
from app.plugins.sandbox.supervisor import SpawnHook, _default_spawn

# Environment keys the worker is allowed to inherit. Everything else — every
# secret loaded from .env.production — is dropped.
_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
)
_FALLBACK_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def scrub_env() -> dict:
    """Build a minimal environment for the worker from a fixed allowlist.

    Never returns secrets — only allowlisted keys present in ``os.environ``,
    with a sane ``PATH`` fallback so the wrapper/interpreter resolve.
    """
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    if not env.get("PATH"):
        env["PATH"] = _FALLBACK_PATH
    return env


def _plugin_group_gid() -> Optional[int]:
    """GID of the plugin group (== settings.plugin_sandbox_user). None if absent / non-POSIX."""
    try:
        import grp  # POSIX-only
        return grp.getgrnam(settings.plugin_sandbox_user).gr_gid
    except (ImportError, KeyError):
        return None


def _flag_value(argv: list, flag: str) -> Optional[str]:
    """Return the value following ``flag`` in argv, or None."""
    try:
        return argv[argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _grant_group_rx_tree(root: str, gid: int) -> None:
    """chgrp ``root`` recursively to gid and add group-read (+ group-exec on dirs).

    Best-effort: skips anything it cannot change.
    """
    def _fix(path: str, is_dir: bool) -> None:
        try:
            if os.path.islink(path):
                return
            os.chown(path, -1, gid)
            mode = os.stat(path).st_mode
            os.chmod(path, mode | (0o050 if is_dir else 0o040))
        except OSError:
            pass

    _fix(root, True)
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            _fix(os.path.join(dirpath, d), True)
        for f in filenames:
            _fix(os.path.join(dirpath, f), False)


def grant_plugin_group_access(argv: list) -> None:
    """Make the host-created UDS socket and the plugin dir reachable by the
    unprivileged plugin user, and nothing else. Best-effort; no-op when the
    plugin group is absent (dev) or paths are unwritable. Only called from the
    hardened path, so dev/Windows are never touched.
    """
    gid = _plugin_group_gid()
    if gid is None:
        return
    connect = _flag_value(argv, "--connect")
    sock_path = connect[5:] if connect and connect.startswith("unix:") else connect
    if sock_path and os.path.exists(sock_path):
        try:
            os.chown(sock_path, -1, gid)   # pathname UDS: connect() needs group write
            os.chmod(sock_path, 0o660)
        except OSError:
            pass
    plugin_dir = _flag_value(argv, "--plugin-dir")
    if plugin_dir and os.path.isdir(plugin_dir):
        _grant_group_rx_tree(plugin_dir, gid)


async def hardened_spawn(argv: list, cwd: str) -> asyncio.subprocess.Process:
    """Spawn the worker through the root-owned sudo wrapper with a scrubbed env.

    The full worker ``argv`` is forwarded; the wrapper parses only the
    ``--connect/--plugin-dir/--plugin-name`` flags it needs and reconstructs the
    privilege-dropping exec line from trusted constants.
    """
    grant_plugin_group_access(argv)
    wrapped = ["sudo", "-n", settings.plugin_sandbox_wrapper_path, *argv]
    return await asyncio.create_subprocess_exec(*wrapped, cwd=cwd, env=scrub_env())


def _wrapper_ready() -> bool:
    """True if the wrapper exists and is executable."""
    return os.access(settings.plugin_sandbox_wrapper_path, os.X_OK)


def _user_exists() -> bool:
    """True if the configured plugin user exists (POSIX only)."""
    try:
        import pwd  # POSIX-only; never reached on Windows (caller short-circuits)
        pwd.getpwnam(settings.plugin_sandbox_user)
        return True
    except (ImportError, KeyError):
        return False


def select_spawn_hook() -> Optional[SpawnHook]:
    """Pick the spawn hook for this host.

    - dev / non-prod, or any non-Linux platform -> ``_default_spawn``
    - prod + Linux + wrapper present + plugin user exists -> ``hardened_spawn``
    - prod + Linux + not provisioned -> ``None`` (caller fails closed)
    """
    is_prod = str(settings.environment).lower() in ("production", "prod")
    if not is_prod or sys.platform != "linux":
        return _default_spawn
    if _wrapper_ready() and _user_exists():
        return hardened_spawn
    return None
