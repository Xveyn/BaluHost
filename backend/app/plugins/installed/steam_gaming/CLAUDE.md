# Steam Gaming Plugin

Bundled (in-process, fully trusted) plugin. Surfaces a running Steam game as a
topbar status pill, books play sessions into the database, sends notifications on
the session edges, shows the last five sessions as a dashboard panel, and offers a
"Gaming Mode" toggle in the system/power menu.

**No router, no `plugin.json`.** Everything is contributed through `PluginBase`
method overrides, so enabling/disabling takes effect within seconds across all
workers — no `baluhost-backend` restart needed (`restart_required` is always
false). Bundled discovery works off the `PluginBase` subclass in `__init__.py`;
a marketplace manifest is not required for that.

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md`.

## Layout

| File | Contents |
|---|---|
| `__init__.py` | `SteamGamingPlugin` — pill, menu items, dashboard panel, notification specs, background task, translations |
| `detection.py` | The **single** "is a game running" source for pill, ledger and panel; owns the dev-mode stand-in and the column-width clamps |
| `detector.py` | Pure `/proc` scan. No dev branch, no config — testable against a fake `proc_root` |
| `names.py` | AppID → display name from `appmanifest_<id>.acf`, with hit/miss caches |
| `gaming_state.py` | Marker file recording that *we* started gaming mode |
| `launcher.py` | Detached `steam steam://open|close/bigpicture` dispatch |
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
- End refuses while a game is running, and refuses to run `steam://close` when no
  Steam client is up (that URL would **start** Steam — see `launcher.py`).
  It does **not** turn displays off: that is its own power-menu entry.
- Every result is phrased as "started"/"ended", never "Big Picture is running" —
  the process is detached, so nothing past the spawn is observable.

Icons come from a **closed** frontend map (#451); anything outside it silently
degrades to the generic plug icon. `Gamepad2` and `Monitor` are known-good.

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
(`detection`, `detector`, `launcher`, `ledger`, `names`, `panel`, `plugin`,
`poller`, `state`). Clocks are injectable everywhere (`_monotonic()`, `_utc_now()`,
the poller's `clock=`), `names.reset_caches()` clears the module caches, and
`detector` takes a `proc_root` — use those rather than monkeypatching time.
