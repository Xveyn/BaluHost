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
├── installer.py         # Plugin install/uninstall/upgrade mechanics
├── manifest.py          # Plugin manifest parsing and validation
├── marketplace.py       # Marketplace index fetch and caching
├── resolver.py          # Dependency/version resolution
├── core_versions.py     # Core API version table (loaded from core_versions.json)
├── core_versions.json   # JSON data: core API ↔ plugin version constraints
├── scope_catalog.py     # Catalog of grantable capability scopes (admin scope-picker at enable time)
├── signing.py           # Track C: ed25519 detached index-signature verify (fail-closed)
├── verify_index_signature.py  # Track C: non-fatal deploy signature smoke-check
├── sandbox/             # Subprocess-isolation layer (protocol, channel, transport, worker, supervisor, capabilities, host_capabilities, proxy, spawn, loader)
├── sdk/                 # Plugin authoring toolkit (cli, validator, dry_install)
├── smart_device/        # SmartDevice plugin framework (base class, manager, poller, capabilities)
└── installed/           # Plugin implementations
    ├── optical_drive/   # CD/DVD burning, reading, ISO browsing
    ├── storage_analytics/  # Storage usage analytics
    └── tapo_smart_plug/ # TP-Link Tapo smart plug integration with mock backend
```

## Trust Tiers

Two plugin trust tiers with different isolation:

- **Bundled (in-process, fully trusted).** Plugins under `installed/`. Loaded as
  Python in the host process, old permission model (`required_permissions` granted
  in the enable modal). Full access to host APIs. Maintained in-repo.
- **External (sandboxed subprocess).** Marketplace plugins discovered as
  `source="external"`. Spawned via the hardened wrapper as the low-privilege
  `baluhost-plugin` user, in a network namespace, fail-closed if unprovisioned
  (Phase 5a). They reach the host only through default-deny **capability scopes**
  (`CAPABILITY_SCOPE`) over UDS-RPC — no host Python import, no DB/FS/shell access.
  The admin grants a subset of the plugin's requested `api_scopes` at enable time
  via the scope-picker (Phase 5b); the catalog of grantable scopes is
  `app/plugins/scope_catalog.py`. The marketplace `index.json` is verified against a
  **detached ed25519 signature (fail-closed)** before it is trusted — an empty or
  unrecognised trusted-key list causes the index to be rejected; see `signing.py`
  and `services/plugin_marketplace.py`.

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
6. Override `get_status_pills()` + `collect_status_pill()` to contribute a
   topbar status-strip pill. Only pick the plugin-local suffix (validated
   against `^[a-z0-9_]+$` on `StatusPillSpec.id`) — the core composes the
   public id as `plugin:<plugin_name>:<suffix>` and seeds its config row
   **enabled by default** (core pills seed disabled). A composed id that
   doesn't match the namespaced shape, or is too long for the `pill_id`
   column, is skipped with a warning rather than breaking the endpoint.
   The collector runs under both an exception guard and a
   `PLUGIN_COLLECTOR_TIMEOUT_SECONDS` (2s) timeout — a collector that throws
   or hangs silences only its own pill, never the whole strip. Labels come
   from `get_translations()`, resolved client-side via `resolvePluginString`,
   with `name_text`/`label_text` as literal fallbacks.
   **Operator note:** plugin enablement lives in the database and every worker
   reconciles itself against it on the next request that needs the state
   (`services/plugin_enablement.py`), so a toggle now takes effect within a few
   seconds across all four production workers — no restart needed for status
   pills, menu actions or the plugin list itself (#448). The reconcile is
   wired to five routes via `Depends(deps.reconciled_plugin_state)`:
   `list_plugins`, `get_ui_manifest`, `run_plugin_menu_action`,
   `get_statusbar_config` and `get_statusbar_state`. The Dashboard plugin
   panel (`GET /api/dashboard/plugin-panel`) is **not** one of them — it reads
   `PluginManager.get_plugin()` directly with no DB fallback, so it only
   catches up once some other reconciled route has run on the same worker.
   **One exception:** plugin HTTP routes are mounted once at startup
   (`core/lifespan.py`), so a plugin that ships its own router still needs a
   `baluhost-backend` restart before its endpoints exist. Its
   method-based contributions work immediately.
7. Override `get_ui_manifest()` with `menu_items` + `run_menu_action()` to
   contribute an action to the system (power) menu. `get_menu_items()` is not
   a separate override point: its default implementation derives the list
   from `get_ui_manifest().menu_items`, so a plugin declares its items in
   exactly one place. That single declaration is what the manifest endpoint
   (`GET /api/plugins/ui/manifest`) serves to the frontend *and* what the
   route validates an incoming `action_id` against — two declaration sites
   would drift silently, and the drift is invisible: the entry still
   renders, the click just 404s. The plugin picks only a local `id`
   (validated against `^[a-z0-9_]+$`); the core enforces the admin gate, the
   rate limit, the audit entry, the declaration check (an `action_id` not
   present in `get_menu_items()` is a 404 and never dispatches — a plugin
   whose `get_menu_items()` itself throws is treated the same way, fail
   closed, not a 500) and a `PLUGIN_MENU_ACTION_TIMEOUT_SECONDS` (20s)
   timeout. `PluginMenuItem` deliberately has **no** `admin_only` field —
   unlike `PluginNavItem`, an action executes something, so its audience is
   not the plugin's call. Failures and timeouts become `ok=false` with a
   generic message; details stay in the log. Labels come from
   `get_translations()`, resolved client-side via `resolvePluginString`.
   Blocking work belongs in `asyncio.to_thread`, otherwise the timeout
   cannot take effect. Disabled plugins are rejected by
   `PluginGateMiddleware` (403, DB-backed) — `menu-actions` is
   intentionally **not** a management route.

## SmartDevice Framework (`smart_device/`)

Base class for hardware device plugins (e.g., Tapo smart plugs). Provides:
- `SmartDevicePlugin` ABC with standardized polling/state interface
- `SmartDeviceManager` for device registration and aggregated status
- `SmartDevicePoller` for periodic device state collection (runs in monitoring worker)
- Capability system (`capabilities.py`) for feature detection
