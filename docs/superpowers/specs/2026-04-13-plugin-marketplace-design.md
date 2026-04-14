# Plugin Marketplace & External Plugin Distribution

**Status:** Spec
**Date:** 2026-04-13
**Scope:** Move plugins out of the BaluHost codebase into a separately-distributed format. Add a Marketplace tab in the UI from which any user can browse, install, update, and remove third-party plugins. Keep the existing in-process plugin runtime, but make discovery, manifests, and Python dependencies first-class.

## Problem

Today, plugins live at `backend/app/plugins/installed/`, are imported as part of the `app.plugins.installed.*` Python package, and ship inside the BaluHost release. This works for the three official plugins (`optical_drive`, `storage_analytics`, `tapo_smart_plug`), but it has hard limits the moment a third party wants to ship a plugin:

- **Discovery is path-hardcoded** (`manager.py:26`). External directories cannot be scanned.
- **Loader is package-name-hardcoded** (`manager.py:140-167` builds the module name `app.plugins.installed.{name}` and patches `sys.modules`). Plugins outside that path cannot be imported.
- **Metadata is only available after `import`** — to know what a plugin requires, you have to execute its code first. Unsuitable for a marketplace listing.
- **Python dependencies are global.** `plugp100` (used only by `tapo_smart_plug`) sits in the core `pyproject.toml`. Community plugins have nowhere to declare their own deps.
- **`min_baluhost_version` exists in the metadata but is never enforced.**
- **No package format** — there is no `.zip`/`.whl`/`.bhplugin` artifact, no checksum, no signature, no index.

Goal of this spec: define what changes so a hobby developer can publish a plugin to a Git repo, BaluHost can list it in a Marketplace tab, and a user can install it with one click — including transparent handling of Python dependency conflicts.

## Goals

- External plugins live **outside** the BaluHost installation directory and survive Core updates.
- A static `plugin.json` manifest lets us read metadata without executing plugin code.
- A central Marketplace index (one JSON file in a Git repo) lists all available plugins with versions and checksums.
- Plugins may declare their own pure-Python dependencies. They are installed in an **isolated per-plugin `site-packages/`** so they don't pollute the Core environment.
- Dependency conflicts (with Core or with other plugins) are detected **before download** and shown in the UI with an actionable message — never as a stack trace.
- The existing three official plugins keep working with minimal changes. They migrate to the new layout but stay bundled inside the Core release.
- The `window.BaluHost` frontend SDK and `bundle.js` distribution model do **not** change — they already work across the marketplace boundary.

## Non-Goals

- **Process isolation / sandboxing.** Plugins run in the same process as the Core, just like today. A future spec may add subprocess-based plugins for high-risk capabilities; this one does not.
- **C-extension dependencies.** Plugins must declare pure-Python deps only. The validator rejects packages with native build steps. We accept that this excludes a class of libraries; the trade-off is install reliability across architectures (x86_64 NAS, ARM Rock Pi).
- **Multi-version coexistence of a single dep.** If `plugin_A` needs `httpx>=0.30` and `plugin_B` needs `httpx<0.29`, the resolver refuses the install. We do not load two `httpx` versions side by side.
- **Decentralized / arbitrary-URL marketplaces in v1.** v1 supports exactly one official index URL (configurable). v2 may add user-added indexes.
- **Plugin signing in v1.** v1 verifies SHA-256 checksums from the index. Cryptographic signatures are tracked as a follow-up.
- **Frontend SDK changes.** The current `window.BaluHost` global, `ui/bundle.js` convention, and `serve_plugin_asset` route are sufficient.

## Architecture

```
┌──────────────────────────────────────┐         ┌──────────────────────────────┐
│ baluhost-plugins (Git repo)          │         │ BaluHost backend             │
│                                      │         │                              │
│  /plugins/                           │   CI    │  PluginRegistryService       │
│    weather_station/                  │  build  │   ├─ fetch index.json        │
│      plugin.json                     │  ────▶  │   ├─ resolve dep conflicts   │
│      __init__.py                     │         │   ├─ download .bhplugin      │
│      ui/bundle.js                    │         │   ├─ verify checksum         │
│      requirements.txt                │         │   ├─ pip install --target    │
│    co2_monitor/ ...                  │         │   └─ extract to dist dir     │
│                                      │         │                              │
│  /dist/                              │         │  PluginManager (existing,    │
│    index.json   ◀───── published ────┤         │   loader gets multi-path     │
│    weather_station-1.2.0.bhplugin    │         │   support + manifest-first   │
│    co2_monitor-0.4.1.bhplugin        │         │   discovery)                 │
└──────────────────────────────────────┘         └──────────────────────────────┘
                  ▲                                            │
                  │                                            ▼
                  │                                  /var/lib/baluhost/plugins/
                  │                                    weather_station/
            user clicks                                    plugin.json
            "Install" in                                   __init__.py
            BaluHost UI                                    ui/bundle.js
                                                           site-packages/
                                                             anyio/
                                                             h11/
                                                             ...
```

