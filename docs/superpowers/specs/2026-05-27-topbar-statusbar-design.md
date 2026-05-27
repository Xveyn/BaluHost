# Topbar Status Strip — Design (Refresh)

**Date:** 2026-05-27
**Status:** Approved
**Author:** Sven (Xveyn) + Claude
**Supersedes:** `docs/superpowers/specs/2026-05-10-topbar-statusbar-design.md` (commit `fc4663ad`, branch `feat/sleep-os-settings-and-custom-datetime`). That earlier spec was approved but its implementation plan was never written; the catalog has since gained three new pills.

## Problem

The BaluHost topbar has empty horizontal space between the mobile-header block and the right-side controls (NotificationCenter, UserMenu, PowerMenu). Status information that admins and users currently need to dig into individual pages for — power profile, Pi-hole on/off, active uploads, RAID health, sleep schedule, VPN clients, **Always-Awake overrides, running scheduler jobs, backup state** — has no at-a-glance surface.

## Solution

A read-only status strip in the topbar that shows admin-configurable pills. Each pill is a click-through link to its detail page. Admin can pick which pills appear, choose per-pill visibility ("Admin only" or "All Users"), and reorder them via drag-and-drop. The strip is hidden on mobile and in Pi-mode. Configuration lives under **System Control → System → Status Bar**.

## Requirements

- Admin enables/disables each pill from a fixed catalog (**11 pills initially**)
- Admin chooses visibility per pill: **Admin only** or **All Users**
- Pills with sensitive data (RAID, Sleep, VPN, Temp, Always Awake, Scheduler, Backup) are `visibility_locked=True` — visibility cannot be set to "All Users" via UI or API
- Admin reorders pills via drag-and-drop; order is global (same for everyone)
- A separate setting controls whether the existing bottom-right `UploadProgressBar` is shown (independent from the Uploads pill in the topbar)
- The strip is read-only — no mutations from the header, only navigation
- The strip is hidden on viewports `< lg` (1024px) and in Pi-mode (`__DEVICE_MODE__ === 'pi'`)
- Pills marked `silent_when_ok` are omitted from the response payload when there is nothing to report (RAID OK, Temp normal, no active uploads, Always-Awake off, no running jobs, no backup activity within 24h of a successful run, etc.) — they cost no pixels in the idle state
- Status payload polled every 10 seconds; pause polling when tab is hidden
- The Always-Awake pill renders a per-second client-side countdown derived from `expires_in_seconds` between polls; on every poll the server value re-anchors (drift > 5s wins)
- All pill data flows through one aggregator endpoint, filtered server-side by user role
- WCAG: status conveyed via icon + text + tone (never color alone); focus-visible ring on every pill; tooltip dismissable per WCAG 1.4.13

## Architecture

### Data flow

```
Admin                                   Any logged-in user
 │                                       │
 │  PUT /api/system/statusbar/config     │  GET /api/system/statusbar/state
 │  (enable, visibility, order, upload   │  (returns pill payload filtered
 │   bar toggle)                          │   by role; polled every 10s)
 │                                       │
 ▼                                       ▼
status_bar_pill_config (DB)          status_bar service
status_bar_settings    (DB)               │ collect_all_states()
                                          │   ↳ existing services
                                          │     (power, pihole, uploads,
                                          │      sync, raid, sleep, vpn,
                                          │      temp, always_awake,
                                          │      scheduler, backup)
                                          ▼
                                       <TopbarStatusStrip /> in Layout.tsx
```

### Persistence

Two new tables (additive migration, safe for live PostgreSQL 17.7):

```python
# backend/app/models/status_bar.py
class StatusBarPillConfig(Base):
    __tablename__ = "status_bar_pill_config"
    id          = Column(Integer, primary_key=True)
    pill_id     = Column(String(32), unique=True, nullable=False)
    enabled     = Column(Boolean, nullable=False, default=False)
    visibility  = Column(String(8), nullable=False, default="admin")  # "admin" | "all"
    sort_order  = Column(Integer, nullable=False, default=0)
    updated_at  = Column(DateTime(timezone=True), server_onupdate=func.now())

class StatusBarSettings(Base):
    __tablename__ = "status_bar_settings"
    id                  = Column(Integer, primary_key=True, default=1)  # singleton
    show_bottom_upload  = Column(Boolean, nullable=False, default=True)
```

