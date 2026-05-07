# Always Awake (Immer wach)

**Date:** 2026-05-07
**Status:** Approved

## Problem

Currently, an admin who wants to keep the NAS unconditionally awake (e.g. during a long migration, transcode, or troubleshooting session) must manually disable three independent sleep mechanisms:

- `auto_idle_enabled` (auto-idle detection)
- `schedule_enabled` (sleep schedule)
- `auto_escalation_enabled` (soft sleep → suspend)

Re-enabling each one afterwards is error-prone. Kernbetriebszeit (`core_uptime_enabled`) is the closest existing override, but it is a recurring time-of-day pattern — not a one-shot "stay awake right now" switch.

## Solution

Add a global, time-independent override `always_awake` to `SleepConfig`. While active it suppresses the same three auto-sleep paths Kernbetriebszeit already suppresses. The override can be set permanently or with an absolute UTC expiry. After expiry, or when the admin manually triggers Sleep/Suspend, the override is cleared automatically — restoring normal Schedule/Kernbetriebszeit behavior on the next wake.

Manual `Sleep`, `Suspend`, and `WoL` paths remain unaffected; the override only blocks automatic transitions.

## Behavior

| Trigger | always_awake state change |
|---|---|
| Admin sets toggle ON, no expiry | `enabled=True`, `until=NULL` (permanent) |
| Admin sets toggle ON with preset (e.g. 4h) | `enabled=True`, `until=now+4h` (UTC) |
| Admin sets toggle OFF | `enabled=False`, `until=NULL` |
| `until` < now (Schedule loop tick) | `enabled=False`, `until=NULL`; audit `always_awake_expired` |
| Manual `enter_soft_sleep` | clear if active; audit `always_awake_cleared_by_sleep` |
| Manual `enter_true_suspend` | clear if active; audit `always_awake_cleared_by_sleep` |
| WoL | no change |

While `always_awake` is active:

- `_idle_detection_loop` skips Soft-Sleep trigger
- `_schedule_check_loop` skips both Schedule-Sleep trigger and Auto-Escalation
- Manual entry points are unblocked (admin can still suspend with one click)

## Backend

### Data model

`backend/app/models/sleep.py` — extend `SleepConfig` (singleton id=1):

```python
always_awake_enabled: Mapped[bool] = mapped_column(
    Boolean, default=False, nullable=False
)
always_awake_until: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

Stored in UTC. `NULL` means "permanent" (no expiry).

Alembic migration: additive, with default `False` / `NULL`. No backfill.

### Service

`backend/app/services/power/sleep.py`:

- New helper `_is_always_awake(self, config: SleepConfig) -> bool`:

```python
def _is_always_awake(self, config) -> bool:
    if not config or not config.always_awake_enabled:
        return False
    if config.always_awake_until is None:
        return True
    return datetime.now(timezone.utc) < config.always_awake_until
```

- `_idle_detection_loop`: before triggering Soft-Sleep, `if self._is_always_awake(config): continue`. Same place as the existing core-uptime guard.

- `_schedule_check_loop`: same guard before Schedule-Sleep trigger and before Auto-Escalation. At the top of every tick, also clean up expired override:

```python
if config.always_awake_enabled and config.always_awake_until \
        and datetime.now(timezone.utc) >= config.always_awake_until:
    self._clear_always_awake(reason="always_awake_expired")
```

- New private `_clear_always_awake(self, reason: str) -> None`: opens a session, sets both fields to defaults, commits, writes an audit log entry.

- `enter_soft_sleep` and `enter_true_suspend`: at the start, if always-awake is active, call `_clear_always_awake(reason="always_awake_cleared_by_sleep")` before continuing. The sleep itself proceeds.

- `get_status`: include `AlwaysAwakeStatus`.

- `get_config`: include both new fields.

### Schemas

`backend/app/schemas/sleep.py`:

```python
class AlwaysAwakeStatus(BaseModel):
    enabled: bool = False
    until: Optional[datetime] = None
    expires_in_seconds: Optional[float] = None  # for live UI countdown
