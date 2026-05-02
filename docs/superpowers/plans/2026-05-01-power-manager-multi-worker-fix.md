# Power Manager Multi-Worker State Sync

**Date:** 2026-05-01 (refined 2026-05-02)
**Status:** Implementation complete — pending manual 2-worker verification
**Branch:** `fix/power-manager-multi-worker` (created from `origin/main` 2026-05-02)

## Problem

`PowerManagerService` (`backend/app/services/power/manager.py:64`) is a per-process Python singleton. Production runs 4 Uvicorn workers. The lifespan correctly gates background tasks with `IS_PRIMARY_WORKER` (`backend/app/core/lifespan.py:412-421`), so only the primary worker:

- initializes `_backend` (the actual CPU control)
- runs `_monitor_loop` (auto-scaling, demand expiration)

But the **API routes don't honor this gate**. `backend/app/api/routes/power.py` calls `get_power_manager()` on whichever worker received the request and mutates that worker's in-memory state.

Each worker has its own copy of: `_demands`, `_current_profile`, `_history`, `_auto_scaling_config`, `_dynamic_mode_enabled`, `_manual_override_until`, `_cooldown_until`.

### Concrete symptoms

1. **`POST /api/power/profile`** (`power.py:131`) — On secondary workers `self._backend is None`, so `_apply_profile_internal` returns `"Power backend not initialized"` and the route raises 500. Random failures depending on round-robin routing.

2. **Duplicate profile-change log entries** — Observed in System Control: three entries at the same second, "manual (manual)" Surge 4.6 GHz, Surge 4.2 GHz, Low 1.1 GHz. `_apply_profile_internal` has an early-return `if profile == self._current_profile` (`manager.py:478`). Two consecutive Surge log entries can only occur if the second click was processed by a different worker whose `_current_profile` was still IDLE — direct evidence of state divergence.

3. **`PUT /api/power/auto-scaling`** (`power.py:331`) — `set_auto_scaling_config` (`manager.py:876`) writes to the worker that handled the request + saves to DB. The primary worker's `_check_auto_scaling` reads `self._auto_scaling_config` from memory and never re-reads from DB. UI threshold changes don't take effect until restart.

4. **`@requires_power` decorator** — Demands registered per-worker. The primary worker's `_recalculate_profile` only sees demands in its own process. Demands registered by request handlers on secondary workers are invisible to the actual scaling logic.

5. **Dynamic mode toggle** (`enable_dynamic_mode`, `manager.py:109`) — Fails with "Power backend not initialized" on 3 of 4 workers. Even if it lands on primary, `GET /api/power/status` returns `dynamic_mode_enabled=False` from the other workers, so the UI flickers depending on which worker answers.

6. Fan control already has a `monitoring=False` read-only mode for secondary workers (`lifespan.py:456-461`); the power manager has no equivalent.

## Goal

Make secondary workers safe to handle `/api/power/*` requests by moving live mutable state to the DB. Hardware operations are still executed only by the primary worker, dispatched via a DB-backed command queue.

## Non-goals

- No change to the primary-worker election / file-lock pattern.
- No change to the monitoring SHM pattern.
- No reduction of worker count.
- No change to the `power_profile_config` (saved profile presets) — those are config, not runtime state.

---

## Implementation Steps

### Step 1 — New table: `power_runtime_state`

Single-row state table (id=1) that holds the live mutable state.

`backend/app/models/power.py`:

```python
class PowerRuntimeState(Base):
    __tablename__ = "power_runtime_state"
    id = Column(Integer, primary_key=True, default=1)
    current_profile = Column(String, default="idle")
    manual_override_until = Column(DateTime(timezone=True), nullable=True)
    cooldown_until = Column(DateTime(timezone=True), nullable=True)
    dynamic_mode_enabled = Column(Boolean, default=False)
    last_profile_change = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    updated_by_pid = Column(Integer, nullable=True)  # for debugging
```

Alembic migration: create table, seed row id=1.

- [ ] Write failing test: `tests/services/test_power_manager.py::test_runtime_state_table_seeded`
- [ ] Add model + migration
- [ ] Run `alembic upgrade head` against test DB

### Step 2 — `power_demands` table

Replace the per-worker `_demands` dict with a DB table.

```python
class PowerDemand(Base):
    __tablename__ = "power_demands"
    source = Column(String, primary_key=True)
    level = Column(String, nullable=False)
    power_property = Column(String, nullable=False)
    description = Column(String, nullable=True)
    registered_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
```

