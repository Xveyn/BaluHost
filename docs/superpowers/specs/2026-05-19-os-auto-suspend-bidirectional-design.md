# OS Auto-Suspend Bidirectional Settings — Design Spec

**Date:** 2026-05-19
**Author:** brainstormed with Claude Opus 4.7
**Status:** Approved (design); implementation plan pending

## Goal

Allow the desktop-class BaluHost prod machine (Debian 13 + KDE Plasma) to manage the OS-level **auto-suspend-at-idle** behavior from either the OS's own settings UI (KDE Energieverwaltung / GNOME Power / `systemd-logind.conf`) **or** the BaluHost web UI. Both paths edit the same underlying OS setting; last write wins.

## Background

`os_sleep_inspector` (read-only) currently surfaces `/etc/systemd/logind.conf`, `/etc/systemd/sleep.conf`, drop-ins, and the 5 sleep-related systemd targets on the BaluHost Sleep page (banner "OS sleep settings"). On the user's prod box (`BaluNode`) it correctly reports "no OS-level sleep triggers active" because KDE PowerDevil — not logind — owns the idle suspend timer. PowerDevil's config is in `~/.config/powerdevilrc` (Plasma 6) and is not visible to the inspector.

Backend service runs as `User=sven, Group=sven` (4 uvicorn workers), confirmed via `systemctl show baluhost-backend`. The user's KDE config file `~/.config/powerdevilrc` does not yet exist (only the migration marker `powermanagementprofilesrc` is present); the adapter must create it on first write.

## Non-Goals

- Display-blanking / dim timeouts (different concern from sleep)
- Power-button action (out of scope — separate setting)
- Lid action (desktop, no lid)
- Hibernate threshold
- Display brightness / battery profiles
- TLP / XFCE / power-profiles-daemon integration
- Active polling, WebSocket push, or D-Bus subscriptions (YAGNI — see Architecture Decisions)

## Key Decisions

1. **Bidirectional, last-write-wins** — both KDE-Panel and BaluHost-UI edit the same OS-level setting; no separate BaluHost copy.
2. **OS surfaces synced:** systemd-logind, KDE PowerDevil (Plasma 6 `powerdevilrc`), GNOME `gsd-power` (via `gsettings`).
3. **Settings synced:** only auto-suspend-at-idle — three fields:
   - `enabled` (boolean, derived from action+timeout when read)
   - `timeout_minutes` (int, 1..1440)
   - `action` enum: `suspend` | `hibernate` | `ignore`
4. **Write authority:** sudoers-whitelisted helper script for logind; direct `~/.config/` write for KDE; `gsettings` subprocess for GNOME.
5. **Write strategy:** auto-detect the active power manager (KDE D-Bus probe → GNOME D-Bus probe → logind fallback) and write only there. No simultaneous multi-target writes (avoids competing idle timers).
6. **Architecture:** read-through pattern (Ansatz A) — no DB copy, no polling, no D-Bus subscriptions. BaluHost is "just another UI" for the OS-owned setting.

## Architecture

```
                       ┌─────────────────────────────┐
                       │  Frontend (Sleep page)      │
                       │  <OsAutoSuspendCard />      │
                       └────────────┬────────────────┘
                                    │ GET / PUT
                       ┌────────────▼────────────────┐
                       │  /api/sleep/os-auto-suspend │
                       │  (sleep.py routes)          │
                       └────────────┬────────────────┘
                                    │
                       ┌────────────▼────────────────┐
                       │  os_auto_suspend service    │
                       │  ┌──────────────────────┐   │
                       │  │ ActivePmDetector     │   │
                       │  └──────────────────────┘   │
                       │  ┌──────────────────────┐   │
                       │  │ Adapters:            │   │
                       │  │  KdeAdapter          │   │
                       │  │  GnomeAdapter        │   │
                       │  │  LogindAdapter       │   │
                       │  └──────────────────────┘   │
                       └────────────┬────────────────┘
                                    │ subprocess / file-io / D-Bus
                       ┌────────────▼────────────────┐
                       │  OS (KDE / GNOME / systemd) │
                       └─────────────────────────────┘
```

### Adapter Protocol

```python
@dataclass(frozen=True)
class AutoSuspendValue:
    enabled: bool
    timeout_minutes: int          # 1..1440
    action: Literal["suspend", "hibernate", "ignore"]

class OsAutoSuspendBackend(Protocol):
    name: str                      # "kde" | "gnome" | "logind"
    label: str                     # "KDE PowerDevil" / "GNOME gsd-power" / "systemd-logind"
    def is_available(self) -> bool: ...
    def read(self) -> AutoSuspendValue: ...
    def write(self, value: AutoSuspendValue) -> None: ...
```

