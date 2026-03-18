"""Tests for SmartDevicePoller — polling loop, state processing, SHM writes."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from sqlalchemy.orm import Session

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.smart_device.poller import PollerDevice, SmartDevicePoller


# =============================================================================
# Helpers
# =============================================================================


def _make_poller_device(
    id: int = 1,
    name: str = "Test Device",
    plugin_name: str = "mock_plugin",
    device_type_id: str = "mock_plug",
    address: str = "192.168.1.100",
    capabilities: list | None = None,
    config_secret: str | None = None,
) -> PollerDevice:
    return PollerDevice(
        id=id,
        name=name,
        plugin_name=plugin_name,
        device_type_id=device_type_id,
        address=address,
        capabilities=capabilities or ["switch", "power_monitor"],
        config_secret=config_secret,
    )


def _create_device_row(
    db: Session,
    name: str = "Test Device",
    plugin_name: str = "mock_plugin",
    device_type_id: str = "mock_plug",
    address: str = "192.168.1.100",
    is_active: bool = True,
) -> SmartDevice:
    device = SmartDevice(
        name=name,
        plugin_name=plugin_name,
        device_type_id=device_type_id,
        address=address,
        capabilities=["switch"],
        is_active=is_active,
        is_online=False,
        created_by_user_id=1,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


# =============================================================================
# PollerDevice dataclass
# =============================================================================


class TestPollerDevice:
    def test_create(self):
        pd = PollerDevice(
            id=1,
            name="Test",
            plugin_name="plug_plugin",
            device_type_id="tapo_p115",
            address="192.168.1.1",
        )
        assert pd.id == 1
        assert pd.name == "Test"
        assert pd.plugin_name == "plug_plugin"
        assert pd.device_type_id == "tapo_p115"
        assert pd.address == "192.168.1.1"
        assert pd.capabilities == []
        assert pd.config_secret is None

    def test_create_with_all_fields(self):
        pd = PollerDevice(
            id=42,
            name="Full",
            plugin_name="test",
            device_type_id="type",
            address="10.0.0.1",
            capabilities=["switch", "power_monitor"],
            config_secret="encrypted_data",
        )
        assert pd.id == 42
        assert pd.capabilities == ["switch", "power_monitor"]
        assert pd.config_secret == "encrypted_data"

    def test_default_capabilities_is_list(self):
        """Each instance should get its own list (default_factory)."""
        pd1 = PollerDevice(id=1, name="A", plugin_name="p", device_type_id="t", address="x")
        pd2 = PollerDevice(id=2, name="B", plugin_name="p", device_type_id="t", address="y")
        pd1.capabilities.append("switch")
        assert pd2.capabilities == []  # Not shared


# =============================================================================
# SmartDevicePoller: _process_state
# =============================================================================


class TestProcessState:
    def test_first_state_creates_snapshot_entry(self):
        poller = SmartDevicePoller()
        device = _make_poller_device(id=1)
        new_state = {"switch": {"is_on": True}}

        with patch.object(poller, "_update_device_online"):
            with patch.object(poller, "_write_shm_changes"):
                poller._process_state(device, new_state)

        assert "1" in poller._snapshot
        assert poller._snapshot["1"]["state"] == new_state
        assert poller._snapshot["1"]["is_online"] is True
        assert poller._snapshot["1"]["name"] == "Test Device"
        assert poller._last_states[1] == new_state

    def test_unchanged_state_does_not_add_change(self):
        poller = SmartDevicePoller()
        device = _make_poller_device(id=2)
        state = {"switch": {"is_on": False}}

        with patch.object(poller, "_update_device_online"):
            with patch.object(poller, "_write_shm_changes"):
                # First call: new state -> change detected
                poller._process_state(device, state)
                changes_after_first = len(poller._pending_changes)

                # Second call: same state -> no new change
                poller._process_state(device, state)
                changes_after_second = len(poller._pending_changes)

        assert changes_after_first == 1
        assert changes_after_second == 1  # No additional change

    def test_changed_state_adds_pending_change(self):
        poller = SmartDevicePoller()
        device = _make_poller_device(id=3)

        with patch.object(poller, "_update_device_online"):
            with patch.object(poller, "_write_shm_changes"):
                poller._process_state(device, {"switch": {"is_on": True}})
                poller._process_state(device, {"switch": {"is_on": False}})

        assert len(poller._pending_changes) == 2
        assert poller._pending_changes[1]["state"]["switch"]["is_on"] is False

    def test_snapshot_contains_metadata(self):
        poller = SmartDevicePoller()
        device = _make_poller_device(id=5, name="Desk Lamp", plugin_name="tapo", device_type_id="p115")

        with patch.object(poller, "_update_device_online"):
            with patch.object(poller, "_write_shm_changes"):
                poller._process_state(device, {"switch": {"is_on": True}})

        entry = poller._snapshot["5"]
        assert entry["name"] == "Desk Lamp"
        assert entry["plugin_name"] == "tapo"
        assert entry["device_type_id"] == "p115"
        assert "last_seen" in entry


# =============================================================================
# SmartDevicePoller: _mark_device_error
# =============================================================================


class TestMarkDeviceError:
    def test_marks_device_offline_in_snapshot(self):
        poller = SmartDevicePoller()
        device = _make_poller_device(id=10)

        # Set up a snapshot entry first
        poller._snapshot["10"] = {
            "state": {"switch": {"is_on": True}},
            "is_online": True,
        }

        with patch.object(poller, "_update_device_online"):
            poller._mark_device_error(device, "Connection refused")

        assert poller._snapshot["10"]["is_online"] is False

    def test_marks_error_for_missing_snapshot_entry(self):
        """No crash if device not yet in snapshot."""
        poller = SmartDevicePoller()
        device = _make_poller_device(id=11)

        with patch.object(poller, "_update_device_online") as mock_update:
            poller._mark_device_error(device, "Timeout")
            mock_update.assert_called_once_with(device, online=False, error="Timeout")


# =============================================================================
# SmartDevicePoller: _get_active_devices
# =============================================================================


class TestGetActiveDevices:
    def test_returns_poller_devices(self, db_session):
        dev = _create_device_row(db_session, name="Active Plug", is_active=True)

        poller = SmartDevicePoller()
        poller._db_session_factory = lambda: db_session

        devices = poller._get_active_devices("mock_plugin")
        assert len(devices) == 1
        assert isinstance(devices[0], PollerDevice)
        assert devices[0].id == dev.id
        assert devices[0].name == "Active Plug"
        assert devices[0].plugin_name == "mock_plugin"

    def test_excludes_inactive_devices(self, db_session):
        _create_device_row(db_session, name="Inactive", is_active=False)

        poller = SmartDevicePoller()
        poller._db_session_factory = lambda: db_session

        devices = poller._get_active_devices("mock_plugin")
        assert len(devices) == 0

    def test_filters_by_plugin_name(self, db_session):
        _create_device_row(db_session, name="A", plugin_name="alpha")
        _create_device_row(db_session, name="B", plugin_name="beta")

        poller = SmartDevicePoller()
        poller._db_session_factory = lambda: db_session

        alpha_devices = poller._get_active_devices("alpha")
        assert len(alpha_devices) == 1
        assert alpha_devices[0].name == "A"

    def test_returns_empty_without_session_factory(self):
        poller = SmartDevicePoller()
        poller._db_session_factory = None
        devices = poller._get_active_devices("anything")
        assert devices == []


# =============================================================================
# SmartDevicePoller: SHM write methods
# =============================================================================


class TestSHMWrites:
    def test_write_shm_snapshot(self):
        poller = SmartDevicePoller()
        poller._snapshot = {"1": {"state": {"switch": {"is_on": True}}}}

        with patch("app.services.monitoring.shm.write_shm") as mock_write_shm:
            poller._write_shm_snapshot()

            mock_write_shm.assert_called_once()
            args = mock_write_shm.call_args
            assert args[0][0] == "smart_devices.json"
            data = args[0][1]
            assert "devices" in data
            assert "timestamp" in data

    def test_write_shm_changes(self):
        poller = SmartDevicePoller()
        poller._pending_changes = [
            {"device_id": 1, "name": "Test", "state": {"switch": {"is_on": True}}}
        ]

        with patch("app.services.monitoring.shm.write_shm") as mock_write_shm:
            poller._write_shm_changes()

            mock_write_shm.assert_called_once()
            args = mock_write_shm.call_args
            assert args[0][0] == "smart_devices_changes.json"
            data = args[0][1]
            assert len(data["changes"]) == 1
        # Pending changes should be cleared after write
        assert len(poller._pending_changes) == 0

    def test_write_shm_changes_empty_is_noop(self):
        poller = SmartDevicePoller()
        poller._pending_changes = []
        with patch("app.services.monitoring.shm.write_shm") as mock_write_shm:
            poller._write_shm_changes()
            mock_write_shm.assert_not_called()

    def test_write_shm_snapshot_handles_exception(self):
        """SHM write failure should not crash the poller."""
        poller = SmartDevicePoller()
        poller._snapshot = {"1": {"state": {}}}
        with patch("app.services.monitoring.shm.write_shm", side_effect=OSError("disk full")):
            # Should not raise
            poller._write_shm_snapshot()


# =============================================================================
# SmartDevicePoller: _update_device_online (DB helper)
# =============================================================================


class _NoCloseSession:
    """Wrapper that prevents the poller from closing our test session."""

    def __init__(self, real_session: Session):
        self._real = real_session

    def __getattr__(self, name):
        if name == "close":
            return lambda: None  # Ignore close
        return getattr(self._real, name)

    def query(self, *args, **kwargs):
        return self._real.query(*args, **kwargs)

    def commit(self):
        return self._real.commit()

    def add(self, obj):
        return self._real.add(obj)


class TestUpdateDeviceOnline:
    def test_sets_device_online(self, db_session):
        dev = _create_device_row(db_session)
        poller = SmartDevicePoller()
        poller._db_session_factory = lambda: _NoCloseSession(db_session)

        pd = _make_poller_device(id=dev.id)
        poller._update_device_online(pd, online=True, error=None)

        db_session.refresh(dev)
        assert dev.is_online is True
        assert dev.last_error is None

    def test_sets_device_offline_with_error(self, db_session):
        dev = _create_device_row(db_session)
        poller = SmartDevicePoller()
        poller._db_session_factory = lambda: _NoCloseSession(db_session)

        pd = _make_poller_device(id=dev.id)
        poller._update_device_online(pd, online=False, error="Connection refused")

        db_session.refresh(dev)
        assert dev.is_online is False
        assert dev.last_error == "Connection refused"

    def test_noop_without_session_factory(self):
        """Should not crash if no session factory."""
        poller = SmartDevicePoller()
        poller._db_session_factory = None
        pd = _make_poller_device(id=999)
        poller._update_device_online(pd, online=True, error=None)  # No exception


# =============================================================================
# SmartDevicePoller: get_status
# =============================================================================


class TestPollerStatus:
    def test_initial_status(self):
        poller = SmartDevicePoller()
        status = poller.get_status()
        assert status["is_running"] is False
        assert status["plugin_count"] == 0
        assert status["plugins"] == []
        assert status["device_count"] == 0

    def test_status_reflects_snapshot(self):
        poller = SmartDevicePoller()
        poller._running = True
        poller._plugins = {"mock": MagicMock()}
        poller._snapshot = {"1": {}, "2": {}}
        status = poller.get_status()
        assert status["is_running"] is True
        assert status["plugin_count"] == 1
        assert status["device_count"] == 2


# =============================================================================
# SmartDevicePoller: _persist_samples_to_db
# =============================================================================


@pytest.mark.asyncio
class TestPersistSamplesToDb:
    async def test_persists_samples(self, db_session):
        dev = _create_device_row(db_session)
        poller = SmartDevicePoller()
        poller._db_session_factory = lambda: _NoCloseSession(db_session)
        poller._snapshot = {
            str(dev.id): {
                "plugin_name": "mock_plugin",
                "state": {
                    "switch": {"is_on": True},
                    "power_monitor": {"watts": 42.5},
                },
            }
        }

        await poller._persist_samples_to_db("mock_plugin")

        samples = db_session.query(SmartDeviceSample).filter(
            SmartDeviceSample.device_id == dev.id
        ).all()
        assert len(samples) == 2
        capabilities = {s.capability for s in samples}
        assert "switch" in capabilities
        assert "power_monitor" in capabilities

    async def test_skips_other_plugins(self, db_session):
        dev = _create_device_row(db_session, plugin_name="other_plugin")
        poller = SmartDevicePoller()
        poller._db_session_factory = lambda: _NoCloseSession(db_session)
        poller._snapshot = {
            str(dev.id): {
                "plugin_name": "other_plugin",
                "state": {"switch": {"is_on": True}},
            }
        }

        await poller._persist_samples_to_db("mock_plugin")

        samples = db_session.query(SmartDeviceSample).all()
        assert len(samples) == 0

    async def test_noop_without_session_factory(self):
        poller = SmartDevicePoller()
        poller._db_session_factory = None
        await poller._persist_samples_to_db("any")  # No exception