- Routes call upsert (insert-on-conflict-update by source).
- Primary's `_check_expired_demands` deletes expired rows.
- `_get_highest_demand_profile` reads from DB (cached on primary, fresh-read on secondary if needed).

- [ ] Write failing tests covering upsert, expiry cleanup, highest-demand selection
- [ ] Migration

### Step 3 — Refactor `manager.py` mutation methods

Every method currently writing to in-memory state writes to DB. In-memory copies become **caches on the primary worker only**.

Touch sites:

- `register_demand` / `unregister_demand` → upsert/delete `power_demands` row
- `apply_profile` → enqueue command (Step 4) instead of calling `_apply_profile_internal` directly
- `set_auto_scaling_config` → already saves to DB; remove the in-memory cache, primary reads fresh each tick
- `enable_dynamic_mode` / `disable_dynamic_mode` → enqueue command + write `power_runtime_state.dynamic_mode_enabled`
- `_apply_profile_internal` (the actual hardware call) **only runs on primary** — guard with `IS_PRIMARY_WORKER` and assert `self._backend is not None`

- [ ] Add follower mode flag (`primary: bool` arg to `start()`)
- [ ] Tests for each mutation: verify DB row written, verify primary picks up

### Step 4 — Command queue for hardware ops

Routes can't do hardware I/O on secondary workers (no backend). Add a `power_commands` table.

```python
class PowerCommand(Base):
    __tablename__ = "power_commands"
    id = Column(Integer, primary_key=True, autoincrement=True)
    command = Column(String)  # "apply_profile" | "enable_dynamic_mode" | "switch_backend"
    payload_json = Column(Text)
    requested_by = Column(String)
    requested_at = Column(DateTime(timezone=True))
    status = Column(String, default="pending")  # pending | applied | failed
    error_message = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
```

Route handler flow:

1. Insert command row, commit
2. Poll the row (with timeout, ~3s) waiting for `status != "pending"`
3. Return success/error to client

Primary worker's lifespan starts a fast command-poll loop (separate from the existing 5s loop) that polls `power_commands WHERE status='pending'` every ~500 ms, executes via `_backend`, updates row status.

- [ ] New file `backend/app/services/power/command_queue.py`
- [ ] Tests: insertion, primary picks up, applies, marks complete; failure path; timeout path
- [ ] Tests: `switch_backend` (admin-only, longer timeout ~10 s)

### Step 5 — Read endpoints

`GET /api/power/status` reads from:

- `power_runtime_state` (current profile, dynamic mode, manual override, cooldown)
- `power_demands` (active demand list)
- SHM file `/tmp/baluhost_shm/power_status.json` written by primary every monitor tick (frequency, backend type, permission status)

Frequency is best-effort; fall back to `None` on secondary if SHM stale (>5 s old). Reuse `backend/app/services/monitoring/shm.py`.

- [ ] Add SHM writer to primary's `_monitor_loop`
- [ ] Refactor `get_power_status` to read from DB + SHM
- [ ] Tests: secondary worker returns same status as primary; stale SHM degrades gracefully

### Step 6 — Lifespan changes

In `lifespan.py:412-421`:

- Primary: same as today, plus start the fast command-poll loop and SHM writer
- Secondary: call `start_power_manager(primary=False)` — loads runtime state from DB, skips backend init / monitor loop, registers in service status as "follower"

```python
await power_manager.start_power_manager(primary=IS_PRIMARY_WORKER)
```

- [ ] Tests covering both branches

### Step 7 — Tests

- `tests/services/test_power_manager.py`: multi-process simulation — two `PowerManagerService` instances (one primary, one follower), verify follower's mutations propagate to primary via DB
- `tests/api/test_power_routes.py`: mutation endpoint succeeds when called against a follower-mode manager (currently would 500)
- `tests/services/test_power_command_queue.py` (new): command insertion, primary picks up, applies, marks complete, failure path, timeout path

### Step 8 — Cleanup

- Remove `_demands`, `_current_profile`, `_auto_scaling_config` instance state from secondary workers' code path (or leave as cache on primary only)
- Audit `service_registry.py` for any power-status reads that should switch to DB-backed reader
- `_history` already reads from DB (`PowerProfileLog`), no change needed

---

## Risks / Open Questions