### Active-Backend Detection

Cached 30s (same TTL as `os_sleep_inspector`).

```python
def detect_active_backend() -> OsAutoSuspendBackend | None:
    if KdeAdapter().is_available():    return KdeAdapter()
    if GnomeAdapter().is_available():  return GnomeAdapter()
    if LogindAdapter().is_available(): return LogindAdapter()
    return None
```

Detection method per backend:
- **KDE:** D-Bus session-bus probe `org.kde.Solid.PowerManagement` (subprocess `qdbus6 org.kde.Solid.PowerManagement` with 2s timeout)
- **GNOME:** D-Bus session-bus probe `org.gnome.SettingsDaemon.Power` (same 2s timeout)
- **logind:** `/etc/systemd` exists AND none of the above

## Components

| # | Component | Path | Responsibility |
|---|---|---|---|
| 1 | Service module | `backend/app/services/power/os_auto_suspend.py` (new) | Adapter protocol + 3 adapters + detector + cache |
| 2 | Schemas | `backend/app/schemas/sleep.py` (extension) | `OsAutoSuspendResponse`, `OsAutoSuspendUpdate`, `OsAutoSuspendAction` enum |
| 3 | Routes | `backend/app/api/routes/sleep.py` (extension) | `GET/PUT /api/sleep/os-auto-suspend` |
| 4 | Sudo-Helper-Script | `deploy/install/scripts/baluhost-write-logind-idle.sh` → `/usr/local/lib/baluhost/` | Validates args, atomically writes `/etc/systemd/logind.conf.d/baluhost-idle.conf`, reloads logind |
| 5 | Sudoers template | `deploy/install/templates/sudoers-baluhost-power` | `sven ALL=(root) NOPASSWD: /usr/local/lib/baluhost/baluhost-write-logind-idle *` |
| 6 | Installer module | `deploy/install/modules/XX-power-helpers.sh` (new) | Copies helper to `/usr/local/lib/baluhost/`, sets 0755 root:root, installs sudoers via `visudo -cf` |
| 7 | Inspector extension | `backend/app/services/power/os_sleep_inspector.py` (edit) | Uses same detector; surfaces KDE/GNOME idle-suspend in report |
| 8 | API client | `client/src/api/sleep.ts` (extension) | `getOsAutoSuspend()`, `setOsAutoSuspend()` |
| 9 | Frontend card | `client/src/components/power/OsAutoSuspendCard.tsx` (new) | Toggle + minutes input + action select + source badge |
| 10 | i18n | `client/src/i18n/locales/{de,en}/system.json` (extension) | Keys under `sleep.osAutoSuspend.*` |
| 11 | Backend tests | `backend/tests/test_os_auto_suspend.py` (new) | See Testing section |
| 12 | Helper tests | `deploy/install/scripts/test-baluhost-write-logind-idle.sh` (new) | Bash test cases |

### Data Model

```python
class OsAutoSuspendAction(str, Enum):
    SUSPEND   = "suspend"
    HIBERNATE = "hibernate"
    IGNORE    = "ignore"            # = "do not suspend on idle"

class OsAutoSuspendResponse(BaseModel):
    supported: bool                  # False on Windows / when no backend selectable
    source: Literal["kde", "gnome", "logind", "none"]
    backend_label: str               # human-readable for UI badge
    enabled: bool                    # derived: action != ignore AND timeout > 0
    timeout_minutes: int             # 1..1440 (0 only when supported=False)
    action: OsAutoSuspendAction

class OsAutoSuspendUpdate(BaseModel):
    enabled: bool
    timeout_minutes: int = Field(ge=1, le=1440)
    action: OsAutoSuspendAction
```

## Data Flow

### Read (GET /api/sleep/os-auto-suspend)

1. Route handler (admin auth) → `service.get_os_auto_suspend()`
2. `detect_active_backend()` (cached 30s)
3. If `None` → `OsAutoSuspendResponse(supported=False, source="none", ...)`
4. Else `backend.read()`:
   - **KDE:** parse `~/.config/powerdevilrc`, section `[AC][SuspendSession]`:
     - `idleTime` (ms) → `timeout_minutes = idleTime/60000`
     - `suspendType` (int) → action (`1`→`suspend`, `2`→`hibernate`, other→`ignore`+warn)
     - File missing → defaults (`enabled=False`, `timeout=15`, `action=suspend`)
     - Section missing → `enabled=False`
   - **GNOME:** subprocess `gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout` (seconds) + `... sleep-inactive-ac-type` (enum). Map non-`{suspend,hibernate,nothing}` → `ignore` + warn
   - **logind:** parse `/etc/systemd/logind.conf` + drop-ins via same INI helper as `os_sleep_inspector`. Read `IdleAction` + `IdleActionSec` (`15min`/`900s`/raw integer formats supported)
