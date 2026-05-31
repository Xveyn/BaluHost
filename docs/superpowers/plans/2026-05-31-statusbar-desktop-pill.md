# Status Bar — KDE Desktop Pill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `desktop` pill to the topbar status strip that reflects the live KDE/SDDM desktop state, with an admin-configurable per-pill display mode (always / only-when-off / only-when-on) scoped to this pill.

**Architecture:** Reuse the existing catalog-driven status strip. Backend: one new `PillDefinition` + a catalog flag `display_mode_configurable`, an async `collect_desktop` collector wrapping the existing `get_desktop_service().get_status()`, a new `display_mode` column on `status_bar_pill_config`, and a display-mode filter in `StatusBarService.collect_state`. Frontend: the generic `PillRenderer` already renders any pill — only an icon-map entry, a config-tab `<select>`, type/hook wiring, and i18n are needed. No new pill component, no new API endpoint.

**Tech Stack:** Python 3.13 / FastAPI / Pydantic v2 / SQLAlchemy 2.0 / Alembic (backend), React 18 + TypeScript + Vitest + @dnd-kit (frontend), pytest.

---

## Context for the implementer (read first)

This is **BaluHost**, a NAS platform. The topbar "Status Strip" is an existing, merged feature. You are adding one pill to it plus a small per-pill setting. Verified facts (2026-05-31, branch `feat/statusbar-desktop-pill`, based on `main`):

- **Run all backend commands from `backend/` with `python -m pytest ...`** (Windows dev box; `python` already resolves the project venv and `import app` resolves this worktree). The plan was authored on Windows; ignore any `.venv/bin/` paths — just use `python`.
- The status strip is **catalog-driven**. Pills are defined in `backend/app/services/status_bar/catalog.py` (`PillDefinition` dataclass + `CATALOG` list). Collectors are async functions in `backend/app/services/status_bar/collectors.py`, registered in the `COLLECTORS` dict at the bottom. The aggregator is `backend/app/services/status_bar/service.py` (`StatusBarService`).
- The **frontend renderer is generic**: `client/src/components/topbar/pillRenderers.tsx` renders any `PillState` via `<Pill>` using `icon` (resolved through `client/src/components/topbar/iconMap.ts`), `tone`, `label`, `value`, `href`. Only `always_awake` has a custom component. **A new pill needs NO new component.**
- The admin config UI is `client/src/components/status-bar-config/` (`StatusBarConfigTab.tsx` → `usePillConfig.ts` → `PillRow.tsx`). It is fully catalog-driven: a new pill appears automatically.
- The desktop feature this pill reflects: `backend/app/services/power/desktop.py` exposes `get_desktop_service().get_status()` returning `DesktopStatus(state: DesktopState, display_manager: str, detail: str|None)` where `DesktopState` is a str-enum with values `"running" | "stopped" | "unknown"`. The method is `async`.
- The pill's click-through `/admin/system-control?tab=sleep` is where the desktop toggle panel lives (same target as the existing `sleep` pill).
- Spec: `docs/superpowers/specs/2026-05-31-statusbar-desktop-pill-design.md`.

**Conventions:** backend async I/O + type hints + Pydantic schemas (never raw dict); collectors must never raise (wrap with `@_safe()`); ORM only; rate-limited/audited endpoints already exist and are reused. Frontend: functional components, Tailwind, `lucide-react` icons (import individual icons), i18n via `useTranslation('statusBar')`, add BOTH `de` + `en` keys. One commit per task.

**Existing tests this change must update (do not leave them red):**
- `backend/tests/services/test_status_bar_service.py::test_pill_config_model_has_expected_columns` — asserts the exact column set; add `display_mode`.
- `backend/tests/services/test_status_bar_service.py::test_catalog_has_eleven_pills_with_unique_ids` — asserts 11; becomes 12.

---

## File Structure

**Modify (backend):**
- `backend/app/services/status_bar/catalog.py` — add `display_mode_configurable` field + `desktop` entry
- `backend/app/schemas/status_bar.py` — `"desktop"` in `PILL_IDS`; `DisplayMode` literal; `display_mode` on `PillConfigItem`; `display_mode` + `display_mode_configurable` on `PillCatalogEntry`
- `backend/app/models/status_bar.py` — `display_mode` column on `StatusBarPillConfig`
- `backend/app/services/status_bar/collectors.py` — `collect_desktop` + `COLLECTORS["desktop"]`
- `backend/app/services/status_bar/service.py` — display-mode filter in `collect_state`; `display_mode`/`display_mode_configurable` in `get_config`; validate+persist `display_mode` in `update_config`
- `backend/tests/services/test_status_bar_service.py` — update the two tests above; add config tests
- `backend/tests/services/test_status_bar_collectors.py` — add `collect_desktop` tests

**Create (backend):**
- `backend/alembic/versions/<rev>_status_bar_display_mode.py` — additive migration

**Modify (frontend):**
- `client/src/api/statusBar.ts` — types
- `client/src/components/status-bar-config/usePillConfig.ts` — `setDisplayMode` + payload
- `client/src/components/status-bar-config/PillRow.tsx` — display-mode `<select>`
- `client/src/components/status-bar-config/StatusBarConfigTab.tsx` — pass `onSetDisplayMode`
- `client/src/components/topbar/iconMap.ts` — add `Monitor`
- `client/src/i18n/locales/de/statusBar.json` + `client/src/i18n/locales/en/statusBar.json` — `pills.desktop.name` + `displayMode.*`
- `client/src/__tests__/components/status-bar-config/PillRow.test.tsx` — display-mode select tests
- `client/src/__tests__/components/status-bar-config/usePillConfig.test.ts` — payload test

