# Lifecycle Push Notifications — Design Spec

**Status:** Approved
**Date:** 2026-04-30
**Author:** Xveyn (via brainstorming session)

## Problem

BaluHost has a mature push-notification system (RAID, SMART, Backup, Security events), but no notifications for the four core NAS lifecycle transitions:

1. **Suspend** — NAS enters `systemctl suspend` (becomes unreachable, ~1-2W)
2. **Resume** — NAS wakes from suspend
3. **Shutdown** — NAS is gracefully shut down
4. **Startup** — NAS cold-boots and is ready

Users currently have no immediate signal when the NAS goes offline or comes back, which matters because:
- Mobile devices lose access without warning
- Scheduled / auto-idle suspends happen unattended
- Cold-boot vs. resume is operationally different (downtime context)

## Goals

- Push notifications for all four lifecycle events
- Distinguish *resume from suspend* vs *cold startup*
- Include useful context (suspend duration, downtime, trigger source)
- Reuse the existing `EventEmitter` infrastructure (no parallel pipeline)
- Per-user opt-in via a new `lifecycle` notification category

## Non-Goals

- Notifications for Soft Sleep transitions (system stays reachable — too noisy)
- Replacing or modifying the BaluPi handshake (parallel concern, keep separate)
- New frontend page for lifecycle history (existing Sleep History covers most; can come later if needed)
- Retry mechanism for failed FCM pushes (best-effort)
- `system.suspend_failed` event (existing sleep error logs cover this)

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Trigger-Punkte (4 Stellen, alle nur PRIMARY_WORKER)            │
├────────────────────────────────────────────────────────────────┤
│  core/lifespan.py                                               │
│    _startup()  ──►  emit system.startup  (mit Downtime-Kontext) │
│    _shutdown() ──►  emit system.shutdown (early, mit ~3s wait)  │
│                                                                 │
│  services/power/sleep.py                                        │
│    enter_true_suspend()                                         │
│      ├─ before _backend.suspend_system() ──► emit system.suspend│
│      └─ after suspend returns ─────────────► emit system.resume │
└────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────┐
│  events.py: EventEmitter (existing, unchanged)                 │
│   - 4 new EventType values                                     │
│   - 4 new EVENT_CONFIGS (category="lifecycle", type="info")    │
│   - emit_for_admins_sync(...) bzw. async-Variante              │
└────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼──────────────────┐
            ▼                 ▼                  ▼
┌────────────────┐  ┌──────────────────┐  ┌──────────────┐
│ Notification-  │  │ Per-User-Routing │  │ FCM-Push     │
│ Eintrag in DB  │  │ + Quiet-Hours    │  │ via Firebase │
│ (existing)     │  │ (existing logic) │  │ (existing)   │
└────────────────┘  └──────────────────┘  └──────────────┘

Persistenz für Downtime-Berechnung:
  models/system_lifecycle.py  ─►  Tabelle system_lifecycle_events
    (id, event_type, timestamp, trigger, details_json)
```

**Kernidee:** Wiederverwendung des bestehenden `EventEmitter` 1:1; Eingriff an exakt 4 Stellen. Bestehendes Routing/Preferences/Quiet-Hours/FCM-Cleanup gilt automatisch.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Sleep scope | Only True Suspend (Soft Sleep stays silent) |
| Trigger filter | All triggers notify (manual, schedule, auto_idle, auto_escalation) |
| Recipients | New `lifecycle` notification category — admins default-on, non-admins default-off, fully configurable per user |
| Resume content | With context: duration + trigger |
| Shutdown timing | Best-effort with ~3s wait on FCM HTTP response |
| Persistence | New DB table `system_lifecycle_events` |

## Components

### New files

| File | Purpose |
|---|---|
| `backend/app/models/system_lifecycle.py` | SQLAlchemy model `SystemLifecycleEvent` (`id`, `event_type` [str], `timestamp` [UTC], `trigger` [str, nullable], `details_json` [str, nullable]) |
| `backend/alembic/versions/<rev>_add_system_lifecycle_events.py` | Alembic migration for new table |
| `backend/tests/test_lifecycle_notifications.py` | Unit tests |

### Modified files

| File | Change |
|---|---|
| `services/notifications/events.py` | 4 new `EventType` values: `SYSTEM_SUSPEND`, `SYSTEM_RESUME`, `SYSTEM_SHUTDOWN`, `SYSTEM_STARTUP`. 4 new `EVENT_CONFIGS` (category=`"lifecycle"`, type=`"info"`, priority=1). 4 new cooldowns (60s for suspend/resume; 0s for shutdown/startup). 4 sync convenience helpers + async variants for use in lifespan |
| `services/notifications/service.py` | `_get_category_pref()` extended for `"lifecycle"`. Default prefs: admins on (push+inapp), non-admins off |
| `services/power/sleep.py` | `enter_true_suspend()`: before `_backend.suspend_system()` call → `await asyncio.wait_for(emit_system_suspend(...), timeout=3.0)`. After resume returns → calculate `duration_seconds` from last suspend event in DB → `await emit_system_resume(trigger=last_trigger, duration_human=...)` |
| `core/lifespan.py` | In `_startup()` (post DB-setup, behind `IS_PRIMARY_WORKER` guard): read latest `shutdown` row from `system_lifecycle_events` → compute `downtime_seconds` → INSERT `startup` row → `await emit_system_startup(downtime_human=...)`. In `_shutdown()` as the very first action (before BaluPi/benchmarks/services-stop): INSERT `shutdown` row, then `await asyncio.wait_for(emit_system_shutdown(...), timeout=3.0)` with fallback |

### Event templates (German, consistent with existing)

```
SYSTEM_SUSPEND:  "NAS wird suspended"
                 "NAS geht in Suspend-Modus ({trigger}). Verbindung wird kurz unterbrochen."