5. Return `OsAutoSuspendResponse`

### Write (PUT /api/sleep/os-auto-suspend)

1. Route handler (admin auth, rate-limited `admin_operations`) — Pydantic validates body
2. Audit log: `action="os_auto_suspend_update"`, `resource=<backend.name>`, details with previous + new values
3. `service.set_os_auto_suspend(value)`
4. `detect_active_backend()` (same logic as read)
5. `backend.write(value)`:
   - **KDE:**
     - Read current `~/.config/powerdevilrc` (or empty defaultdict)
     - If `enabled=True`: write section `[AC][SuspendSession]` with `idleTime=timeout*60000`, `suspendType=1|2`
     - If `enabled=False`: delete the `[AC][SuspendSession]` section entirely (matches KDE-UI uncheck behavior)
     - Other sections preserved (read-modify-write)
     - Atomic write via `tempfile.NamedTemporaryFile` in `~/.config/` + `os.replace()`
     - Best-effort D-Bus reload: `qdbus6 org.kde.kded6 /modules/powerdevil reparseConfiguration` (failure logged as warn, not raised — KConfigWatcher reacts to inotify regardless)
   - **GNOME:**
     - `gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout <minutes*60>`
     - `gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type '<action_or_nothing>'`
     - `gsd-power` reacts automatically; no reload call needed
   - **logind:**
     - `subprocess.run(["sudo", "-n", "/usr/local/lib/baluhost/baluhost-write-logind-idle", "--timeout", str(timeout*60), "--action", <action>], check=True, timeout=10)`
     - Helper writes `/etc/systemd/logind.conf.d/baluhost-idle.conf` atomically + `systemctl reload systemd-logind`
6. `backend.read()` sanity check; return the **read-back** value (transparent to user if OS rounded/coerced the input)

### Inspector Extension (no API change)

`os_sleep_inspector.inspect_os_sleep()` adds a step:
- Run `detect_active_backend()`
- If active backend is KDE or GNOME and its `read()` returns `enabled=True`, append an `info` issue with key `pm.<backend>.idle_suspend` and message reflecting the configured timeout/action
- The Banner-card on the Sleep page will then show "KDE idle suspend in 15min" instead of the misleading "BaluHost is in sole control"

## Error Handling

| Scenario | Behavior |
|---|---|
| D-Bus probe hangs | 2s subprocess timeout → backend marked unavailable |
| `~/.config/powerdevilrc` missing on first read | Adapter returns defaults; first write creates the file |
| KDE `suspendType` unknown (`4`/`16`/`32`) | Read maps to `ignore` + `log.warning`; write only uses `1`/`2` or section-delete |
| KDE disable | Section `[AC][SuspendSession]` deleted; other sections preserved |
| GNOME enum has more values (`blank`/`logout`/etc.) | Read maps unknown → `ignore` + warn; write only emits `suspend`/`hibernate`/`nothing` |
| `[Battery]` section present in powerdevilrc | Read-modify-write preserves it (laptop users) |
| Helper script not installed | LogindAdapter `is_available()` returns `False`; detector skips it; UI shows "logind backend not available — rerun installer to enable" |
| Sudo NOPASSWD missing | `subprocess.run` exit≠0 → service raises `RuntimeError`; route returns 503 with installer hint |
| KDE `~/.config/powerdevilrc` not writable | Adapter raises `PermissionError`; route returns 500 with detail |
| `systemctl reload systemd-logind` fails | Helper rolls back file (prior version cached in `/tmp` for the request lifetime) + exits non-zero; route returns 500 with detail |
| Read-after-write mismatch | Response contains the **read-back** value; UI transparently shows what the OS accepted |
| Concurrent PUTs from two UIs | Atomic `os.replace` / helper-script atomic mv → last write wins (accepted per Decision 1) |

## Security

- **Sudo helper is the only privilege escalation surface.** Sudoers entry is scoped to one exact binary path with arg wildcard (per `.claude/rules/ci-cd-security.md` reviewer checklist):
  ```
  sven ALL=(root) NOPASSWD: /usr/local/lib/baluhost/baluhost-write-logind-idle *
  ```
