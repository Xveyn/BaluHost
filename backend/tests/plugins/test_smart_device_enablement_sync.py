"""SmartDevice registry follows plugin enablement across workers (#459).

The registry ``SmartDeviceManager._plugins`` decides whether
``/api/smart-devices/{id}/command`` can reach a device. Enablement itself lives
in the database and is reconciled per worker
(``services/plugin_enablement.reconcile_worker``). These tests pin the two
directions of that coupling:

- a plugin enabled on another worker becomes commandable here,
- a plugin disabled on another worker stops being commandable here.

Before #459 only the first direction worked, and it worked through a
synchronous DB read inside ``get_smart_device_manager()`` - on the request path,
in three cases directly on the event loop.
"""

import inspect
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.smart_device import SmartDevice
from app.plugins.base import PluginBase, PluginMetadata
from app.plugins.manager import PluginManager
from app.plugins.smart_device.base import DeviceTypeInfo, SmartDevicePlugin
from app.plugins.smart_device.capabilities import DeviceCapability, SwitchState
from app.plugins.smart_device.manager import (
    SmartDeviceManager,
    get_smart_device_manager,
)
from app.services import plugin_enablement as pe

pytestmark = pytest.mark.asyncio


# =============================================================================
# Doubles
# =============================================================================


class _SmartPlugin(SmartDevicePlugin):
    """Minimal SmartDevicePlugin implementing the Switch capability."""

    def __init__(self, name: str = "mock_plug_plugin"):
        self._name = name

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name,
            version="1.0.0",
            display_name="Mock Plug",
            description="Smart device plugin double",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="mock_plug",
                display_name="Mock Plug",
                manufacturer="MockCorp",
                capabilities=[DeviceCapability.SWITCH],
            ),
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {"switch": SwitchState(is_on=True)}

    async def turn_on(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True, changed_at=datetime.now(timezone.utc))

    async def turn_off(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=False, changed_at=datetime.now(timezone.utc))

    async def get_switch_state(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True)


