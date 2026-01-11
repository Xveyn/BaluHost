import json
import os
import tempfile

from app.core.config import settings
from app.schemas.system import RaidSimulationRequest
import app.services.raid as raid
from types import SimpleNamespace


class _SettingsProxy:
    def __init__(self, base, **overrides):
        self._base = base
        for k, v in overrides.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        return getattr(self._base, name)


def test_raid_dry_run_audit_and_response(tmp_path):

    # Backup raid module settings reference
    old_raid_settings = raid.settings

    try:
        audit_file = tmp_path / "raid_audit_test.log"
        # Replace raid module settings with a proxy that enables dry-run
        raid.settings = _SettingsProxy(settings, raid_dry_run=True, raid_audit_log=str(audit_file))

        payload = RaidSimulationRequest(array="md0", device="sda1")
        resp = raid.simulate_failure(payload)

        # Audit file should exist and contain a JSON line with the action
        assert audit_file.exists(), "Audit file was not created"
        lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "Audit file is empty"
        record = json.loads(lines[-1])
        assert record.get("action") == "simulate_failure"
        assert record.get("dry_run") is True

        # If the real backend was not already the dev backend, the wrapper should return a DRY-RUN message
        if not isinstance(raid._backend, raid.DevRaidBackend):
            assert resp.message.startswith("[DRY-RUN]"), resp.message

    finally:
        # Restore raid module settings reference
        raid.settings = old_raid_settings