Two distinct directories for plugin sources:

- **Bundled / official** — `backend/app/plugins/installed/`. The three current plugins stay here. They are part of the BaluHost release artifact.
- **External / marketplace** — `/var/lib/baluhost/plugins/` on Linux prod, `backend/dev-plugins/` in dev. Configurable via the `BALUHOST_PLUGINS_DIR` env var (settings field `plugins_external_dir`). Survives Core updates and Core reinstalls. The directory is created and `chown`ed by the install module — see *Deployment Changes* below.

The `PluginManager` is taught to scan **both** directories and merge results. Bundled plugins are immutable from the UI ("Bundled" badge, no uninstall button). External plugins are full CRUD.

## Directory Layout

### Plugin (on disk, after install)

```
/var/lib/baluhost/plugins/weather_station/
├── plugin.json              # static manifest, NEW
├── __init__.py              # PluginBase subclass (unchanged shape)
├── service.py
├── ui/
│   └── bundle.js            # served by existing /api/plugins/{name}/ui/...
├── requirements.txt         # pure-Python deps, pinned
└── site-packages/           # isolated deps, populated by `pip install --target`
    ├── pyowm/
    └── ...
```

`site-packages/` is **owned by BaluHost** — created at install time, deleted at uninstall, never edited by the user.

### Core (after this spec lands)

```
backend/app/plugins/
├── base.py                  # unchanged (PluginBase, PluginMetadata, ...)
├── manager.py               # CHANGED: multi-path discovery, manifest-first scan
├── manifest.py              # NEW: load + validate plugin.json
├── resolver.py              # NEW: dependency conflict resolver
├── installer.py             # NEW: download / verify / extract / pip install
├── installed/               # bundled official plugins (unchanged location)
│   ├── optical_drive/
│   ├── storage_analytics/
│   └── tapo_smart_plug/
└── ...
```

## Plugin Manifest (`plugin.json`)

The manifest is the single source of truth for marketplace listings, dependency resolution, and version checks. It is **read without executing plugin code**.

```json
{
  "manifest_version": 1,
  "name": "weather_station",
  "version": "1.2.0",
  "display_name": "Weather Station",
  "description": "Pulls local weather and exposes a dashboard panel.",
  "author": "Jane Hobby",
  "homepage": "https://github.com/jane/baluhost-weather",
  "category": "monitoring",

  "min_baluhost_version": "1.30.0",
  "max_baluhost_version": null,

  "required_permissions": ["network:outbound", "system:info"],
  "plugin_dependencies": [],

  "python_requirements": [
    "pyowm==3.3.0",
    "tzdata>=2024.1"
  ],

  "entrypoint": "__init__.py",
  "ui": {
    "bundle": "ui/bundle.js",
    "styles": null
  },

  "checksum": null
}
```

Notes:

- The `metadata` Pydantic model in `base.py` is reused 1:1 — the manifest is just a serialized form. A new `PluginManifest` Pydantic class in `manifest.py` validates the file and produces a `PluginMetadata` instance.
- `manifest_version: 1` lets us evolve the schema without breaking old plugins.
- `python_requirements` uses standard PEP 508 strings. Resolver and `pip install --target` both understand them natively.
- `checksum` is null in the on-disk file but populated in the marketplace index (see below).
- Names of fields that already exist in `PluginMetadata` (`name`, `version`, `display_name`, `category`, `required_permissions`, `min_baluhost_version`) are preserved — no renaming.

## Marketplace Index Format

A single static `index.json` file, published to a known URL (e.g. GitHub Pages `https://plugins.baluhost.dev/index.json`). Built by CI in the `baluhost-plugins` repo.

```json
{
  "index_version": 1,
  "generated_at": "2026-04-13T12:00:00Z",
  "plugins": [
    {
      "name": "weather_station",
      "latest_version": "1.2.0",
      "versions": [
        {
          "version": "1.2.0",
          "min_baluhost_version": "1.30.0",
          "max_baluhost_version": null,
          "python_requirements": ["pyowm==3.3.0", "tzdata>=2024.1"],
          "required_permissions": ["network:outbound", "system:info"],
          "download_url": "https://plugins.baluhost.dev/weather_station-1.2.0.bhplugin",
          "checksum_sha256": "a3f1e8...",
          "size_bytes": 184320,
          "released_at": "2026-04-10T08:00:00Z"
        },
        { "version": "1.1.0", "...": "..." }
      ],
      "display_name": "Weather Station",
      "description": "Pulls local weather and exposes a dashboard panel.",
      "author": "Jane Hobby",
      "homepage": "https://github.com/jane/baluhost-weather",
      "category": "monitoring"
    }
  ]
}
```

