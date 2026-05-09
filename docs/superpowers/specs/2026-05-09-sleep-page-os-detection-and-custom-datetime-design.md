# Sleep Page: OS-Sleep-Settings banner + Always-Awake custom datetime

**Date:** 2026-05-09
**Page:** System Control → Hardware → Sleep (`/sleep`)
**Status:** Design accepted, plan pending

## 1. Goals

Two independent additions to the existing Sleep page:

1. **OS-Sleep-Settings banner** — a read-only card at the top of the page showing whether the operating system has its own sleep/suspend triggers configured (logind `IdleAction`, lid switch handling, `sleep.conf` flags, masked targets, etc.). Read-only: no editing, no writing to OS config files.

2. **Custom datetime in the "Immer wach" panel** — alongside the existing `1h / 4h / 8h / Dauerhaft` presets, a fifth option that lets the user pick an arbitrary date+time in the future (capped at 7 days) for the always-awake override.

## 2. Non-goals

- No edit/write capability for OS sleep settings (no buttons that mask targets, no `systemctl mask` from the UI). Pure read.
- No new third-party dependencies, frontend or backend. Native HTML inputs only (`<input type="datetime-local">`, `<details>` for the expandable section).
- No D-Bus integration. Reading systemd config files + cheap `systemctl is-enabled` is sufficient.
- No changes to the `CoreUptimePanel` ("Kernbetriebszeit") — the user-facing terminology was clarified upfront: this work targets the `AlwaysAwakePanel` ("Immer wach").

## 3. Page layout

`client/src/pages/SleepMode.tsx` gains one new component as the very first child:

```
SleepMode
├── OsSleepSettingsBanner   ← NEW (Feature 1)
├── SleepModePanel
├── AlwaysAwakePanel        ← extended with custom datetime button (Feature 2)
├── CoreUptimePanel
├── SleepConfigPanel
└── SleepHistoryTable
```

When the OS-sleep banner has nothing to display (e.g. Windows dev mode), it returns `null` and the page falls back to its current order without a placeholder.

## 4. Feature 1 — OS-Sleep-Settings banner

### 4.1 User-facing contract

Three render states:

1. **Loading** — skeleton card.
2. **Unsupported platform** (`platform_supported: false`) — component returns `null`. No "not available" message.
3. **Linux** — header line, one line per detected issue with severity icon (⚠ warning / ✓ ok / ✗ error / ℹ info), an expandable `[Details ⌄]` section with a flat key/value table, and a `[Refresh ⟳]` button. When `issues` is empty: a single "alles okay" line so users can see the panel did its job.

### 4.2 Backend service: `backend/app/services/power/os_sleep_inspector.py` (new)

```python
@dataclass(frozen=True)
class OsSleepIssue:
    severity: Literal["info", "warning", "error"]
    key: str                      # stable id, e.g. "logind.idle_action.suspend"
    message: str                  # fallback text if frontend has no i18n entry for `key`
    detail: Optional[str]

@dataclass(frozen=True)
class OsSleepReport:
    platform_supported: bool
    logind: dict[str, str]        # resolved values: HandleLidSwitch, IdleAction, IdleActionSec, …
    sleep_conf: dict[str, str]    # AllowSuspend, AllowHibernation, HibernateMode, …
    targets: dict[str, str]       # {"sleep.target": "enabled", "suspend.target": "masked", …}
    issues: list[OsSleepIssue]
    sources: list[str]            # config file paths actually read
    collected_at: datetime

def inspect_os_sleep(force_refresh: bool = False) -> OsSleepReport: ...
```

**Inputs read** (last-write-wins, mirroring how systemd resolves drop-ins):

1. `/etc/systemd/logind.conf` then drop-ins under `/etc/systemd/logind.conf.d/*.conf` and `/run/systemd/logind.conf.d/*.conf`.
2. `/etc/systemd/sleep.conf` then drop-ins under `/etc/systemd/sleep.conf.d/*.conf` and `/run/systemd/sleep.conf.d/*.conf`.
3. One `systemctl is-enabled sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target` call (no sudo, list-args, 5s timeout). Output parsed line-by-line into `targets`.

