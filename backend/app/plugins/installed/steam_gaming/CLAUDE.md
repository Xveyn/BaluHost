# Steam Gaming Plugin

Bundled (in-process, fully trusted) plugin. Surfaces a running Steam game as a
topbar status pill, books play sessions into the database, sends notifications on
the session edges, shows the last five sessions as a dashboard panel, and offers a
"Gaming Mode" toggle in the system/power menu. It also lets holders of
`can_launch_games` list installed games and launch one (`GET /games`,
`POST /games/{app_id}/launch`), mainly for BaluApp.

**One router, no `plugin.json`.** Pill, menu, panel, notifications and the
background task come from `PluginBase` method overrides and take effect within
seconds across all workers. The launch routes (`routes.py`) are a router, and
routers are mounted once at startup: enabling the plugin after the backend
started needs a `baluhost-backend` restart before `/api/plugins/steam_gaming/*`
exists (`restart_required` reports it; until then requests get
`404 "Plugin not found"` from the catch-all proxy). `get_router()` imports
`routes` lazily to avoid an import cycle. `routes.py` and `models.py` must not
use `from __future__ import annotations` (slowapi body detection).

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md`.

## Layout

| File | Contents |
|---|---|
| `__init__.py` | `SteamGamingPlugin` — pill, menu items, dashboard panel, notification specs, background task, translations |
| `detection.py` | The **single** "is a game running" source for pill, ledger and panel; owns the dev-mode stand-in and the column-width clamps |
| `detector.py` | Pure `/proc` scan. No dev branch, no config — testable against a fake `proc_root` |
| `names.py` | AppID → display name from `appmanifest_<id>.acf`, with hit/miss caches |
| `gaming_state.py` | Marker file recording that *we* started gaming mode |
| `launcher.py` | `steam://` dispatch through `systemd-run --user` — Steam runs in sven's user manager, never as a backend child (no inherited secrets, survives backend restarts; #640) |
| `library.py` | Launchable games: `appmanifest_<id>.acf` present, name readable, not a tool; 30 s per-worker list cache; `LibraryUnavailable` when no steamapps dir exists |
| `launch.py` | `start_gaming_mode()` — the displays → unlock → Big Picture → marker sequence shared by the menu action and the launch route; re-exports `launch_game` |
| `models.py` | Pydantic models of the routes; field names are the API contract |
| `routes.py` | `GET /games`, `POST /games/{app_id}/launch`; right, LAN gate, audit |
| `ledger.py` | Observations → `SteamSession` rows; returns what is worth announcing |
| `poller.py` | Background task: detect → book → announce |

Related core code: `app/models/steam_session.py`,
`app/services/game_libraries/` (`steam.py`, `vdf.py`),
`app/services/power/` (`desktop`, `desktop_windows`, `session_lock`, `session_env`,
`gpu/display_detector`).

## Detection

Steam launches every title — native or Proton — through
`reaper SteamLaunch AppId=<n> -- …`, so `detector.py` greps `/proc/*/cmdline` for
that. Two alternatives were measured and rejected: `registry.vdf`'s `RunningAppID`
is dead upstream (always 0), and Steam creates no per-game systemd scope.

Layering matters and is deliberate:

- `detector.py` stays **pure** — no `settings`, no dev branch. The test suite runs
  with `NAS_MODE=dev`, so a dev branch here would make the detector tests assert
  the mock instead of the real scan.
- `detection.py` is the layer everything else imports. It adds the dev stand-in
  (`DEV_APP_ID="0"`, `"Dev Mode Game"` — there is no `/proc` on the Windows dev
  box) and clamps to the DB column widths: app_id > 32 chars is discarded, names
  are truncated at 200. Without the clamps every booking would fail with a
  PostgreSQL `DataError` in prod while passing on SQLite locally.
- `_STEAM_CLIENT_RE` in `detector.py` matches the Steam **client** only —
  `steamwebhelper`/`steamerrorreporter` must not match. A false positive there
  would let the end action fire `steam steam://close/bigpicture` at a box where
  Steam is down, which **starts** Steam.

All of this is blocking filesystem I/O. Call it via `asyncio.to_thread` —
`asyncio.wait_for` cannot cancel blocking sync code, so a spun-down library mount
would otherwise stall a whole worker's event loop past the collector timeout.

## State: three different stores, on purpose

| State | Where | Why there |
|---|---|---|
| "what is running right now" | per-worker dict `_CACHE`, 3s TTL | The pill is an activity indicator, not a ledger; a per-worker cache avoids sharing state between the four workers entirely |
| "what was played" | `steam_sessions` table | The open row **is** the poller's state — no in-process `last_app_id`, which is what makes a restart mid-session harmless |
| "did we start gaming mode" | marker file under `<storage>/.system/steam_gaming/` | An in-process flag would flap between workers; `/tmp` is ephemeral under `PrivateTmp`; the storage root survives a deploy (`git reset --hard` without `git clean`) |

`names.py` adds a fourth, process-lifetime cache: name hits are permanent (a
game's name never changes), misses retry after 60s (a manifest appears while a
game is still installing; non-Steam shortcuts never get one).

## The ledger

`ledger.record()` books one observation and **never raises** — a DB failure rolls
back, logs and returns no events, so the next tick simply retries. Two thresholds
drive the behaviour:

- `STALE_AFTER_SECONDS = 60` (two poll intervals) — only while the poller was
  demonstrably present is `now` a truthful end time, and only then is an edge
  announced as live news.
- `ADOPT_WINDOW_SECONDS = 600` — the same game across a shorter gap (a deploy
  mid-game) is adopted as one session; a longer gap opens a new one **without**
  announcing it.

Invariant: at most one open session. `_claim_current_session()` re-establishes it
every tick instead of trusting it, closing orphans at their `last_seen_at`.

`RETENTION_DAYS = 365`, enforced by the poller once a day. Deliberately **not**
wired into `services/monitoring/retention_manager.py`: that hangs off the
`MetricType` enum and `monitoring_config` rows, so putting a plugin table there
would couple the core to a plugin. Configurability is tracked in #464.

Order in `poller.py` is load-bearing: book and commit first, announce afterwards.
A failed push must never roll back a booking. The task runs **primary-only**
(#448), so exactly one instance polls and no cross-worker guard is needed.

## Gaming Mode (the menu action)

Big Picture's own state is **not detectable from the outside** (measured
2026-07-24). That single fact explains most of the design:

- `get_ui_manifest()` advertises exactly one direction, chosen by
  `_end_action_is_current()` = marker set **and** at least one display lit. The
  display check is what rescues a stale marker.
- `get_menu_items()` is overridden to return **both** directions. The core
  validates a clicked `action_id` against this list, so deriving it from the
  manifest (the base-class default) would 404 any click that raced a state
  change. Advertising a subset of what is declared is the safe direction.
- `on_startup()` clears the marker: a deploy or crash restarts the backend while
  Big Picture may keep running. Offering "start" wrongly costs one harmless
  click; a stale "end" minimizes the windows of someone who never asked.
- Start order is displays → unlock (via `unlock_if_permitted()`, which applies
  its own right + LAN gate and writes the audit entry) → Big Picture → *then*
  mark started. Recording a start that never happened would hide the start
  action behind a useless end action.
- The sequence lives in `launch.py:start_gaming_mode()` and is reused by the
  launch route; tests patch `steam_gaming.launch.*`, not the package names.
  There is no outer timeout around it (`wait_for` cancels awaits, not threads
  — #643); each step bounds itself. `systemd-run` now blocks up to
  `_STEAM_RUN_TIMEOUT_SECONDS` (10s) instead of returning in milliseconds like
  the old detached `Popen`. Worst case ≈ 70s (displays 30s, unlock ~15s, Big
  Picture 10s, game 10s, lock state ~3s), typically < 3s; in the menu path a
  20s cut-off can leave Big Picture opening without `mark_started` running, so
  the menu keeps offering "start".
- End refuses while a game is running, and refuses to run `steam://close` when no
  Steam client is up (that URL would **start** Steam — see `launcher.py`).
  It does **not** turn displays off: that is its own power-menu entry.
- Every result is phrased as "started"/"ended", never "Big Picture is running" —
  ok means the systemd unit was started, not that Big Picture actually shows up
  or goes away, which stays unobservable from here.

Icons come from a **closed** frontend map (#451); anything outside it silently
degrades to the generic plug icon. `Gamepad2` and `Monitor` are known-good.

## Game launch (routes)

- Both routes require `require_power_launch_games` (admins implicitly). The
  right lets a user turn the displays on and open Big Picture as part of a
  launch; unlocking still needs `can_unlock_session` via `unlock_if_permitted()`.
- `POST` checks, before any side effect: LAN/VPN for every role (403, audited
  with IP) → `library.is_valid_app_id` + `find_installed_game` (404; 503 when no
  library is readable) → `current_app_id(dev_stand_in=False)` (409).
- The steam:// URL is built from the library entry's id; `launcher.launch_game`
  re-checks digits-only.
- Audit `steam_game_launch` carries only `app_id` and `failed_step` — never the
  manifest name, never subprocess output. 404/409/503 are not audited.
- Rate limits: `steam_games_read` 60/min, `steam_launch` 6/min.
- `running` and the 409 use `current_app_id(dev_stand_in=False)`, so the
  Windows dev box can click through a launch.

## Contributions in one place

- **Pill** `plugin:steam_gaming:session` — `default_visibility="admin"`,
  `silent_when_ok=True` (nothing shown when no game runs). The collector runs
  under a 2s timeout and an exception guard; a failure silences only this pill.
- **Panel** — five newest sessions, `admin_only=True` (the game name is
  information about the box owner). Returns `None` when nothing was ever
  recorded, because `StatusItem` has no translation-key fields and a placeholder
  line would be an untranslatable string.
- **Notifications** — `session_started` / `session_ended`, `default_target="admins"`,
  60s cooldown. Texts are server-rendered German templates, like the core events.
- **Translations** — `get_translations()` (en/de), resolved client-side via
  `resolvePluginString`; `*_text` fields are the literal fallback.
- Durations are formatted digits-only (`3h 04m`, `12m`) so no string needs
  translating.

## Tests

`backend/tests/plugins/test_steam_gaming_*.py` — one file per module
(`detection`, `detector`, `launch`, `launcher`, `ledger`, `library`, `names`,
`panel`, `plugin`, `poller`, `routes`, `state`). Clocks are injectable everywhere
(`_monotonic()`, `_utc_now()`, the poller's `clock=`), `names.reset_caches()`
clears the module caches, and `detector` takes a `proc_root` — use those rather
than monkeypatching time.
