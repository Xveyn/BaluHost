# BaluHost Plugin System

The plugin system lets you extend BaluHost without touching core code — adding API routes,
background tasks, event handlers, dashboard panels, and frontend UI.

## Trust Tiers

Two distinct trust tiers exist with different isolation guarantees. Understanding which tier
applies is the most important starting point.

### Bundled (in-process, fully trusted)

Plugins under `installed/`. Loaded directly as Python in the host process. They have:

- Full access to the host's database, filesystem, services, and Python APIs.
- Old permission model: declare `required_permissions` in `PluginMetadata`; the admin grants
  these in the enable modal (`permissions.py`).
- Routes mounted at `/api/plugins/{name}/`.
- All bundled plugins are maintained in-repo and ship with BaluHost.

The rest of this README's "Plugin Authoring" sections apply to this tier.

### External (sandboxed subprocess)

Marketplace plugins with `source="external"`. They are:

- Spawned via a hardened OS-level wrapper (`sandbox/spawn.py`) as the low-privilege
  `baluhost-plugin` OS user, inside a dedicated network namespace (loopback only).
- **Fail-closed when unprovisioned**: if the host has not had the provisioning scripts run
  (Module 03+10: `baluhost-plugin` user, sudoers entry, wrapper binary), the spawn fails
  rather than silently degrading.
- Able to reach the host **only** through default-deny **capability scopes** (`CAPABILITY_SCOPE`)
  over UDS-RPC — no host Python imports, no direct DB, filesystem, or shell access.
- Subject to an admin-granted scope subset: the admin picks a subset of the plugin's
  requested `api_scopes` at enable time via the scope-picker. The authoritative catalog of
  grantable scopes is `scope_catalog.py`.
- Denied capability calls are audit-logged automatically by `CapabilityRouter`.

**Current grantable backend scopes** (from `sandbox/capabilities.py` and `scope_catalog.py`):

| Scope | Operations covered | Description |
|---|---|---|
| `storage` | `storage.get`, `storage.set`, `storage.delete`, `storage.list` | Per-plugin per-user key/value store |
| `core.system_metrics` | `core.system_metrics` | Read system CPU/RAM/network metrics |
| `core.notify` | `core.notify` | Send push notifications to users |

Frontend-tier scopes (`read:system-info`, `read:storage`, `read:power`) are also in the
catalog and mirrored in `client/src/lib/plugin-sandbox/scopeCatalog.ts`.

## Marketplace Index Signing (Track C)

Before the marketplace `index.json` is trusted it is verified against a **detached ed25519
signature** — the gate is fail-closed:

- An empty or unrecognised trusted-key list raises `SignatureError("no trusted public keys
  configured")` and the index is rejected before parsing.
- Implementation: `signing.py` → `verify_detached_ed25519(message, signature_b64,
  public_keys_b64)`. Pure function, no I/O.
- Called in `services/plugin_marketplace.py:get_index()` over the raw bytes before parsing.
- Trusted keys come from `settings.plugins_marketplace_public_keys` (empty default =
  fail-closed; provisioned out-of-band).
- `verify_index_signature.py` is a non-fatal standalone deploy smoke-check for the same
  verification path.

## Directory Layout

