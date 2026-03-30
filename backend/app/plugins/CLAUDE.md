# Plugin System

Extensible plugin architecture for adding features without modifying core code. Plugins can inject routes, background tasks, event handlers, dashboard panels, and frontend UI.

## Architecture

```
plugins/
├── base.py              # PluginBase ABC, PluginMetadata, PluginUIManifest, DashboardPanelSpec
├── manager.py           # PluginManager singleton — discovery, loading, lifecycle, route mounting
├── hooks.py             # Pluggy hook specs (on_system_startup, on_system_shutdown, etc.)
├── events.py            # Async event bus (EventManager) for inter-plugin communication
├── emit.py              # Convenience: emit_hook(), emit_event(), emit_event_sync()
├── permissions.py       # PluginPermission enum, DANGEROUS_PERMISSIONS list
├── dashboard_panel.py   # Dashboard panel bridge for plugin data
├── smart_device/        # SmartDevice plugin framework (base class, manager, poller, capabilities)
└── installed/           # Plugin implementations
    ├── optical_drive/   # CD/DVD burning, reading, ISO browsing
    ├── storage_analytics/  # Storage usage analytics
    └── tapo_smart_plug/ # TP-Link Tapo smart plug integration with mock backend
```

## Plugin Lifecycle

1. **Discovery**: `PluginManager` scans `installed/` for `__init__.py` files with a `PluginBase` subclass
2. **Registration**: Plugin instance created, metadata validated
3. **Permission check**: Required permissions compared against granted permissions in DB (`InstalledPlugin` model)
4. **Activation**: `on_startup()` called, routes mounted at `/api/plugins/{name}/`, background tasks started
5. **Running**: Requests gated by `PluginGateMiddleware` (checks enabled + permissions)
6. **Deactivation**: `on_shutdown()` called, tasks cancelled

## Creating a Plugin

1. Create directory in `plugins/installed/my_plugin/`
2. Create `__init__.py` exporting a class that extends `PluginBase`
3. Implement `metadata` property returning `PluginMetadata`
4. Override `get_router()` for API routes, `get_background_tasks()` for periodic work
5. Override `get_dashboard_panel()` + `get_dashboard_data()` for dashboard integration

## SmartDevice Framework (`smart_device/`)

Base class for hardware device plugins (e.g., Tapo smart plugs). Provides:
- `SmartDevicePlugin` ABC with standardized polling/state interface
- `SmartDeviceManager` for device registration and aggregated status
- `SmartDevicePoller` for periodic device state collection (runs in monitoring worker)
- Capability system (`capabilities.py`) for feature detection