The service layer ensures both tables are populated with sensible defaults on first read — fresh DB or new pills introduced in a future version are auto-inserted as `enabled=False`.

### Pill Catalog

Hardcoded registry in `backend/app/services/status_bar/catalog.py`. Mirrored frontend renderer-map in `client/src/components/topbar/pillRenderers.tsx`.

| `pill_id` | Name | Default visibility | `visibility_locked` | `silent_when_ok` | Click-through |
|---|---|---|---|---|---|
| `power`         | Power Profile        | admin | false    | false | `/admin/system-control?tab=energy` |
| `pihole`        | Pi-hole DNS          | admin | false    | false | `/pihole` |
| `uploads`       | Uploads / Downloads  | all   | false    | true  | `/files` |
| `sync`          | Sync                 | all   | false    | true  | `/devices` |
| `raid`          | RAID Health          | admin | **true** | true  | `/admin/system-control?tab=raid` |
| `sleep`         | Sleep Mode           | admin | **true** | true  | `/admin/system-control?tab=sleep` |
| `vpn`           | VPN Clients          | admin | **true** | false | `/admin/system-control?tab=vpn` |
| `temp`          | Temperature / Fans   | admin | **true** | true  | `/admin/system-control?tab=fan` |
| `always_awake`  | Always Awake         | admin | **true** | true  | `/admin/system-control?tab=sleep` |
| `scheduler`     | Scheduler            | admin | **true** | true  | `/admin/schedulers` |
| `backup`        | Backup               | admin | **true** | true  | `/admin/system-control?tab=backup` |

Free-to-expose-to-all (admin can choose): `power`, `pihole`, `uploads`, `sync`. Locked admin-only: `raid`, `sleep`, `vpn`, `temp`, `always_awake`, `scheduler`, `backup`.

`PillDefinition` shape:

```python
@dataclass
class PillDefinition:
    id: str
    name_key: str
    default_visibility: str            # "admin" | "all"
    visibility_locked: bool
    silent_when_ok: bool
    href: str
    collector: Callable[[Session, str], dict | None]
```

Each `collector` is a thin wrapper (5–20 LOC) around an existing service:

- `collect_power` → `power_manager.get_status()`
- `collect_pihole` → `pihole_backend.get_status()`
- `collect_uploads` → `upload_progress_manager.get_summary()`
- `collect_sync` → `sync_scheduler.get_active_summary()`
- `collect_raid` → `raid_backend.list_arrays()` filtered to `degraded/resync/failed`
- `collect_sleep` → `sleep_manager.get_schedule_summary()`
- `collect_vpn` → `vpn_service.get_active_peers_count()`
- `collect_temp` → `fan_control.get_status()` filtered to threshold-exceeded
- `collect_always_awake` → `sleep_manager.get_status().always_awake` (active only)
- `collect_scheduler` → count of `SchedulerExecution.status IN (RUNNING, REQUESTED)` plus up to 3 job-display names
- `collect_backup` → backup activity (see Backup-Pill semantics below)

A collector returns `None` for `silent_when_ok` pills with no signal, or wraps in try/except to return `None` on backend failure (no 5xx leaks into the strip).

#### Always-Awake-Pill semantics

- Returns `None` when `always_awake.enabled == False`.
- Returns a payload otherwise with:
  - `tone = "warning"` (auto-sleep is actively blocked)
  - `value = "permanent"` when `until is None`
  - `value = formatted countdown` when `until` is set (e.g. `"03:42"` for MM:SS, `"02:15:00"` for HH:MM:SS when >1h)
  - `extra = {"expires_in_seconds": float}` so the frontend can run a per-second client countdown between polls
- The pill **coexists** with the `sleep` pill — `sleep` shows the schedule status (e.g. "Sleep at 23:00"); `always_awake` shows the active override. When both are active simultaneously, the admin sees at a glance that the override is blocking the scheduled sleep.

#### Scheduler-Pill semantics

- Returns `None` when no execution is in `RUNNING` or `REQUESTED`.
- Returns `tone="info"`, `value="3"` (active count), `extra={"jobs": ["Backup", "Health Check", "..."]}` with up to 3 most-recently-started display names.
- The frontend renders the count as the pill value and the job names as a native `title` tooltip.