---

## Task 1: Catalog flag + `desktop` entry + PILL_IDS literal

**Files:**
- Modify: `backend/app/services/status_bar/catalog.py`
- Modify: `backend/app/schemas/status_bar.py`
- Test: `backend/tests/services/test_status_bar_service.py`

- [ ] **Step 1: Update/extend tests**

In `backend/tests/services/test_status_bar_service.py`, change `test_catalog_has_eleven_pills_with_unique_ids` to expect 12 and append two new tests:

```python
def test_catalog_has_twelve_pills_with_unique_ids():
    from app.services.status_bar.catalog import CATALOG
    ids = [p.id for p in CATALOG]
    assert len(ids) == 12
    assert len(set(ids)) == 12


def test_desktop_pill_in_catalog_unlocked_admin_default():
    from app.services.status_bar.catalog import CATALOG_BY_ID
    d = CATALOG_BY_ID["desktop"]
    assert d.default_visibility == "admin"
    assert d.visibility_locked is False
    assert d.display_mode_configurable is True
    assert d.href == "/admin/system-control?tab=sleep"


def test_only_desktop_is_display_mode_configurable():
    from app.services.status_bar.catalog import CATALOG
    configurable = {p.id for p in CATALOG if p.display_mode_configurable}
    assert configurable == {"desktop"}
```

Delete the old `test_catalog_has_eleven_pills_with_unique_ids` (replaced above).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "catalog or desktop_pill or display_mode_configurable" -v`
Expected: FAIL (`display_mode_configurable` attribute / `desktop` key missing; count is 11).

- [ ] **Step 3: Implement catalog change**

In `backend/app/services/status_bar/catalog.py`, add the field to the dataclass (after `href`) and the entry (append to `CATALOG`):

```python
@dataclass(frozen=True)
class PillDefinition:
    id: str
    name_key: str                 # i18n key, e.g. "statusBar.pills.power.name"
    default_visibility: str       # "admin" | "all"
    visibility_locked: bool
    silent_when_ok: bool
    href: str
    display_mode_configurable: bool = False  # only True for pills with an admin-chosen display mode
```

Append to `CATALOG` (after the `backup` entry):

```python
    PillDefinition("desktop", "statusBar.pills.desktop.name", "admin", False, False,
                   "/admin/system-control?tab=sleep", display_mode_configurable=True),