**Helpers:**

- `_parse_systemd_ini(path: Path, section: str) -> dict[str, str]` — minimal INI reader: skips blank lines and `#`/`;` comments, recognises `[Section]` headers, splits `KEY=VALUE` and trims. Malformed lines are logged at WARNING and skipped.
- `_merge_drop_ins(base: dict, drop_in_dir: Path, section: str) -> dict` — sorts drop-in files alphabetically (systemd's behaviour) and overlays.
- `_classify(report) -> list[OsSleepIssue]` — initial rule set:

| Rule | Severity | `key` |
|---|---|---|
| `logind.IdleAction == "suspend"` | warning | `logind.idle_action.suspend` |
| `logind.IdleAction == "hibernate"` | warning | `logind.idle_action.hibernate` |
| `logind.IdleAction == "hybrid-sleep"` | warning | `logind.idle_action.hybrid_sleep` |
| `logind.HandleLidSwitch in {suspend, hibernate}` AND lid sensor present | info | `logind.lid_switch.suspend` (or `.hibernate`) |
| `sleep.AllowSuspend == no` | info | `sleep_conf.suspend_disabled` |
| `targets["suspend.target"] == "masked"` | error | `targets.suspend.masked` |

One distinct `key` per variant, so the frontend can attach precise i18n strings. Backend `message` field is a German fallback if no i18n entry matches.

Lid sensor probe: `Path("/proc/acpi/button/lid").is_dir()` — keeps the laptop-only rule from firing on desktops.

**Platform guard:** if `sys.platform != "linux"` OR `Path("/etc/systemd").is_dir() is False`, return `OsSleepReport(platform_supported=False, logind={}, sleep_conf={}, targets={}, issues=[], sources=[], collected_at=now())`. No subprocess calls made on Windows/macOS.

**Caching:** module-level `_CACHE: tuple[OsSleepReport, float] | None`, TTL 60s. The endpoint forwards `?force=true` to bypass.

**Resilience:** the entire body of `inspect_os_sleep` is wrapped in try/except. Any unexpected error produces a report with `platform_supported=True` and a single `OsSleepIssue(severity="error", key="inspector.failed", …)` so the endpoint always returns 200 and the banner renders something meaningful.

### 4.3 Backend endpoint

In `backend/app/api/routes/sleep.py` (existing file):

```python
@router.get("/os-settings", response_model=OsSleepReportResponse)
@limiter.limit(get_limit("default"))
async def get_os_sleep_settings(
    request: Request,
    force: bool = False,
    current_user: User = Depends(deps.get_current_admin),
) -> OsSleepReportResponse:
    return os_sleep_inspector.inspect_os_sleep(force_refresh=force)
```

- Admin-only (matches the rest of `/api/system/sleep/`).
- Default rate limit; the call is cheap when cached.
- Pydantic schema `OsSleepReportResponse` mirrors the dataclass (lives in `backend/app/schemas/sleep.py`).

### 4.4 Frontend component: `client/src/components/power/OsSleepSettingsBanner.tsx` (new)

```
┌────────────────────────────────────────────┐
│ [icon] OS-Sleep-Einstellungen   [Refresh ⟳]│
│ ⚠ logind: IdleAction=suspend nach 30min   │
│ ✓ suspend.target nicht maskiert            │
│ ─────────────────────────────────────────  │
│ [Details ⌄]                                │
│   ▸ logind.HandleLidSwitch = suspend       │
│   ▸ logind.IdleAction      = suspend       │
│   ▸ sleep.AllowSuspend     = yes           │
│   ▸ targets.suspend.target = enabled       │
│   ▸ Quellen: /etc/systemd/logind.conf, …  │
└────────────────────────────────────────────┘
```

- Same shell as siblings: `card border-slate-700/50 p-4 sm:p-6 space-y-4`.
- `useEffect` loads on mount; refresh button calls `getOsSleepSettings(true)`.
- `report.platform_supported === false` → component returns `null`.
- Severity colors from existing palette: `error` red-400, `warning` amber-400, `info` slate-300, `ok` emerald-400.
- Details section is a plain `<details><summary>` (native HTML).
- All visible strings via `useTranslation('system')` under `sleep.osSettings.*`. Issue strings use the backend's `key` for i18n lookup with `defaultValue: issue.message`, so unknown keys still show the backend's fallback text.

### 4.5 API client addition

`client/src/api/sleep.ts`:

```typescript
export type OsSleepSeverity = 'info' | 'warning' | 'error';

export interface OsSleepIssue {
  severity: OsSleepSeverity;
  key: string;
  message: string;
  detail: string | null;
}

export interface OsSleepReport {
  platform_supported: boolean;
  logind: Record<string, string>;
  sleep_conf: Record<string, string>;
  targets: Record<string, string>;
  issues: OsSleepIssue[];
  sources: string[];
  collected_at: string;
}

export async function getOsSleepSettings(force = false): Promise<OsSleepReport> {
  const res = await apiClient.get('/api/system/sleep/os-settings', {
    params: force ? { force: true } : undefined,
  });
  return res.data;
}
```

## 5. Feature 2 — Custom datetime in AlwaysAwakePanel

### 5.1 User-facing contract

The preset row gains a fifth chip alongside `1h / 4h / 8h / Dauerhaft`:

- **No custom value set:** `[ Bis Datum… ]` — clicking opens a popover.
- **Custom value set + active:** `[ Bis 14.05. 18:30  ⌄ ]` — the chip is the active preset, clicking reopens the popover for editing.

The popover contains a single `<input type="datetime-local">` with `min` = now+5min, `max` = now+7d, plus `[Übernehmen]` / `[Abbrechen]` buttons. Inline error text appears below the input on validation failure.

### 5.2 Backend tweak

Existing validator `backend/app/schemas/sleep.py:SleepConfigUpdate._validate_until_future` is extended to enforce a 7-day cap:

```python
MAX_ALWAYS_AWAKE_HORIZON = timedelta(days=7)
…
if v > datetime.now(timezone.utc) + MAX_ALWAYS_AWAKE_HORIZON:
    raise ValueError("always_awake_until must be at most 7 days in the future")
```

The 1h/4h/8h presets stay well under the cap; the change is invisible to existing callers.

### 5.3 Frontend changes: `client/src/components/power/AlwaysAwakePanel.tsx`

1. Extend the `Preset` union with `'custom'` and add constants:

   ```typescript
   type Preset = '1h' | '4h' | '8h' | 'permanent' | 'custom';
   const MAX_HORIZON_MS = 7 * 24 * 3600 * 1000;
   const MIN_HORIZON_MS = 5 * 60 * 1000;
   ```

2. New picker state:

   ```typescript
   const [pickerOpen, setPickerOpen] = useState(false);
   const [pickerValue, setPickerValue] = useState<string>(''); // datetime-local string
   const [pickerError, setPickerError] = useState<string | null>(null);
   ```

3. Extend the preset-inference block (currently lines 58-81): if `enabled && always_awake_until != null` and remaining seconds doesn't match `1h/4h/8h` within ±5min, set `activePreset = 'custom'`.

4. Render the fifth chip conditionally on `activePreset`. Active label is the chosen datetime formatted as `Bis DD.MM. HH:mm` (or full date if more than 6 days out).

5. New `setCustomPreset(value: string)` handler: validates locally (`MIN_HORIZON_MS ≤ delta ≤ MAX_HORIZON_MS`), then `updateSleepConfig({ always_awake_enabled: true, always_awake_until: new Date(value).toISOString() })` with the same optimistic-update + revert-on-error pattern the existing presets use (see lines 116-141).

6. **`<input type="datetime-local">` quirks:** value format is local time `YYYY-MM-DDTHH:mm`, no timezone. Conversion: `new Date(value).toISOString()` for the API call (browser interprets the local string in the user's TZ). Helper `toLocalInputValue(date: Date): string` for prefilling and for `min`/`max` attributes.

### 5.4 Popover implementation

A plain absolutely-positioned `<div>` anchored to the chip, with a click-outside listener (`useEffect` on `document.mousedown`). No Radix/Headless UI. The popover closes on Escape, on click outside, on Übernehmen success, and on Abbrechen.

## 6. i18n keys (new)

In `client/src/i18n/locales/{de,en}/system.json`:

```
sleep.osSettings.title
sleep.osSettings.refresh
sleep.osSettings.detailsToggle
sleep.osSettings.allClear
sleep.osSettings.sources
sleep.osSettings.issue.<key>            (one per backend issue.key)

sleep.alwaysAwake.presetCustom          "Bis Datum…"
sleep.alwaysAwake.activeCustom          "Bis {{datetime}}"
sleep.alwaysAwake.pickerLabel           "Datum & Uhrzeit"
sleep.alwaysAwake.pickerApply           "Übernehmen"
sleep.alwaysAwake.pickerCancel          "Abbrechen"
sleep.alwaysAwake.pickerErrorPast       "Zeitpunkt muss in der Zukunft liegen (mind. 5 Min)"
sleep.alwaysAwake.pickerErrorMax        "Maximal 7 Tage in der Zukunft"
```

EN strings are direct translations (e.g. `presetCustom: "Until date…"`).

## 7. Data flow

### 7.1 Page load

```
SleepMode mounts
  └─ OsSleepSettingsBanner.useEffect
       └─ GET /api/system/sleep/os-settings
            └─ os_sleep_inspector.inspect_os_sleep()
                 ├─ cache hit (≤60s old) → return cached report
                 └─ cache miss
                      ├─ platform check (sys.platform != "linux" → unsupported report)
                      ├─ parse logind.conf + drop-ins
                      ├─ parse sleep.conf + drop-ins
                      ├─ subprocess `systemctl is-enabled …` (5s timeout)
                      ├─ _classify(report) → issues[]
                      └─ cache + return
```

Refresh button takes the same path with `force=True`, bypassing the cache.

### 7.2 Custom datetime save

```
User picks 2026-05-14T18:30 → "Übernehmen"
  └─ AlwaysAwakePanel.setCustomPreset
       ├─ local validation (≥now+5min, ≤now+7d)
       ├─ optimistic update: enabled=true, until=ISO, expiresIn=secs, activePreset='custom'
       ├─ PUT /api/system/sleep/config
       │   { always_awake_enabled: true, always_awake_until: "2026-05-14T16:30:00Z" }
       │     └─ backend SleepConfigUpdate validator (future + ≤7d guard)
       └─ on success: keep state; on error: revert + toast.error
```

## 8. Error handling

**`os_sleep_inspector`:**
- `FileNotFoundError` on a config file → that section is empty in the report; no exception propagates. `sources` only lists files actually opened.
- `subprocess.TimeoutExpired` / non-zero exit on `systemctl is-enabled` → `targets` is empty `{}`; no exception. The classifier doesn't flag missing target data.
- INI parser sees a malformed line → log at WARNING, skip the line, continue.
- Unexpected exception → wrapped at the top of `inspect_os_sleep`, returns a report with a single `inspector.failed` error issue.

**Endpoint:** standard 401/403 from auth dep → handled by existing axios interceptor. No special UI.

**`OsSleepSettingsBanner`:**
- Network failure → render a single `error` issue tile inline; `[Refresh]` stays enabled. No toast (passive panel; toasts on every failed page mount would be noisy).
- `platform_supported: false` → returns `null` silently.

**`AlwaysAwakePanel`:**
- Backend rejects datetime (past or >7d) → revert optimistic state, `toast.error(err.message)`. Existing pattern at lines 134-140 already does this.
- Reopening popover with custom set → prefill `pickerValue` from `until` converted to local input format.

## 9. Testing strategy

### Backend

`tests/services/power/test_os_sleep_inspector.py` (new):

- `test_parse_logind_simple` — fixture `tmp_path/logind.conf` with `[Login]\nIdleAction=suspend\n`, assert dict.
- `test_drop_in_overrides_base` — base says `IdleAction=ignore`, drop-in `30-baluhost.conf` says `IdleAction=suspend` → effective value is `suspend`.
- `test_classifier_flags_idle_suspend` — fed a mock dict with `IdleAction=suspend`, expect a warning issue with key `logind.idle_action.suspend`.
- `test_classifier_flags_masked_target` — `targets={"suspend.target": "masked"}` → error issue.
- `test_unsupported_platform` — monkeypatch `sys.platform = "win32"` → `platform_supported is False`, no subprocess called.
- `test_cache_hit_skips_subprocess` — call twice within TTL, assert `subprocess.run` called once.
- `test_force_refresh_bypasses_cache` — `inspect_os_sleep(force_refresh=True)` calls subprocess on every call.
- `test_subprocess_timeout_does_not_raise` — patch `subprocess.run` to raise `TimeoutExpired` → report still returned, `targets` is `{}`.
- `test_inspector_catches_unexpected_exception` — patch `_parse_systemd_ini` to raise → report has `inspector.failed` issue, no exception escapes.

`tests/api/test_sleep_os_settings_route.py` (new):

- `test_requires_admin` — non-admin user → 403.
- `test_returns_report_for_admin` — admin → 200, body matches `OsSleepReportResponse`.
- `test_force_param_bypasses_cache` — patch the inspector, assert `force_refresh=True` propagated.

`tests/api/test_sleep_always_awake_routes.py` (existing, extend):

- `test_until_rejected_when_more_than_7_days` — PUT with `always_awake_until` 8 days out → 422.
- `test_until_accepted_at_6_days_23h` — PUT with 6d 23h → 200.

Full backend `pytest` run before PR (per existing memory `feedback_run_tests_before_pr`).

### Frontend

Type-check + manual smoke (project doesn't ship vitest tests for these panels, matching the established pattern from `2026-05-07-always-awake.md`):

1. `cd client && npx tsc --noEmit` clean.
2. `cd client && npm run build` succeeds.
3. `python start_dev.py`, navigate to System Control → Hardware → Sleep:
   - Banner: appears in Linux, returns `null` in Windows dev mode (no console error).
   - Custom button: `[Bis Datum…]` opens popover; picker enforces min/max; Übernehmen triggers `updateSleepConfig`.
   - Custom value persists across page reload (chip becomes `Bis 14.05. 18:30`).
   - Picking >7 days: backend 422, optimistic state reverts, toast appears.

## 10. Files touched

### Backend

| File | Change |
|---|---|
| `backend/app/services/power/os_sleep_inspector.py` | **new** — service module |
| `backend/app/schemas/sleep.py` | **add** `OsSleepIssue`, `OsSleepReportResponse`; **extend** `SleepConfigUpdate._validate_until_future` with 7-day cap |
| `backend/app/api/routes/sleep.py` | **add** `GET /os-settings` endpoint |
| `backend/tests/services/power/test_os_sleep_inspector.py` | **new** |
| `backend/tests/api/test_sleep_os_settings_route.py` | **new** |
| `backend/tests/api/test_sleep_always_awake_routes.py` | **extend** — 7-day cap tests |

### Frontend

| File | Change |
|---|---|
| `client/src/api/sleep.ts` | **add** `OsSleepReport`/`OsSleepIssue`/`getOsSleepSettings` |
| `client/src/components/power/OsSleepSettingsBanner.tsx` | **new** |
| `client/src/components/power/AlwaysAwakePanel.tsx` | extend with custom datetime button + popover |
| `client/src/pages/SleepMode.tsx` | mount `<OsSleepSettingsBanner />` as first child |
| `client/src/i18n/locales/de/system.json` | new keys under `sleep.osSettings.*` and `sleep.alwaysAwake.*` |
| `client/src/i18n/locales/en/system.json` | mirror DE keys |

## 11. Open questions / future work

- **Edit functionality** — masking targets / writing logind drop-ins from the UI was rejected for this iteration (YAGNI risk + sudo/polkit complexity). Could be a follow-up if users actually want it.
- **D-Bus integration** — also rejected for this iteration; file-parsing is sufficient and avoids a new dep. Could be revisited if file-resolved values diverge from runtime values often enough to be worth the cost.
- **Issue rule expansion** — initial classifier rules are intentionally narrow. Add rules incrementally as we hit real-world OS configurations that surprise users.