#### Backup-Pill semantics

Three states:

| Condition | Output |
|---|---|
| Any backup in `running` or `requested` state | `tone="info"`, `value="47%"` (progress) or `value="läuft"` if no progress available |
| Most recent finished backup is `status="failed"` **and** finished < 24h ago | `tone="danger"`, `value="fehlgeschlagen"` |
| Most recent backup older than 24h ago, or finished status is `completed` | `None` (silent) |

The 24h window prevents a failure from haunting the topbar indefinitely; if it really matters, the admin will see it on the Backup page. After 24h the failure age is too old to be actionable from a status pill.

## API

New router `backend/app/api/routes/status_bar.py`, mounted at `/api/system/statusbar`:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET`  | `/api/system/statusbar/config` | admin | Full catalog + current persisted config + `show_bottom_upload` |
| `PUT`  | `/api/system/statusbar/config` | admin | Bulk update (per-pill `enabled`/`visibility`/`sort_order` + `show_bottom_upload`) |
| `GET`  | `/api/system/statusbar/state`  | any-auth | Aggregated pill payload, filtered by user role |

All endpoints rate-limited via `@limiter.limit(get_limit(...))`. Use the existing `admin_operations` key for the admin write endpoints; for the high-frequency `GET /state` (every 10s per logged-in user), introduce a new rate-limit key `status_polling` in `backend/app/core/rate_limiter.py` with a generous default (e.g. 30/minute) so it doesn't trip on legitimate use. Pydantic schemas in `backend/app/schemas/status_bar.py`:

```python
PILL_IDS = Literal[
    "power","pihole","uploads","sync","raid","sleep","vpn","temp",
    "always_awake","scheduler","backup",
]

class PillConfigItem(BaseModel):
    pill_id: PILL_IDS
    enabled: bool
    visibility: Literal["admin", "all"]
    sort_order: int

class StatusBarConfigUpdate(BaseModel):
    pills: list[PillConfigItem]
    show_bottom_upload: bool

class PillState(BaseModel):
    id: PILL_IDS
    kind: Literal["state", "activity", "alert"]
    tone: Literal["success", "info", "warning", "danger", "neutral"]
    label: str
    value: str | None = None
    icon: str | None = None
    href: str
    extra: dict | None = None    # e.g. {"expires_in_seconds": 3742.5} for always_awake

class StatusBarStateResponse(BaseModel):
    pills: list[PillState]
    show_bottom_upload: bool
```

Server-side validation rejects PUT with `visibility="all"` for any `visibility_locked=True` pill → 400 Bad Request.

> **Schema note:** the `PILL_IDS` Literal is hardcoded to the current 11-pill catalog. When a future pill is added, both the Python `CATALOG` list and the Pydantic `Literal` need updating — the schema validator should fail loudly if these drift apart, and the catalog has a unit test (`test_pill_id_literal_matches_catalog`) that asserts equality.

### Audit logging

Every successful PUT writes one audit event `status_bar.config_changed` with the user_id and a JSON diff (added/removed pills, visibility changes, reordering, upload-bar toggle).

## Frontend

### Component tree

```
client/src/components/topbar/
├── TopbarStatusStrip.tsx          — container, ≥ lg only, fetches state, maps to renderers
├── pillRenderers.tsx              — { pill_id → React component }
├── pills/
│   ├── PowerPill.tsx · PiholePill.tsx · UploadsPill.tsx · SyncPill.tsx
│   ├── RaidPill.tsx · SleepPill.tsx · VpnPill.tsx · TempPill.tsx
│   └── AlwaysAwakePill.tsx · SchedulerPill.tsx · BackupPill.tsx
└── useStatusBarState.ts            — polling hook, 10s interval, pause-when-hidden

client/src/components/ui/Pill.tsx    — generic primitive (tone, icon, label, value, href)