SYSTEM_RESUME:   "NAS wieder online"
                 "NAS aufgewacht nach {duration_human} Suspend ({trigger})."

SYSTEM_SHUTDOWN: "NAS wird heruntergefahren"
                 "NAS fährt herunter ({trigger})."

SYSTEM_STARTUP:  "NAS hochgefahren"
                 "NAS ist wieder einsatzbereit. Letzter Shutdown vor {downtime_human}."
```

`{trigger}` is mapped from `SleepTrigger` enum values to German plain text (`manual` → "manuell", `schedule` → "geplant", `auto_idle` → "Auto-Idle", `auto_escalation` → "Auto-Eskalation").

`{duration_human}` / `{downtime_human}` formatted via small helper:
- `12` seconds → `"12s"`
- `4*3600 + 32*60` → `"4h 32min"`
- `3*86400 + 2*3600` → `"3 Tage 2h"`
- `None` (cold-boot without prior shutdown row) → `"unbekannt"`

## Data Flow

### Suspend → Resume (within same Python process)

```
sleep.py: enter_true_suspend(reason, trigger, wake_at)
  │
  ├─ enter_soft_sleep(...)              [existing, unchanged]
  ├─ INSERT system_lifecycle_events    (event_type=suspend, trigger, ts=now)
  ├─ asyncio.wait_for(
  │     emit_system_suspend(trigger=trigger.value),
  │     timeout=3.0)                   ← Push goes out before system is gone
  │   except TimeoutError: log & continue
  │
  ├─ self._current_state = TRUE_SUSPEND
  ├─ await self._backend.suspend_system(wake_at=wake_at)
  │   ─────────────── KERNEL SUSPEND ───────────────
  │   ←──────── Process resumes here after wake ────────
  │
  ├─ ts_resume = now()
  ├─ duration = ts_resume − ts_of_last_suspend_event_in_db
  ├─ INSERT system_lifecycle_events    (event_type=resume, trigger=last_trigger,
  │                                     details={duration_seconds, wake_method})
  ├─ await emit_system_resume(
  │     trigger=last_trigger,
  │     duration_human=fmt(duration))   ← System is online, no timeout needed
  │
  └─ _exit_soft_sleep("resume_from_suspend")
```

### Shutdown → Startup (process boundary)

```
lifespan.py: _shutdown()                [PRIMARY_WORKER only]
  │
  ├─ INSERT system_lifecycle_events    (event_type=shutdown, trigger="api"|"signal", ts=now)
  ├─ asyncio.wait_for(
  │     emit_system_shutdown(trigger=...),
  │     timeout=3.0)                   ← Push goes out before app dies
  │   except TimeoutError: log & continue
  │
  ├─ BaluPi-Notify, Benchmarks, Services-Stop, …  [existing order]
  └─ Process exit

           ─────────── HOST RESTART / BOOT ───────────

lifespan.py: _startup()                 [PRIMARY_WORKER only]
  │
  ├─ DB-Setup, Migrations, …            [existing]
  ├─ last_shutdown = SELECT MAX(ts) FROM system_lifecycle_events
  │                  WHERE event_type='shutdown'
  ├─ downtime = now − last_shutdown    (None if first start ever)
  ├─ INSERT system_lifecycle_events    (event_type=startup, ts=now,
  │                                     details={downtime_seconds})
  └─ await emit_system_startup(
        downtime_human=fmt(downtime) or "unbekannt")
