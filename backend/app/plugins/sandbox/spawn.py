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


async def hardened_spawn(argv: list, cwd: str) -> asyncio.subprocess.Process:
    """Spawn the worker through the root-owned sudo wrapper with a scrubbed env.

    The full worker ``argv`` is forwarded; the wrapper parses only the
    ``--connect/--plugin-dir/--plugin-name`` flags it needs and reconstructs the
    privilege-dropping exec line from trusted constants.
    """
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