1. **Latency**: Command queue polling at 500 ms adds up to ~500 ms latency on profile changes. Acceptable for UI; spot-check `@requires_power` callers (services like backup/sync that register demand at request start) — if any need faster turnaround, bump poll rate or use a notify mechanism (e.g. `LISTEN/NOTIFY` on Postgres).
2. **Race**: Two workers inserting commands simultaneously — DB autoincrement + primary processes in order, fine.
3. **History**: `get_history` already reads from DB (`PowerProfileLog`), no change needed.
4. **Backend switch**: `switch_backend` is admin-only and rare; route via command queue with longer timeout (~10 s).
5. **Migration**: Existing `power_profile_config` table stays as-is (config, not runtime state).
6. **Deadlock**: Routes that hold a DB session while polling for command completion must release the session during polling waits to avoid pool exhaustion. Consider opening a fresh session per poll iteration.

## Files Touched

- `backend/app/models/power.py` — 2 new models (`PowerRuntimeState`, `PowerDemand`, `PowerCommand`)
- `backend/alembic/versions/<new>.py` — migration with seed row for runtime state
- `backend/app/services/power/manager.py` — mutation methods → DB; add follower mode; SHM writer in monitor loop
- `backend/app/services/power/command_queue.py` — **new file**, command poll loop + dispatch
- `backend/app/services/power/config_store.py` — add demand/runtime read/write helpers
- `backend/app/api/routes/power.py` — route handlers go via command queue for mutations
- `backend/app/core/lifespan.py` — pass `primary=` flag, start command poll loop + SHM writer on primary
- `backend/tests/services/test_power_manager.py` — multi-process tests
- `backend/tests/api/test_power_routes.py` — secondary-worker route tests
- `backend/tests/services/test_power_command_queue.py` — **new**, command queue lifecycle

## Estimated Scope

~600–800 lines changed, ~300 lines of tests. Ship behind no feature flag — it's a correctness fix.

## Verification

- [ ] All existing power tests still pass
- [ ] New multi-process tests pass
- [ ] Manual test: spin up local 2-worker uvicorn (`gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app`), repeatedly click Surge in UI, verify exactly one log entry per click and no 500s
- [ ] Manual test: change auto-scaling threshold in UI, verify primary picks up new threshold within 5 s without restart
- [ ] Manual test: enable dynamic mode, refresh status repeatedly, verify all responses consistent

---

# Konkretisierung 2026-05-02

## Codebase-Verifikation (durchgeführt vor Implementierung)

| Annahme im Plan | Verifiziert | Anmerkung |
|---|---|---|
| `lifespan.py:412-421` gated Background-Tasks | ✓ | unverändert; aktueller Aufruf `await power_manager.start_power_manager()` (kein `primary=` Argument) |
| `manager.py:64` Singleton | ✓ | `__new__` mit Class-Lock, in-memory state in Zeilen 88-105 |
| `_apply_profile_internal` early-return bei gleichem Profil | ✓ Zeile 478 (`if profile == self._current_profile`) |
| Routes rufen `get_power_manager()` ohne Worker-Check | ✓ alle 14 Routes in `power.py` |
| Fan-Control hat `monitoring=False` Pattern | ✓ `lifespan.py:456-458` ruft `start_fan_control(monitoring=False)` für secondary |
| Sleep-Manager hat `monitoring=False` Pattern | ✓ `lifespan.py:462-464` ergänzt im Sleep-PR (analog Vorgehen) |
| `monitoring/shm.py` für SHM-IPC vorhanden | ✓ unterstützt Linux (`/dev/shm/baluhost`) und Windows (`%TEMP%/baluhost-shm`) |
| `config_store.py` für DB-Persistierung etabliert | ✓ enthält schon `load_/save_auto_scaling_config`, `_dynamic_mode_config`, `persist_profile_change`, `persist_demand_log` — neue Helpers folgen demselben Stil |
| Aktueller Alembic HEAD | ✓ `f4b1c0e7d2a3` (extend_metrictype_enum_power_uptime, 2026-05-01) — neue Revision `down_revision='f4b1c0e7d2a3'` |
| `power.set_auto_scaling_config` ruft schon DB | ✓ `manager.py:876-880` — Symptom #3 ist nur, dass Primary den Cache nie reload't; Fix = Primary liest pro Tick frisch |

## Reuse-Inventar (vor Neu-Implementierung prüfen)