```

- [ ] **Step 4: Add `"desktop"` to the PILL_IDS literal**

In `backend/app/schemas/status_bar.py`, extend `PILL_IDS`:

```python
PILL_IDS = Literal[
    "power", "pihole", "uploads", "sync", "raid", "sleep", "vpn", "temp",
    "always_awake", "scheduler", "backup", "desktop",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "catalog or desktop_pill or display_mode_configurable or pill_id_literal" -v`
Expected: PASS (incl. the existing `test_pill_id_literal_matches_catalog` drift test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/status_bar/catalog.py backend/app/schemas/status_bar.py backend/tests/services/test_status_bar_service.py
git commit -m "feat(statusbar): add desktop pill to catalog + PILL_IDS"
```

---

## Task 2: `display_mode` column + migration

**Files:**
- Modify: `backend/app/models/status_bar.py`
- Create: `backend/alembic/versions/<rev>_status_bar_display_mode.py`
- Test: `backend/tests/services/test_status_bar_service.py`

**Design notes:** Tests build tables from `Base.metadata` (the `db_session` fixture), so the model column is what tests need; the migration is for prod PostgreSQL. The current single Alembic head is **`9c4dcf5d487b`** (verified via `alembic heads`). The new migration's `down_revision` MUST be `9c4dcf5d487b` so it chains onto the real head (a stale `down_revision` previously caused a multi-head prod-deploy failure). After creating it, `alembic heads` must still show exactly one head.

- [ ] **Step 1: Update the column-set test**

In `backend/tests/services/test_status_bar_service.py`, update `test_pill_config_model_has_expected_columns`:

```python
def test_pill_config_model_has_expected_columns():
    cols = set(StatusBarPillConfig.__table__.columns.keys())
    assert cols == {"id", "pill_id", "enabled", "visibility", "sort_order", "display_mode", "updated_at"}
```

Add:

```python
def test_pill_config_display_mode_defaults_to_always():
    assert StatusBarPillConfig.__table__.columns["display_mode"].default.arg == "always"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "expected_columns or display_mode_defaults" -v`
Expected: FAIL (no `display_mode` column).

- [ ] **Step 3: Add the model column**

In `backend/app/models/status_bar.py`, add to `StatusBarPillConfig` (after `sort_order`, before `updated_at`):

```python
    display_mode: Mapped[str] = mapped_column(
        String(8), nullable=False, default="always", server_default="always"
    )  # "always" | "when_off" | "when_on" — only meaningful for display_mode_configurable pills
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "expected_columns or display_mode_defaults" -v`
Expected: PASS.

- [ ] **Step 5: Create the migration**

Create `backend/alembic/versions/a1b2c3d4e5f6_status_bar_display_mode.py`:

```python
"""add display_mode to status_bar_pill_config

Revision ID: a1b2c3d4e5f6
Revises: 9c4dcf5d487b
Create Date: 2026-05-31

Additive column for the per-pill display mode (desktop pill). Safe for live
PostgreSQL: NOT NULL with a server default so existing rows backfill to 'always'.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "9c4dcf5d487b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "status_bar_pill_config",
        sa.Column("display_mode", sa.String(length=8), nullable=False, server_default="always"),
    )


def downgrade() -> None:
    op.drop_column("status_bar_pill_config", "display_mode")
```

- [ ] **Step 6: Verify single head + migration applies**

Run from `backend/`:
```bash
python -m alembic heads
python -m alembic upgrade head
```
Expected: `alembic heads` prints exactly one head (`a1b2c3d4e5f6 (head)`); `upgrade head` succeeds with no error. (If `heads` shows two lines, the `down_revision` is wrong — fix it to the previous single head.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/status_bar.py backend/alembic/versions/a1b2c3d4e5f6_status_bar_display_mode.py backend/tests/services/test_status_bar_service.py
git commit -m "feat(statusbar): add display_mode column + migration"
```

---

## Task 3: Schemas — DisplayMode, config item + catalog entry fields

**Files:**
- Modify: `backend/app/schemas/status_bar.py`
- Test: `backend/tests/services/test_status_bar_service.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/services/test_status_bar_service.py`:

```python
def test_pill_config_item_accepts_display_mode():
    from app.schemas.status_bar import PillConfigItem
    item = PillConfigItem(pill_id="desktop", enabled=True, visibility="admin",
                          sort_order=0, display_mode="when_off")
    assert item.display_mode == "when_off"


def test_pill_config_item_display_mode_defaults_always():
    from app.schemas.status_bar import PillConfigItem
    item = PillConfigItem(pill_id="power", enabled=True, visibility="admin", sort_order=0)
    assert item.display_mode == "always"


def test_pill_config_item_rejects_bad_display_mode():
    import pytest
    from pydantic import ValidationError
    from app.schemas.status_bar import PillConfigItem
    with pytest.raises(ValidationError):
        PillConfigItem(pill_id="desktop", enabled=True, visibility="admin",
                       sort_order=0, display_mode="sometimes")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "display_mode" -v`
Expected: FAIL (`PillConfigItem` has no `display_mode`).

- [ ] **Step 3: Implement schema changes**

In `backend/app/schemas/status_bar.py`, add the literal and extend the models:

```python
DisplayMode = Literal["always", "when_off", "when_on"]
```

```python
class PillConfigItem(BaseModel):
    pill_id: PILL_IDS
    enabled: bool
    visibility: PillVisibility
    sort_order: int
    display_mode: DisplayMode = "always"
```

```python
class PillCatalogEntry(BaseModel):
    """One catalog pill plus its persisted config — for the admin config GET."""
    pill_id: PILL_IDS
    name_key: str
    enabled: bool
    visibility: PillVisibility
    visibility_locked: bool
    sort_order: int
    href: str
    display_mode: DisplayMode
    display_mode_configurable: bool
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "display_mode" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/status_bar.py backend/tests/services/test_status_bar_service.py
git commit -m "feat(statusbar): add display_mode to status bar schemas"
```

---

## Task 4: `collect_desktop` collector

**Files:**
- Modify: `backend/app/services/status_bar/collectors.py`
- Test: `backend/tests/services/test_status_bar_collectors.py`

**Design notes:** Mirror the existing `@_safe()` collectors. `get_desktop_service().get_status()` is async, returning an object with `.state` (a str-enum). Return `None` when state is `unknown` (no display manager → Pi/headless). Include a private `"_state"` key so the service can apply the display-mode filter; the service pops it before building `PillState`.

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/services/test_status_bar_collectors.py`:

```python
@pytest.mark.asyncio
async def test_collect_desktop_running_neutral():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="running")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result is not None
    assert result["tone"] == "neutral"
    assert result["value"] == "An"
    assert result["icon"] == "Monitor"
    assert result["_state"] == "running"


@pytest.mark.asyncio
async def test_collect_desktop_stopped_success():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="stopped")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["_state"] == "stopped"


@pytest.mark.asyncio
async def test_collect_desktop_unknown_silent():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="unknown")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result is None


@pytest.mark.asyncio
async def test_collect_desktop_swallows_error():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(side_effect=RuntimeError("no sddm"))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result is None


def test_desktop_registered_in_collectors():
    from app.services.status_bar.collectors import COLLECTORS
    assert "desktop" in COLLECTORS
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/services/test_status_bar_collectors.py -k desktop -v`
Expected: FAIL (`collect_desktop` does not exist).

- [ ] **Step 3: Implement the collector**

In `backend/app/services/status_bar/collectors.py`, add before the `# ── registry ──` section:

```python
# ── desktop (KDE/SDDM) ───────────────────────────────────────────────
@_safe()
async def collect_desktop(db: Session, role: str) -> Optional[dict]:
    from app.services.power.desktop import get_desktop_service
    status = await get_desktop_service().get_status()
    state = status.state.value  # "running" | "stopped" | "unknown"
    if state == "unknown":
        return None  # no display manager (Pi/headless) → stay silent
    running = state == "running"
    return {
        "kind": "state",
        "tone": "neutral" if running else "success",
        "label": "Desktop",
        "value": "An" if running else "Aus · GPU idle",
        "icon": "Monitor",
        "_state": state,  # private hint for the service's display-mode filter; popped before PillState
    }
```

Add `"desktop": collect_desktop,` to the `COLLECTORS` dict:

```python
COLLECTORS = {
    "power": collect_power,
    "pihole": collect_pihole,
    "uploads": collect_uploads,
    "sync": collect_sync,
    "raid": collect_raid,
    "sleep": collect_sleep,
    "vpn": collect_vpn,
    "temp": collect_temp,
    "always_awake": collect_always_awake,
    "scheduler": collect_scheduler,
    "backup": collect_backup,
    "desktop": collect_desktop,
}
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/services/test_status_bar_collectors.py -k desktop -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/status_bar/collectors.py backend/tests/services/test_status_bar_collectors.py
git commit -m "feat(statusbar): add collect_desktop collector"
```

---

## Task 5: Service — display-mode filter + config read/write

**Files:**
- Modify: `backend/app/services/status_bar/service.py`
- Test: `backend/tests/services/test_status_bar_service.py`

**Design notes:** Three changes in `StatusBarService`:
1. `get_config()` — include `display_mode` (from row) and `display_mode_configurable` (from definition) in each `PillCatalogEntry`.
2. `update_config()` — validate `display_mode != "always"` is only allowed for `display_mode_configurable` pills (raise `ValueError` → the route maps it to 400); persist `row.display_mode`; record it in the diff.
3. `collect_state()` — for `display_mode_configurable` pills, pop the collector's `_state` hint and drop the pill per `row.display_mode`.

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/services/test_status_bar_service.py` (the file already imports `StatusBarService` and uses the `db_session` fixture):

```python
from app.schemas.status_bar import StatusBarConfigUpdate, PillConfigItem


def _enable_desktop(svc, mode="always"):
    cfg = svc.get_config()
    items = [
        PillConfigItem(pill_id=p.pill_id, enabled=(p.pill_id == "desktop"),
                       visibility=p.visibility, sort_order=p.sort_order,
                       display_mode=(mode if p.pill_id == "desktop" else "always"))
        for p in cfg.pills
    ]
    svc.update_config(StatusBarConfigUpdate(pills=items, show_bottom_upload=True))


def test_get_config_exposes_display_mode_fields(db_session):
    svc = StatusBarService(db_session)
    cfg = svc.get_config()
    desktop = next(p for p in cfg.pills if p.pill_id == "desktop")
    power = next(p for p in cfg.pills if p.pill_id == "power")
    assert desktop.display_mode == "always"
    assert desktop.display_mode_configurable is True
    assert power.display_mode_configurable is False


def test_update_config_rejects_display_mode_on_non_configurable(db_session):
    import pytest
    svc = StatusBarService(db_session)
    cfg = svc.get_config()
    items = [
        PillConfigItem(pill_id=p.pill_id, enabled=p.enabled, visibility=p.visibility,
                       sort_order=p.sort_order,
                       display_mode=("when_off" if p.pill_id == "power" else "always"))
        for p in cfg.pills
    ]
    with pytest.raises(ValueError):
        svc.update_config(StatusBarConfigUpdate(pills=items, show_bottom_upload=True))


def test_update_config_persists_desktop_display_mode(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_off")
    cfg = svc.get_config()
    desktop = next(p for p in cfg.pills if p.pill_id == "desktop")
    assert desktop.display_mode == "when_off"


import pytest


def _patch_desktop_state(state):
    from unittest.mock import AsyncMock, MagicMock, patch
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value=state)))
    return patch("app.services.power.desktop.get_desktop_service", return_value=fake)


