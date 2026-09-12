"""RAID/SMART degrade gracefully when their optional system tool is missing (#543).

mdadm and smartmontools are optional in the installer (ENABLE_RAID / ENABLE_SMART
default to false), so a self-hosted box may legitimately run without them.
"""
import importlib
import platform
from unittest import mock

import pytest

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.schemas.system import CreateArrayRequest
import app.services.hardware.raid.api as raid_api


def _no_raid_backend():
    """Context: Linux host, prod mode, mdadm not installed."""
    return [
        mock.patch.object(settings, "raid_force_dev_backend", False),
        mock.patch.object(settings, "is_dev_mode", False),
        mock.patch.object(platform, "system", return_value="Linux"),
        mock.patch("shutil.which", return_value=None),
    ]


class TestRaidBackendUnavailable:
    def test_import_survives_without_mdadm(self):
        """Importing the module must not resolve the backend (#543).

        _backend = _select_backend() ran at module level, so a missing mdadm
        raised during import. 14 modules outside the package import
        app.services.hardware top-level (lifespan, routes/system, the
        monitoring collectors), so the whole backend refused to start.
        """
        patches = _no_raid_backend()
        for p in patches:
            p.start()
        try:
            importlib.reload(raid_api)
            assert raid_api._backend_cache is None
        finally:
            for p in reversed(patches):
                p.stop()
            importlib.reload(raid_api)

    def test_select_backend_raises_raid_unavailable(self):
        patches = _no_raid_backend()
        for p in patches:
            p.start()
        try:
            with pytest.raises(raid_api.RaidUnavailableError):
                raid_api._select_backend()
        finally:
            for p in reversed(patches):
                p.stop()

    def test_raid_unavailable_maps_to_503(self):
        """Routes need no try/except: the global ServiceError handler answers 503."""
        assert issubclass(raid_api.RaidUnavailableError, ServiceUnavailableError)
        assert raid_api.RaidUnavailableError().http_status == 503

    def test_get_status_degrades_to_empty(self, monkeypatch):
        """Read path stays usable: no arrays instead of a 500 (or invented ones)."""
        def _boom():
            raise raid_api.RaidUnavailableError()

        monkeypatch.setattr(raid_api, "_get_backend", _boom)
        status = raid_api.get_status()
        assert status.arrays == []

    def test_mutating_call_raises_unavailable(self, monkeypatch):
        """Write path must fail loudly -- an empty answer would be a lie."""
        def _boom():
            raise raid_api.RaidUnavailableError()

        monkeypatch.setattr(raid_api, "_get_backend", _boom)
        with pytest.raises(raid_api.RaidUnavailableError):
            raid_api.create_array(CreateArrayRequest(name="md9", level="1", devices=["sda", "sdb"]))


class TestSmartUnavailableInProduction:
    def test_prod_without_smartctl_returns_empty_not_mock(self, monkeypatch):
        """Production must report "no data", never invented disks.

        The prod path fell back to _mock_status() -- "BaluHost Dev Disk 5GB",
        status PASSED -- so a box without smartmontools showed healthy hardware
        that does not exist.
        """
        from app.services.hardware.smart import api as smart_api
        from app.services.hardware.smart import cache as smart_cache

        smart_cache.invalidate_smart_cache()
        monkeypatch.setattr(settings, "is_dev_mode", False)

        def _unavailable():
            raise smart_cache.SmartUnavailableError("smartctl not found in PATH")

        monkeypatch.setattr(smart_api, "_read_real_smart_data", _unavailable)
        try:
            status = smart_api.get_smart_status()
            assert status.devices == []
            assert not any("Dev Disk" in d.model for d in status.devices)
        finally:
            smart_cache.invalidate_smart_cache()