- `app.services.monitoring.shm.write_shm/read_shm` → SHM-Datei `power_status.json` per Tick schreiben. Kein neuer Pfad-Code nötig.
- `app.services.power.config_store` → neue Helpers dort einhängen, nicht neue Datei.
- `app.core.lifespan.IS_PRIMARY_WORKER` → bereits exportiert; per `from app.core.lifespan import IS_PRIMARY_WORKER` nur, wenn der Manager beim Start gefragt wird (sicherer: `primary=` als Argument durchreichen wie hier).
- `PowerProfileLog` (history, models/power.py:12) → unverändert; weiter als Quelle für `get_history`.
- `PowerDemandLog` → bleibt als **Audit-Log** der Demand-Aktionen (`registered/unregistered/expired`); die neue `power_demands`-Tabelle hält den **aktuellen** Zustand.

## Architektur-Entscheidungen (gegen Risk #1+#6 aus Plan)

1. **Polling vs. LISTEN/NOTIFY**: Bleibt Polling à 500 ms. SQLite (dev) hat kein `LISTEN/NOTIFY`, und der Plan muss in Dev ohne Zusatzaufwand laufen. Falls in Postgres-Produktion >100 ms Latenz spürbar wird, später als Optimierung.
2. **DB-Session-Isolation**: Routes, die auf Command-Completion warten, öffnen pro Poll-Iteration eine *neue* `SessionLocal()`-Session. Niemals die FastAPI-`Depends(get_db)`-Session über den `await asyncio.sleep` halten — Connection-Pool-Exhaustion bei 4 Workern × N Polls.
3. **Primary-Bestimmung**: `power_manager.start_power_manager(primary: bool)` — der Aufrufer in `lifespan.py` reicht `IS_PRIMARY_WORKER` weiter. Manager liest die globale Variable nicht selbst (vermeidet Import-Zyklus).
4. **`@requires_power` Decorator** (`core/power_rating.py`): registriert via `manager.register_demand()` — wird durch Step 5 automatisch DB-backed; keine Änderung am Decorator nötig.

## Tabellenschema (final, mit Indizes)

```python
# backend/app/models/power.py — Anhängen, KEINE bestehenden Klassen ändern

class PowerRuntimeState(Base):
    __tablename__ = "power_runtime_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # immer 1
    current_profile: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    current_property: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    manual_override_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dynamic_mode_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_profile_change: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    backend_kind: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "linux"|"dev"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class PowerDemand(Base):
    __tablename__ = "power_demands"
    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    power_property: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class PowerCommand(Base):
    __tablename__ = "power_commands"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command: Mapped[str] = mapped_column(String(40), nullable=False)
    # "apply_profile" | "enable_dynamic_mode" | "disable_dynamic_mode" | "switch_backend"
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_power_commands_status_requested", "status", "requested_at"),
    )
```

## Manager-Signatur-Diff

```python
# backend/app/services/power/manager.py

class PowerManagerService:
    def __init__(self):
        ...
        self._primary: bool = True  # default; gesetzt in start()

    async def start(self, primary: bool = True) -> None:
        self._primary = primary
        # Common: load runtime state (profile, dynamic-mode flag, override/cooldown) aus DB-Cache
        self._load_runtime_state_from_db()

        if primary:
            self._backend = self._select_backend()
            # Apply initial state (existing logic) — only on primary
            ...
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            self._command_poll_task = asyncio.create_task(_command_queue.run_poll_loop(self))
        else:
            # Follower: kein Backend, kein Monitor, kein Command-Loop
            self._backend = None
            self._is_running = True

    # Mutationen — funktionieren in beiden Modi:
    async def apply_profile(self, profile, reason="manual", duration_seconds=None) -> Tuple[bool, Optional[str]]:
        if self._primary:
            # bisheriger Pfad (direkt _apply_profile_internal)
            ...
        else:
            cmd_id = enqueue_command("apply_profile", {"profile": profile.value,
                                                       "reason": reason,
                                                       "duration_seconds": duration_seconds})
            return await wait_for_completion(cmd_id, timeout_s=3.0)

    async def register_demand(self, source, level, ...):
        # immer DB-write (upsert in power_demands), unabhängig von primary/follower
        ...
        # primary: zusätzlich _recalculate_profile() lokal aufrufen
        # follower: implicit über _check_expired_demands-Tick auf primary
```

## File-Plan (final)