```
plugins/
├── __init__.py              # Public API (re-exports)
├── base.py                  # PluginBase ABC, PluginMetadata, PluginUIManifest, DashboardPanelSpec
├── manager.py               # PluginManager — discovery, loading, lifecycle, route mounting
├── hooks.py                 # Pluggy hook specs (on_file_uploaded, on_user_login, …)
├── events.py                # Async event bus (EventManager, queue-based, non-blocking)
├── emit.py                  # emit_hook() / emit_event() helpers for services
├── permissions.py           # PluginPermission enum, DANGEROUS_PERMISSIONS list
├── dashboard_panel.py       # Dashboard panel schemas (Gauge, Stat, Status, Chart)
├── installer.py             # Plugin install/uninstall/upgrade mechanics
├── manifest.py              # Manifest parsing and validation
├── marketplace.py           # Marketplace index fetch and caching
├── resolver.py              # Dependency/version resolution
├── core_versions.py         # Core API version table
├── core_versions.json       # Core API ↔ plugin version constraints data
├── scope_catalog.py         # Catalog of grantable capability scopes (admin scope-picker)
├── signing.py               # ed25519 detached index-signature verify (fail-closed)
├── verify_index_signature.py  # Non-fatal deploy signature smoke-check
├── sandbox/                 # Subprocess-isolation layer
│   ├── protocol.py          # Wire format (RPC message types)
│   ├── channel.py           # Framed UDS channel
│   ├── transport.py         # Async transport over the channel
│   ├── worker.py            # Worker-side RPC loop
│   ├── supervisor.py        # Host-side RPC dispatcher + capability gate
│   ├── capabilities.py      # CAPABILITY_SCOPE map + CapabilityRouter (default-deny)
│   ├── host_capabilities.py # Host-side wiring (DB, metrics, notifier) injected into router
│   ├── proxy.py             # Host-side async proxy for calling into the sandbox
│   ├── spawn.py             # Hardened subprocess spawn (sudoers wrapper → baluhost-plugin user)
│   ├── loader.py            # Module loader inside the worker process
│   └── sdk.py               # Worker-side SDK stub used by external plugins at runtime
├── sdk/                     # Plugin authoring toolkit (for external plugin developers)
│   ├── cli.py               # CLI: scaffold, validate, package
│   ├── validator.py         # Manifest and structure validation
│   ├── dry_install.py       # Simulate install without touching the host
│   └── __init__.py
├── smart_device/            # SmartDevice plugin framework
│   ├── base.py              # SmartDevicePlugin ABC
│   ├── capabilities.py      # Capability enums + protocols (Switch, Dimmer, Color, …)
│   ├── manager.py           # SmartDeviceManager (CRUD, command dispatch, SHM state)
│   ├── poller.py            # SmartDevicePoller (runs in monitoring-worker process)
│   └── schemas.py           # Pydantic request/response schemas
└── installed/               # Bundled plugin implementations
    ├── optical_drive/       # CD/DVD burning, reading, ISO browsing
    ├── storage_analytics/   # Storage usage analytics
    └── tapo_smart_plug/     # TP-Link Tapo smart plug integration with mock backend
```

## Plugin Lifecycle (Bundled)

1. **Discovery** — `PluginManager.discover_plugins()` scans `installed/` for directories with `__init__.py`
2. **Loading** — `load_plugin()` imports the module and finds the `PluginBase` subclass
3. **Permission check** — required permissions compared against granted permissions in DB (`installed_plugins` table)
4. **Activation** — `on_startup()` called, Pluggy hooks and event handlers registered, routes mounted at `/api/plugins/{name}/`
5. **Running** — requests gated by `PluginGateMiddleware` (checks enabled state + permissions)
6. **Deactivation** — `on_shutdown()` called, tasks cancelled, handlers unregistered

Enabled/disabled state is persisted in `installed_plugins`. On app start, `load_enabled_plugins()` auto-loads all enabled plugins.

---

## Bundled Plugin Authoring

The sections below describe how to write a **bundled** plugin (under `installed/`).
External marketplace plugins use the SDK (`sdk/`) and reach the host only through
capability scopes — they do not use the patterns shown here.

### Minimal Plugin

Create a directory under `installed/` with `__init__.py`:

```python
# installed/my_plugin/__init__.py
from app.plugins.base import PluginBase, PluginMetadata

class MyPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_plugin",               # Must match directory name
            version="1.0.0",
            display_name="My Plugin",
            description="Does something useful",
            author="Your Name",
            category="general",             # general | monitoring | storage | network | security | smart_device
            required_permissions=["system:info"],
        )
```

### With API Routes