client/src/components/status-bar-config/
├── StatusBarConfigTab.tsx          — admin config UI (System Control tab)
├── PillRow.tsx                     — single row: drag-handle + label + visibility-select + enabled-toggle
└── usePillConfig.ts                — admin write/read hook
```

`AlwaysAwakePill.tsx` includes a `useCountdown(expiresInSeconds)` hook that decrements once per second. When a new poll arrives with a fresh `expires_in_seconds`, the countdown re-anchors to the server value; if the local countdown has drifted >5s from the server value, the server value wins immediately (defensive against tab-throttling).

### Layout integration

`Layout.tsx:517` currently has `<div className="hidden lg:block flex-1" />` as a desktop-only spacer. That becomes:

```tsx
<div className="hidden lg:flex flex-1 items-center justify-center px-6">
  {!isPi && <TopbarStatusStrip />}
</div>
```

Mobile header is unchanged.

### `<Pill>` primitive

Generic, theme-aware. Tone → tailwind classes via a small lookup. A11y: rendered as `<Link>`, `aria-label` derived from `label`+`value`, `title` attribute for native browser tooltip on desktop, focus-visible ring inherited from project's existing button styles.

```tsx
type PillTone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';
type PillProps = {
  tone: PillTone;
  icon?: React.ReactNode;
  label: string;
  value?: string;
  href: string;
  ariaLabel?: string;
};
```

Tone classes (matching existing glass-accent slate theme):
- `success` → `border-emerald-500/40 bg-emerald-500/10 text-emerald-300`
- `info`    → `border-sky-500/40 bg-sky-500/10 text-sky-300`
- `warning` → `border-amber-500/40 bg-amber-500/10 text-amber-300`
- `danger`  → `border-rose-500/40 bg-rose-500/10 text-rose-300`
- `neutral` → `border-slate-700 bg-slate-800/60 text-slate-300`

### `useStatusBarState` hook

Uses TanStack Query (already a project dependency) which natively supports `refetchIntervalInBackground: false` via the Page Visibility API:

```ts
useStatusBarState({
  refetchInterval: 10_000,
  refetchIntervalInBackground: false,   // pauses when document.hidden === true
  staleTime: 8_000,                      // tolerate brief network hiccups
})
```

On 3 consecutive failures → return last-known state with a stale flag; if no last-known state → return empty pill list.

### Config UI (System Control tab)

New tab registered in `client/src/pages/SystemControlPage.tsx` under category `system`:

```tsx
{ id: 'statusbar', labelKey: 'systemControl.tabs.statusBar', icon: <LayoutPanelTop className="h-5 w-5" /> }
```

Layout (11 rows, scrollable if needed):

```
[Header: "Topbar Status Strip" + helper text]

[Card: Pills — drag to reorder]
  ┌─────────────────────────────────────────────────────────────────┐
  │ ≡  ⚡ Power Profile                [▼ Admin only]   [●——] active │
  │ ≡  🛡  Pi-hole DNS                 [▼ All Users]    [●——] active │
  │ ≡  ↑   Uploads/Downloads           [▼ All Users]    [——●] off    │
  │ ≡  ⟳   Sync                        [▼ All Users]    [——●] off    │
  │ ≡  ⚠   RAID Health                 [🔒 Admin only]  [●——] active │
  │ ≡  🌙  Sleep Mode                  [🔒 Admin only]  [——●] off    │
  │ ≡  🔐  VPN Clients                 [🔒 Admin only]  [——●] off    │
  │ ≡  🌡  Temperature                 [🔒 Admin only]  [——●] off    │
  │ ≡  ⏰  Always Awake                [🔒 Admin only]  [●——] active │
  │ ≡  ⚙   Scheduler                   [🔒 Admin only]  [——●] off    │
  │ ≡  💾  Backup                      [🔒 Admin only]  [——●] off    │
  └─────────────────────────────────────────────────────────────────┘

[Card: Bottom Upload Bar]
  ┌────────────────────────────────────────────────┐
  │ Show bottom upload bar          [●——] on        │
  │ Independent from the Uploads pill in the topbar │
  └────────────────────────────────────────────────┘

[Card: Live Preview]
  ┌────────────────────────────────────────────────────────┐
  │ [⚡ Performance] [🛡 Pi-hole · 23%] [⏰ Always Awake 03:42] │
  └────────────────────────────────────────────────────────┘

