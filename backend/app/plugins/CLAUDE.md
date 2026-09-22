# Plugin System

Extensible plugin architecture for adding features without modifying core code. Plugins can inject routes, background tasks, event handlers, dashboard panels, and frontend UI.

## Architecture

```
plugins/
├── base.py              # PluginBase ABC, PluginMetadata, PluginUIManifest, DashboardPanelSpec
├── config.py            # resolve_plugin_config() — the one read path for InstalledPlugin.config (#522)
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
└── installed/           # Bundled plugin implementations (one CLAUDE.md each)
    ├── audio_control/      # Volume, output device and per-app mixer of the desktop session (pactl)
    ├── bluetooth/          # BlueZ over D-Bus: devices, scan, pairing with an own agent
    ├── display_output/     # KWin output selection and video mode (kscreen-doctor) + brightness (powerdevil over D-Bus)
    ├── optical_drive/      # CD/DVD burning, reading, ISO browsing (own router)
    ├── steam_gaming/       # Status pill, session ledger, Gaming-Mode menu action, game launch routes
    ├── storage_analytics/  # DEMO ONLY — every number is hard-coded, see its CLAUDE.md
    └── tapo_smart_plug/    # TP-Link Tapo smart plugs via the SmartDevice framework
```

Each bundled plugin has its own `CLAUDE.md` with its layout, invariants and
pitfalls. Read that one before changing a plugin; this file covers the framework
they plug into.

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
5. Override `get_dashboard_panel()` + `get_dashboard_data()` for dashboard integration.
   `DashboardPanelSpec.admin_only=True` beschränkt ein Panel auf privilegierte
   Nutzer. Durchgesetzt wird das **im Core** an zwei Stellen, nicht im Plugin:
   in `api/routes/dashboard.py` (`is_privileged`) und in
   `services/dashboard_panel_bridge.py`, das seinen WebSocket-Broadcast dann
   mit `broadcast_typed(..., admins_only=True)` fährt. Beides ist nötig — der
   Bridge schiebt dieselben Daten unabhängig von der Route an verbundene
   Clients. Panel-Icons werden im Frontend dynamisch aus lucide aufgelöst
   (kebab-case → PascalCase, Fallback `Plug`), ein neues Icon braucht also
   keine Core-Änderung.
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
   `get_statusbar_config` and `get_statusbar_state`. The Dashboard plugin panel
   (`GET /api/dashboard/plugin-panel`) is one of them as well
   (`api/routes/dashboard.py`), so it catches up on the same request like the
   other five. The five enablement-dependent smart-device routes declare it too
   (`api/routes/smart_devices.py`: `list_device_types`, `discover_devices`,
   `create_device`, `execute_command`, `import_device_history`) — see the
   SmartDevice section below. The remaining smart-device routes deliberately do
   not: they read rows and SHM only and never consult the plugin registry.
   **One exception:** plugin HTTP routes are mounted once at startup
   (`core/lifespan.py`), so a plugin that ships its own router still needs a
   `baluhost-backend` restart before its endpoints exist. Its
   method-based contributions work immediately. `GET /api/plugins/{name}`
   surfaces this as `PluginDetailResponse.restart_required` — true when the
   plugin contributes a router that was not part of the set
   `PluginManager.get_router()` mounted at startup
   (`PluginManager.router_restart_required()`); always false for plugins
   without a router and for external (sandboxed) plugins, whose requests are
   routed dynamically through the catch-all proxy with no restart needed.
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
   `run_menu_action()` bekommt zusätzlich `user` und `client_host` (keyword-only,
   Default `None`) — den authentifizierten Aufrufer und dessen IP. Damit kann
   eine Aktion einen privilegierten Seiteneffekt beim Core anfragen, der ihn
   nach **seinen** Regeln prüft (siehe
   `services/power/session_lock.unlock_if_permitted()`), statt sich auf den
   impliziten Vertrag „die Route hat Admin schon geprüft" zu verlassen.
   **Bewusster API-Bruch:** Ein Plugin, das `run_menu_action` mit der alten
   Signatur `(self, action_id, db)` überschreibt, scheitert seitdem mit
   `TypeError`. Verworfen wurde ein Kompatibilitäts-Fallback im Dispatch: ein
   `TypeError` aus dem Plugin-Rumpf wäre von einem Signatur-Mismatch nicht
   unterscheidbar, und ein Retry würde eine Aktion, die Displays schaltet und
   Prozesse startet, ein zweites Mal ausführen.