A `.bhplugin` file is just a renamed `.zip` containing the plugin directory (everything in the on-disk layout *except* `site-packages/`).

## Dependency Model

There are two kinds of Python packages a plugin can touch:

1. **Shared (Core-provided)** — anything already in `backend/pyproject.toml`: `fastapi`, `sqlalchemy`, `pydantic`, `httpx`, `cryptography`, `pluggy`, etc. Plugins are **expected** to import these directly. They may declare them in `python_requirements` only as a *compatibility constraint* — the resolver checks the constraint against the Core version and never installs a separate copy.
2. **Isolated (plugin-private)** — anything else. Installed via `pip install --target /var/lib/baluhost/plugins/{name}/site-packages/`. The Core pre-pends the plugin's `site-packages/` to `sys.path` once, at install time, in a stable order — see Loader Changes.

The split is **automatic**: at install time the resolver looks at each entry in `python_requirements`, asks "is this name in `core_versions.json`?", and routes it accordingly. The plugin developer doesn't have to label them.

### `core_versions.json`

Generated at Core build time from `pip freeze` of the locked Core environment. Shipped inside the BaluHost release artifact at `backend/app/plugins/core_versions.json`. Looks like:

```json
{
  "baluhost_version": "1.30.0",
  "python_version": "3.11",
  "packages": {
    "httpx": "0.27.2",
    "cryptography": "43.0.7",
    "pydantic": "2.6.4",
    "...": "..."
  }
}
```

The resolver loads this once at startup and on every Core update.

## Resolver

A single function — `resolve_install(plugin_manifest, core_versions, installed_plugins) -> ResolveResult` — used in three places:

1. **Marketplace UI**, before the user clicks Install: dry-run, show conflicts, gate the button.
2. **`installer.py`**, before downloading: hard gate, refuses to install on conflict (unless `force=True`).
3. **Background check** after a Core update: re-run for every installed plugin; mark broken ones with `last_load_error` and notify.

```python
@dataclass
class Conflict:
    package: str
    requirement: str           # what the plugin asked for
    found: str                 # version actually present
    source: Literal["core", "plugin:other_name"]
    suggestion: str            # human-readable fix hint

@dataclass
class ResolveResult:
    ok: bool
    shared_satisfied: list[str]      # core deps ok
    isolated_to_install: list[str]   # will go into site-packages/
    conflicts: list[Conflict]
```

Logic per requirement:

1. Parse PEP 508 → `(name, specifier)`.
2. If `name` is in `core_versions.packages`:
   - `specifier.contains(core_version)` → mark as `shared_satisfied`.
   - else → emit `Conflict(source="core")` with suggestion "Update BaluHost to a version where {name} satisfies {specifier}".
3. Else, look at every other **enabled** plugin's `python_requirements`:
   - If another plugin declares the same `name` with an **incompatible** specifier → `Conflict(source="plugin:{other}")` with suggestion "Plugin '{other}' requires {their_specifier}; cannot coexist".
   - Else → mark as `isolated_to_install`.
4. Bonus: reject any `name` that points to a known C-extension package list (small whitelist of "no, this won't work" — `numpy`, `pillow`, `psycopg2`, `cryptography`, …). This is just a friendly early-exit; the real failure mode is `pip install --target` choking on the build, but the early check produces a much better message.

### `min_baluhost_version` enforcement

Done in the same pass. If `manifest.min_baluhost_version > core_versions.baluhost_version`, the result is `ok=False` with a single conflict explaining the mismatch.

## Loader Changes

The current `manager.py` is moderately invasive but localized. Three changes:

### 1. Multi-path discovery

```python
PLUGINS_DIRS: list[Path] = [
    Path(__file__).parent / "installed",            # bundled (immutable)
    Path(settings.plugins_external_dir),            # external (~/.baluhost/plugins)
]
```

`discover_plugins()` iterates both, prefers manifest-first scan: a directory is a plugin if it contains `plugin.json` **or** (legacy) `__init__.py`. For each, it constructs a `DiscoveredPlugin(name, path, source: "bundled"|"external", manifest|None)`.

### 2. Manifest-first metadata

