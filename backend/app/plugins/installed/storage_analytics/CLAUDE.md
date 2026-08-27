# Storage Analytics Plugin

> **Read this first: the numbers are fake.** Every value this plugin serves is
> hard-coded in `_perform_storage_scan()` — 1234 files, 50 GB, two invented users
> named `admin`/`user`, a fixed `.jpg/.mp4/.pdf/.docx` distribution and three
> made-up "top files". Nothing scans the filesystem, nothing reads the database,
> and the two hook implementations (`on_file_uploaded`, `on_file_deleted`) are
> `pass`. It is a **reference/demo plugin** for the plugin API, not a feature.

Do not treat its output as data, do not wire it into anything, and do not "fix a
bug" in the numbers. If real analytics are wanted, that is a new implementation —
the honest storage figures already live in `services/files/` and the
`storage-breakdown` endpoint (`backend/tests/test_storage_breakdown.py`).

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md`.

## What it does demonstrate

It is the most complete example of the **classic bundled-plugin surface** in one
small file, which is why it is worth keeping:

| `PluginBase` hook | Used for |
|---|---|
| `get_router()` | Five routes under `/api/plugins/storage_analytics/` |
| `on_startup` / `on_shutdown` | Warm and clear the module-level cache |
| `get_background_tasks()` | `storage_scan` every 6 h, `run_on_startup=False` |
| `get_ui_manifest()` | A `PluginNavItem` (`analytics`, `bar-chart-2`, order 50) + `bundle_path` + `dashboard_widgets` |
| `get_config_schema()` / `get_default_config()` | `StorageAnalyticsConfig` (Pydantic → settings form) |
| `@hookimpl` | Pluggy hooks `on_file_uploaded` / `on_file_deleted` |

## Layout

| File | Contents |
|---|---|
| `__init__.py` | Everything: config + response schemas, the fake scan, the router, `StorageAnalyticsPlugin` |
| `ui/bundle.js` | Plugin UI, hand-written against the sandbox runtime (`window.BaluHost`) |
| `plugin.json` | Marketplace manifest |

## Things that will bite you

- **Contributes a router**, so it is mounted once at startup
  (`core/lifespan.py`). Enabling it at runtime leaves
  `/api/plugins/storage_analytics/*` at 404 until `baluhost-backend` restarts;
  `GET /api/plugins/storage_analytics` reports this as `restart_required`.
- **`_storage_cache` is a module global**, so in production each of the four
  Uvicorn workers holds its own copy with its own `last_scan` timestamp. Two
  identical requests can report different values. Same for the background task,
  which runs primary-only (#448) and therefore only ever refreshes one worker's
  cache.
- **`on_shutdown()` calls `_storage_cache.clear()`**, which removes the keys
  entirely rather than resetting them to `None`. The `if _storage_cache["stats"]
  is None` guards in the routes would then raise `KeyError`. Only reachable if a
  request is served after shutdown, but do not copy this pattern.
- `StorageAnalyticsConfig` is declared but never read — the 6 h interval and the
  30-day retention in the code are hard-coded, not driven by the config.
- The routes use `Depends(get_current_user)` only: **any** logged-in user sees the
  (fake) per-user breakdown. If this ever serves real data, that gate has to
  become `get_current_admin` or a per-user filter, and the endpoints need a
  `@limiter.limit(...)` — they currently have none, and there is no global
  fallback limit (see `.claude/rules/security-agent.md`).
- `min_baluhost_version` in `plugin.json` is `1.29.0`; its `homepage` points at
  the external `BaluHost-Plugin-Market` repo, while `PluginMetadata.homepage` in
  the code points somewhere else. The manifest is not read for bundled discovery —
  the manager finds the `PluginBase` subclass in `__init__.py` — so the two drift
  silently.

## Tests

**None.** `backend/tests/plugins/test_plugins.py` and `test_plugin_manager*.py`
build their own throwaway plugins under `tmp_path`, so nothing in the suite loads
this package. Any change here is unverified until you add a test.