class _PlainPlugin(PluginBase):
    """A plugin that is NOT a SmartDevicePlugin."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="plain_plugin",
            version="1.0.0",
            display_name="Plain",
            description="Not a smart device plugin",
            author="Test",
            category="utility",
        )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _isolate_module_state():
    """Both the registry and the enablement cache are module/class state that
    survives test-file boundaries in one pytest process."""
    SmartDeviceManager.reset_instance()
    pe.invalidate()
    pe._failed_until.clear()
    yield
    SmartDeviceManager.reset_instance()
    pe.invalidate()
    pe._failed_until.clear()


@pytest.fixture
def plugin_manager(tmp_path) -> PluginManager:
    """A PluginManager with the smart-device double pre-loaded.

    Injecting into ``_plugins`` is what ``load_plugin()`` does; it lets
    ``enable_plugin()`` run without a plugin package on disk.
    """
    mgr = PluginManager(plugins_dir=tmp_path)
    mgr._plugins["mock_plug_plugin"] = _SmartPlugin()
    return mgr


def _device_row(db: Session, plugin_name: str = "mock_plug_plugin") -> SmartDevice:
    device = SmartDevice(
        name="Mock Plug",
        plugin_name=plugin_name,
        device_type_id="mock_plug",
        address="192.168.1.50",
        capabilities=["switch"],
        is_active=True,
        is_online=True,
        created_by_user_id=1,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


# =============================================================================
# PluginManager drives the registry
# =============================================================================


class TestEnablementDrivesTheRegistry:
    async def test_enabling_registers_the_plugin(self, plugin_manager: PluginManager):
        registry = SmartDeviceManager.get_instance()
        assert registry.get_plugin("mock_plug_plugin") is None

        ok = await plugin_manager.enable_plugin("mock_plug_plugin", [], MagicMock())

        assert ok is True
        assert registry.get_plugin("mock_plug_plugin") is plugin_manager._plugins[
            "mock_plug_plugin"
        ]

    async def test_disabling_unregisters_the_plugin(self, plugin_manager: PluginManager):
        registry = SmartDeviceManager.get_instance()
        await plugin_manager.enable_plugin("mock_plug_plugin", [], MagicMock())
        assert registry.get_plugin("mock_plug_plugin") is not None

        ok = await plugin_manager.disable_plugin("mock_plug_plugin")

        assert ok is True
        assert registry.get_plugin("mock_plug_plugin") is None

    async def test_a_plain_plugin_never_enters_the_registry(self, tmp_path):
        """``get_all_device_types()`` calls ``get_device_types()`` on every
        registered plugin - a non-SmartDevicePlugin in there breaks the
        device-type endpoint for all plugins."""
        mgr = PluginManager(plugins_dir=tmp_path)
        mgr._plugins["plain_plugin"] = _PlainPlugin()

        await mgr.enable_plugin("plain_plugin", [], MagicMock())

        assert SmartDeviceManager.get_instance().list_plugins() == []


class TestCommandSurface:
    async def test_a_disabled_plugin_is_no_longer_commandable(
        self, plugin_manager: PluginManager, db_session: Session
    ):
        """The symptom from #459: a deactivated ``tapo_smart_plug`` stayed
        switchable through ``/api/smart-devices/{id}/command`` on every worker
        that did not handle the toggle."""
        registry = SmartDeviceManager.get_instance()
        device = _device_row(db_session)
        await plugin_manager.enable_plugin("mock_plug_plugin", [], MagicMock())

        result = await registry.execute_command(
            device_id=device.id,
            capability="switch",
            command="turn_on",
            params={},
            db=db_session,
        )
        assert result["success"] is True

        await plugin_manager.disable_plugin("mock_plug_plugin")

        with pytest.raises(ValueError, match="not loaded"):
            await registry.execute_command(
                device_id=device.id,
                capability="switch",
                command="turn_on",
                params={},
                db=db_session,
            )


# =============================================================================
# Cross-worker: the reconcile carries the registry with it
# =============================================================================


class TestReconcileCarriesTheRegistry:
    async def test_a_plugin_enabled_elsewhere_becomes_commandable_here(
        self, plugin_manager: PluginManager
    ):
        registry = SmartDeviceManager.get_instance()
        desired = {
            "mock_plug_plugin": {
                "granted_permissions": [],
                "granted_api_scopes": [],
            }
        }

        with patch.object(pe, "_fetch", return_value=desired), \
             patch.object(pe, "_get_manager", return_value=plugin_manager):
            await pe.reconcile_worker()

        assert registry.get_plugin("mock_plug_plugin") is not None

    async def test_a_plugin_disabled_elsewhere_stops_being_commandable_here(
        self, plugin_manager: PluginManager
    ):
        registry = SmartDeviceManager.get_instance()
        await plugin_manager.enable_plugin("mock_plug_plugin", [], MagicMock())
        assert registry.get_plugin("mock_plug_plugin") is not None

        with patch.object(pe, "_fetch", return_value={}), \
             patch.object(pe, "_get_manager", return_value=plugin_manager):
            await pe.reconcile_worker()

        assert registry.get_plugin("mock_plug_plugin") is None


# =============================================================================
# The accessor is off the DB
# =============================================================================


class TestAccessorDoesNoDatabaseWork:
    async def test_the_accessor_opens_no_session(self):
        """The registry is maintained by enable/disable, so the accessor has no
        reason to read the database. It was called from three ``async def``
        handlers, where a synchronous read blocks the event loop."""
        from app.core import database

        sentinel = MagicMock(side_effect=AssertionError("opened a DB session"))
        with patch.object(database, "SessionLocal", sentinel):
            manager = get_smart_device_manager()

        assert manager is SmartDeviceManager.get_instance()
        sentinel.assert_not_called()


# =============================================================================
# Routes that depend on enablement reconcile first
# =============================================================================


class TestRoutesReconcile:
    async def test_enablement_dependent_routes_declare_the_reconcile(self):
        """Without the dependency, a worker that only ever serves
        ``/api/smart-devices/...`` never reconciles, so the registry fix above
        would never be triggered on it.

        Only the handlers that actually consult the plugin registry are listed;
        the pure DB/SHM readers (``list_devices``, ``get_device``,
        ``get_power_summary``, ``get_device_history``, ``update_device``,
        ``delete_device``) deliberately are not.
        """
        from app.api.deps import reconciled_plugin_state
        from app.api.routes import smart_devices as sd_routes

        expected = [
            sd_routes.list_device_types,
            sd_routes.discover_devices,
            sd_routes.create_device,
            sd_routes.execute_command,
            sd_routes.import_device_history,
        ]
        for func in expected:
            declared = [
                param.default.dependency
                for param in inspect.signature(func).parameters.values()
                if hasattr(param.default, "dependency")
            ]
            assert reconciled_plugin_state in declared, (
                f"{func.__name__} misses the reconcile dependency"
            )