| Datei | Aktion | Größe |
|---|---|---|
| `backend/app/models/power.py` | +3 Klassen | ~70 Zeilen |
| `backend/app/models/__init__.py` | Imports + `__all__` | 4 Zeilen |
| `backend/alembic/versions/2026_05_02_power_multi_worker.py` | NEU, down_revision=`f4b1c0e7d2a3` | ~80 Zeilen |
| `backend/app/services/power/config_store.py` | +5 Helper-Fn | ~120 Zeilen |
| `backend/app/services/power/command_queue.py` | NEU | ~150 Zeilen |
| `backend/app/services/power/manager.py` | start(primary=), Mutation-Routing, SHM-Writer in monitor_loop | ~200 Zeilen Diff |
| `backend/app/api/routes/power.py` | get_power_status (DB+SHM), POST /profile + PUT /dynamic-mode + POST /backend (queue), demands (DB-direkt) | ~150 Zeilen Diff |
| `backend/app/core/lifespan.py` | `primary=IS_PRIMARY_WORKER`, secondary-branch | ~10 Zeilen |
| `backend/tests/services/test_power_command_queue.py` | NEU | ~150 Zeilen |
| `backend/tests/services/test_power_manager.py` | +follower/primary Tests | ~150 Zeilen |
| `backend/tests/api/test_power_routes.py` | +secondary-Worker-Pfad | ~80 Zeilen |

**Total**: ~700 LOC Code, ~380 LOC Tests.

## Reihenfolge der TaskList (siehe TaskList in Session)

Tasks #1–#11 entsprechen Steps 0–10. Step 0 ist diese Konkretisierung (jetzt erledigt). Step 1 startet mit den Modellen.

## Out-of-scope explizit

- Kein neuer Code für `PowerProfileLog` (history) — bleibt 1:1
- Kein Refactor der `presets.py` / `preset_service`
- Kein Refactor von `power_permissions.py`
- Keine Frontend-Änderung — die Routes bleiben API-kompatibel

## Status-Update 2026-05-02 (Implementierung)

Steps 1–9 abgeschlossen. Lokale Tests:

- `tests/services/test_power_manager.py`: 41 Tests (38 bestehend + 3 neu für follower / DB-roundtrip / runtime-state) — alle grün
- `tests/services/test_power_command_queue.py`: 7 neue Tests (enqueue, dispatch happy/sad path, unknown command, caller timeout) — alle grün
- `tests/services/test_power_presets.py` + `tests/api/test_power_routes.py` + `tests/api/test_power_permissions_routes.py`: unverändert grün
- Komplette `tests/services/`: **707/707 grün** (151 s)
- Komplette `tests/api/`: **235/235 grün** (382 s)

Nicht-triviale Anpassung gegenüber dem Original-Plan:

- **`switch_backend` über Command-Queue** liefert nicht über `error_message`-JSON zurück, sondern liest `backend_kind` aus `power_runtime_state` nach erfolgreicher Completion. Hält das Queue-Schema sauber (`error_message` wird nur im Fehlerfall gefüllt).
- **Existierende Power-Tests** brauchten ein autouse-Fixture (`_power_tables_in_global_db`), das die drei neuen Tabellen in der Test-`SessionLocal`-DB anlegt und nach jedem Test säubert. Die existierenden Tests konstruieren `PowerManagerService` direkt und umgehen `conftest.db_session` — der Manager ruft jetzt aber `SessionLocal()` für `upsert_demand`/`update_runtime_state`. Ohne das Fixture würden die Tests an `OperationalError: no such table: power_demands` scheitern.
- **`get_active_demands()` ist jetzt rein DB-backed** (`list_active_demands()`) statt aus `_demands`-Cache zu lesen — bedeutet, dass jeder Worker dieselbe Antwort liefert, unabhängig davon, wer die Anfrage gehandhabt hat.

Offen: Step 10 — manuelle 2-Worker-Verifikation auf Linux-Production. Die drei Manual-Tests aus dem ursprünglichen Verification-Block stehen aus.

## Manueller Verifikationsplan (Step 10)

Auf der Linux-Produktionskiste (oder in einer 2-Worker-Dev-Konfiguration):

```bash
# 1. Migration anwenden
cd backend && alembic upgrade head

# 2. 2-Worker-Uvicorn starten
gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app

# 3. UI öffnen, in System Control Surge 5x klicken (mit Pause dazwischen)
# Erwartung: GENAU 5 Profile-Change-Logs in History — kein Doppel-Eintrag mehr.
#            Kein 500-Fehler ("Power backend not initialized") in den Logs.

# 4. Auto-Scaling-Threshold im UI ändern (z.B. cpu_surge_threshold von 80 → 70)
# Erwartung: Innerhalb 5 s passt der Primary-Worker das Scaling an, ohne Restart.

# 5. Dynamic-Mode toggle 5x in Folge
# Erwartung: GET /api/power/status liefert konsistent dynamic_mode_enabled=true/false,
#            unabhängig davon, welcher Worker antwortet.
```
