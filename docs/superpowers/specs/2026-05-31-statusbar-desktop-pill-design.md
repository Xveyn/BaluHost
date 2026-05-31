# Status Bar — KDE Desktop Pill — Design

**Date:** 2026-05-31
**Status:** Approved
**Author:** Sven (Xveyn) + Claude
**Extends:** `docs/superpowers/specs/2026-05-27-topbar-statusbar-design.md` (the Topbar Status Strip, now merged to `main`)
**Builds on:** the Desktop (KDE/SDDM) toggle feature (`backend/app/services/power/desktop.py`, endpoints `/api/system/sleep/desktop/*`, PR #122)

## Problem

Admins can now stop/start the KDE desktop (SDDM) at runtime so the dedicated GPU drops to idle (see the Desktop toggle on the Sleep page). But the current desktop power state is only visible by opening the Sleep page. There is no at-a-glance surface in the topbar telling the admin whether the desktop is currently up (GPU pinned awake) or down (GPU can idle).

## Solution

Add a new **`desktop`** pill to the existing catalog-driven Topbar Status Strip. It reflects the live desktop state from `get_desktop_service().get_status()` and links through to the Sleep page where the toggle lives.

One new capability is introduced: a **per-pill display mode**, admin-configurable in the existing Status Bar config tab, scoped to the desktop pill only:

- **Immer anzeigen** (`always`, default) — pill always shown when enabled, tone reflects state
- **Nur wenn AUS** (`when_off`) — pill shown only while the desktop is stopped (a reminder "KDE is off · GPU idling")
- **Nur wenn AN** (`when_on`) — pill shown only while the desktop is running ("GPU pinned awake")

Everything else reuses the existing generic pill machinery: no new frontend pill component, no new API endpoint, no new router.

## Requirements

- New catalog pill `desktop`, `default_visibility="admin"`, `visibility_locked=False` (admin may expose it to all users, like `power`/`pihole`)
- Admin can pick the display mode for the desktop pill from the Status Bar config tab; modes: `always` | `when_off` | `when_on`; default `always`
- The display-mode control appears **only** for pills that declare themselves mode-configurable (currently just `desktop`) — driven by a catalog flag, not a hardcoded id in the frontend
- Server enforces that a non-default `display_mode` can only be set for a mode-configurable pill (reject otherwise, mirroring the `visibility_locked` validation)
- On hosts with no display manager (`get_status()` returns `unknown` — e.g. Pi, headless), the collector returns `None` → pill silently absent
- Pill is a read-only click-through to `/admin/system-control?tab=sleep` (same target as the existing `sleep` pill)
- Reuses the existing `/api/system/statusbar/{config,state}` endpoints, 10s polling, role filtering, audit logging

## Architecture

### Where it plugs in

```
GET /api/system/statusbar/state   (existing, polled 10s)
  → StatusBarService.collect_state(role)
      → COLLECTORS["desktop"](db, role)          ← NEW collector
          → get_desktop_service().get_status()    (existing desktop service)
      → display-mode filter (when definition.display_mode_configurable)  ← NEW
  → PillState in payload → generic <PillRenderer> → <Pill>   (existing, unchanged)
```

### Backend

**1. Catalog** (`backend/app/services/status_bar/catalog.py`)

Add a `display_mode_configurable: bool = False` field to `PillDefinition` and one new entry:

```python
PillDefinition(
    "desktop", "statusBar.pills.desktop.name",
    default_visibility="admin", visibility_locked=False,
    silent_when_ok=False,            # visibility governed by display_mode, not this flag
    href="/admin/system-control?tab=sleep",
    display_mode_configurable=True,
)
```

All existing entries keep `display_mode_configurable=False` (default).

**2. Collector** (`backend/app/services/status_bar/collectors.py`)

New async, `@_safe()`-wrapped `collect_desktop(db, role)`:

```python
@_safe()
async def collect_desktop(db, role):
    from app.services.power.desktop import get_desktop_service
    status = await get_desktop_service().get_status()
    state = status.state.value          # "running" | "stopped" | "unknown"
    if state == "unknown":
        return None                     # no display manager → silent (Pi/headless)
    running = state == "running"
    return {
        "kind": "state",
        "tone": "neutral" if running else "success",
        "label": "Desktop",
        "value": "An" if running else "Aus · GPU idle",
        "icon": "Monitor",
        "_state": state,                # private hint for the display-mode filter; popped before PillState
    }
```

Registered in the `COLLECTORS` dict.

**3. Display-mode filter** (`backend/app/services/status_bar/service.py`, in `collect_state`)

After `partial = await collector(...)` and the `None` check, before building `PillState`:

```python
if definition.display_mode_configurable:
    state = partial.pop("_state", None)
    mode = getattr(_row, "display_mode", "always")
    if (mode == "when_off" and state != "stopped") or (mode == "when_on" and state != "running"):
        continue
```

`_state` is popped so it never reaches `PillState(**partial)` (which would reject an unknown field). Generic — keyed on the catalog flag, not on the literal `"desktop"`.

**4. Persistence** (`backend/app/models/status_bar.py` + Alembic)

Add to `StatusBarPillConfig`:

```python
display_mode: Mapped[str] = mapped_column(
    String(8), nullable=False, default="always", server_default="always"
)  # "always" | "when_off" | "when_on" — only meaningful for mode-configurable pills
```

Additive migration (safe for live PostgreSQL 17.7): `ADD COLUMN display_mode VARCHAR(8) NOT NULL DEFAULT 'always'`. **The migration must chain onto the real `alembic heads`** (run `alembic heads` first; do not assume the dev-DB head) — a stale `down_revision` has caused a multi-head prod-deploy failure before. `_ensure_rows()` keeps seeding new pills by column default, so the `desktop` row is auto-created with `display_mode="always"`.

**5. Schemas** (`backend/app/schemas/status_bar.py`)

- Add `"desktop"` to the `PILL_IDS` Literal (the existing `test_pill_id_literal_matches_catalog` drift test then passes again).
- New `DisplayMode = Literal["always", "when_off", "when_on"]`.
- `PillConfigItem` gains `display_mode: DisplayMode = "always"`.
- `PillCatalogEntry` gains `display_mode: DisplayMode` and `display_mode_configurable: bool` (so the config GET tells the frontend what to render and the current value).

**6. Service config read/write** (`service.py`)

- `get_config()` includes `display_mode=row.display_mode` and `display_mode_configurable=definition.display_mode_configurable` per entry.
- `update_config()` validates: if `item.display_mode != "always"` for a pill whose definition is **not** `display_mode_configurable`, raise `ValueError` → 400 (mirrors the locked-visibility rejection). Persists `row.display_mode` and records it in the audit diff.

### Frontend

No new pill component — the generic `PillRenderer` already renders any `PillState` via `<Pill>` using `icon`/`tone`/`label`/`value`/`href`.

**7. Icon** (`client/src/components/topbar/iconMap.ts`) — add `Monitor` (lucide-react) to the `ICONS` map.

**8. Config UI** (`client/src/components/status-bar-config/`)

- `api/statusBar.ts` (or wherever the config types live): add `display_mode` + `display_mode_configurable` to the catalog-entry type and `display_mode` to the update payload type.
- `PillRow.tsx`: when `pill.display_mode_configurable`, render a small `<select>` (Immer / Nur wenn AUS / Nur wenn AN) bound to `display_mode`; otherwise render nothing extra (existing rows unchanged).
- `usePillConfig.ts`: carry `display_mode` through read and into the PUT payload.

**9. i18n** (`statusBar` namespace, DE + EN): `pills.desktop.name` ("Desktop (KDE)"), `displayMode.label`, `displayMode.always`, `displayMode.whenOff`, `displayMode.whenOn`.

## Tone / Label semantics

| Desktop state | tone | label | value |
|---|---|---|---|
| running | `neutral` | Desktop | An |
| stopped | `success` | Desktop | Aus · GPU idle |
| unknown | — | — | (collector returns `None`, pill absent) |

Runtime strings are returned server-side as short display strings (consistent with existing collectors). DE chosen to match the Desktop toggle panel (`Läuft`/`Gestoppt`). *(Open nit for spec review: existing pills mix EN/DE runtime values, and `"Aus · GPU idle"` is the longest pill value — shorten to `"Aus"` if it crowds the strip.)*

## Edge Cases

| Case | Handling |
|---|---|
| No display manager (Pi/headless, `unknown`) | Collector returns `None` → pill absent |
| Desktop service raises | `@_safe()` swallows → `None` → pill absent, no 5xx |
| Fresh DB / pill not yet in `status_bar_pill_config` | `_ensure_rows()` inserts `desktop` with `enabled=False`, `display_mode="always"` |
| `display_mode` set on a non-configurable pill via crafted PUT | 400 Bad Request (server validation) |
| Mode `when_off` while desktop running | Pill filtered out of payload; reappears on next poll once stopped (≤10s lag) |
| Non-admin user, pill `visibility="admin"` | Existing role filter drops it before collection |
| Migration re-run | Additive `ADD COLUMN ... DEFAULT 'always'` is idempotent under the existing pattern |

## Security

- No new endpoint or auth surface — reuses `GET /state` (any-auth, role-filtered) and `PUT /config` (admin, rate-limited, audited).
- `display_mode` is non-sensitive (it only changes when a pill is shown). Validation prevents setting it on non-configurable pills.
- Desktop state exposed is coarse (running/stopped) — no paths, IPs, or identifiers. With `visibility="all"`, non-admins would see only "Desktop An/Aus", which is acceptable (admin opts in deliberately).
- The config change is captured by the existing `status_bar.config_changed` audit event; extend its diff to include `display_mode` changes.

## Tests

### Backend (`backend/tests/test_status_bar.py`, extend)

| Test | Verifies |
|---|---|
| `test_pill_id_literal_matches_catalog` (existing) | passes again with `desktop` added to both CATALOG and `PILL_IDS` |
| `test_desktop_collector_running` | service status `running` → pill `tone=neutral`, `value="An"`, `icon="Monitor"` |
| `test_desktop_collector_stopped` | status `stopped` → `tone=success`, `value` for GPU-idle |
| `test_desktop_collector_unknown_silent` | status `unknown` → collector returns `None` |
| `test_desktop_collector_swallows_error` | desktop service raises → `None`, no exception escapes |
| `test_display_mode_always_shows_both_states` | mode `always` → pill present for running and stopped |
| `test_display_mode_when_off_hides_running` | mode `when_off` + running → pill absent; stopped → present |
| `test_display_mode_when_on_hides_stopped` | mode `when_on` + stopped → pill absent; running → present |
| `test_display_mode_rejected_for_non_configurable_pill` | PUT `display_mode="when_off"` on `power` → 400 |
| `test_display_mode_persisted_and_in_config` | PUT mode → GET config returns it; `display_mode_configurable=True` for desktop, `False` for others |
| `test_desktop_pill_visibility_unlocked` | admin may set `desktop` visibility to `all` (not locked) |

### Frontend (`status-bar-config/__tests__/`)

| Test | Verifies |
|---|---|
| `PillRow renders display-mode select only for configurable pill` | `display_mode_configurable=true` → select present; `false` → absent |
| `PillRow display-mode change is sent in PUT` | change select → update payload carries new `display_mode` |
| `Desktop pill renders via generic renderer` | `PillState{id:'desktop', icon:'Monitor', tone, value}` → `<Pill>` with Monitor icon + tone classes |

## Build Order

1. Backend foundation — catalog flag + `desktop` entry; `PILL_IDS`; model column + Alembic migration (chained onto real head); schema fields
2. Collector — `collect_desktop` + COLLECTORS registration
3. Service — display-mode filter in `collect_state`; `display_mode` in `get_config`/`update_config` + validation + audit diff
4. Backend tests
5. Frontend — `iconMap` Monitor; config types; `PillRow` select; `usePillConfig` wiring
6. i18n DE+EN
7. Frontend tests
8. Manual smoketest (admin enables desktop pill, toggles desktop, verifies pill + each display mode; non-admin visibility; Pi/headless absence)

Estimated: ~3–5 hours (mostly the display-mode plumbing; the pill itself is a thin collector).

## Out of Scope

- General per-pill display-mode for all pills (explicitly scoped to `desktop` only)
- Toggling the desktop from the pill (read-only click-through, like all pills)
- A dedicated `DesktopPill` component (generic renderer suffices)
- New endpoint / WebSocket push (existing 10s polling)
- Showing the GPU power level in the pill (out of scope; the pill reflects desktop state, not GPU sysfs)

## References

- `docs/superpowers/specs/2026-05-27-topbar-statusbar-design.md` — base status-strip design
- `docs/superpowers/plans/2026-05-30-desktop-toggle.md` — the desktop toggle this pill reflects
- `backend/app/services/status_bar/catalog.py` — `PillDefinition` + `CATALOG` (add flag + entry)
- `backend/app/services/status_bar/collectors.py` — `@_safe()` collector pattern + `COLLECTORS` map
- `backend/app/services/status_bar/service.py:128-140` — `collect_state` loop (display-mode hook)
- `backend/app/models/status_bar.py` — `StatusBarPillConfig` (add `display_mode`)
- `backend/app/schemas/status_bar.py` — `PILL_IDS`, `PillConfigItem`, `PillCatalogEntry`
- `backend/app/services/power/desktop.py` — `get_desktop_service().get_status()` → `DesktopStatus`
- `client/src/components/topbar/iconMap.ts` — icon registry (add `Monitor`)
- `client/src/components/status-bar-config/PillRow.tsx`, `usePillConfig.ts` — config UI
- `.claude/rules/security-agent.md` — auth/audit patterns