@pytest.mark.asyncio
async def test_collect_state_always_shows_running(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="always")
    with _patch_desktop_state("running"):
        resp = await svc.collect_state(role="admin")
    ids = [p.id for p in resp.pills]
    assert "desktop" in ids
    pill = next(p for p in resp.pills if p.id == "desktop")
    assert pill.value == "An"
    # the private hint must not leak into the payload
    assert pill.extra is None or "_state" not in (pill.extra or {})


@pytest.mark.asyncio
async def test_collect_state_when_off_hides_running(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_off")
    with _patch_desktop_state("running"):
        resp = await svc.collect_state(role="admin")
    assert "desktop" not in [p.id for p in resp.pills]


@pytest.mark.asyncio
async def test_collect_state_when_off_shows_stopped(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_off")
    with _patch_desktop_state("stopped"):
        resp = await svc.collect_state(role="admin")
    assert "desktop" in [p.id for p in resp.pills]


@pytest.mark.asyncio
async def test_collect_state_when_on_hides_stopped(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="when_on")
    with _patch_desktop_state("stopped"):
        resp = await svc.collect_state(role="admin")
    assert "desktop" not in [p.id for p in resp.pills]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "display_mode_fields or rejects_display_mode or persists_desktop or collect_state_always or collect_state_when" -v`
Expected: FAIL (`get_config` lacks fields; `update_config` ignores `display_mode`; filter not applied).

- [ ] **Step 3a: `get_config` — expose fields**

In `backend/app/services/status_bar/service.py`, in `get_config()`, extend the `PillCatalogEntry(...)` construction:

```python
            entries.append(PillCatalogEntry(
                pill_id=definition.id,
                name_key=definition.name_key,
                enabled=row.enabled,
                visibility=row.visibility,
                visibility_locked=definition.visibility_locked,
                sort_order=row.sort_order,
                href=definition.href,
                display_mode=row.display_mode,
                display_mode_configurable=definition.display_mode_configurable,
            ))
```

- [ ] **Step 3b: `update_config` — validate + persist + diff**

In the validation loop at the top of `update_config()` (which already rejects locked-visibility), add a display-mode check inside the same `for item in update.pills:` loop:

```python
        for item in update.pills:
            definition = CATALOG_BY_ID.get(item.pill_id)
            if definition and definition.visibility_locked and item.visibility == "all":
                raise ValueError(
                    f"pill '{item.pill_id}' is visibility_locked and cannot be set to 'all'"
                )
            if (definition and not definition.display_mode_configurable
                    and item.display_mode != "always"):
                raise ValueError(
                    f"pill '{item.pill_id}' does not support a custom display_mode"
                )
```

Then in the apply loop, include `display_mode` in the before/after tuples and assignment:

```python
            before = (row.enabled, row.visibility, row.sort_order, row.display_mode)
            row.enabled = item.enabled
            row.visibility = item.visibility
            row.sort_order = item.sort_order
            row.display_mode = item.display_mode
            after = (row.enabled, row.visibility, row.sort_order, row.display_mode)
            if before != after:
                diff["changed"].append({
                    "pill_id": item.pill_id,
                    "before": {"enabled": before[0], "visibility": before[1],
                               "sort_order": before[2], "display_mode": before[3]},
                    "after": {"enabled": after[0], "visibility": after[1],
                              "sort_order": after[2], "display_mode": after[3]},
                })
```

- [ ] **Step 3c: `collect_state` — display-mode filter**

In `collect_state()`, inside the `for definition, _row in visible:` loop, after the `if partial is None: continue` line and before `pills.append(...)`:

```python
            if definition.display_mode_configurable:
                state = partial.pop("_state", None)
                mode = getattr(_row, "display_mode", "always")
                if (mode == "when_off" and state != "stopped") or \
                   (mode == "when_on" and state != "running"):
                    continue
```

(`partial.pop("_state", None)` guarantees the private hint never reaches `PillState(**partial)`.)

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/services/test_status_bar_service.py -k "display_mode_fields or rejects_display_mode or persists_desktop or collect_state_always or collect_state_when" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/status_bar/service.py backend/tests/services/test_status_bar_service.py
git commit -m "feat(statusbar): display-mode filter + config read/write for desktop pill"
```

---

## Task 6: Route-level test (validation 400 end-to-end)

**Files:**
- Test: `backend/tests/api/test_status_bar_routes.py`

**Design notes:** The route already maps `ValueError → 400` (`update_statusbar_config`). Add a test that a PUT with `display_mode` on a non-configurable pill returns 400, mirroring the existing locked-visibility route test. Read the top of `backend/tests/api/test_status_bar_routes.py` first to reuse its admin-client fixture and request-shape helpers.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/api/test_status_bar_routes.py`, following the existing fixture style in that file (use the same admin `client` fixture and `GET /api/system/statusbar/config` to seed the payload):

```python
def test_put_config_rejects_display_mode_on_non_configurable_pill(client):
    cfg = client.get("/api/system/statusbar/config").json()
    pills = []
    for p in cfg["pills"]:
        pills.append({
            "pill_id": p["pill_id"],
            "enabled": p["enabled"],
            "visibility": p["visibility"],
            "sort_order": p["sort_order"],
            "display_mode": "when_off" if p["pill_id"] == "power" else "always",
        })
    r = client.put("/api/system/statusbar/config",
                   json={"pills": pills, "show_bottom_upload": True})
    assert r.status_code == 400


def test_put_config_accepts_display_mode_on_desktop(client):
    cfg = client.get("/api/system/statusbar/config").json()
    pills = []
    for p in cfg["pills"]:
        pills.append({
            "pill_id": p["pill_id"],
            "enabled": p["enabled"],
            "visibility": p["visibility"],
            "sort_order": p["sort_order"],
            "display_mode": "when_off" if p["pill_id"] == "desktop" else "always",
        })
    r = client.put("/api/system/statusbar/config",
                   json={"pills": pills, "show_bottom_upload": True})
    assert r.status_code == 200
    desktop = next(p for p in r.json()["pills"] if p["pill_id"] == "desktop")
    assert desktop["display_mode"] == "when_off"
    assert desktop["display_mode_configurable"] is True
```

> If the existing tests in this file use a differently-named fixture than `client`, match it. Read the file's top ~40 lines before writing.

- [ ] **Step 2: Run to verify failure, then it should pass against Task-5 code**

Run: `python -m pytest tests/api/test_status_bar_routes.py -k "display_mode" -v`
Expected: PASS (the backend already implements the behavior from Task 5; this test pins the HTTP contract). If it FAILS with 422 instead of 400, the payload is missing a required field — align the dict keys with `PillConfigItem`.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_status_bar_routes.py
git commit -m "test(statusbar): desktop display_mode PUT validation (400/200)"
```

---

## Task 7: Frontend types (`api/statusBar.ts`)

**Files:**
- Modify: `client/src/api/statusBar.ts`

**Design notes:** No test for pure type changes; the build (Task 12) type-checks. Add `'desktop'` to `PillId`, a `DisplayMode` type, and the new fields. Run all frontend commands from `client/`.

- [ ] **Step 1: Edit types**

In `client/src/api/statusBar.ts`:

```typescript
export type PillId =
  | 'power' | 'pihole' | 'uploads' | 'sync' | 'raid' | 'sleep' | 'vpn' | 'temp'
  | 'always_awake' | 'scheduler' | 'backup' | 'desktop';

export type DisplayMode = 'always' | 'when_off' | 'when_on';
```

Extend `PillCatalogEntry`:

```typescript
export interface PillCatalogEntry {
  pill_id: PillId;
  name_key: string;
  enabled: boolean;
  visibility: PillVisibility;
  visibility_locked: boolean;
  sort_order: number;
  href: string;
  display_mode: DisplayMode;
  display_mode_configurable: boolean;
}
```

Extend `PillConfigItem`:

```typescript
export interface PillConfigItem {
  pill_id: PillId;
  enabled: boolean;
  visibility: PillVisibility;
  sort_order: number;
  display_mode: DisplayMode;
}
```

- [ ] **Step 2: Commit** (build verified in Task 12)

```bash
git add client/src/api/statusBar.ts
git commit -m "feat(statusbar): frontend types for desktop pill + display_mode"
```

---

## Task 8: `usePillConfig` — display-mode state + payload

**Files:**
- Modify: `client/src/components/status-bar-config/usePillConfig.ts`
- Test: `client/src/__tests__/components/status-bar-config/usePillConfig.test.ts`

- [ ] **Step 1: Write the failing test**

Read the existing `usePillConfig.test.ts` to match its mock of `../../api/statusBar`. Add a test asserting `setDisplayMode` updates state and `save()` sends `display_mode` in each item. Following the existing mock pattern in that file:

```typescript
it('includes display_mode in the save payload and setDisplayMode updates it', async () => {
  // (mirror the existing getStatusBarConfig mock; include display_mode + display_mode_configurable
  //  on each returned catalog entry, with desktop configurable)
  const { result } = renderHook(() => usePillConfig());
  await waitFor(() => expect(result.current.loading).toBe(false));

  act(() => result.current.setDisplayMode('desktop', 'when_off'));
  await act(async () => { await result.current.save(); });

  const payload = (updateStatusBarConfig as Mock).mock.calls[0][0];
  const desktop = payload.pills.find((p: any) => p.pill_id === 'desktop');
  expect(desktop.display_mode).toBe('when_off');
  // every item carries a display_mode (defaults 'always')
  expect(payload.pills.every((p: any) => typeof p.display_mode === 'string')).toBe(true);
});
```

> Match the existing file's imports (`renderHook`, `act`, `waitFor` from `@testing-library/react`, `vi.mock('../../api/statusBar', ...)`). Ensure the mocked `getStatusBarConfig` returns entries that include `display_mode: 'always'` and `display_mode_configurable` (true for desktop, false otherwise).

- [ ] **Step 2: Run to verify failure**

Run (from `client/`): `npx vitest run src/__tests__/components/status-bar-config/usePillConfig.test.ts`
Expected: FAIL (`setDisplayMode` undefined; payload lacks `display_mode`).

- [ ] **Step 3: Implement**

In `client/src/components/status-bar-config/usePillConfig.ts`:

Add to the `UsePillConfig` interface:

```typescript
  setDisplayMode: (id: string, displayMode: DisplayMode) => void;
```

Import the type:

```typescript
import type { PillCatalogEntry, PillVisibility, DisplayMode } from '../../api/statusBar';
```

Add the setter (next to `setVisibility`):

```typescript
  const setDisplayMode = useCallback((id: string, displayMode: DisplayMode) => {
    setPills(prev => prev.map(p => (p.pill_id === id ? { ...p, display_mode: displayMode } : p)));
  }, []);
```

Include `display_mode` in the save payload mapping:

```typescript
        pills: pills.map(p => ({
          pill_id: p.pill_id, enabled: p.enabled,
          visibility: p.visibility, sort_order: p.sort_order,
          display_mode: p.display_mode,
        })),
```

Return `setDisplayMode`:

```typescript
  return {
    pills, showBottomUpload, loading, saving, error,
    setEnabled, setVisibility, setDisplayMode,
    setShowBottomUpload: setShow, reorder, save, reload,
  };
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/__tests__/components/status-bar-config/usePillConfig.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/status-bar-config/usePillConfig.ts client/src/__tests__/components/status-bar-config/usePillConfig.test.ts
git commit -m "feat(statusbar): usePillConfig carries display_mode"
```

---

## Task 9: `PillRow` display-mode select + tab wiring

**Files:**
- Modify: `client/src/components/status-bar-config/PillRow.tsx`
- Modify: `client/src/components/status-bar-config/StatusBarConfigTab.tsx`
- Test: `client/src/__tests__/components/status-bar-config/PillRow.test.tsx`

**Design notes:** The display-mode `<select>` renders only when `entry.display_mode_configurable`. Place it before the visibility select. The global test setup mocks i18n so `t(key)` returns the key — query the select by role, not by translated label.

- [ ] **Step 1: Write the failing test**

Read the existing `PillRow.test.tsx` to reuse its render helper and a sample `entry`. Add:

```tsx
it('renders a display-mode select only for display_mode_configurable pills', () => {
  const base = { name_key: 'statusBar.pills.x.name', enabled: true, visibility: 'admin' as const,
                 visibility_locked: false, sort_order: 0, href: '/x', display_mode: 'always' as const };
  const { rerender } = render(
    <PillRow entry={{ ...base, pill_id: 'desktop', display_mode_configurable: true }}
             onToggleEnabled={() => {}} onSetVisibility={() => {}} onSetDisplayMode={() => {}} />
  );
  expect(screen.getByLabelText('display mode')).toBeInTheDocument();

  rerender(
    <PillRow entry={{ ...base, pill_id: 'power', display_mode_configurable: false }}
             onToggleEnabled={() => {}} onSetVisibility={() => {}} onSetDisplayMode={() => {}} />
  );
  expect(screen.queryByLabelText('display mode')).not.toBeInTheDocument();
});

it('calls onSetDisplayMode when the select changes', () => {
  const onSetDisplayMode = vi.fn();
  render(
    <PillRow
      entry={{ pill_id: 'desktop', name_key: 'statusBar.pills.desktop.name', enabled: true,
               visibility: 'admin', visibility_locked: false, sort_order: 0, href: '/x',
               display_mode: 'always', display_mode_configurable: true }}
      onToggleEnabled={() => {}} onSetVisibility={() => {}} onSetDisplayMode={onSetDisplayMode} />
  );
  fireEvent.change(screen.getByLabelText('display mode'), { target: { value: 'when_off' } });
  expect(onSetDisplayMode).toHaveBeenCalledWith('desktop', 'when_off');
});
```

> Wrap render in the same `DndContext`/`SortableContext` provider the existing `PillRow.test.tsx` uses (PillRow calls `useSortable`, which needs a sortable context). Reuse that file's existing wrapper.

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/__tests__/components/status-bar-config/PillRow.test.tsx`
Expected: FAIL (no display-mode select; `onSetDisplayMode` prop unknown).

- [ ] **Step 3: Implement `PillRow`**

In `client/src/components/status-bar-config/PillRow.tsx`:

Update imports + props:

```tsx
import type { PillCatalogEntry, PillVisibility, DisplayMode } from '../../api/statusBar';

interface Props {
  entry: PillCatalogEntry;
  onToggleEnabled: (id: string, enabled: boolean) => void;
  onSetVisibility: (id: string, visibility: PillVisibility) => void;
  onSetDisplayMode: (id: string, displayMode: DisplayMode) => void;
}

export function PillRow({ entry, onToggleEnabled, onSetVisibility, onSetDisplayMode }: Props) {
```

Insert the select just before the visibility `<select>` (after the `visibility_locked` badge block):

```tsx
      {entry.display_mode_configurable ? (
        <select
          aria-label="display mode"
          className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200"
          value={entry.display_mode}
          onChange={(e) => onSetDisplayMode(entry.pill_id, e.target.value as DisplayMode)}
        >
          <option value="always">{t('displayMode.always')}</option>
          <option value="when_off">{t('displayMode.whenOff')}</option>
          <option value="when_on">{t('displayMode.whenOn')}</option>
        </select>
      ) : null}
```

- [ ] **Step 4: Wire the tab**

In `client/src/components/status-bar-config/StatusBarConfigTab.tsx`, pass the new handler to `PillRow`:

```tsx
              <PillRow
                key={entry.pill_id}
                entry={entry}
                onToggleEnabled={cfg.setEnabled}
                onSetVisibility={cfg.setVisibility}
                onSetDisplayMode={cfg.setDisplayMode}
              />
```

- [ ] **Step 5: Run to verify pass**

Run: `npx vitest run src/__tests__/components/status-bar-config/PillRow.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/status-bar-config/PillRow.tsx client/src/components/status-bar-config/StatusBarConfigTab.tsx client/src/__tests__/components/status-bar-config/PillRow.test.tsx
git commit -m "feat(statusbar): display-mode select in PillRow for configurable pills"
```

---

## Task 10: Icon map — `Monitor`

**Files:**
- Modify: `client/src/components/topbar/iconMap.ts`

- [ ] **Step 1: Add the icon**

In `client/src/components/topbar/iconMap.ts`, add `Monitor` to the import and the `ICONS` map:

```typescript
import {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer,
  Coffee, Clock, Save, Monitor,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer, Coffee, Clock, Save, Monitor,
};
```

- [ ] **Step 2: (Optional) extend the renderer test**

In `client/src/__tests__/components/topbar/pillRenderers.test.tsx` (read it first to match the render helper), add a case asserting a `PillState` with `id:'desktop', icon:'Monitor'` renders without falling back to no-icon. If the existing test structure doesn't make this easy, rely on Task 12's build + manual smoketest instead — do not force a brittle test.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/topbar/iconMap.ts
git commit -m "feat(statusbar): map Monitor icon for desktop pill"
```

---

## Task 11: i18n (DE + EN)

**Files:**
- Modify: `client/src/i18n/locales/de/statusBar.json`
- Modify: `client/src/i18n/locales/en/statusBar.json`

- [ ] **Step 1: Add German keys**

In `client/src/i18n/locales/de/statusBar.json`, add to `pills` (after `backup`) and add a `displayMode` block (after `visibility`):

`pills` entry:
```json
    "backup": { "name": "Backup" },
    "desktop": { "name": "Desktop (KDE)" }
```

new block:
```json
  "displayMode": {
    "label": "Anzeige",
    "always": "Immer anzeigen",
    "whenOff": "Nur wenn AUS",
    "whenOn": "Nur wenn AN"
  },
```

- [ ] **Step 2: Add English keys**

In `client/src/i18n/locales/en/statusBar.json`, mirror:

`pills` entry:
```json
    "backup": { "name": "Backup" },
    "desktop": { "name": "Desktop (KDE)" }
```

new block:
```json
  "displayMode": {
    "label": "Display",
    "always": "Always show",
    "whenOff": "Only when OFF",
    "whenOn": "Only when ON"
  },
```

- [ ] **Step 3: Verify JSON validity**

Run (from `client/`): `node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/statusBar.json')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/statusBar.json')); console.log('OK')"`
Expected: `OK` (no JSON syntax error from the added commas).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/statusBar.json client/src/i18n/locales/en/statusBar.json
git commit -m "feat(statusbar): i18n for desktop pill + display-mode (de/en)"
```

---

## Task 12: Full verification + manual smoketest

**Files:** none (verification only)

- [ ] **Step 1: Backend — desktop + status-bar suites**

Run from `backend/`:
```bash
python -m pytest tests/services/test_status_bar_service.py tests/services/test_status_bar_collectors.py tests/api/test_status_bar_routes.py -v
```
Expected: all pass (incl. the updated 12-pill count + drift test).

- [ ] **Step 2: Backend — broader regression**

Run from `backend/`: `python -m pytest -q`
Expected: no new failures vs `main`. (Known Windows flakiness: `tests/auth/test_permissions.py::test_owner_can_delete_own_file` / `::test_admin_can_delete_any_file` fail only in the full run; re-run them standalone to confirm green — not caused by this change.)

- [ ] **Step 3: Frontend — targeted tests + build**

Run from `client/`:
```bash
npx vitest run src/__tests__/components/status-bar-config src/__tests__/components/topbar
npm run build
```
Expected: tests pass; `npm run build` succeeds with no TypeScript errors (this type-checks Tasks 7–10).

- [ ] **Step 4: Manual smoketest (dev mode)**

1. `python start_dev.py`, log in as admin (`admin` / `DevMode2024`).
2. System Control → System → Status Bar: the **Desktop (KDE)** row appears with a **Anzeige** dropdown (Immer / Nur wenn AUS / Nur wenn AN) and a visibility select that is **not** locked.
3. Enable the Desktop pill, mode **Immer**, save → the topbar shows a Desktop pill. In dev mode `DevDesktopBackend` starts `running` → neutral "An".
4. (Dev) Toggle the desktop off via the Sleep page panel → within ~10s the pill flips to success "Aus · GPU idle".
5. Set mode **Nur wenn AUS**, save → pill hidden while desktop is running, visible when stopped.
6. Set visibility **Alle Nutzer**, save; open as a non-admin → the Desktop pill is visible (proves it is not locked).

- [ ] **Step 5: Final commit (if any smoketest tweaks)** — otherwise nothing to commit.

---

## Self-Review

**Spec coverage:**
- New `desktop` catalog pill, admin-default, unlocked → Task 1. OK
- Collector over `get_desktop_service().get_status()`, `unknown`→silent → Task 4. OK
- Per-pill display mode (always/when_off/when_on), scoped via `display_mode_configurable` flag → Tasks 1 (flag), 3 (schema), 5 (filter + persist), 9 (UI). OK
- Server rejects display_mode on non-configurable pills (400) → Task 5 (ValueError) + Task 6 (HTTP). OK
- Persistence via additive migration chained onto real head → Task 2. OK
- Icon `Monitor`, generic renderer, no new component → Task 10. OK
- Config UI dropdown only for configurable pills → Task 9. OK
- i18n DE+EN → Task 11. OK
- Audit diff includes display_mode → Task 5 (diff tuples). OK
- Existing breaking tests updated (12-pill count, column set) → Tasks 1, 2. OK

**Placeholder scan:** No TBD/TODO; each code step has full code. Frontend test steps reference reusing the sibling test file's render/mocks — that is a concrete instruction (the harness exists), not a placeholder.

**Type consistency:** `DisplayMode = "always"|"when_off"|"when_on"` identical in Python (`schemas/status_bar.py`) and TS (`api/statusBar.ts`). `display_mode_configurable` consistent across catalog → schema → service → API type → PillRow. Collector emits `_state`; service pops it (`partial.pop("_state")`) before `PillState(**partial)` — never leaks. `setDisplayMode(id, mode)` signature consistent between `usePillConfig` and `PillRow`/`StatusBarConfigTab`.

## Open nits (decide during implementation; non-blocking)
- `"Aus · GPU idle"` is the longest pill value — shorten to `"Aus"` if it crowds the strip (per spec review note).
- Runtime pill strings are DE (matches the desktop panel); existing pills mix EN/DE — out of scope to unify here.