- **Helper input validation** (Bash, `set -euo pipefail`):
  - Exactly two args: `--timeout <int>` and `--action <enum>`
  - `timeout` ∈ `[60, 86400]` (1min..1d)
  - `action` ∈ `{suspend, hibernate, ignore}`
  - Reject any other args
  - Config path hardcoded: `/etc/systemd/logind.conf.d/baluhost-idle.conf`
  - mktemp in the same FS (`/etc/systemd/logind.conf.d/`) for atomic mv
- **Auth:** `Depends(deps.get_current_admin)` on both routes (admin-only, consistent with existing sleep config routes at `backend/app/api/routes/sleep.py:183`).
- **Rate limit:** `@user_limiter.limit(get_limit("admin_operations"))` on both routes.
- **Audit log:** every PUT writes via `get_audit_logger_db()` (`action="os_auto_suspend_update"`, includes previous + new values + backend name).

## Testing Strategy

### Backend unit tests (`backend/tests/test_os_auto_suspend.py`, new)

**Adapter tests** (all with `tmp_path`/`monkeypatch`, no real D-Bus or `/etc` touch):

| Test | Description |
|---|---|
| `test_kde_read_file_missing` | File absent → defaults (`enabled=False`, `timeout=15`, `action=suspend`) |
| `test_kde_read_basic` | Fixture file with `idleTime=900000 suspendType=1` → `(True, 15, suspend)` |
| `test_kde_read_section_missing` | File present, no `[AC][SuspendSession]` → `enabled=False` |
| `test_kde_read_unknown_suspendtype` | `suspendType=32` → action=`ignore` + `log.warning` |
| `test_kde_write_creates_file` | File absent → created with correct content |
| `test_kde_write_preserves_other_sections` | `[Battery][SuspendSession]` untouched after write |
| `test_kde_write_disable_removes_section` | `enabled=False` → `[AC][SuspendSession]` removed, rest kept |
| `test_kde_write_atomic` | `os.replace` mocked; tmp file in same dir as target |
| `test_gnome_read_via_gsettings` | subprocess mocked; returns `900\n` + `'suspend'\n` → `(True, 15, suspend)` |
| `test_gnome_read_unknown_action_maps_ignore` | gsettings returns `'blank'` → action=`ignore` + warn |
| `test_gnome_write_calls_gsettings` | Two `gsettings set` calls with correct args |
| `test_logind_read_basic` | logind.conf with `IdleAction=suspend IdleActionSec=15min` |
| `test_logind_read_seconds_format` | `IdleActionSec=900` (raw seconds) → 15min |
| `test_logind_read_drop_in_priority` | Drop-in overrides main file |
| `test_logind_write_calls_helper` | `subprocess.run` with correct sudo args |
| `test_logind_write_helper_failure_raises` | subprocess returncode≠0 → `RuntimeError` |

**Detector tests:**

| Test | Description |
|---|---|
| `test_detector_kde_present` | D-Bus mock returns KDE → KdeAdapter |
| `test_detector_gnome_only` | KDE absent, GNOME present → GnomeAdapter |
| `test_detector_headless` | Both absent, `/etc/systemd` present → LogindAdapter |
| `test_detector_windows` | `sys.platform=win32` → `None` |
| `test_detector_dbus_timeout` | Probe timeout 2s → graceful fallback |
| `test_detector_cache_ttl` | Second call within 30s does not re-probe |

**Service-layer tests:**

| Test | Description |
|---|---|
| `test_get_supported_false_when_no_backend` | Detector returns `None` → `supported=False` |
| `test_set_calls_backend_write_and_reads_back` | Mock backend write + read; response reflects read |
| `test_set_audit_logged` | `get_audit_logger_db` mocked; one entry written |

**Route integration tests** (via TestClient):

| Test | Description |
|---|---|
| `test_get_requires_admin` | Non-admin user → 403 |
| `test_put_requires_admin` | Non-admin user → 403 |
| `test_put_validation_timeout_zero` | `timeout=0` → 422 |
| `test_put_validation_timeout_huge` | `timeout=2000` → 422 |
| `test_put_rate_limited` | Excess requests → 429 |
| `test_put_happy_path` | Mocked backend → 200 + correct response |

### Helper script tests (`deploy/install/scripts/test-baluhost-write-logind-idle.sh`, new)

Plain Bash script with `set -e`, executable in CI without root via `systemctl` PATH stub:
- Missing args → `exit 2`
- `--timeout=abc` → `exit 2` (non-integer)
- `--timeout=30` → `exit 2` (below min)
- `--action=poweroff` → `exit 2` (invalid enum)
- Happy path with mocked `systemctl` → file written, correct format, exit 0