```python
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status")
        async def get_status(current_user=Depends(get_current_user)):
            return {"status": "ok"}

        return router
    # Routes accessible at /api/plugins/my_plugin/status
```

### With Background Tasks

```python
from app.plugins.base import BackgroundTaskSpec

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_background_tasks(self) -> list[BackgroundTaskSpec]:
        async def check_something():
            pass  # Called every 60 s

        return [
            BackgroundTaskSpec(
                name="checker",
                func=check_something,
                interval_seconds=60,
                run_on_startup=True,
            )
        ]
```

### With Pluggy Hooks

React to system events by implementing hook methods from `BaluHostHookSpec`:

```python
from app.plugins.hooks import hookimpl

class MyPlugin(PluginBase):
    # ... metadata ...

    @hookimpl
    def on_file_uploaded(self, path: str, user_id: int, size: int, content_type=None):
        print(f"File uploaded: {path}")

    @hookimpl
    def on_user_login(self, user_id: int, username: str, ip: str, user_agent=None):
        print(f"User {username} logged in")
```

Available hooks (defined in `hooks.py`):

| Category | Hooks |
|---|---|
| **Files** | `on_file_uploaded`, `on_file_deleted`, `on_file_moved`, `on_file_downloaded` |
| **Users** | `on_user_login`, `on_user_logout`, `on_user_created`, `on_user_deleted` |
| **Backup** | `on_backup_started`, `on_backup_completed` |
| **Shares** | `on_share_created`, `on_share_accessed` |
| **System** | `on_system_startup`, `on_system_shutdown`, `on_storage_threshold` |
| **RAID** | `on_raid_degraded`, `on_raid_rebuild_started`, `on_raid_rebuild_completed` |
| **SMART** | `on_disk_health_warning` |
| **Devices** | `on_device_registered`, `on_device_removed` |
| **Smart Devices** | `on_smart_device_state_changed`, `on_smart_device_added`, `on_smart_device_removed` |
| **VPN** | `on_vpn_client_created`, `on_vpn_client_revoked` |

### With Async Events

An async event bus runs alongside Pluggy hooks for loose coupling:

```python
class MyPlugin(PluginBase):
    # ... metadata ...

    def get_event_handlers(self) -> dict[str, list]:
        async def handle_custom_event(event):
            print(f"Event: {event.name}, Data: {event.data}")

        return {
            "my_custom_event": [handle_custom_event],
            "*": [handle_custom_event],  # Wildcard: receives all events
        }
```

Emitting from services:

```python
from app.plugins.emit import emit_hook, emit_event

# Pluggy hook (synchronous, fire-and-forget)
emit_hook("on_file_uploaded", path="/test.txt", user_id=1, size=100)

# Async event (queue-based)
await emit_event("my_custom_event", {"key": "value"}, source="my_service")
```

**Two event systems compared:**

| | Pluggy Hooks | Async Events |
|---|---|---|
| **Emit** | `emit_hook("on_file_uploaded", ...)` | `await emit_event("custom", {...})` |
| **Execution** | Synchronous, same thread | Async, queue-based |
| **Subscriber** | Class implementing hook method with `@hookimpl` | Any async function via `get_event_handlers()` |
| **Wildcard** | No | Yes (`"*"` receives all events) |
| **Use case** | System events with a fixed contract | Loose coupling, plugin-to-plugin |

### With a Dashboard Panel

```python
from app.plugins.base import DashboardPanelSpec

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_dashboard_panel(self) -> DashboardPanelSpec:
        return DashboardPanelSpec(
            panel_type="gauge",   # gauge | stat | status | chart
            title="My Metric",
            icon="activity",      # Lucide icon name
            accent="from-sky-500 to-indigo-500",  # Tailwind gradient
        )

    async def get_dashboard_data(self, db) -> dict:
        # Must match the panel_type schema (see dashboard_panel.py)
        return {
            "value": "42 W",
            "meta": "1 device monitored",
            "progress": 28.0,
            "delta_tone": "live",
        }
```

