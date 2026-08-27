# Optical Drive Plugin

Bundled (in-process, fully trusted) plugin: detect optical drives, browse/rip/burn
discs and ISOs, manage the resulting jobs. Ships its own FastAPI router and a
hand-written UI bundle.

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md` —
this file only covers what is specific to this plugin.

## Layout

| File | Lines | Contents |
|---|---|---|
| `__init__.py` | 429 | `OpticalDrivePlugin`, and the **entire** router (built inside `get_router()`) |
| `service.py` | 614 | `OpticalDriveService`: drive detection, validation, dev-mode simulation, job bookkeeping |
| `reading.py` | 278 | `ReadingMixin` — ISO copy (`dd`), audio rip (`cdparanoia`) |
| `burning.py` | 330 | `BurningMixin` — burn ISO / audio (`wodim`), blank, `dvd+rw-mediainfo` |
| `browsing.py` | 768 | `BrowsingMixin` — disc + ISO listing (`isoinfo`, `7z`), extract, preview |
| `models.py` | 236 | Pydantic request/response models, `MediaType`/`JobType`/`JobStatus` enums, `OpticalDriveConfig` |
| `ui/bundle.js` | 894 | Plugin UI, hand-written against the sandbox runtime (`window.BaluHost`) |
| `plugin.json` | — | Marketplace manifest (see "plugin.json vs. metadata") |

`OpticalDriveService(ReadingMixin, BurningMixin, BrowsingMixin)` — the mixins call
back into helpers the service owns (`_run_command`, `_create_job`, `_update_job`,
`validate_*`, `self.config`, `self._is_dev_mode`). They are **not** standalone;
adding a mixin method means it may use anything on the service.

Module-level singleton via `get_optical_drive_service()`; the route dependency
`get_service()` returns that same instance.

## The router is built lazily on purpose

`get_router()` imports `app.api.deps`, the models and `fastapi.Depends` **inside**
the method and caches the result in `self._router`. This avoids circular imports
at plugin-load time — the manager imports the plugin package while the core app is
still being assembled. Do not hoist those imports to module scope.

Because the plugin contributes a router, it is mounted **once at startup**
(`core/lifespan.py`). Enabling it at runtime makes its method-based contributions
work immediately but leaves `/api/plugins/optical_drive/*` returning 404 until
`baluhost-backend` restarts; `GET /api/plugins/optical_drive` reports this as
`restart_required`. Same for any route added here.

Routes (all `Depends(get_current_user)`, no admin gate):

```
GET  /drives                            POST /drives/{device}/read/iso
GET  /drives/{device}/info               POST /drives/{device}/read/audio
POST /drives/{device}/eject              POST /drives/{device}/read/audio/{track}
POST /drives/{device}/close              POST /drives/{device}/extract
GET  /drives/{device}/blank-info         GET  /drives/{device}/files[/{path}]
POST /drives/{device}/burn/iso           GET  /drives/{device}/preview/{path}
POST /drives/{device}/burn/audio         POST /iso/list | /iso/extract | /iso/preview
POST /drives/{device}/blank              GET  /jobs | /jobs/{id} · POST /jobs/{id}/cancel
```

`{device:path}` arrives without the `/dev/` prefix from the frontend, so every
handler re-prefixes it before calling the service. Keep that line when adding a
device-scoped route — `validate_device()` rejects a bare `sr0`.

## Safety invariants

Every entry point re-validates; the mixins do **not** trust their caller.

- `validate_device()` — `^/dev/sr[0-9]+$`. The only accepted device shape; this is
  what keeps a caller-supplied string out of `dd if=…`, `wodim dev=…` and `eject`.
- `validate_path()` — resolves the path and requires it under
  `settings.nas_storage_path` or `settings.nas_backup_path` (plus `./dev-storage`
  in dev mode). Used for every **output** path (ISO target, rip dir, extract
  destination).
- `validate_source_file()` — `validate_path()` **and** the file must exist. Used
  for every **input** path (ISO to burn, WAV list, ISO to browse).
- All external tools run through `asyncio.create_subprocess_exec(*cmd)` with
  argument lists. No `shell=True`, no string commands, anywhere in this plugin.
  Keep it that way — several args are user-influenced (`iso_path`, `output_path`,
  the WAV list, `speed`).

**Known weakness, do not "clean up" silently:** `validate_path()` compares with
`str(resolved).startswith(str(root))`, a plain string prefix without a separator
check — a sibling directory such as `/mnt/storage-scratch` passes for the root
`/mnt/storage`. Tightening it means comparing with `Path.is_relative_to()`; treat
that as its own change with its own test, not a drive-by edit.

## Job model — per-process, in-memory

`_jobs` / `_job_tasks` are plain dicts on the singleton, and jobs run as
`asyncio.create_task`. Consequences that matter in production (4 Uvicorn workers):

- A job started through worker A is invisible to `GET /jobs` on worker B, and
  `POST /jobs/{id}/cancel` on the wrong worker returns 400.
- Everything is lost on restart; a burn in flight is orphaned, not resumed.

**The stored config never reaches the service.** `get_config_schema()` exposes
`OpticalDriveConfig` to the settings form, but both `on_startup()` and the route
dependency call `get_optical_drive_service()` **without arguments**, so the
singleton is built from `OpticalDriveConfig()` defaults and an admin's saved
values are silently ignored. Only `auto_eject_after_operation` is read at all
(after every job); `max_concurrent_jobs`, `scan_interval_seconds`,
`default_output_dir` and `default_burn_speed` have no consumer anywhere in the
codebase.

Progress comes from parsing tool stdout/stderr line by line (`wodim`'s
`N of M MB written`, `cdparanoia`'s `N of M sectors`, `7z`'s `N%`). Blanking has
no progress at all — the parse loop is an empty `pass`.

## Dev mode

`self._is_dev_mode = settings.is_dev_mode`, and it is checked *everywhere*, not
centrally. Two layers:

- `_run_command()` short-circuits into `_simulate_command()`, which returns canned
  stdout per tool name (`lsblk`, `cd-info`, `isoinfo`, `dvd+rw-mediainfo`, `wodim`,
  `cdparanoia`, `dd`).
- Individual operations have their own dev branches that sleep through a fake
  progress curve and write dummy files (`b"RIFF" + …` for WAVs,
  `b"SIMULATED ISO DATA" * 100` for ISOs).

Simulated hardware: `/dev/sr0` = 5-track audio CD, `/dev/sr1` = blank DVD.
`_simulate_disc_files()` / `_simulate_iso_files()` supply fixed trees for the
browser. A new operation needs a dev branch too, or it dies on a Windows box.

## External tool dependencies (prod only)

`wodim` (burn + blank), `cdparanoia` (audio rip), `dd` (ISO copy), `isoinfo`
(disc listing + file extract for preview), `7z` (ISO listing, data-file extract),
`eject`, `udevadm` (media detection), `dvd+rw-mediainfo` (blank media info).
Drive discovery reads `/sys/class/block/sr*`. None of these are declared as a
dependency anywhere — a missing binary surfaces as return code 127 from
`_run_command()` or as a failed job.

Media detection uses `udevadm info --query=property` rather than `cd-info`,
deliberately: `cd-info` hangs on some drives. `cd-info` parsing
(`_parse_audio_tracks`) still exists but is only reached in the dev simulation
path, so real audio CDs report tracks with `duration_seconds=0`.

## plugin.json vs. metadata

`plugin.json` is the **marketplace** manifest (`min_baluhost_version`,
`ui.bundle`, `api_scopes`, `min_runtime_abi`) and its `homepage` points at the
external `BaluHost-Plugin-Market` repo. Bundled discovery does not need it — the
manager finds the `PluginBase` subclass in `__init__.py`. The `required_permissions`
list therefore exists twice (`plugin.json` and `PluginMetadata`) and the two
`homepage` values already disagree. When editing one, check the other.

## Tests

`backend/tests/plugins/test_optical_drive_plugin.py`. Runs in dev mode
(`conftest.py` sets `NAS_MODE=dev`), so it exercises the simulation branches, not
the tool invocations.