### Inspector extension tests (update `backend/tests/test_os_sleep_inspector.py`)

| Test | Description |
|---|---|
| `test_inspector_lists_kde_idle` | Detector returns KDE adapter with `enabled=True`, 15min → issue `info` "KDE idle suspend in 15min" surfaced |
| `test_inspector_no_double_warn_when_logind_idle_unset` | KDE has idle, logind has none → only KDE issue, no duplicate |

### Frontend tests (Vitest + RTL)

| Test | Description |
|---|---|
| `OsAutoSuspendCard.render-source-badge` | `source=kde` → "KDE PowerDevil" badge visible |
| `OsAutoSuspendCard.unsupported` | `supported=false` → card not rendered |
| `OsAutoSuspendCard.disabled-state` | `enabled=false` → timeout/action inputs disabled |
| `OsAutoSuspendCard.save-calls-api` | Form submit triggers `setOsAutoSuspend` with correct body |
| `OsAutoSuspendCard.error-toast` | API 503 → `toast.error` with i18n message |
| `i18n.de_en_keys_present` | Both locale files contain all `sleep.osAutoSuspend.*` keys |

### Manual smoke test (on prod after implementation)

```
1. systemctl stop baluhost-backend
2. KDE → System Settings → Energieverwaltung
3. Set "Sitzung aussetzen nach: 30 min", save
4. systemctl start baluhost-backend
5. curl -H 'Authorization: Bearer ...' http://localhost:8000/api/sleep/os-auto-suspend
   → expect source=kde, enabled=true, timeout_minutes=30, action=suspend
6. PUT timeout=10 → 200
7. Reopen KDE Energieverwaltung panel → must show 10 min
8. PUT enabled=false → 200
9. KDE panel → "Sitzung aussetzen" must be unchecked
10. PUT timeout=20 (re-enable) → enabled=true, KDE panel shows 20 min
```

### CI integration

- Backend tests + frontend Vitest run in the existing `ci-check.yml` jobs on `ubuntu-latest` (mocks cover D-Bus — no real session-bus needed)
- Helper script test runs as a new step in the `backend-tests` job (no own job; fast)
- **Nothing** on the self-hosted runner (Layer 2 of `.claude/rules/ci-cd-security.md` stays intact)

### Coverage targets

- Service module + adapters: ≥90%
- Routes: ≥80%
- Helper script: all 4 negative + 1 positive paths

## Open Items for Implementation

These are intentional knowns that will be resolved during implementation, not during design:

1. **Exact KDE `powerdevilrc` Plasma 6 section nesting** — the file is migrated but empty on the user's box. Once a value is set via KDE Settings, the precise group structure (`[AC]\n[SuspendSession]` vs `[AC][SuspendSession]` vs grouped) needs verification. KConfig-library may also recognise both.
2. **Exact KDE reload D-Bus call** — `qdbus6 org.kde.kded6 /modules/powerdevil reparseConfiguration` is the leading candidate; alternative is relying entirely on KConfigWatcher (inotify) which should also work. Verify which one actually triggers re-application without restarting PowerDevil.
3. **Sudoers user** — design assumes `sven` (as deployed today). If deployment ever moves to a dedicated `baluhost` user, the sudoers template needs to be parameterised by the installer.

## Migration & Compatibility

- No DB migration (no DB schema changes).
- No new dependencies — `qdbus6`, `gsettings`, `sudo`, and Python stdlib only.
- Backward compatible: if helper not installed, the LogindAdapter just isn't available; KDE/GNOME paths still work. UI shows a "logind backend not available" hint instead of breaking.
- The existing `os_sleep_inspector` keeps working unchanged for users on headless deployments; the new detector-based extension is additive.

## Cross-References

- Memory: `project_balunode_kde_gaming.md` — prod box context (KDE + gaming dual-use)
- Rules: `.claude/rules/security-agent.md` — auth, audit, subprocess hardening invariants
- Rules: `.claude/rules/ci-cd-security.md` — sudoers reviewer checklist (Layer 2/3)
- Existing code:
  - `backend/app/services/power/os_sleep_inspector.py` — read-only inspector to be extended
  - `backend/app/api/routes/sleep.py:246` — existing `/api/sleep/os-settings` route (sibling)
  - `backend/app/services/power/sleep_backend_linux.py` — existing logind D-Bus suspend caller (proves DBus session works under `sven`)
  - `client/src/components/power/OsSleepSettingsBanner.tsx` — sibling component on Sleep page