Panel types and their data schemas (`dashboard_panel.py`):

| Type | Schema | Description |
|---|---|---|
| `gauge` | `GaugePanelData` | Value + progress bar + trend |
| `stat` | `StatPanelData` | Simple value + meta text |
| `status` | `StatusPanelData` | List of status items (label/value/tone) |
| `chart` | `ChartPanelData` | Value + sparkline (~30 data points) |

### With Frontend UI

```python
from app.plugins.base import PluginUIManifest, PluginNavItem

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(
            enabled=True,
            nav_items=[
                PluginNavItem(
                    path="overview",
                    label="My Plugin",
                    icon="plug",          # Lucide icon name
                    admin_only=False,
                    order=50,
                )
            ],
            bundle_path="ui/bundle.js",     # Relative to plugin directory
            styles_path="ui/styles.css",    # Optional
            dashboard_widgets=["MyWidget"],
        )
```

### With i18n / Translations

```python
class MyPlugin(PluginBase):
    # ... metadata ...

    def get_translations(self) -> dict[str, dict[str, str]]:
        return {
            "en": {"display_name": "My Plugin", "description": "..."},
            "de": {"display_name": "Mein Plugin", "description": "..."},
        }
```

## Permission System (Bundled Plugins)

Bundled plugins declare required permissions in `metadata.required_permissions`. The admin
grants these at enable time. Dangerous permissions require explicit admin confirmation.

| Permission | Description | Dangerous |
|---|---|---|
| `file:read` | Read files | No |
| `file:write` | Write files | **Yes** |
| `file:delete` | Delete files | **Yes** |
| `system:info` | Read system metrics | No |
| `system:execute` | Execute shell commands | **Yes** |
| `network:outbound` | Outbound HTTP requests | No |
| `db:read` | Read database | No |
| `db:write` | Write database | **Yes** |
| `user:read` | Read user info | No |
| `user:write` | Modify user data | **Yes** |
| `notification:send` | Send push notifications | No |
| `task:background` | Run background tasks | No |
| `event:subscribe` | Subscribe to system events | No |
| `event:emit` | Emit custom events | No |
| `device:control` | Control smart devices | No |

## SmartDevice Plugins

For IoT/smart-home devices there is a specialised base class `SmartDevicePlugin` extending `PluginBase`:

```python
from app.plugins.smart_device.base import SmartDevicePlugin, DeviceTypeInfo
from app.plugins.smart_device.capabilities import DeviceCapability

class MyDevicePlugin(SmartDevicePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_device",
            # ...
            category="smart_device",  # Required for SmartDevice plugins
        )

    def get_device_types(self) -> list[DeviceTypeInfo]:
        return [DeviceTypeInfo(
            type_id="my_device_v1",
            display_name="My Device V1",
            manufacturer="Acme",
            capabilities=[DeviceCapability.SWITCH, DeviceCapability.POWER_MONITOR],
            config_schema={"type": "object", "properties": {"api_key": {"type": "string"}}},
        )]

    async def connect_device(self, device_id: str, config: dict) -> bool:
        return True

    async def poll_device(self, device_id: str) -> dict:
        return {"switch": SwitchState(is_on=True)}

    async def poll_device_mock(self, device_id: str) -> dict:
        # Mock data for dev mode (Windows-compatible)
        return {"switch": SwitchState(is_on=True)}
```

Available capabilities:

| Capability | Protocol | Data model | `poll_device()` key |
|---|---|---|---|
| `switch` | `Switch` | `SwitchState` | `"switch"` |
| `power_monitor` | `PowerMonitor` | `PowerReading` | `"power_monitor"` |
| `sensor` | `Sensor` | `SensorReading` | `"sensor"` |
| `dimmer` | `Dimmer` | `DimmerState` | `"dimmer"` |
| `color` | `ColorControl` | `ColorState` | `"color"` |