[Footer: Save / Reset to defaults]
```

Drag-and-drop via `@dnd-kit/sortable` with `verticalListSortingStrategy`. The visibility-select is a small dropdown; for `visibility_locked=true` pills it renders as a read-only badge with a lock icon.

`<TopbarStatusStrip>` accepts an optional `previewState?: StatusBarStateResponse` prop. When provided, it renders the supplied state and skips polling — the Config tab's Live Preview uses this to render the unsaved config exactly as the real strip would render it server-side, with no API roundtrip.

### i18n

New namespace `statusBar` with keys `tabTitle`, `description`, `pills.<id>.name` (11 entries), `visibility.{admin,all,locked}`, `uploadBar.{title,desc}`, `preview.{title,empty}`. Plus `systemControl.tabs.statusBar` in `common.json`. DE + EN.

## Edge Cases

| Case | Handling |
|---|---|
| No pill enabled | Container renders empty, no visual artifact |
| `/state` returns 5xx | Hook holds last-known state; after 3 failures, clear pills + console warning. No toast. |
| Pi-hole backend unreachable | Collector returns `None` → pill missing from payload, no error in UI |
| User role changes mid-session (promote/demote) | Next poll returns role-correct payload; pills update transparently |
| Pi-mode (`__DEVICE_MODE__=pi`) | `<TopbarStatusStrip>` not rendered, tree-shaken from build |
| Setup wizard active | `Layout.tsx` not rendered, no conflict |
| Visibility changed from "all" to "admin" while user views | Next poll filters pill out, it disappears |
| Catalog pill missing in DB (fresh install or new pill in update) | Service inserts it with `enabled=False, visibility=default_visibility, sort_order=999` |
| Migration re-run | `CREATE TABLE IF NOT EXISTS` + `INSERT ... ON CONFLICT DO NOTHING` — idempotent |
| Pill collector raises | Wrapped in try/except, returns `None`, pill silently absent |
| New pill introduced in future version | Appears in admin config tab disabled by default — no auto-enable |
| PUT with `visibility="all"` for locked pill | 400 Bad Request from server-side validator |
| Config changed by another admin in second tab | Frontend re-fetches on focus; latest wins (last-write-wins is acceptable here) |
| `always_awake` expires between polls | Client countdown hits 00:00, pill remains until next poll returns `None`; visually OK (≤10s lag) |
| Always-Awake `until` race (server clears just after a poll) | Next poll returns `None`, pill disappears |
| Scheduler executes >50 jobs concurrently | Pill shows count, `extra.jobs` capped at 3 most-recently-started entries (consistent with collector ordering) |
| Backup just transitioned `running` → `failed` between polls | Next poll within 10s flips pill from info to danger |
| Backup `running` and previous failure within 24h | `running` state wins (in-progress is more actionable) |

## Security

- `PUT /api/system/statusbar/config` → `Depends(get_current_admin)`, rate-limited
- `GET /api/system/statusbar/state` → `Depends(get_current_user)` (any auth), server filters by role
- `visibility_locked` enforced server-side, not just UI — prevents privilege escalation via crafted PUT
- Audit-log entry on every config change (who, what, when, diff)
- No sensitive data in `/state` payload — no IPs, no file paths, no disk serials, no usernames; only display-ready strings
- Pi-hole pill exposed to non-admins shows only on/off + global block percent — no per-client query data
- VPN, RAID, Sleep, Temp, Always-Awake, Scheduler, Backup pills are `visibility_locked` — non-admins never see this data, even if a future bug allows toggling visibility
- Scheduler pill's `extra.jobs` contains user-facing display names only, not internal job IDs or parameter dumps

## Tests

### Backend (`backend/tests/test_status_bar.py`)

| Test | Verifies |
|---|---|
| `test_default_config_returns_full_catalog` | Fresh DB → GET returns all 11 catalog pills with defaults |
| `test_admin_can_enable_pill` | PUT with `enabled=True` → subsequent GET shows pill enabled |
| `test_visibility_locked_rejects_all` | PUT `pill_id=raid, visibility=all` → 400 |
| `test_state_endpoint_filters_admin_pills_for_user` | Non-admin user → enabled admin-only pill not in payload |
| `test_state_endpoint_includes_all_pill_for_user` | Non-admin → pill with `visibility=all` is in payload |
| `test_silent_when_ok_pill_omitted_when_no_signal` | RAID all OK → no RAID pill in payload |
| `test_silent_when_ok_pill_present_when_problem` | RAID degraded → RAID pill with `tone=warning` in payload |
| `test_collector_failure_returns_none_not_500` | Pi-hole backend raises → pill missing, endpoint returns 200 |
| `test_sort_order_respected_in_state_payload` | Pills in payload are sorted by `sort_order` |
| `test_show_bottom_upload_setting_in_state` | `show_bottom_upload` is in `/state` response |
| `test_audit_log_on_config_change` | PUT creates audit-log entry with user_id and diff |
| `test_user_endpoint_rejects_anonymous` | GET `/state` without JWT → 401 |
| `test_admin_endpoint_rejects_user` | PUT `/config` as non-admin → 403 |
| `test_new_catalog_pill_auto_inserted_on_read` | Catalog has 12th pill → service inserts row, GET returns 12 pills |
| `test_pill_id_literal_matches_catalog` | `PILL_IDS` Literal values exactly match `CATALOG` ids — drift detection |
| `test_always_awake_pill_active_with_countdown` | `always_awake.enabled=True, until=now+1h` → pill with `extra.expires_in_seconds ≈ 3600` |
| `test_always_awake_pill_active_permanent` | `enabled=True, until=None` → pill with `value="permanent"`, no `expires_in_seconds` |
| `test_always_awake_pill_silent_when_disabled` | `enabled=False` → no pill in payload |
| `test_scheduler_pill_shows_active_count` | 2 RUNNING + 1 REQUESTED → pill with `value="3"`, `extra.jobs` list ≤3 entries |
| `test_scheduler_pill_silent_when_no_jobs` | No active executions → no pill |
| `test_scheduler_pill_caps_jobs_at_three` | 5 RUNNING → `extra.jobs` has exactly 3 entries (newest-started first) |
| `test_backup_pill_in_progress` | One backup `status=running` → pill with `tone=info`, `value=progress%` or `"läuft"` |
| `test_backup_pill_failed_within_24h` | Last backup `status=failed, finished 2h ago` → pill with `tone=danger` |
| `test_backup_pill_silent_when_failed_older_than_24h` | Last backup `status=failed, finished 25h ago` → no pill |
| `test_backup_pill_silent_when_last_completed` | Last backup `status=completed` → no pill |
| `test_backup_pill_running_beats_failed` | One `running` + one recent `failed` → pill shows `running`, not `failed` |

### Frontend (`client/src/components/topbar/__tests__/`, `status-bar-config/__tests__/`)

| Test | Verifies |
|---|---|
| `TopbarStatusStrip renders nothing when no pills` | Empty payload → no children |
| `TopbarStatusStrip renders pills in order` | Payload with 3 pills → 3 anchors in correct order |
| `TopbarStatusStrip is hidden on mobile` | Test viewport `< lg` → strip not in DOM |
| `TopbarStatusStrip is hidden in Pi mode` | `__DEVICE_MODE__=pi` → strip not rendered |
| `Pill renders correct tone classes` | Snapshot per tone |
| `Pill click navigates to href` | userEvent.click → `useNavigate` invoked with href |
| `AlwaysAwakePill counts down per second` | Render with `expires_in_seconds=120`, fake-timer +5s → value "01:55" |
| `AlwaysAwakePill re-anchors on new poll` | Drift >5s between local countdown and incoming poll → server value applied |
| `AlwaysAwakePill renders 'permanent' when no expiry` | `expires_in_seconds=null` → static "permanent" label |
| `SchedulerPill renders count and tooltip` | Payload with 3 jobs → value="3", `title` contains all 3 names |
| `BackupPill in-progress tone` | `tone=info, value="47%"` → info classes applied |
| `BackupPill failed tone` | `tone=danger, value="fehlgeschlagen"` → danger classes applied |
| `StatusBarConfigTab disables visibility-select for locked pills` | Locked pill → select is `aria-disabled` |
| `StatusBarConfigTab updates sort_order on drag` | dnd-kit fireEvent → API call with new order |
| `StatusBarConfigTab live preview reflects unsaved changes` | Toggle changes preview without save |
| `StatusBarConfigTab save then reload preserves order` | Save → reload → order unchanged |

### Manual smoketest (post-deploy)

1. Login as admin, open System Control → System → Status Bar
2. Enable Power, Pi-hole, Uploads, Always Awake, Scheduler, Backup with mixed visibilities
3. Drag-reorder, save → verify topbar reflects order
4. Toggle bottom-upload off → verify `<UploadProgressBar>` disappears
5. Trigger an upload → verify Uploads pill appears with progress
6. Login as non-admin user (second browser) → verify only "All Users" pills visible (Always-Awake/Scheduler/Backup NOT visible)
7. Simulate RAID degraded (dev backend) → verify RAID pill appears with warning tone
8. Toggle Always Awake on with 5-minute preset → verify pill appears with live countdown
9. Trigger a manual scheduler run → verify Scheduler pill appears with count=1, name in tooltip
10. Simulate backup failure (dev backend) → verify Backup pill appears with danger tone; advance time >24h → pill disappears
11. Promote user to admin via DB → on next poll, admin-only pills appear
12. Open in Pi-mode build → strip not shown
13. Resize to mobile → strip not shown

## Build Order

1. **Backend foundation** — Migration, models, catalog (11 entries) with stub collectors
2. **Backend collectors** — One commit per real collector (11 commits, of which 3 are new vs. 2026-05-10)
3. **Backend API + service** — Routes, schemas, service layer, tests
4. **Frontend foundation** — `<Pill>` primitive, `useStatusBarState()`, `<TopbarStatusStrip>` with mock data
5. **Frontend pill renderers** — 11 small components (3 new: `AlwaysAwakePill`, `SchedulerPill`, `BackupPill`)
6. **Frontend countdown hook** — `useCountdown` for Always-Awake re-anchoring
7. **Layout integration** — replace empty spacer in `Layout.tsx`
8. **Config tab (MVP)** — Up/Down buttons for reorder
9. **dnd-kit reorder** — drag-and-drop replacement for buttons
10. **Live Preview** — preview card in config tab
11. **i18n** — DE+EN strings (11 pill names)
12. **Audit logging** — hook in `update_config`
13. **Frontend tests** — parallel to implementation
14. **Smoketest** — full manual run-through

Estimated: ~14–18 hours focused work (3–4h more than the 2026-05-10 spec, due to 3 extra pills + countdown hook), splittable into ~5–6 PRs (backend / frontend strip / countdown+new pills / config tab / dnd reorder / polish).

## Out of Scope

- Plugin-defined pills (catalog is hardcoded; later extension if a plugin needs it)
- WebSocket push (10s polling sufficient; Always-Awake countdown handled client-side between polls)
- Per-user pill customization (admin decides globally)
- Mobile mini-bar (mobile keeps current header unchanged)
- Popovers / quick-actions in pills (read-only click-through only)
- Custom tooltip widget (browser-native `title` is enough)
- Updates-available pill, Live-Power-W pill, Free-Storage pill, Services-Health pill — discussed and explicitly deferred (2026-05-27 brainstorming session)
- Acked-failure persistence for backup pill — 24h time-window deemed sufficient

## References

- `client/src/components/Layout.tsx` — host file for `<TopbarStatusStrip>` integration (replaces line 517 spacer)
- `client/src/pages/SystemControlPage.tsx` — receives new `statusbar` tab under `system` category
- `client/src/App.tsx:233` — confirms Backup route `/admin/system-control?tab=backup`
- `client/src/components/UploadProgressBar.tsx` — gated by new `show_bottom_upload` setting
- `backend/app/services/upload_progress.py` — already exposes `get_summary()` for collector
- `backend/app/services/power/manager.py` — `get_status()` for power collector
- `backend/app/services/power/sleep.py` — `get_status().always_awake` for always-awake collector (incl. `expires_in_seconds`)
- `backend/app/services/scheduler/service.py` — `SchedulerExecution` table query for scheduler collector
- `backend/app/services/backup/service.py` — backup state query for backup collector
- `docs/superpowers/specs/2026-05-07-always-awake-design.md` — Always-Awake feature this pill reflects
- `docs/superpowers/specs/2026-05-10-topbar-statusbar-design.md` — superseded base spec
- `.claude/rules/security-agent.md` — auth dependencies, audit-logging patterns