8. Override `get_notification_events()` to contribute notification events, and
   `get_background_tasks()` if something needs to emit them on an interval. Each
   `PluginEventSpec` picks only a local `id` (`^[a-z0-9_]+$`); the core
   namespaces it to `plugin:<name>:<suffix>`, **derives the category from the
   plugin name** (the category is the delivery routing key — a plugin-chosen one
   would reach users routed for that category), and delivers through the
   existing machine (persistence, routing, push, WebSocket). Fire an event with
   `services.notifications.plugin_events.emit_plugin_event(plugin_name, event_id,
   entity_id="", **kwargs)`; it enforces the declared `cooldown_seconds` itself
   (the async emit path has none) and delivers to `default_target` (`admins` by
   default — a plugin cannot widen its own reach). `default_target="all_users"`
   delivers to every active user **unrouted** — the category-routing filter
   that scopes the `admins` default does not apply on that branch — so it
   must stay restricted to fully-trusted bundled plugins. Texts are server-rendered in
   one language (like the core events), so they are plain templates, not
   `resolvePluginString` keys. Background tasks run **primary-only** (#448), so a
   poller needs no cross-worker guard.
   That is **enforced in one place**: `PluginManager._start_background_tasks()`
   returns early unless `lifespan.IS_PRIMARY_WORKER` (#465). The
   `start_background_tasks` parameter stays a veto a caller can exercise, but
   it is no longer what makes primary-only true — the enable endpoint never
   passed it, so a UI toggle started the poller a second time on whichever
   worker answered the request, and the duplicate notifications followed from
   the cooldown cache being process-local. **Do not re-add the gate at a call
   site**; two places that must agree is how this broke.
   Consequence of the gate: when a secondary worker handles the toggle (three
   times out of four), only the primary can start the task. It does so on its
   next reconcile, which no longer depends on request traffic — the primary
   runs `_reconcile_plugin_enablement()` every
   `_PLUGIN_RECONCILE_INTERVAL_SECONDS` (15s, `core/lifespan.py`), so the wait
   is bounded even with no browser tab open. Before that loop existed, the
   catch-up rode on the reconcile-wired routes the frontend polls, and those
   stop polling while the tab is hidden.
9. A plugin that only contributes a topbar control, a status pill or a menu
   action still overrides `get_ui_manifest()` (`PluginUIManifest(enabled=True)`,
   no `nav_items`) — without a manifest the frontend treats it as disabled and
   nothing renders. It needs **no** `ui/` directory. `GET /api/plugins/ui/manifest`
   reports `has_page` per plugin, and `/plugins/<name>` only frames the sandbox
   host when it is true (#454). `has_page` comes from
   `PluginManager.has_ui_page()`, which checks the bundle the `host.html`
   bootstrap would actually load (`ui_bundle_name()`: `plugin.json` `ui.bundle`,
   else `bundle.js`) — `PluginUIManifest.bundle_path` is not what the
   bootstrap reads, so do not rely on it to decide whether a page exists.

## Plugin Configuration (#522)

`PUT /api/plugins/{name}/config` validates against `get_config_schema()` and
stores the result in `InstalledPlugin.config`. **Nothing is pushed into the
plugin on save**, deliberately: a hook called from the route would reach only
the worker that answered the request, not the other three nor the monitoring
worker's poller instances (same trap as #448/#459/#465).

A plugin reads its config with `self.get_config(db)` when it needs it. That is
the **only** read path (`app/plugins/config.py`): it validates the stored row,
fills fields missing from older rows with their defaults, and falls back to
`get_default_config()` on a missing, empty or invalid row. Both
`GET /api/plugins/{name}` (the details route the settings form actually uses)
and `GET /api/plugins/{name}/config` serve `get_config(db)`, so the settings
form shows what the plugin actually uses. **Do not read `InstalledPlugin.config`
directly** — that is how `optical_drive` ended up ignoring saved values while
`tapo_smart_plug` honoured them. The one documented exception is the details
route's external-plugin branch, which has no in-process instance to call
`get_config()` on and so still serves the raw stored row (#522).

External (sandboxed) plugins have no config channel at all: `get_plugin()`
only knows bundled plugins, so the route 404s for them, and the sandbox has no
DB access and no config scope.

## SmartDevice Framework (`smart_device/`)

Base class for hardware device plugins (e.g., Tapo smart plugs). Provides:
- `SmartDevicePlugin` ABC with standardized polling/state interface
- `SmartDeviceManager` for device registration and aggregated status
- `SmartDevicePoller` for periodic device state collection (runs in monitoring worker)
- Capability system (`capabilities.py`) for feature detection

**The registry follows enablement — one place only (#459).**
`SmartDeviceManager._plugins` is what decides whether `/api/smart-devices/…`
can reach a device, and `/api/smart-devices/…` is a **core** route that
`PluginGateMiddleware` does not cover. So the registry is written in exactly one
place: `PluginManager.enable_plugin()` mirrors a `SmartDevicePlugin` into it,
`disable_plugin()` drops it again (unconditionally, before every early return).
Startup, the toggle endpoint and the per-worker reconcile all route through
those two methods and therefore agree by construction — **do not add a second
registration pass anywhere.** Four parallel ones is what left a disabled
`tapo_smart_plug` switchable on the three workers that had not handled the
toggle.

Consequently `get_smart_device_manager()` is a plain singleton accessor and
does **no** database work; it used to run its own synchronous `SessionLocal()`
read on the request path (three of its callers are `async def`) that only ever
added plugins, never removed them, and skipped `on_startup()` for what it
registered. Cross-worker catch-up is the reconcile's job, declared by the five
routes listed in the Operator note above.

The poller in the monitoring worker is a separate process with its own
registry, loaded from the DB in `poller.py:_load_plugins()` — unaffected by all
of the above.