### Capability Contracts

Capabilities are **contracts**, not just labels. When a plugin declares a capability it must:

1. **Implement the corresponding protocol** — checked at plugin startup (both web-worker and monitoring-worker). A plugin that declares but does not implement a protocol is not loaded.
2. **Return the corresponding data model from `poll_device()`** — checked each poll cycle at runtime.

All capability data must flow through the central pipeline:

```
poll_device() → Poller → SHM → Energy-Service → Mobile API
```

Plugin-own API routes must not expose capability data in a parallel format. The pipeline is the single source for the mobile app and dashboard.

**Validation behaviour:**

- **Startup**: plugin not loaded if a declared protocol is not implemented
- **Runtime**: invalid data discarded (warning logged); valid data flows normally
- **Empty return**: `poll_device()` may return `{}` (no data this cycle)
- **Partial return**: not all declared capabilities need to be present in every poll
- **Extra keys**: undeclared keys are ignored (warning logged)

SmartDevice plugins have no own routes — all interaction goes through the unified
`/api/smart-devices/` API. `SmartDevicePoller` runs in the separate monitoring-worker
process; state is communicated to the web-worker via SHM (shared memory files).

## External Plugin Model

External marketplace plugins run in a subprocess, isolated from the host:

- Discovered from a signed marketplace `index.json` (see Marketplace Index Signing above).
- Have `source="external"` in their manifest.
- Spawned in a subprocess via `sandbox/spawn.py` as the `baluhost-plugin` OS user inside a
  network namespace (loopback only).
- Communicate with the host exclusively over UDS-RPC using the protocol defined in
  `sandbox/protocol.py`.
- Request host capabilities via `cap_call` messages — `sandbox/supervisor.py` dispatches
  these through `CapabilityRouter` in `sandbox/capabilities.py`, which enforces the
  default-deny granted-scope check before any handler runs.

### Sandbox Layer (`sandbox/`)

| Module | Role |
|---|---|
| `protocol.py` | Wire format — RPC message type definitions |
| `channel.py` | Framed UDS channel (read/write) |
| `transport.py` | Async transport over the channel |
| `worker.py` | Worker-side RPC loop |
| `supervisor.py` | Host-side RPC dispatcher + capability gate |
| `capabilities.py` | `CAPABILITY_SCOPE` map + `CapabilityRouter` (default-deny enforcer) |
| `host_capabilities.py` | Host-side dependency wiring (DB, metrics, notifier) injected into the router |
| `proxy.py` | Host-side async proxy for calling into the sandbox |
| `spawn.py` | Hardened subprocess spawn via sudoers wrapper → `baluhost-plugin` user |
| `loader.py` | Module loader inside the worker process |
| `sdk.py` | Worker-side SDK stub used by external plugins at runtime |

## Plugin SDK (`sdk/`)

Authoring toolkit for external plugin developers. Not used by bundled plugins.

| Module | Purpose |
|---|---|
| `cli.py` | CLI entrypoint: scaffold, validate, package |
| `validator.py` | Manifest and plugin structure validation |
| `dry_install.py` | Simulate an install without touching the host |

## Bundled Plugins (Reference Implementations)

| Plugin | Category | Description |
|---|---|---|
| `optical_drive` | storage | CD/DVD/Blu-ray: read, rip (ISO/WAV), burn, blank |
| `storage_analytics` | storage | Storage usage analytics per user, file-type breakdown, top files |
| `tapo_smart_plug` | smart_device | TP-Link Tapo P110/P115 with Switch + Power Monitoring |

Patterns covered:

- **`optical_drive`** — own API routes, UI manifest, config schema, async job management
- **`storage_analytics`** — background tasks, Pluggy hook implementations (`@hookimpl`), periodic scans
- **`tapo_smart_plug`** — `SmartDevicePlugin` subclass, capability protocols, dashboard panel, i18n, dev/prod-mode split
