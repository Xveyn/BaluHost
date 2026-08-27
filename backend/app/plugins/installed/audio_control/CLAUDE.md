# Audio Control Plugin

Bundled (in-process, fully trusted) plugin: master volume, output device and the
per-application mixer of the desktop session, driven from a popover in the topbar.
Ships its own FastAPI router; the UI is a **core** component, not a sandbox bundle.

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md` —
this file only covers what is specific to this plugin.

## Layout

| File | Lines | Contents |
|---|---|---|
| `__init__.py` | 258 | `AudioControlPlugin`, the router, the audit helper and the two error-mapping helpers |
| `pactl.py` | 236 | The **only** module that knows `pactl` exists: pure parsers plus `run_pactl` / `run_pactl_json` |
| `backend.py` | 164 | `AudioBackend` protocol, `DevAudioBackend` (in-memory), `PipeWireAudioBackend` |
| `service.py` | 73 | `AudioService` — picks the backend, module-level singleton via `get_audio_service()` |
| `models.py` | 64 | Pydantic models; the field names are the API contract to the frontend |

No `plugin.json`, no `ui/bundle.js`. Discovery works off the `PluginBase` subclass.

Frontend counterparts: `client/src/components/topbar/AudioMenu.tsx` (260),
`client/src/api/audioControl.ts` (69), `client/src/i18n/locales/{de,en}/audio.json`.

## Why it must be a bundled plugin

The plugin runs in the host process and therefore under the same UID as the
desktop session, which is what gets it to the PipeWire socket through
`XDG_RUNTIME_DIR` alone — no sudo, no wrapper. A **sandbox plugin would not reach
the socket at all**: it runs as `baluhost-plugin` in its own network namespace.

## `pactl` only — never `wpctl`, `pw-cli`, `pw-dump`

`pactl` and `wpctl` keep **separate ID spaces**: the same output is index 61 in
`pactl` and 35 in `wpctl`. Mixing the two produces confusions that only surface at
runtime. Every subprocess call is list-args, no `shell=True`, 5 s timeout, wrapped
in `asyncio.to_thread` — `subprocess.run` blocks, and a blocking call on the event
loop stalls the whole worker.

## Indices are volatile

The same GPU output carried indices 655, 90 and 731 within one hour on BaluNode.
**No index may be assumed valid beyond a single poll cycle.** A 404 on an unknown
index is therefore a normal case, not a server error — the UI reloads its list.

`_apply()` separates two failures the backend both reports as plain `False`:

- **the index is gone** → 404, so the UI refetches;
- **the audio stack is broken** (no `pactl`, timeout, PipeWire gone) → 502.

Reporting both as 404 would be a false statement: the UI would treat an outage as
a stale list, and debugging would follow the wrong trail. The extra read only
happens on the failure path.

## Security invariants

- **Every route** carries `require_power_control_audio` — the reading one included.
  Stream titles reveal what is playing on the desktop; that is not public.
- **Every route** carries `@user_limiter.limit(get_limit("audio_control"))`. Its own
  category at `240/minute`: the popover polls every 2 s, so the read alone burns
  30 requests per minute. `admin_operations` (30/min) would be wrong here.
- **`pactl` output never reaches a client.** stdout/stderr carry device names and
  paths; they are logged, and a successful write answers `{"success": true}`.
- **The default-sink name is validated against the read device list *before* the
  call.** It is the only client string that ever becomes a `pactl` argument.
  List-args already rule out shell injection — this is the belt to that suspender,
  and a test asserts an unknown name never reaches the backend.
- Volume is capped server-side at 0–150 % (`MAX_VOLUME_PERCENT`); PipeWire itself
  allows overdrive far beyond that.
- Audit entries are written for **device switches and mutes only**. Volume changes
  produce dozens of writes even debounced and would bury the interesting entries.

## Two traps that cost a session each

**No `from __future__ import annotations` in `__init__.py`.** Together with
Pydantic v2 and FastAPI's body detection through slowapi's `@user_limiter.limit`
wrapper, deferred annotations become ForwardRefs that FastAPI no longer resolves
as Pydantic models — the request body is mistaken for query parameters and every
`PUT` answers 422. Same reason as in `gpu_power.py`.

**`get_ui_manifest()` must be overridden.** `PluginBase` returns `None` there, and
`PluginManager.get_ui_manifest()` only lists plugins with a truthy, enabled
manifest in `GET /api/plugins/ui/manifest` — exactly the list
`usePluginEnabled('audio_control')` reads. Without the override the plugin counts
as disabled in the frontend forever and the topbar stays empty, with no error and
no log line. `PluginUIManifest(enabled=True)` with empty `nav_items` is enough: no
nav item means no route, so no `bundle.js` is ever fetched.

## Routes

All under `/api/plugins/audio_control/`, all gated as described above:

| Method | Path | Body |
|---|---|---|
| GET | `/state` | — (returns sinks, streams, `available`, `detail`) |
| PUT | `/sinks/{sink_id}/volume` | `{"percent": 0..150}` |
| PUT | `/sinks/{sink_id}/mute` | `{"muted": bool}` |
| PUT | `/default-sink` | `{"name": str}` |
| PUT | `/streams/{stream_id}/volume` | `{"percent": 0..150}` |
| PUT | `/streams/{stream_id}/mute` | `{"muted": bool}` |

Because the plugin contributes a router, it is mounted **once at startup**
(`core/lifespan.py`). Enabling it at runtime leaves these paths at 404 until
`baluhost-backend` restarts.

## Permission and backends

The routes hang off `can_control_audio` (table `user_power_permissions`, migration
`a7d3c9f18e42`, `server_default="0"` — denied by default). It stands **beside** the
sleep/suspend chains and is deliberately absent from `_apply_implications`; admins
get it implicitly.

`AudioService` picks `DevAudioBackend` in dev mode and on any non-Linux platform
(`pactl` does not exist on Windows, and dev must not reach into a real session),
`PipeWireAudioBackend` otherwise. The dev backend serves two sinks and two streams
from memory, one of them `corked`, so the whole UI is exercisable on Windows.

## Tests

`backend/tests/plugins/test_audio_control_{parser,backend,routes,ui_manifest}.py`.
The parser fixtures are **verbatim excerpts of measured `pactl -f json` output**
from BaluNode (PipeWire 1.4.2), trimmed of irrelevant fields — not invented
payloads. Keep them that way; re-measure rather than hand-edit.