```

## Edge Cases

| Case | Handling |
|---|---|
| Suspend fails (`suspend_system` returns False) | No resume event written. Suspend push already out — out of scope to recall |
| FCM not configured | `FirebaseService.is_available()` → False → `_send_push_sync` no-op. In-app notification still created (existing behavior) |
| Cold boot without prior `shutdown` row (crash, very first start) | `last_shutdown = None` → `downtime_human = "unbekannt"` |
| Multiple Uvicorn workers | All 4 hooks behind `IS_PRIMARY_WORKER` (lifespan) / Sleep manager runs as primary-only singleton. No duplicate emits |
| Fast reboot loop / crash loop | 60s cooldown for suspend/resume; **no cooldown** for shutdown/startup (legitimate reboots must always notify). Crash-loop pushes are desired signal |
| Quiet hours active | Existing `_send_push_sync` logic applies (priority=1 < 3 → muted). In-app notification still created |
| User disabled `lifecycle` category | Gate in `emit_sync` filters → no DB insert, no push (existing behavior) |
| `.metadata.json` / audit-log | No file write, only DB → no security-constraint conflict |

## Schema

```python
# backend/alembic/versions/<rev>_add_system_lifecycle_events.py
def upgrade():
    op.create_table(
        "system_lifecycle_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now(), index=True),
        sa.Column("trigger", sa.String(32), nullable=True),
        sa.Column("details_json", sa.Text, nullable=True),
    )
    op.create_index("ix_lifecycle_type_ts", "system_lifecycle_events",
                    ["event_type", "timestamp"])

def downgrade():
    op.drop_index("ix_lifecycle_type_ts", "system_lifecycle_events")
    op.drop_table("system_lifecycle_events")
```

- Additive only → safe for live PostgreSQL 17.7 production
- Composite index `(event_type, timestamp)` keeps `last_shutdown` lookup O(log n)
- No data migration script needed (table starts empty)

## Tests

`backend/tests/test_lifecycle_notifications.py`:

| Test | Verifies |
|---|---|
| `test_suspend_event_emits_before_kernel_suspend` | Order: `emit_system_suspend` called BEFORE `_backend.suspend_system()` (mock-based) |
| `test_suspend_emit_respects_3s_timeout` | FCM mock with delay > 3s → suspend continues, no hang |
| `test_resume_event_includes_duration_and_trigger` | After mock-suspend: resume push has `duration_human` + `trigger`; DB has `resume` row with `duration_seconds` |
| `test_shutdown_event_persisted_before_emit` | `_shutdown()` writes `system_lifecycle_events` row BEFORE FCM call (so next startup can read `last_shutdown` even if FCM hangs) |
| `test_startup_calculates_downtime_from_last_shutdown` | DB seeded with fake `shutdown` row 5min ago → startup push contains `5min` downtime |
| `test_startup_handles_missing_last_shutdown` | Empty DB → `downtime_human = "unbekannt"`, no crash |
| `test_lifecycle_category_default_prefs` | New admin: `lifecycle.push = True`. New non-admin: `lifecycle.push = False` |
| `test_quiet_hours_suppresses_push_but_keeps_inapp` | Quiet hours active: no FCM call, but notification row exists |
| `test_secondary_worker_does_not_emit` | `IS_PRIMARY_WORKER = False` → no lifecycle events created |
| `test_cooldown_60s_for_suspend_resume` | Two suspends within 60s → second suppressed |
| `test_no_cooldown_for_shutdown_startup` | Two shutdowns in quick succession → both emit |
| `test_format_duration_human` | Helper: `12` → `"12s"`, `4*3600+32*60` → `"4h 32min"`, `3*86400+2*3600` → `"3 Tage 2h"` |

## Manual Smoketest (post-deploy)

1. `python start_dev.py` → first start → Push *"NAS hochgefahren … unbekannt"*
2. `POST /api/sleep/suspend` (dev backend mocks suspend) → Push *"NAS wird suspended (manuell)"*
3. Sleep ends → Push *"NAS wieder online nach 0s Suspend (manuell)"*
4. `POST /api/system/shutdown` → Push *"NAS wird heruntergefahren (api)"*
5. Restart → Push *"NAS hochgefahren. Letzter Shutdown vor Xs"*
6. Verify mobile push reception, in-app notification list, `system_lifecycle_events` table

## Build Order

1. Migration + Model (DB foundation)
2. `EventType` + `EVENT_CONFIGS` + convenience helpers + cooldowns + category prefs
3. `format_duration_human` helper
4. Hook into `lifespan._startup()` and `lifespan._shutdown()`
5. Hook into `sleep.py:enter_true_suspend()` (suspend + resume)
6. Tests
7. Smoketest