`get_all_plugins()` no longer needs to import code to fill the marketplace listing. It reads `plugin.json`, validates with the `PluginManifest` model, and returns metadata directly. **Importing only happens on enable.** This fixes the security smell and makes the Marketplace tab cheap.

### 3. Per-plugin `site-packages/` on `sys.path`

In `load_plugin()`, before `spec.loader.exec_module(module)`:

```python
sp = plugin_path / "site-packages"
if sp.exists() and str(sp) not in sys.path:
    sys.path.insert(0, str(sp))
```

The order of insertion is stable (alphabetical by plugin name) and only happens for plugins enabled in the DB. Because the resolver already guaranteed no version conflicts across enabled plugins, prepending is safe.

External plugins are loaded under a new module namespace `baluhost_plugins.{name}` (so they don't collide with `app.plugins.installed.{name}`). The `sys.modules` registration trick in the current loader is generalized to support either parent package.

## Install / Uninstall / Update Flow

### Install

1. UI: user clicks Install on `weather_station 1.2.0`.
2. Backend `POST /api/plugins/marketplace/install` with `{name, version}`.
3. `installer.install()`:
   1. Look up entry in cached `index.json`.
   2. Run `resolver.resolve_install(...)` — if `not ok`, return 409 with the conflict list.
   3. `httpx.get(download_url)` → bytes in memory (size capped at e.g. 50 MB).
   4. Verify `sha256(bytes) == checksum_sha256` → 422 on mismatch.
   5. Extract `.bhplugin` (zip) into a temp dir, validate that `plugin.json` matches the index entry.
   6. `pip install --target {temp}/site-packages --no-deps --only-binary=:all: --platform={target_platform} --python-version={target_py} --implementation cp --abi cp{XY} {each isolated requirement}` (`--no-deps` keeps the surface small — transitive deps must be declared explicitly, the validator enforces this; `--only-binary=:all:` plus the platform/abi flags are required together to actually prevent pip from falling back to a source build, especially on ARM).
   7. `os.rename` temp dir into `/var/lib/baluhost/plugins/{name}/`.
   8. Insert/update `InstalledPlugin` row, `is_enabled=False` initially. UI prompts the user to grant permissions and enable.
4. Frontend re-fetches the plugin list. New plugin appears with "Disabled — review permissions".

### Uninstall

1. UI dialog asks: *"Remove plugin data as well? (DB tables, files, config) — default: Keep"*. Two buttons: **Keep data** (default, recommended) and **Delete everything**.
2. Backend disables the plugin (`disable_plugin()`), calling `on_shutdown()`, removing background tasks, etc.
3. Removes the `/var/lib/baluhost/plugins/{name}/` directory entirely (the code + isolated `site-packages/`).
4. If the user chose **Delete everything**, also calls a new optional `PluginBase.on_uninstall(db)` hook that lets the plugin drop its tables and files. Default implementation is a no-op. Plugin data outside that hook (e.g. arbitrary files written into shared dirs) is the plugin author's responsibility to clean up there.
5. Removes the `InstalledPlugin` row.
6. Bundled plugins reject this with 403.

### Update

1. Periodic background job hits `index.json`, compares versions, populates `available_update` on each `InstalledPlugin`.
2. UI shows an "Update available" badge.
3. User clicks Update → `installer.update()`:
   1. Resolve against the *new* manifest.
   2. If conflict → show diff ("This update bumps `httpx` to 0.30 — incompatible with current Core 1.30").
   3. Else → install to a sibling temp dir, disable old plugin, swap directories, enable new plugin.

## Conflict UX

Three touchpoints, all backed by the same `ResolveResult`:

1. **Marketplace listing** (per-plugin card): if any version is incompatible with the current Core, show a small ⚠️ badge. Tooltip: "Requires BaluHost ≥ 1.31".
2. **Install dialog**: if `not ok`, the Install button is disabled and the dialog body lists each `Conflict` with its `suggestion`. A small "Show technical details" disclosure shows the raw PEP 508 strings.
3. **Background check after Core update**: produces an in-app notification:

> 🔌 BaluHost was updated to 1.31.0
> 1 plugin is now broken: **weather_station 1.2.0** — needs `httpx<0.29`, current is `0.30.1`.
> [Update plugin] [Open marketplace]

The `last_load_error` column on `InstalledPlugin` (new) holds the structured conflict so the Plugins page can render it inline instead of a generic "failed to load".

## SDK Support for Plugin Authors

Two additions to the existing planned `baluhost-sdk` (see `2026-03-24-plugin-sdk-design.md`):

1. **`baluhost-sdk validate`** gains manifest checks: `plugin.json` exists, schema valid, declared `python_requirements` are PEP 508-parseable, no C-extensions in requirements, `min_baluhost_version` is set.
2. **`baluhost-sdk dry-install <plugin_dir>`** runs the full resolver against the *current* Core environment and prints the same conflict report the UI would. Hobby devs run this locally before publishing.

## Migration of Existing Plugins

The three bundled plugins keep working with one mechanical change each: add a `plugin.json` next to `__init__.py`, generated from the existing `metadata` property. Their Python deps stay in core `pyproject.toml` — bundled plugins are allowed to assume the Core environment. No code change to `optical_drive` or `storage_analytics`.

`tapo_smart_plug` is the interesting case: `plugp100` stays in core `pyproject.toml` (because the bundled plugin uses it), but the manifest also lists it under `python_requirements` as `"plugp100>=5.0.0,<6.0.0"`. The resolver sees `plugp100` is in `core_versions.json`, marks it `shared_satisfied`, and never tries to install it twice.

## Resolved Decisions

1. **External plugins dir:** `/var/lib/baluhost/plugins/` in prod (FHS-correct pairing with `/opt/baluhost/` for code). Configurable via `BALUHOST_PLUGINS_DIR` env var, exposed as `settings.plugins_external_dir`. Dev fallback: `backend/dev-plugins/`. Rationale: avoids tying plugin state to a personal `$HOME`, survives a future switch to a dedicated `baluhost` system user, and stays compatible if the systemd unit ever adds `ProtectHome=yes` for hardening.
2. **Uninstall data handling:** dialog asks the user, **Keep data** is the default. A new optional `PluginBase.on_uninstall(db)` hook is invoked only when the user picks "Delete everything".
3. **`pip install` mechanism:** subprocess (`{venv}/bin/pip install --target ...`), not `pip._internal`. The UI shows a progress indicator and documents the typical 5–10 s wait per plugin install. Failures from the subprocess are captured and surfaced as structured errors in the install dialog.
4. **Multi-arch wheels:** the installer always passes `--only-binary=:all: --platform={target} --python-version={py} --implementation cp --abi cp{XY}` together. Without `--only-binary=:all:` pip silently falls back to source builds even when platform flags are set — this is the most common ARM-install footgun and we explicitly prevent it. The `target_platform` is read from `core_versions.json` (populated at Core build time).
5. **Marketplace search:** client-side filter over the cached `index.json` in v1. The index file is expected to stay well below 1 MB even with hundreds of plugins. v2 may add a server-side search API if needed.

## Deployment Changes

The new external plugins directory needs one-time setup at install time. Concrete edits:

- **`deploy/install/modules/`**: a new module (or addition to an existing one — likely `30-directories.sh` or a fresh `25-plugins-dir.sh`) creates `/var/lib/baluhost/plugins/`, sets ownership to `$BALUHOST_USER:baluhost`, mode `0755`. Idempotent.
- **`deploy/install/templates/baluhost-backend.service`**: no `ProtectHome` change yet (we don't have it set today), but add `ReadWritePaths=/var/lib/baluhost/plugins` *if* and when systemd hardening (`ProtectSystem=strict`) is introduced later. Tracked as a follow-up — not blocking this spec.
- **`deploy/install/templates/env.production`**: add `BALUHOST_PLUGINS_DIR=/var/lib/baluhost/plugins` so the value is explicit, not implicit from a default.
- **Uninstall script** (if one exists): leave `/var/lib/baluhost/plugins/` alone by default, mirroring how Postgres data isn't wiped on uninstall. Add a `--purge` flag for the "really delete everything" case.

## Implementation Phases

Concrete order of work, each phase shippable on its own:

1. **Loader v2** — multi-path discovery + manifest-first scan + `baluhost_plugins.*` namespace + `plugin.json` for the three bundled plugins. No marketplace yet. Existing plugin tests still pass.
2. **Resolver + `core_versions.json`** — pure functions, fully unit-testable, no network, no install.
3. **`installer.py`** — download, verify, `pip install --target`, atomic swap. Tested against a fake local index served from a temp dir.
4. **Marketplace API endpoints** — `GET /api/plugins/marketplace/index`, `POST /api/plugins/marketplace/install`, `POST /api/plugins/marketplace/update`, `DELETE /api/plugins/marketplace/{name}`.
5. **Marketplace UI tab** — list, search, install dialog, conflict rendering, update badges.
6. **`baluhost-plugins` Git repo + CI** — directory layout, build script that emits `index.json` and `.bhplugin` artifacts, GitHub Pages publish.
7. **SDK additions** — `validate` manifest checks, `dry-install` command.
8. **Background update check + notification routing.**
