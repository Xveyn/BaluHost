"""SmartDevicePoller — runs in the MonitoringWorker process.

Loads all enabled smart_device plugins, polls every active device on each
plugin's interval, writes state to SHM and (periodically) to the DB.

This module is intentionally self-contained so it can be imported in the
monitoring worker without pulling in web-worker state.
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# How often to persist samples to DB (seconds); polls happen more frequently.
_DB_PERSIST_INTERVAL = 60.0

# Path to the installed plugins directory (same as PluginManager.PLUGINS_DIR)
_PLUGINS_DIR = Path(__file__).parent.parent / "installed"


class SmartDevicePoller:
    """Polls all active smart devices for all enabled smart_device plugins.

    Designed to run entirely inside the MonitoringWorker process (a separate
    OS process).  It writes state to two SHM files:

    - ``smart_devices.json``         — full snapshot (all devices, all plugins)
    - ``smart_devices_changes.json`` — delta changes with timestamp, consumed
      by the WebSocket bridge in the web worker.
    """

    def __init__(self) -> None:
        self._running = False
        self._db_session_factory: Optional[Callable] = None

        # plugin_name → SmartDevicePlugin instance
        self._plugins: Dict[str, Any] = {}

        # device_id (int) → last known state dict
        self._last_states: Dict[int, Dict[str, Any]] = {}

        # Timestamps of last DB persist per plugin_name
        self._last_db_persist: Dict[str, float] = {}

        # Full in-memory snapshot: device_id (str) → {state, meta}
        self._snapshot: Dict[str, Any] = {}

        # Pending delta changes list (written to smart_devices_changes.json)
        self._pending_changes: List[Dict[str, Any]] = []

        # Per-plugin poll tasks
        self._poll_tasks: List[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, db_session_factory: Callable) -> None:
        """Load plugins and start polling loops.

        Args:
            db_session_factory: SQLAlchemy session factory.
        """
        self._db_session_factory = db_session_factory
        self._running = True

        # Load enabled smart_device plugins from DB
        await self._load_plugins()

        if not self._plugins:
            logger.info("SmartDevicePoller: no smart_device plugins found, poller idle")
            return

        # Start one poll loop per plugin
        for plugin in self._plugins.values():
            task = asyncio.create_task(
                self._poll_loop(plugin),
                name=f"smart_device_poll_{plugin.metadata.name}",
            )
            self._poll_tasks.append(task)

        logger.info(
            "SmartDevicePoller started with %d plugin(s): %s",
            len(self._plugins),
            list(self._plugins.keys()),
        )

    async def stop(self) -> None:
        """Stop all polling loops gracefully."""
        self._running = False
        for task in self._poll_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._poll_tasks.clear()
        logger.info("SmartDevicePoller stopped")

    def get_status(self) -> Dict[str, Any]:
        """Return a status dict for the heartbeat / admin dashboard."""
        return {
            "is_running": self._running,
            "plugin_count": len(self._plugins),
            "plugins": list(self._plugins.keys()),
            "device_count": len(self._snapshot),
        }

    # ------------------------------------------------------------------
    # Plugin loading (simplified, independent of PluginManager)
    # ------------------------------------------------------------------

    async def _load_plugins(self) -> None:
        """Discover and load enabled smart_device plugins from DB."""
        if not _PLUGINS_DIR.exists():
            logger.debug("SmartDevicePoller: plugins dir not found: %s", _PLUGINS_DIR)
            return

        if self._db_session_factory is None:
            logger.warning("SmartDevicePoller: no DB session factory, cannot load plugins")
            return

        # Query enabled plugins with category 'smart_device'
        enabled_names: List[str] = []
        try:
            from app.models.plugin import InstalledPlugin
            db = self._db_session_factory()
            try:
                records = (
                    db.query(InstalledPlugin)
                    .filter(
                        InstalledPlugin.is_enabled == True,  # noqa: E712
                    )
                    .all()
                )
                enabled_names = [r.name for r in records]
            finally:
                db.close()
        except Exception as exc:
            logger.warning("SmartDevicePoller: could not query enabled plugins: %s", exc)
            return

        from app.plugins.smart_device.base import SmartDevicePlugin
        from app.plugins.base import PluginBase

        for name in enabled_names:
            plugin_path = _PLUGINS_DIR / name
            init_file = plugin_path / "__init__.py"
            if not init_file.exists():
                continue

            try:
                module_name = f"app.plugins.installed.{name}"

                # Ensure parent package stubs exist in sys.modules
                if "app.plugins.installed" not in sys.modules:
                    import types as _types
                    for pkg in ("app", "app.plugins"):
                        if pkg not in sys.modules:
                            sys.modules[pkg] = _types.ModuleType(pkg)
                    installed_mod = _types.ModuleType("app.plugins.installed")
                    installed_mod.__path__ = [str(_PLUGINS_DIR)]
                    sys.modules["app.plugins.installed"] = installed_mod

                if module_name not in sys.modules:
                    spec = importlib.util.spec_from_file_location(
                        module_name,
                        init_file,
                        submodule_search_locations=[str(plugin_path)],
                    )
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)  # type: ignore[union-attr]
                else:
                    module = sys.modules[module_name]

                # Find SmartDevicePlugin subclass
                plugin_cls = None
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, SmartDevicePlugin)
                        and attr is not SmartDevicePlugin
                        and attr is not PluginBase
                    ):
                        plugin_cls = attr
                        break

                if plugin_cls is None:
                    # Not a smart_device plugin
                    continue

                plugin = plugin_cls()
                if plugin.metadata.category != "smart_device":
                    continue

                await plugin.on_startup()
                self._plugins[name] = plugin
                logger.info("SmartDevicePoller: loaded plugin '%s'", name)

            except Exception as exc:
                logger.warning("SmartDevicePoller: failed to load plugin '%s': %s", name, exc)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _get_active_devices(self, plugin_name: str) -> List[Any]:
        """Fetch active devices for a plugin from DB."""
        if self._db_session_factory is None:
            return []
        try:
            from app.models.smart_device import SmartDevice
            db = self._db_session_factory()
            try:
                return (
                    db.query(SmartDevice)
                    .filter(
                        SmartDevice.plugin_name == plugin_name,
                        SmartDevice.is_active == True,  # noqa: E712
                    )
                    .all()
                )
            finally:
                db.close()
        except Exception as exc:
            logger.debug("SmartDevicePoller: DB query failed for plugin %s: %s", plugin_name, exc)
            return []

    async def _poll_loop(self, plugin: Any) -> None:
        """Continuous poll loop for a single plugin.

        Args:
            plugin: SmartDevicePlugin instance.
        """
        from app.core.config import settings

        plugin_name = plugin.metadata.name
        interval = plugin.get_poll_interval_seconds()

        while self._running:
            loop_start = time.time()

            devices = self._get_active_devices(plugin_name)
            for device in devices:
                if not self._running:
                    break
                await self._poll_one_device(plugin, device, settings.is_dev_mode)

            # Write SHM snapshot after each full plugin round
            self._write_shm_snapshot()

            # Persist to DB if interval elapsed
            last_persist = self._last_db_persist.get(plugin_name, 0.0)
            if time.time() - last_persist >= _DB_PERSIST_INTERVAL:
                await self._persist_samples_to_db(plugin_name)
                self._last_db_persist[plugin_name] = time.time()

            # Sleep for the remainder of the interval
            elapsed = time.time() - loop_start
            sleep_time = max(0.0, interval - elapsed)
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break

    async def _poll_one_device(self, plugin: Any, device: Any, dev_mode: bool) -> None:
        """Poll a single device, handling timeouts and errors.

        Args:
            plugin: SmartDevicePlugin.
            device: SmartDevice ORM instance.
            dev_mode: True if NAS_MODE=dev (use mock data).
        """
        device_id: int = device.id
        device_id_str = str(device_id)

        try:
            if dev_mode:
                new_state = await asyncio.wait_for(
                    plugin.poll_device_mock(device_id_str),
                    timeout=10.0,
                )
            else:
                new_state = await asyncio.wait_for(
                    plugin.poll_device(device_id_str),
                    timeout=10.0,
                )

            # Serialize any Pydantic models in the state dict
            serialized: Dict[str, Any] = {}
            for cap_key, cap_value in new_state.items():
                if hasattr(cap_value, "model_dump"):
                    serialized[cap_key] = cap_value.model_dump(mode="json")
                else:
                    serialized[cap_key] = cap_value

            self._process_state(device, serialized)

        except asyncio.TimeoutError:
            logger.warning(
                "SmartDevicePoller: timeout polling device %d ('%s')",
                device_id, device.name,
            )
            self._mark_device_error(device, "Poll timeout")

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.debug(
                "SmartDevicePoller: error polling device %d: %s", device_id, exc
            )
            self._mark_device_error(device, str(exc)[:500])

    def _process_state(self, device: Any, new_state: Dict[str, Any]) -> None:
        """Compare new_state with previous, update snapshot, flag changes.

        Args:
            device: SmartDevice ORM instance.
            new_state: Freshly polled state dict.
        """
        device_id: int = device.id
        prev_state = self._last_states.get(device_id)

        # Detect changes
        changed = prev_state != new_state

        # Update in-memory snapshot
        self._snapshot[str(device_id)] = {
            "state": new_state,
            "name": device.name,
            "plugin_name": device.plugin_name,
            "device_type_id": device.device_type_id,
            "is_online": True,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }

        self._last_states[device_id] = new_state

        # Update device online status in DB (best-effort)
        self._update_device_online(device, online=True, error=None)

        if changed:
            self._pending_changes.append(
                {
                    "device_id": device_id,
                    "name": device.name,
                    "state": new_state,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            # Write changes SHM immediately
            self._write_shm_changes()

    def _mark_device_error(self, device: Any, error_msg: str) -> None:
        """Mark a device as offline and update its error in DB."""
        device_id: int = device.id
        snapshot_entry = self._snapshot.get(str(device_id))
        if snapshot_entry:
            snapshot_entry["is_online"] = False

        self._update_device_online(device, online=False, error=error_msg)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _update_device_online(
        self, device: Any, online: bool, error: Optional[str]
    ) -> None:
        """Update is_online / last_seen / last_error in the DB (best-effort)."""
        if self._db_session_factory is None:
            return
        try:
            from app.models.smart_device import SmartDevice
            db = self._db_session_factory()
            try:
                row = db.query(SmartDevice).filter(SmartDevice.id == device.id).first()
                if row:
                    row.is_online = online
                    if online:
                        row.last_seen = datetime.now(timezone.utc)
                    row.last_error = error
                    db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("SmartDevicePoller: DB online-update failed: %s", exc)

    async def _persist_samples_to_db(self, plugin_name: str) -> None:
        """Write current snapshot data as SmartDeviceSample rows (time-series)."""
        if self._db_session_factory is None:
            return
        try:
            from app.models.smart_device import SmartDeviceSample
            now = datetime.now(timezone.utc)
            db = self._db_session_factory()
            try:
                for device_id_str, entry in self._snapshot.items():
                    # Only persist for this plugin
                    if entry.get("plugin_name") != plugin_name:
                        continue
                    state = entry.get("state", {})
                    for capability, cap_state in state.items():
                        sample = SmartDeviceSample(
                            device_id=int(device_id_str),
                            capability=capability,
                            data_json=json.dumps(cap_state, default=str),
                            timestamp=now,
                        )
                        db.add(sample)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("SmartDevicePoller: DB persist failed for plugin %s: %s", plugin_name, exc)

    # ------------------------------------------------------------------
    # SHM writes
    # ------------------------------------------------------------------

    def _write_shm_snapshot(self) -> None:
        """Write full state snapshot to smart_devices.json."""
        try:
            from app.services.monitoring.shm import write_shm, SMART_DEVICES_FILE
            data = {
                "devices": self._snapshot,
                "timestamp": time.time(),
            }
            write_shm(SMART_DEVICES_FILE, data)
        except Exception as exc:
            logger.debug("SmartDevicePoller: SHM snapshot write failed: %s", exc)

    def _write_shm_changes(self) -> None:
        """Write pending delta changes to smart_devices_changes.json and clear the list."""
        if not self._pending_changes:
            return
        try:
            from app.services.monitoring.shm import write_shm, SMART_DEVICES_CHANGES_FILE
            data = {
                "changes": list(self._pending_changes),
                "timestamp": time.time(),
            }
            write_shm(SMART_DEVICES_CHANGES_FILE, data)
            self._pending_changes.clear()
        except Exception as exc:
            logger.debug("SmartDevicePoller: SHM changes write failed: %s", exc)
