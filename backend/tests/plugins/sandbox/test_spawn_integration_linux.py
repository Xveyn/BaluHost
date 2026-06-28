"""REAL spawn integration test for the hardened external-plugin sandbox.

Runs ONLY on a provisioned Linux box (or a dedicated CI lane):
  - Linux,
  - root (needed to drop to the baluhost-plugin user via the sudoers wrapper),
  - baluhost-plugin user exists,
  - /usr/local/sbin/baluhost-spawn-plugin-worker.sh installed & executable.

It is SKIPPED on Windows dev machines and any unprovisioned host. It must never
fail the Windows dev suite.
"""
import os
import shutil
import sys

import pytest

WRAPPER = "/usr/local/sbin/baluhost-spawn-plugin-worker.sh"


def _baluhost_plugin_user_exists() -> bool:
    try:
        import pwd  # noqa: PLC0415  (Linux-only)

        pwd.getpwnam("baluhost-plugin")
        return True
    except (ImportError, KeyError):
        return False


_provisioned = (
    sys.platform.startswith("linux")
    and hasattr(os, "geteuid")
    and os.geteuid() == 0
    and _baluhost_plugin_user_exists()
    and os.path.isfile(WRAPPER)
    and os.access(WRAPPER, os.X_OK)
)

pytestmark = pytest.mark.skipif(
    not _provisioned,
    reason="requires provisioned Linux box (root + baluhost-plugin user + spawn wrapper)",
)


@pytest.mark.asyncio
async def test_real_hardened_spawn_health_roundtrip(tmp_path):
    """Spawn a fixture plugin through the real wrapper; assert it answers health."""
    # Implementer: build a minimal fixture plugin dir (plugin.json + a worker entry
    # that uses the Phase 3 Plugin-SDK register(host) contract), construct the real
    # supervisor via the production factory (the same path _enable_external uses),
    # await supervisor.start(), then issue a health/dispatch RPC and assert a
    # successful response. Reuse the Phase 3 e2e fixture plugin if one already
    # exists under tests/plugins/sandbox/ rather than authoring a new one.
    pytest.skip("fixture wiring done at implementation time on the provisioned box")