```

Add to `SleepStatusResponse`:

```python
always_awake: AlwaysAwakeStatus = Field(default_factory=AlwaysAwakeStatus)
```

Extend `SleepConfigResponse` and `SleepConfigUpdate`:

```python
always_awake_enabled: Optional[bool] = None
always_awake_until: Optional[datetime] = None
```

`SleepConfigUpdate` validator:
- If `always_awake_until` is provided and not `None`, it must be in the future (UTC). Otherwise raise `ValueError`.
- Service-side: if the update sets `always_awake_enabled=False`, normalize `always_awake_until` to `None`.

### API

No new routes. Existing `PUT /api/system/sleep/config` (admin, rate-limited) accepts the two new fields and emits an `always_awake_toggled` audit log entry on every change. `GET /status` and `GET /config` surface the new state.

### Audit log entries

- `always_awake_toggled` — admin action via API, details `{enabled, until}`
- `always_awake_expired` — system action from Schedule loop
- `always_awake_cleared_by_sleep` — system action from `enter_soft_sleep` / `enter_true_suspend`

`SleepStateLog`: no new entries. The override changes loop behavior, not state machine state, and the existing Kernbetriebszeit feature also does not log per-tick suppressions.

## Frontend

### New component

`client/src/components/power/AlwaysAwakePanel.tsx` — own card, inserted in `pages/SleepMode.tsx` between `SleepModePanel` and `CoreUptimePanel`:

```
┌─ Immer wach ───────────────────────────  [●○] ┐
│  Auto-Sleep, Schedule und Auto-Escalation     │
│  werden ignoriert. Manueller Sleep ist        │
│  weiterhin möglich.                           │
│                                                │
│  (when active:)                               │
│  Aktiv bis: 14:30 (in 2h 15m)   [Aufheben]    │
│                                                │
│  Quick-Presets:  [1h] [4h] [8h] [Dauerhaft]   │
└────────────────────────────────────────────────┘
```

Behavior:

- Master toggle (top right) flips `always_awake_enabled` with optimistic update; pattern from `CoreUptimePanel`.
- Activating without a preset choice defaults to `until=null` ("Dauerhaft").
- Preset buttons set `until=now+Δ` (UTC ISO). "Dauerhaft" sets `until=null`. Active choice is highlighted.
- When `until` is set: countdown rendered from `expires_in_seconds`, decremented client-side every second.
- "Aufheben" sends `enabled=false` (and clears `until` server-side).

Conditional hint banners inside the same card:

- If `always_awake.enabled` AND (`schedule_enabled` OR `core_uptime_enabled`) AND `always_awake.until !== null`: yellow note *"Geplante Kernbetriebszeit / Sleep-Schedule wird ab {time} wieder berücksichtigt."*
- If `always_awake.enabled` AND `until === null`: blue note *"Dauerhaft aktiv — schalte aus, damit Schedule/Kernbetriebszeit wieder greifen."*

### Cross-component touches

- `SleepModePanel.tsx`: when `status.always_awake.enabled`, render an extra emerald-styled banner under the existing Kernbetriebszeit banner: *"Immer wach aktiv [bis {time} | dauerhaft] — Auto-Sleep blockiert."*
- `SleepConfigPanel.tsx`: in the Schedule block, mirror the existing Kernbetriebszeit hint when `always_awake.enabled` is on.

### API client

`client/src/api/sleep.ts`:
- `SleepConfigResponse` / `SleepConfigUpdate` get `always_awake_enabled?: boolean` and `always_awake_until?: string | null`.
- New type `AlwaysAwakeStatus { enabled, until, expires_in_seconds }`.
- `SleepStatusResponse.always_awake?: AlwaysAwakeStatus`.

### i18n

New subtree `system.sleep.alwaysAwake.*` in both `de/system.json` and `en/system.json`. Keys:

```
title, description, masterToggle
preset1h, preset4h, preset8h, presetPermanent
activeUntil, dauerhaftActive, cancel, untilTime
hintScheduleResumes, hintPermanentClearToResume
bannerActive, bannerActiveWithUntil
```

## Edge cases

1. **Reboot with active `until`**: first Schedule-loop tick after boot detects `until < now` and clears cleanly. No special boot path.
2. **Clock jump (NTP, DST)**: stored UTC + `datetime.now(timezone.utc)` comparison. Robust against local time changes.
3. **WoL while active**: WoL is a wake path, not a sleep path. Override is not cleared.
4. **Auto-wake on Kernbetriebszeit start while in Soft-Sleep**: pre-existing logic; unchanged. Only matters if override was off at sleep time.
5. **`until` in the past via API**: `SleepConfigUpdate` validator rejects with 422.
6. **`enabled=false` with `until` set in same payload**: service normalizes `until=null` after applying the update, so client never sees a stale future timestamp on a disabled override.

## Testing

### Backend unit tests — `backend/tests/services/test_sleep_always_awake.py` (new)

- Auto-idle loop skips trigger when override active (mirror of `test_idle_loop_skipped_during_core_uptime`)
- Schedule loop skips Sleep trigger when override active
- Schedule loop skips Auto-Escalation when override active
- `until=null` → dauerhaft (`_is_always_awake` returns True)
- `until` future → True; `until` past → False
- Schedule loop with `until` past clears the flag and writes `always_awake_expired` audit entry
- `enter_soft_sleep` clears override and writes `always_awake_cleared_by_sleep`
- `enter_true_suspend` clears override and writes `always_awake_cleared_by_sleep`
- Regression: `_is_always_awake` works with naive `datetime.now()` legacy data and UTC-aware `until` (no `TypeError`)

### Backend API tests — `backend/tests/api/test_sleep_always_awake.py` (new)

- Admin can set `enabled=true` with `until=now+1h` → 200, status reflects new state
- Regular user → 403
- `until` in the past → 422
- `enabled=false` resets `until` to `null`
- Roundtrip: `GET /config` and `GET /status` return the new fields after update

### Frontend

No automated tests added (Vitest is a placeholder per repo convention). Manual smoke test in dev mode covers the verification step.

## Out of scope

- Wakelock-style multi-source override list (YAGNI for single-admin NAS)
- Quick toggle in the global PowerMenu / header (user opted for Sleep-page-only access)
- Automated frontend tests (matches repo convention)
- Notifications about expiry (audit log is sufficient; can be added later if requested)
