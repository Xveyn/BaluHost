# Display Output Plugin

Bundled (in-process, fully trusted) plugin: enumerates the KWin outputs, picks
which one is active and sets its video mode, driven from a popover in the topbar.
Ships its own FastAPI router; the UI is a **core** component, not a sandbox bundle.

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md` —
this file only covers what is specific to this plugin.

## Layout

| File | Contents |
|---|---|
| `__init__.py` | `DisplayOutputPlugin`, the router, the audit helper, the error mapping |
| `kscreen.py` | The **only** module that knows `kscreen-doctor` exists: parser, runner, argv builder |
| `backend.py` | `DisplayBackend` protocol, `DevDisplayBackend`, `KWinDisplayBackend` |
| `service.py` | `DisplayService` — backend choice, the whole validation, module singleton |
| `models.py` | Pydantic models; the field names are the API contract to the frontend |

Frontend counterparts: `client/src/components/topbar/DisplayMenu.tsx`,
`client/src/api/displayOutput.ts`, `client/src/i18n/locales/{de,en}/display.json`.

## Why it must be a bundled plugin

Same reason as `audio_control`: the plugin runs in the host process and therefore
under the same UID as the desktop session, which is what gets it to the KWin
socket through `wayland_session_env()` alone — no sudo, no wrapper. A **sandbox
plugin would not reach the socket at all**: it runs as `baluhost-plugin` in its
own network namespace.

Measured proof of the env's necessity: `kscreen-doctor -j` from an SSH session
without `XDG_RUNTIME_DIR`/`WAYLAND_DISPLAY` aborts — Qt falls back to the `xcb`
platform plugin and finds no display.

## Mode names are ambiguous — address modes by ID

`libkscreen`'s `findMode()` builds a mode's name with `qRound(refreshRate)`:

    "%1x%2@%3".arg(width, height, qRound(mode->refreshRate()))
    if (mode->id() == query || name == query) return mode;

So 119.88 and 120.000 are **both** called `3840x2160@120`, and the function
returns the first match and stops. Measured on BaluNode: HDMI-A-1 has 55 modes
but only 45 distinct names; DP-3's ids 57 and 58 are exactly that pair.

Addressing by name would therefore set an arbitrary member of the group, with no
error. The same code line proves the ID **is** a valid argument, so that is what
is used.

**But never a stored ID.** That is the defect in #589, where a hard-coded id in
`deploy/scripts/display-switch` outlives the reboot that renumbered it. Here the
id comes from the enumeration of the same request cycle and `apply` re-reads and
cross-checks it against the client-supplied `mode_name` — a mismatch is a 409,
not a silently wrong mode. `mode_id` and `mode_name` are all-or-nothing on the
wire; accepting one without the other would make the cross-check optional.

## Two levels of "on"

| Level | Source | Field |
|---|---|---|
| KWin | `kscreen-doctor -j`, `enabled` | `selected` |
| DRM | sysfs `enabled` per connector | `lit` |

With DPMS off **every** DRM connector is `disabled` while KWin keeps its choice —
that is why `DesktopTogglePanel` can say "stopped" while KWin holds DP-3 active.
Not a bug, two truths about different things. They are never folded into one
field, and a name that maps to no connector yields `lit=None`, not `False`:
reporting an unknown answer as "off" would be a false statement.

`get_connector_states()` lives in `services/power/gpu/display_detector.py`, not
here — `desktop_backend` and `steam_gaming` already read that sysfs tree.

## `kscreen-doctor` lists only connected outputs

`/sys/class/drm/` shows `card0-DP-1` and `card0-DP-2` on BaluNode; the JSON does
not mention them. `connected` stays in the schema but is true in practice, and
`DevDisplayBackend` deliberately serves **no** disconnected output — it would be
a state the real backend never produces.

Field presence also varies between outputs: HDMI-A-1 carries `vrrPolicy`, DP-3
does not. Every field access goes through `.get()`.

## Security invariants

- **Every route** carries `require_power_manage_displays` — the reading one
  included. The output list reveals the attached hardware, EDID sizes included.
- **Every route** carries `@user_limiter.limit(get_limit("display_output"))`,
  its own category at `60/minute`: the popover polls only while open, every 5 s.
- **Nothing from the request becomes an argv element without having appeared in
  the live enumeration first.** Names and mode ids are matched against measured
  values, not escaped or filtered. List-args already rule out shell injection —
  this is the belt to that suspender.
- **`kscreen-doctor` output never reaches a client.** stdout/stderr carry EDID
  names and paths; they are logged, and a success answers `{"success": true}`.
- **An `apply` after which no connected output would be selected is rejected.**
  "Nothing should be lit" belongs on the DPMS switch in `PowerMenu` — reversible,
  and it does not throw the KWin configuration away.
- One `apply` is exactly **one** `kscreen-doctor` invocation; the tool applies
  all arguments together, so there is no partial state on failure. The argument
  order follows the enumeration, not the request — deterministic and beyond
  client influence.
- A 502 is always raised as `BadGatewayError`, never `HTTPException(502)` — the
  global 5xx handler in `core/exception_handlers.py` rewrites a plain
  `HTTPException`'s detail to "Internal server error" from 500 up; only a
  `ServiceError` subclass survives that scrubber with its curated message.

## The two traps inherited from `audio_control`

**No `from __future__ import annotations` in `__init__.py`.** With Pydantic v2
and FastAPI's body detection through slowapi's `@user_limiter.limit` wrapper,
deferred annotations become ForwardRefs FastAPI no longer resolves — the request
body is mistaken for query parameters and every `POST` answers 422.

**`get_ui_manifest()` must be overridden.** `PluginBase` returns `None`, and only
plugins with a truthy manifest appear in `GET /api/plugins/ui/manifest` — exactly
the list `usePluginEnabled('display_output')` reads. Without it the plugin counts
as disabled forever and the topbar stays empty, with no error and no log line.

## Routes

| Method | Path | Body |
|---|---|---|
| GET | `/state` | — (returns outputs, `displays_powered`, `available`, `detail`) |
| POST | `/apply` | `{"outputs": [{"name", "selected", "mode_id"?, "mode_name"?}]}` |

Failure mapping: validation → 400, stale `mode_name` for a live `mode_id` → 409,
KWin unreachable on a write → 502. A **read** with an unreachable session is not
an error — it answers 200 with `available: false` so the UI can show that state.

Because the plugin contributes a router, it is mounted **once at startup**
(`core/lifespan.py`). Enabling it at runtime leaves these paths at 404 until
`baluhost-backend` restarts.

## Permission

`can_manage_displays` (table `user_power_permissions`, migration `b8c41d92e7f5`,
`server_default="0"` — denied by default). It stands **beside** the sleep/suspend
chains and is deliberately absent from `_apply_implications`; admins get it
implicitly.

## Tests

`backend/tests/plugins/test_display_output_{parser,kscreen,backend,service,routes,ui_manifest}.py`
plus `backend/tests/test_display_detector_connector_states.py`.

The fixture `backend/tests/plugins/fixtures/kscreen_balunode.json` is a
**measured** `kscreen-doctor -j` recording from BaluNode (2026-09-08), not an
invented payload. The duplicate and ambiguous modes in it are the test subject —
re-measure rather than hand-edit. No test invokes real `kscreen-doctor`; the CI
runner has no Wayland session.
