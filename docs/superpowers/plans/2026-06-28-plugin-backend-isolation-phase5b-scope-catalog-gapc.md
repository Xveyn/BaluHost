# Plugin Backend Isolation — Phase 5b: Scope Catalog, Scope-Picker & UI Surfacing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give admins a scope-granting UI for external sandboxed plugins, expose a server-defined scope catalog, surface external plugins' static UI in the SPA (Gap C), and fold in three 5a follow-ups.

**Architecture:** `granted_api_scopes` stays a single union column consumed by two enforcement layers (Track A frontend SDK regex; Track B backend `CapabilityRouter`). A new server-defined catalog (`scope_catalog.py`) enumerates exactly the six already-enforced scopes — backend-tier keys are *derived* from `CAPABILITY_SCOPE` so they cannot drift. The enable flow gains an external-only scope-picker. External plugins declare nav items statically in `plugin.json`; `get_ui_manifest()` gets an external branch.

**Tech Stack:** FastAPI + Pydantic v2 (backend), pytest; React 18 + TypeScript + Tailwind + i18next (frontend), vitest.

## Global Constraints

- **Six scopes, no new ones.** Catalog = exactly `read:system-info`, `read:storage`, `read:power` (frontend tier) + `storage`, `core.system_metrics`, `core.notify` (backend tier). No new backend capability, no new frontend scope.
- **Backend-tier keys are derived**, never hand-listed: `sorted(set(CAPABILITY_SCOPE.values()))`.
- **Single DB column.** `granted_api_scopes` stays the union bag; no second column, no migration.
- **External-only picker.** Bundled plugins keep the unchanged permissions modal + old permission model. The scope-picker only appears for external plugins.
- **Naming kept distinct:** request field `grant_api_scopes`; persisted column / router input `granted_api_scopes`. Do not conflate.
- **Catalog labels are i18n, not server text.** The endpoint returns structural data only (`key`, `tier`, `dangerous`); labels/descriptions live in `client/src/i18n/locales/{de,en}/plugins.json`.
- **i18next separator pitfall:** catalog keys contain `:` (nsSeparator) and `.` (keySeparator). NEVER build a dynamic `t('scopeDescriptions.' + key + '.label')` — it will mis-parse. Always fetch the whole object: `t('scopeDescriptions', { returnObjects: true })` and index by key in JS.
- **No `PluginDocumentation.tsx` changes** — that two-tier rewrite is a separate sibling PR.
- **Windows dev box:** the Linux spawn integration test MUST be `skipif`-gated (Linux + root + provisioned); it must never fail the Windows suite.
- Add both `de` and `en` for every new i18n key (missing keys fall back to German).
- Repo runs `core.autocrlf=true`; let git handle line endings.

---

## File Structure

**Backend — create:**
- `backend/app/plugins/scope_catalog.py` — `ScopeInfo` dataclass, `SCOPE_CATALOG`, `CATALOG_KEYS`.
- `backend/tests/plugins/test_scope_catalog.py` — catalog + endpoint + drift-guard tests.
- `backend/tests/plugins/sandbox/test_spawn_integration_linux.py` — gated real-spawn integration test (5a follow-up).

**Backend — modify:**
- `backend/app/schemas/plugin.py` — `ScopeInfoSchema`, `ScopeCatalogResponse`; `PluginToggleRequest.grant_api_scopes`; `PluginDetailResponse.requested_api_scopes` + `is_external`; `PluginInfo.is_external`.
- `backend/app/plugins/manifest.py` — `ManifestNavItem`; `PluginManifestUI.nav_items` + `.dashboard_widgets`.
- `backend/app/api/routes/plugins.py` — `GET /scope-catalog`; `/ui/manifest` enrichment fix; `_toggle_external` scope threading; external `get_plugin_details` `requested_api_scopes` + `is_external`; `list_plugins` `is_external`.
- `backend/app/plugins/manager.py` — `get_ui_manifest()` external branch (Gap C); `get_all_plugins()` `is_external` key; `_enable_external` success audit.
- `backend/app/plugins/CLAUDE.md` — trust-tier note.

**Frontend — modify:**
- `client/src/api/plugins.ts` — `ScopeInfo`, `getScopeCatalog()`; `grant_api_scopes` on toggle; `requested_api_scopes`/`is_external` on detail; `is_external` on list.
- `client/src/pages/PluginsPage.tsx` — scope-picker modal + external branch in the enable flow.
- `client/src/i18n/locales/en/plugins.json` + `client/src/i18n/locales/de/plugins.json` — `scopeDescriptions`, `scopeTiers`, `picker`.

**Frontend — create (tests):** this repo uses a **centralized mirror tree** under `client/src/__tests__/<area>/` (NOT co-located, NOT per-dir `__tests__/`). Depth from a test file back to `src/` is `../../`. New tests:
- `client/src/__tests__/api/plugins.scopeCatalog.test.ts`
- `client/src/__tests__/pages/PluginsPage.scopePicker.test.tsx`
- `client/src/__tests__/contexts/PluginContext.externalNav.test.tsx`

**Repo vitest convention (verified):** `useTranslation` is universally stubbed as `t: (key) => key` — tests assert on i18n **keys**, not translated text. `apiClient` is mocked via `vi.mock('../../lib/api', …)`. Contexts (`AuthContext`) are mocked, not provided. There is no shared i18n test provider / render helper. Mock skeleton to reuse:

```ts
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  memoizedApiRequest: vi.fn(),
}));
```

---

## Task 1: Scope catalog module, schemas & endpoint

**Files:**
- Create: `backend/app/plugins/scope_catalog.py`
- Modify: `backend/app/schemas/plugin.py` (add two schemas)
- Modify: `backend/app/api/routes/plugins.py` (add `GET /scope-catalog`)
- Create: `backend/tests/plugins/test_scope_catalog.py`

**Interfaces:**
- Produces: `SCOPE_CATALOG: tuple[ScopeInfo, ...]`, `CATALOG_KEYS: frozenset[str]`, `ScopeInfo{key, tier, dangerous}` (Task 5 imports `CATALOG_KEYS`).
- Produces: `ScopeInfoSchema{key: str, tier: str, dangerous: bool}`, `ScopeCatalogResponse{scopes: List[ScopeInfoSchema]}`.
- Consumes: `app.plugins.sandbox.capabilities.CAPABILITY_SCOPE` (values: `storage`, `core.system_metrics`, `core.notify`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_scope_catalog.py`:

```python
"""Tests for the external-plugin scope catalog (Phase 5b)."""
from app.plugins.scope_catalog import SCOPE_CATALOG, CATALOG_KEYS, ScopeInfo
from app.plugins.sandbox.capabilities import CAPABILITY_SCOPE


def test_catalog_has_six_entries():
    assert len(SCOPE_CATALOG) == 6


def test_frontend_tier_keys_are_the_three_sdk_scopes():
    fe = {s.key for s in SCOPE_CATALOG if s.tier == "frontend"}
    assert fe == {"read:system-info", "read:storage", "read:power"}


def test_backend_tier_keys_derived_from_capability_scope_no_drift():
    be = {s.key for s in SCOPE_CATALOG if s.tier == "backend"}
    assert be == set(CAPABILITY_SCOPE.values())


def test_every_entry_is_structural_and_not_dangerous():
    for s in SCOPE_CATALOG:
        assert isinstance(s, ScopeInfo)
        assert s.tier in ("frontend", "backend")
        assert s.dangerous is False


def test_catalog_keys_matches_entry_keys():
    assert CATALOG_KEYS == frozenset(s.key for s in SCOPE_CATALOG)
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `backend/`): `python -m pytest tests/plugins/test_scope_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.scope_catalog'`.

- [ ] **Step 3: Create the catalog module**

Create `backend/app/plugins/scope_catalog.py`:

```python
"""Server-defined catalog of capability scopes grantable to external plugins.

Single source of truth for the scope-picker UI. Human labels/descriptions live
in frontend i18n (`scopeDescriptions.<key>`), exactly like `permissionDescriptions`.
Backend-tier keys are DERIVED from `CAPABILITY_SCOPE` so they cannot drift from
what the CapabilityRouter actually enforces.
"""
from dataclasses import dataclass
from typing import Literal, Tuple

from app.plugins.sandbox.capabilities import CAPABILITY_SCOPE


@dataclass(frozen=True)
class ScopeInfo:
    key: str
    tier: Literal["frontend", "backend"]
    dangerous: bool


# Frontend-tier keys mirror client/src/lib/plugin-sandbox/scopeCatalog.ts.
_FRONTEND_SCOPES = ("read:system-info", "read:storage", "read:power")

SCOPE_CATALOG: Tuple[ScopeInfo, ...] = (
    *(ScopeInfo(k, "frontend", False) for k in _FRONTEND_SCOPES),
    *(ScopeInfo(v, "backend", False) for v in sorted(set(CAPABILITY_SCOPE.values()))),
)

CATALOG_KEYS = frozenset(s.key for s in SCOPE_CATALOG)
```

- [ ] **Step 4: Run the catalog tests to verify they pass**

Run: `python -m pytest tests/plugins/test_scope_catalog.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Add the response schemas**

In `backend/app/schemas/plugin.py`, after the `PermissionListResponse` class (line ~172), add:

```python
class ScopeInfoSchema(BaseModel):
    """A single grantable external-plugin capability scope (structural only)."""

    key: str
    tier: str  # "frontend" | "backend"
    dangerous: bool


class ScopeCatalogResponse(BaseModel):
    """Catalog of scopes grantable to external plugins. Labels are i18n on the client."""

    scopes: List[ScopeInfoSchema] = []
```

- [ ] **Step 6: Write the failing endpoint test (direct-call style)**

The route tests in this repo call handlers directly (no TestClient/auth-header fixtures) — see `backend/tests/plugins/test_external_plugin_routes.py`, which defines `_make_mock_request()` / `_make_mock_response()` and imports the route module as `plugins_route`. Append this endpoint test to **`backend/tests/plugins/test_external_plugin_routes.py`** (it already has the helpers, `asyncio`, `types`):

```python
def test_get_scope_catalog_endpoint_returns_six_entries():
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.get_scope_catalog(
            request=_make_mock_request(), response=_make_mock_response(), current_user=user,
        )
    )
    assert len(resp.scopes) == 6
    keys = {s.key for s in resp.scopes}
    assert "read:system-info" in keys
    assert "core.notify" in keys
    for s in resp.scopes:
        assert s.tier in ("frontend", "backend")
        assert s.dangerous is False
```

(The pure catalog-data tests in Steps 1-4 stay in `test_scope_catalog.py`; only the endpoint test lives here so it can reuse the mock-request helpers.)

- [ ] **Step 7: Run it to verify it fails**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py::test_get_scope_catalog_endpoint_returns_six_entries -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'get_scope_catalog'` (route not yet defined).

- [ ] **Step 8: Add the endpoint**

In `backend/app/api/routes/plugins.py`:

Add to the schema import block (the `from app.schemas.plugin import (...)` list, lines 19-34):

```python
    ScopeCatalogResponse,
    ScopeInfoSchema,
```

Add a new import near the other `app.plugins` imports (after line 15):

```python
from app.plugins.scope_catalog import SCOPE_CATALOG, CATALOG_KEYS
```

Add the route immediately after `list_permissions` (after line 102):

```python
@router.get("/scope-catalog", response_model=ScopeCatalogResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_scope_catalog(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
) -> ScopeCatalogResponse:
    """Grantable external-plugin capability scopes (structural; labels are i18n on the client)."""
    return ScopeCatalogResponse(
        scopes=[
            ScopeInfoSchema(key=s.key, tier=s.tier, dangerous=s.dangerous)
            for s in SCOPE_CATALOG
        ]
    )
```

> NOTE: `/scope-catalog` must be registered BEFORE the `@router.get("/{name}")` detail route (line 132) so it is not captured as `name="scope-catalog"`. Placing it right after `list_permissions` (line 102) satisfies this.

- [ ] **Step 9: Run the catalog + endpoint tests**

Run: `python -m pytest tests/plugins/test_scope_catalog.py tests/plugins/test_external_plugin_routes.py::test_get_scope_catalog_endpoint_returns_six_entries -v`
Expected: PASS (5 catalog tests + 1 endpoint test).

- [ ] **Step 10: Commit**

```bash
git add backend/app/plugins/scope_catalog.py backend/app/schemas/plugin.py backend/app/api/routes/plugins.py backend/tests/plugins/test_scope_catalog.py backend/tests/plugins/test_external_plugin_routes.py
git commit -m "feat(plugin-sandbox): scope catalog module + GET /scope-catalog (Phase 5b)"
```

---

## Task 2: Static nav declaration in the manifest

**Files:**
- Modify: `backend/app/plugins/manifest.py`
- Test: `backend/tests/plugins/test_manifest.py` (existing module — has a `valid_manifest_data` fixture with a `ui` block; append the new tests here)

**Interfaces:**
- Produces: `ManifestNavItem{path: str, label: str, icon: Optional[str]=None, admin_only: bool=False, order: int=100}`.
- Produces: `PluginManifestUI` gains `nav_items: List[ManifestNavItem]` (default `[]`) and `dashboard_widgets: List[str]` (default `[]`). `bundle`/`styles` unchanged. (Task 3 reads `discovered.manifest.ui.nav_items` / `.bundle` / `.styles` / `.dashboard_widgets`.)

- [ ] **Step 1: (no separate step — tests go into the existing `test_manifest.py`)**

The manifest test module is `backend/tests/plugins/test_manifest.py` (verified to exist, with a `valid_manifest_data` fixture whose `ui` is `{"bundle": ..., "styles": None}`). Append the new tests to it.

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/plugins/test_manifest.py`:

```python
from app.plugins.manifest import PluginManifestUI, ManifestNavItem


def test_manifest_ui_nav_items_parse():
    ui = PluginManifestUI.model_validate({
        "bundle": "bundle.js",
        "nav_items": [
            {"path": "weather", "label": "Weather", "icon": "cloud", "order": 50},
        ],
        "dashboard_widgets": ["WeatherWidget"],
    })
    assert len(ui.nav_items) == 1
    assert ui.nav_items[0] == ManifestNavItem(
        path="weather", label="Weather", icon="cloud", admin_only=False, order=50
    )
    assert ui.dashboard_widgets == ["WeatherWidget"]


def test_manifest_ui_without_nav_items_defaults_empty():
    ui = PluginManifestUI.model_validate({"bundle": "bundle.js"})
    assert ui.nav_items == []
    assert ui.dashboard_widgets == []
    assert ui.styles is None
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/plugins/test_manifest.py -v` (or the chosen module)
Expected: FAIL — `ImportError: cannot import name 'ManifestNavItem'`.

- [ ] **Step 4: Extend the manifest model**

In `backend/app/plugins/manifest.py`, replace the `PluginManifestUI` class (lines 30-34) with:

```python
class ManifestNavItem(BaseModel):
    """A static sidebar nav entry declared by an external plugin in plugin.json."""

    path: str
    label: str
    icon: Optional[str] = None
    admin_only: bool = False
    order: int = 100


class PluginManifestUI(BaseModel):
    """UI section of a plugin manifest."""

    bundle: str = Field(..., description="Path to the JS bundle, relative to plugin dir")
    styles: Optional[str] = Field(default=None, description="Optional CSS path")
    nav_items: List[ManifestNavItem] = Field(default_factory=list)
    dashboard_widgets: List[str] = Field(default_factory=list)
```

(`List`, `Optional`, `BaseModel`, `Field` are already imported at the top of the file.)

- [ ] **Step 5: Run the manifest tests to verify they pass**

Run: `python -m pytest tests/plugins/test_manifest.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full manifest test module for regressions**

Run: `python -m pytest tests/plugins/ -k manifest -v`
Expected: PASS (existing manifest tests still green — backward-compatible defaults).

- [ ] **Step 7: Commit**

```bash
git add backend/app/plugins/manifest.py backend/tests/plugins/test_manifest.py
git commit -m "feat(plugin-sandbox): static nav_items/dashboard_widgets in PluginManifestUI (Phase 5b)"
```

---

## Task 3: Gap C — surface external plugins in `get_ui_manifest()`

**Files:**
- Modify: `backend/app/plugins/manager.py` (`get_ui_manifest`, lines 782-809)
- Test: `backend/tests/plugins/test_external_plugin_routes.py` (extend) or a new `test_external_ui_manifest.py`

**Interfaces:**
- Consumes: `ManifestNavItem`/`PluginManifestUI` from Task 2; `self.get_discovered(name)` → `DiscoveredPlugin{name, path, source, manifest}`; `self._sandboxes` (external enabled); `self._enabled`.
- Produces: each external plugin's `/ui/manifest` entry dict: `{name, display_name, nav_items, bundle_path, styles_path, dashboard_widgets, translations: None}` — same shape the in-process branch already appends.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_external_ui_manifest.py`:

```python
"""Gap C: external sandboxed plugins surface their static UI in get_ui_manifest()."""
import types
from pathlib import Path

from app.plugins.manager import PluginManager, DiscoveredPlugin
from app.plugins.manifest import PluginManifestUI, ManifestNavItem


def _external_manifest(tmp_path: Path):
    return types.SimpleNamespace(
        name="weather",
        display_name="Weather",
        ui=PluginManifestUI(
            bundle="bundle.js",
            styles="styles.css",
            nav_items=[ManifestNavItem(path="weather", label="Weather", icon="cloud", order=50)],
            dashboard_widgets=["WeatherWidget"],
        ),
    )


def test_external_plugin_appears_in_ui_manifest(tmp_path):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()
    mgr._discovered = {
        "weather": DiscoveredPlugin(
            name="weather", path=pdir, source="external",
            manifest=_external_manifest(tmp_path),
        ),
    }
    # External enabled: present in _enabled + _sandboxes, NOT in _plugins.
    mgr._enabled.add("weather")
    mgr._sandboxes["weather"] = object()

    manifest = mgr.get_ui_manifest()
    entry = next(p for p in manifest["plugins"] if p["name"] == "weather")
    assert entry["bundle_path"] == "bundle.js"
    assert entry["styles_path"] == "styles.css"
    assert entry["dashboard_widgets"] == ["WeatherWidget"]
    assert entry["nav_items"][0]["path"] == "weather"
    assert entry["nav_items"][0]["label"] == "Weather"
    assert entry["translations"] is None


def test_external_plugin_without_ui_is_absent(tmp_path):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "noui"
    pdir.mkdir()
    mgr._discovered = {
        "noui": DiscoveredPlugin(
            name="noui", path=pdir, source="external",
            manifest=types.SimpleNamespace(name="noui", display_name="NoUI", ui=None),
        ),
    }
    mgr._enabled.add("noui")
    mgr._sandboxes["noui"] = object()

    manifest = mgr.get_ui_manifest()
    assert all(p["name"] != "noui" for p in manifest["plugins"])
```

> NOTE: confirm `DiscoveredPlugin` is importable from `app.plugins.manager` (the existing `test_external_plugin_routes.py` imports it this way). `_sandboxes` is the external-enabled registry from Phase 4; verify the attribute name in `manager.py` and match it.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/plugins/test_external_ui_manifest.py -v`
Expected: FAIL — `weather` not found in `manifest["plugins"]` (external branch missing).

- [ ] **Step 3: Add the external branch to `get_ui_manifest()`**

In `backend/app/plugins/manager.py`, the loop at lines 792-807. Replace:

```python
        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin:
                ui_manifest = plugin.get_ui_manifest()
                if ui_manifest and ui_manifest.enabled:
                    manifest["plugins"].append({
                        "name": name,
                        "display_name": plugin.metadata.display_name,
                        "nav_items": [
                            item.model_dump() for item in ui_manifest.nav_items
                        ],
                        "bundle_path": ui_manifest.bundle_path,
                        "styles_path": ui_manifest.styles_path,
                        "dashboard_widgets": ui_manifest.dashboard_widgets,
                        "translations": plugin.get_translations() or None,
                    })

        return manifest
```

with:

```python
        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin:
                ui_manifest = plugin.get_ui_manifest()
                if ui_manifest and ui_manifest.enabled:
                    manifest["plugins"].append({
                        "name": name,
                        "display_name": plugin.metadata.display_name,
                        "nav_items": [
                            item.model_dump() for item in ui_manifest.nav_items
                        ],
                        "bundle_path": ui_manifest.bundle_path,
                        "styles_path": ui_manifest.styles_path,
                        "dashboard_widgets": ui_manifest.dashboard_widgets,
                        "translations": plugin.get_translations() or None,
                    })
                continue

            # External sandboxed plugin: surface UI from its static manifest.
            # getattr guards against test-double manifests (e.g. object()) that some
            # sandbox tests place in _enabled without a real PluginManifest.
            discovered = self.get_discovered(name)
            if (
                discovered is not None
                and discovered.source == "external"
                and discovered.manifest is not None
                and getattr(discovered.manifest, "ui", None) is not None
            ):
                ui = discovered.manifest.ui
                manifest["plugins"].append({
                    "name": name,
                    "display_name": discovered.manifest.display_name,
                    "nav_items": [item.model_dump() for item in ui.nav_items],
                    "bundle_path": ui.bundle,
                    "styles_path": ui.styles,
                    "dashboard_widgets": ui.dashboard_widgets,
                    "translations": None,  # external plugins ship UI strings inside their bundle
                })

        return manifest
```

- [ ] **Step 4: Run the Gap-C tests to verify they pass**

Run: `python -m pytest tests/plugins/test_external_ui_manifest.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the existing plugin manager/UI tests for regressions**

Run: `python -m pytest tests/plugins/ -k "ui_manifest or manifest or external" -v`
Expected: PASS (in-process plugin manifest path unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/manager.py backend/tests/plugins/test_external_ui_manifest.py
git commit -m "feat(plugin-sandbox): Gap C -- external plugins surface static UI in get_ui_manifest (Phase 5b)"
```

---

## Task 4: `/ui/manifest` enrichment resolves the real discovered dir

**Files:**
- Modify: `backend/app/api/routes/plugins.py` (`get_ui_manifest` route, lines 119-129)
- Test: `backend/tests/plugins/test_external_plugin_routes.py` (extend — it already has `_make_mock_request`/`_make_mock_response`, `asyncio`, `types`)

**Interfaces:**
- Consumes: `plugin_manager.get_discovered(name)` → manifest with `min_runtime_abi`; `plugin_service.get_installed_plugin(db, name)` → `.granted_api_scopes`.
- Produces: each `/ui/manifest` item carries `granted_api_scopes` (DB) + `min_runtime_abi` (its own discovered manifest), no longer mis-resolved against `plugins_dir / name`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_external_plugin_routes.py`:

```python
def test_ui_manifest_enrichment_uses_discovered_manifest_for_abi(monkeypatch):
    """min_runtime_abi must come from the plugin's OWN discovered manifest, not from
    load_manifest(plugins_dir / name) — that path is wrong for external plugins."""
    from app.api.routes import plugins as plugins_route

    class _Mgr:
        def get_ui_manifest(self):
            return {"plugins": [{
                "name": "weather", "display_name": "Weather",
                "nav_items": [], "bundle_path": "bundle.js",
                "styles_path": None, "dashboard_widgets": [], "translations": None,
            }]}

        def get_discovered(self, name):
            return types.SimpleNamespace(
                manifest=types.SimpleNamespace(min_runtime_abi=2)
            )

    def fake_get_installed(db, name):
        return types.SimpleNamespace(granted_api_scopes=["storage"])

    monkeypatch.setattr(plugins_route.plugin_service, "get_installed_plugin", fake_get_installed)

    # Old code path resolved via load_manifest(plugins_dir / name); guard it.
    def boom(_path):
        raise AssertionError("must not resolve manifest via plugins_dir")

    monkeypatch.setattr(plugins_route, "load_manifest", boom)

    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    result = asyncio.run(
        plugins_route.get_ui_manifest(
            request=_make_mock_request(), response=_make_mock_response(),
            db=object(), current_user=user, plugin_manager=_Mgr(),
        )
    )
    item = next(p for p in result.plugins if p.name == "weather")
    assert item.min_runtime_abi == 2
    assert item.granted_api_scopes == ["storage"]
```

> Why this fails before the fix: the current loop calls `load_manifest(...)` inside a `try/except Exception`, so `boom`'s `AssertionError` is swallowed and `min_runtime_abi` is set to `None` → the `== 2` assertion fails. After the fix, `load_manifest` is never called and `min_runtime_abi` comes from `get_discovered`.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py::test_ui_manifest_enrichment_uses_discovered_manifest_for_abi -v`
Expected: FAIL — `assert None == 2` (current code resolves ABI via `plugins_dir / name`).

- [ ] **Step 3: Fix the enrichment loop**

In `backend/app/api/routes/plugins.py`, replace the body of the `/ui/manifest` enrichment loop (lines 121-128):

```python
    for item in result.plugins:
        record = plugin_service.get_installed_plugin(db, item.name)
        item.granted_api_scopes = (record.granted_api_scopes or []) if record else []
        try:
            _manifest = load_manifest(plugin_manager.plugins_dir / item.name)
            item.min_runtime_abi = getattr(_manifest, "min_runtime_abi", None)
        except Exception:
            item.min_runtime_abi = None
```

with:

```python
    for item in result.plugins:
        record = plugin_service.get_installed_plugin(db, item.name)
        item.granted_api_scopes = (record.granted_api_scopes or []) if record else []
        discovered = plugin_manager.get_discovered(item.name)
        item.min_runtime_abi = (
            discovered.manifest.min_runtime_abi
            if discovered is not None and discovered.manifest is not None
            else None
        )
```

> NOTE: `load_manifest` may now be unused in this route file. Leave the import if any other handler still uses it (e.g. the bundled-enable branch in `toggle_plugin`); otherwise Ruff F401 will flag it — remove it only if truly unused. Verify before removing.

- [ ] **Step 4: Run the enrichment test to verify it passes**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py::test_ui_manifest_enrichment_uses_discovered_manifest_for_abi -v`
Expected: PASS.

- [ ] **Step 5: Run the route module for regressions**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/plugins.py backend/tests/plugins/test_external_plugin_routes.py
git commit -m "fix(plugin-sandbox): /ui/manifest resolves ABI from each plugin's discovered manifest (Phase 5b Gap C)"
```

---

## Task 5: Scope-picker backend — toggle field, threading, detail surfacing

**Files:**
- Modify: `backend/app/schemas/plugin.py` (`PluginToggleRequest`, `PluginDetailResponse`, `PluginInfo`)
- Modify: `backend/app/api/routes/plugins.py` (`_toggle_external`, external `get_plugin_details`, `list_plugins`)
- Modify: `backend/app/plugins/manager.py` (`get_all_plugins` — `is_external` key)
- Test: `backend/tests/plugins/test_external_plugin_routes.py` (extend)

**Interfaces:**
- Consumes: `CATALOG_KEYS` from Task 1.
- Produces: request `PluginToggleRequest.grant_api_scopes: List[str]`; `PluginDetailResponse.requested_api_scopes: List[str]` + `.is_external: bool`; `PluginInfo.is_external: bool`. Frontend Task 9 mirrors these names exactly.
- `_toggle_external` enabling now uses `granted = [s for s in body.grant_api_scopes if s in CATALOG_KEYS]` and passes `granted` to both `plugin_service.enable_plugin(api_scopes=granted)` and `plugin_manager.enable_plugin(..., granted_api_scopes=granted)`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/plugins/test_external_plugin_routes.py`:

```python
def test_toggle_enable_external_filters_grant_api_scopes_to_catalog(tmp_path, db_session, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        api_scopes = ["storage", "core.notify"]
        version = "2.0.0"
        display_name = "Weather"
        required_permissions = []

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }

    captured = {}

    async def fake_enable(name, perms, db, start_background_tasks=True, granted_api_scopes=None):
        captured["scopes"] = granted_api_scopes
        return True

    monkeypatch.setattr(mgr, "enable_plugin", fake_enable)

    persisted = {}
    real_enable = plugins_route.plugin_service.enable_plugin

    def spy_enable(db, **kwargs):
        persisted["api_scopes"] = kwargs.get("api_scopes")
        return real_enable(db, **kwargs)

    monkeypatch.setattr(plugins_route.plugin_service, "enable_plugin", spy_enable)

    # "network:evil" is NOT in the catalog -> must be dropped.
    body = plugins_route.PluginToggleRequest(
        enabled=True, grant_permissions=[],
        grant_api_scopes=["storage", "core.notify", "network:evil"],
    )
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.toggle_plugin(
            request=_make_mock_request(), response=_make_mock_response(), name="weather", body=body,
            db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert resp.is_enabled is True
    assert sorted(captured["scopes"]) == ["core.notify", "storage"]
    assert sorted(persisted["api_scopes"]) == ["core.notify", "storage"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py::test_toggle_enable_external_filters_grant_api_scopes_to_catalog -v`
Expected: FAIL — `PluginToggleRequest` has no `grant_api_scopes`.

- [ ] **Step 3: Add `grant_api_scopes` to the request schema**

In `backend/app/schemas/plugin.py`, extend `PluginToggleRequest` (lines 128-135):

```python
class PluginToggleRequest(BaseModel):
    """Request to enable/disable a plugin."""

    enabled: bool
    grant_permissions: List[str] = Field(
        default_factory=list,
        description="Permissions to grant (bundled plugins, old model)",
    )
    grant_api_scopes: List[str] = Field(
        default_factory=list,
        description="Capability scopes to grant an external plugin (filtered to the catalog)",
    )
```

- [ ] **Step 4: Thread scopes through `_toggle_external`**

In `backend/app/api/routes/plugins.py`, in `_toggle_external`, the enable branch currently reads `api_scopes` from the manifest:

```python
    if body.enabled:
        api_scopes = list(getattr(manifest, "api_scopes", []) or [])
```

Replace that line with the admin-granted, catalog-filtered subset:

```python
    if body.enabled:
        api_scopes = [s for s in body.grant_api_scopes if s in CATALOG_KEYS]
```

(The rest of the enable branch already passes `api_scopes` to `plugin_service.enable_plugin(api_scopes=…)` and `plugin_manager.enable_plugin(..., granted_api_scopes=api_scopes)` — unchanged.)

- [ ] **Step 5: Run the toggle test to verify it passes**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py::test_toggle_enable_external_filters_grant_api_scopes_to_catalog -v`
Expected: PASS.

> NOTE: the pre-existing `test_toggle_enable_external_uses_manifest` asserts `enabled["scopes"] == ["storage"]` from manifest `api_scopes`. With this change the granted scopes come from the REQUEST, not the manifest. Update that test to pass `grant_api_scopes=["storage"]` in its `PluginToggleRequest` so the assertion still holds. Run it and confirm green:
> `python -m pytest tests/plugins/test_external_plugin_routes.py -v`

- [ ] **Step 6: Write the failing detail/list `is_external` + `requested_api_scopes` test**

Append to `backend/tests/plugins/test_external_plugin_routes.py`:

```python
def test_get_plugin_details_external_surfaces_requested_scopes_and_flag(tmp_path, db_session):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        manifest_version = 1
        name = "weather"
        version = "2.0.0"
        display_name = "Weather"
        description = "d"
        author = "a"
        category = "general"
        homepage = None
        min_baluhost_version = None
        plugin_dependencies = []
        required_permissions = []
        api_scopes = ["storage", "core.notify"]
        ui = None

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.get_plugin_details(
            request=_make_mock_request(), response=_make_mock_response(),
            name="weather", db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert resp.is_external is True
    assert sorted(resp.requested_api_scopes) == ["core.notify", "storage"]
```

- [ ] **Step 7: Run it to verify it fails**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py::test_get_plugin_details_external_surfaces_requested_scopes_and_flag -v`
Expected: FAIL — `PluginDetailResponse` has no `is_external` / `requested_api_scopes`.

- [ ] **Step 8: Add the detail/list schema fields**

In `backend/app/schemas/plugin.py`:

In `PluginInfo` (after line 52, `error: Optional[str] = None`), add:

```python
    is_external: bool = False
```

In `PluginDetailResponse`, in the "Status" group (after line 110, `dashboard_panel_enabled: bool = False`), add:

```python
    is_external: bool = False
    requested_api_scopes: List[str] = []
```

- [ ] **Step 9: Populate the new fields in the routes + manager**

In `backend/app/api/routes/plugins.py`, in the external branch of `get_plugin_details` (the `PluginDetailResponse(...)` return at lines 147-176), add two kwargs (e.g. after `dashboard_panel_enabled=...`):

```python
            is_external=True,
            requested_api_scopes=list(getattr(manifest, "api_scopes", []) or []),
```

In the in-process `get_plugin_details` return (lines 205-237), add (e.g. after `dashboard_panel_enabled=...`):

```python
        is_external=False,
        requested_api_scopes=[],
```

In `list_plugins` (the `PluginInfo(...)` append, lines 68-83), add:

```python
                is_external=info.get("is_external", False),
```

In `backend/app/plugins/manager.py`, in `get_all_plugins`:
- external branch dict (lines 860-874): add `"is_external": True,`
- in-process branch dict (lines 883-897): add `"is_external": False,`
- error branch dict (lines 899-903): add `"is_external": False,`

- [ ] **Step 10: Run the detail/list tests to verify they pass**

Run: `python -m pytest tests/plugins/test_external_plugin_routes.py -v`
Expected: PASS (all, including the updated `uses_manifest` test).

- [ ] **Step 11: Commit**

```bash
git add backend/app/schemas/plugin.py backend/app/api/routes/plugins.py backend/app/plugins/manager.py backend/tests/plugins/test_external_plugin_routes.py
git commit -m "feat(plugin-sandbox): scope-picker backend -- grant_api_scopes threading + is_external/requested_api_scopes (Phase 5b)"
```

---

## Task 6: Success audit `plugin_sandbox_spawned` (5a follow-up)

**Files:**
- Modify: `backend/app/plugins/manager.py` (`_enable_external`, after line 553)
- Test: `backend/tests/plugins/test_manager_sandbox_failclosed.py` (the 5a fail-closed audit module — append the success-path test here)

**Interfaces:**
- Consumes: `get_audit_logger_db()` (already imported/used in `_enable_external`).
- Produces: on successful spawn, a security event `action="plugin_sandbox_spawned", user="system", resource=f"plugin:{name}", details={"granted_api_scopes": sorted(...)}, success=True`.

> **Existing-test impact (review finding):** `test_manager_sandbox_failclosed.py::test_enable_external_uses_selected_hook` patches the supervisor + `build_capability_router` but NOT `get_audit_logger_db`. After this change its success path will call the real `get_audit_logger_db().log_security_event(...)`. It will still pass (audit errors are swallowed and `_enable_external` returns `True` regardless), but to keep it clean and avoid a stray audit row, add `monkeypatch.setattr("app.plugins.manager.get_audit_logger_db", lambda: <stub>)` to that test as part of this task. Step 5 (full-module run) verifies it.

- [ ] **Step 1: Write the failing test**

In the 5a audit test module (mirror its existing fail-closed test), add a success-path test:

```python
def test_enable_external_emits_spawned_audit_on_success(tmp_path, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()
    discovered = DiscoveredPlugin(
        name="weather", path=pdir, source="external",
        manifest=types.SimpleNamespace(name="weather", display_name="Weather", ui=None),
    )

    class _Supervisor:
        async def start(self):
            return None

    monkeypatch.setattr(mgr, "_supervisor_factory", lambda *a, **k: _Supervisor())
    monkeypatch.setattr(
        "app.plugins.manager.build_capability_router", lambda name, scopes: object(), raising=False
    )

    events = []

    class _Audit:
        def log_security_event(self, **kwargs):
            events.append(kwargs)

    monkeypatch.setattr("app.plugins.manager.get_audit_logger_db", lambda: _Audit())

    ok = asyncio.run(mgr._enable_external("weather", discovered, ["storage", "core.notify"]))
    assert ok is True
    spawned = [e for e in events if e.get("action") == "plugin_sandbox_spawned"]
    assert len(spawned) == 1
    assert spawned[0]["success"] is True
    assert spawned[0]["user"] == "system"
    assert spawned[0]["resource"] == "plugin:weather"
    assert spawned[0]["details"]["granted_api_scopes"] == ["core.notify", "storage"]
```

> NOTE: `build_capability_router` is imported lazily inside `_enable_external` (`from app.plugins.sandbox.host_capabilities import build_capability_router`). The monkeypatch target above (`app.plugins.manager.build_capability_router`) will NOT intercept a function imported inside the method. Instead patch the source: `monkeypatch.setattr("app.plugins.sandbox.host_capabilities.build_capability_router", lambda name, scopes: object())`. Use that target.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/plugins/test_manager_sandbox_failclosed.py -k spawned_audit -v`
Expected: FAIL — no `plugin_sandbox_spawned` event emitted.

- [ ] **Step 3: Emit the success audit**

In `backend/app/plugins/manager.py`, in `_enable_external`, after `self._enabled.add(name)` (line 553) and before `logger.info(...)`/`return True`:

```python
        self._sandboxes[name] = supervisor
        self._enabled.add(name)
        get_audit_logger_db().log_security_event(
            action="plugin_sandbox_spawned",
            user="system",
            resource=f"plugin:{name}",
            details={"granted_api_scopes": sorted(granted_api_scopes)},
            success=True,
        )
        logger.info("Enabled external (sandboxed) plugin: %s", name)
        return True
```

- [ ] **Step 4: Run the audit test to verify it passes**

Run: `python -m pytest tests/plugins/test_manager_sandbox_failclosed.py -k spawned_audit -v`
Expected: PASS.

- [ ] **Step 5: Run the full audit module for regressions**

Run: `python -m pytest tests/plugins/test_manager_sandbox_failclosed.py -v`
Expected: PASS (fail-closed test still green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/manager.py backend/tests/plugins/test_manager_sandbox_failclosed.py
git commit -m "feat(plugin-sandbox): success audit plugin_sandbox_spawned on external enable (Phase 5a follow-up)"
```

---

## Task 7: Gated Linux spawn integration test (5a follow-up)

**Files:**
- Create: `backend/tests/plugins/sandbox/test_spawn_integration_linux.py`

**Interfaces:**
- Consumes: the real spawn path (`hardened_spawn` / supervisor) provisioned by install modules 03+10 (`baluhost-plugin` user + `/usr/local/sbin/baluhost-spawn-plugin-worker.sh`).
- Produces: a `skipif`-gated test that spawns a fixture plugin through the real wrapper and asserts the worker connects and answers `health`.

- [ ] **Step 1: Write the gated test**

Create `backend/tests/plugins/sandbox/test_spawn_integration_linux.py`:

```python
"""REAL spawn integration test for the hardened external-plugin sandbox.

Runs ONLY on a provisioned Linux box (or a dedicated CI lane):
  - Linux,
  - root (needed to drop to the baluhost-plugin user via the sudoers wrapper),
  - baluhost-plugin user exists,
  - /usr/local/sbin/baluhost-spawn-plugin-worker.sh installed & executable.

It is SKIPPED on Windows dev machines and any unprovisioned host. It must never
fail the Windows dev suite.
"""
import os
import shutil
import sys

import pytest

WRAPPER = "/usr/local/sbin/baluhost-spawn-plugin-worker.sh"


def _baluhost_plugin_user_exists() -> bool:
    try:
        import pwd  # noqa: PLC0415  (Linux-only)

        pwd.getpwnam("baluhost-plugin")
        return True
    except (ImportError, KeyError):
        return False


_provisioned = (
    sys.platform.startswith("linux")
    and hasattr(os, "geteuid")
    and os.geteuid() == 0
    and _baluhost_plugin_user_exists()
    and os.path.isfile(WRAPPER)
    and os.access(WRAPPER, os.X_OK)
)

pytestmark = pytest.mark.skipif(
    not _provisioned,
    reason="requires provisioned Linux box (root + baluhost-plugin user + spawn wrapper)",
)


@pytest.mark.asyncio
async def test_real_hardened_spawn_health_roundtrip(tmp_path):
    """Spawn a fixture plugin through the real wrapper; assert it answers health."""
    # Implementer: build a minimal fixture plugin dir (plugin.json + a worker entry
    # that uses the Phase 3 Plugin-SDK register(host) contract), construct the real
    # supervisor via the production factory (the same path _enable_external uses),
    # await supervisor.start(), then issue a health/dispatch RPC and assert a
    # successful response. Reuse the Phase 3 e2e fixture plugin if one already
    # exists under tests/plugins/sandbox/ rather than authoring a new one.
    pytest.skip("fixture wiring done at implementation time on the provisioned box")
```

> NOTE: this task's deliverable is the *gated harness* plus its documentation. The inner fixture wiring is finished on the provisioned Linux box (it cannot run on the Windows dev machine). The controlling guard + skip semantics are what this task verifies. Do not attempt to un-skip the body on Windows.

- [ ] **Step 2: Run it on the dev box to verify it SKIPS cleanly**

Run (from `backend/`): `python -m pytest tests/plugins/sandbox/test_spawn_integration_linux.py -v`
Expected: SKIPPED (1 skipped) — never failed, never errored on Windows.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/plugins/sandbox/test_spawn_integration_linux.py
git commit -m "test(plugin-sandbox): gated Linux spawn integration harness (Phase 5a follow-up)"
```

---

## Task 8: `plugins/CLAUDE.md` trust-tier note (5a follow-up)

**Files:**
- Modify: `backend/app/plugins/CLAUDE.md`

- [ ] **Step 1: Add the trust-tier section**

In `backend/app/plugins/CLAUDE.md`, after the `## Architecture` block (before `## Plugin Lifecycle`), insert:

```markdown
## Trust Tiers

Two plugin trust tiers with different isolation:

- **Bundled (in-process, fully trusted).** Plugins under `installed/`. Loaded as
  Python in the host process, old permission model (`required_permissions` granted
  in the enable modal). Full access to host APIs. Maintained in-repo.
- **External (sandboxed subprocess).** Marketplace plugins discovered as
  `source="external"`. Spawned via the hardened wrapper as the low-privilege
  `baluhost-plugin` user, in a network namespace, fail-closed if unprovisioned
  (Phase 5a). They reach the host only through default-deny **capability scopes**
  (`CAPABILITY_SCOPE`) over UDS-RPC — no host Python import, no DB/FS/shell access.
  The admin grants a subset of the plugin's requested `api_scopes` at enable time
  via the scope-picker (Phase 5b); the catalog of grantable scopes is
  `app/plugins/scope_catalog.py`.
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/plugins/CLAUDE.md
git commit -m "docs(plugin-sandbox): document bundled vs external trust tiers (Phase 5a follow-up)"
```

---

## Task 9: Frontend API client — catalog, scopes, flags

**Files:**
- Modify: `client/src/api/plugins.ts`
- Test: `client/src/__tests__/api/plugins.scopeCatalog.test.ts` (new — centralized mirror tree; see Global/File-Structure note)

**Interfaces:**
- Produces: `ScopeInfo {key: string; tier: 'frontend' | 'backend'; dangerous: boolean}`, `ScopeCatalogResponse {scopes: ScopeInfo[]}`, `getScopeCatalog(): Promise<ScopeCatalogResponse>`. `PluginToggleRequest.grant_api_scopes?: string[]`. `PluginDetail.requested_api_scopes?: string[]` + `.is_external?: boolean`. `PluginInfo.is_external?: boolean`. Task 10 consumes all of these.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/api/plugins.scopeCatalog.test.ts` (imports reach `src/` via `../../`):

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getScopeCatalog } from '../../api/plugins';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn() },
  memoizedApiRequest: vi.fn(),
}));

describe('getScopeCatalog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('maps the scope-catalog response', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        scopes: [
          { key: 'read:system-info', tier: 'frontend', dangerous: false },
          { key: 'storage', tier: 'backend', dangerous: false },
        ],
      },
    });
    const res = await getScopeCatalog();
    expect(apiClient.get).toHaveBeenCalledWith('/api/plugins/scope-catalog');
    expect(res.scopes).toHaveLength(2);
    expect(res.scopes[0].tier).toBe('frontend');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `client/`): `npx vitest run src/__tests__/api/plugins.scopeCatalog.test.ts`
Expected: FAIL — `getScopeCatalog` is not exported.

- [ ] **Step 3: Add the types and function**

In `client/src/api/plugins.ts`:

After `PluginNavItem` (line 13), add:

```ts
export interface ScopeInfo {
  key: string;
  tier: 'frontend' | 'backend';
  dangerous: boolean;
}

export interface ScopeCatalogResponse {
  scopes: ScopeInfo[];
}
```

In `PluginInfo` (after `error?: string;`, line 29), add:

```ts
  is_external?: boolean;
```

In `PluginDetail` (after `dashboard_panel_enabled: boolean;`, line 73), add:

```ts
  is_external?: boolean;
  requested_api_scopes?: string[];
```

In `PluginToggleRequest` (after `grant_permissions?: string[];`, line 85), add:

```ts
  grant_api_scopes?: string[];
```

After the `listPermissions` function (line 177), add:

```ts
/**
 * List the catalog of capability scopes grantable to external plugins
 */
export async function getScopeCatalog(): Promise<ScopeCatalogResponse> {
  const response = await apiClient.get<ScopeCatalogResponse>('/api/plugins/scope-catalog');
  return response.data;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/__tests__/api/plugins.scopeCatalog.test.ts`
Expected: PASS.

- [ ] **Step 5: Type-check**

Run (from `client/`): `npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/api/plugins.ts client/src/__tests__/api/plugins.scopeCatalog.test.ts
git commit -m "feat(plugin-sandbox): frontend scope-catalog client + is_external/requested_api_scopes types (Phase 5b)"
```

---

## Task 10: Scope-picker modal in PluginsPage

**Files:**
- Modify: `client/src/pages/PluginsPage.tsx`
- Test: `client/src/__tests__/pages/PluginsPage.scopePicker.test.tsx` (new — centralized mirror tree)

**Interfaces:**
- Consumes: `getScopeCatalog`, `ScopeInfo`, `PluginDetail.is_external`, `PluginDetail.requested_api_scopes`, `PluginToggleRequest.grant_api_scopes` (Task 9); `t('scopeDescriptions'|'scopeTiers'|'picker', ...)` (Task 11).
- Produces: an external-only scope-picker; bundled plugins keep the unchanged permissions modal.

**TEST CONVENTION (verified — do NOT deviate):** `useTranslation` is stubbed `t:(k)=>k`, so the DOM shows i18n **keys**, not English. Assert on keys (`'picker.title'`, `'picker.grant'`, `'modal.enableDesc'`, `'buttons.enable'`). The scope checkboxes are labelled by `scope.key` (the `scopeDescriptions` lookup returns `undefined` under the stub and the code falls back to `scope.key`), so `getByRole('checkbox', {name:/storage/i})` works as written. There is NO i18n provider/render helper in this repo.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/pages/PluginsPage.scopePicker.test.tsx`. Mock every module `PluginsPage` imports (the page pulls in heavy children + hooks). Paths are relative to the test file (`../../`):

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import PluginsPage from '../../pages/PluginsPage';
import { usePlugins } from '../../contexts/PluginContext';
import {
  getScopeCatalog, getPluginDetails, togglePlugin, listPermissions,
} from '../../api/plugins';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../contexts/PluginContext', () => ({ usePlugins: vi.fn() }));
vi.mock('../../api/plugins', () => ({
  getScopeCatalog: vi.fn(),
  getPluginDetails: vi.fn(),
  togglePlugin: vi.fn().mockResolvedValue({ name: 'x', is_enabled: true, message: 'ok' }),
  listPermissions: vi.fn().mockResolvedValue({ permissions: [] }),
  toggleDashboardPanel: vi.fn(),
  uninstallPlugin: vi.fn(),
}));
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn(), dialog: null }),
}));
vi.mock('../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: unknown, f: string) => f }));
vi.mock('../../lib/safeUrl', () => ({ safeExternalUrl: () => null }));
vi.mock('../../components/plugins/PluginDocumentation', () => ({ default: () => null }));
vi.mock('../../components/plugins/PluginSettingsSection', () => ({ PluginSettingsSection: () => null }));
vi.mock('../../components/plugins/MarketplaceTab', () => ({ default: () => null }));
vi.mock('../../components/LocalOnlyAction', () => ({ LocalOnlyAction: ({ children }: { children: React.ReactNode }) => children }));

const mockUsePlugins = usePlugins as unknown as ReturnType<typeof vi.fn>;
const CATALOG = {
  scopes: [
    { key: 'read:system-info', tier: 'frontend', dangerous: false },
    { key: 'read:storage', tier: 'frontend', dangerous: false },
    { key: 'read:power', tier: 'frontend', dangerous: false },
    { key: 'storage', tier: 'backend', dangerous: false },
    { key: 'core.system_metrics', tier: 'backend', dangerous: false },
    { key: 'core.notify', tier: 'backend', dangerous: false },
  ],
};

function makePlugin(over: Record<string, unknown> = {}) {
  return {
    name: 'weather', version: '2.0.0', display_name: 'Weather', description: 'd',
    author: 'a', category: 'general', required_permissions: [], dangerous_permissions: [],
    is_enabled: false, has_ui: true, has_routes: true, is_external: true, ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  (getScopeCatalog as ReturnType<typeof vi.fn>).mockResolvedValue(CATALOG);
});

describe('PluginsPage scope-picker (external) vs permissions modal (bundled)', () => {
  it('external: pre-checks requested scopes, sends the checked subset', async () => {
    mockUsePlugins.mockReturnValue({
      plugins: [makePlugin()], isLoading: false, error: null, refreshPlugins: vi.fn(),
    });
    (getPluginDetails as ReturnType<typeof vi.fn>).mockResolvedValue(
      makePlugin({ is_installed: false, requested_api_scopes: ['storage', 'read:power'], dashboard_panel_enabled: false }),
    );

    render(<PluginsPage />);
    // Wait until the catalog has loaded before opening the picker (avoids the
    // mount-effect race: selectedScopes is computed from scopeCatalog at click time).
    await waitFor(() => expect(getScopeCatalog).toHaveBeenCalled());

    fireEvent.click(await screen.findByText('buttons.enable'));

    expect(await screen.findByText('picker.title')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /storage/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /read:power/i })).toBeChecked();

    fireEvent.click(screen.getByRole('checkbox', { name: /read:power/i }));
    fireEvent.click(screen.getByText('picker.grant'));

    await waitFor(() =>
      expect(togglePlugin).toHaveBeenCalledWith('weather', {
        enabled: true,
        grant_api_scopes: ['storage'],
      }),
    );
  });

  it('bundled: shows the permissions modal, not the scope-picker', async () => {
    mockUsePlugins.mockReturnValue({
      plugins: [makePlugin({ is_external: false, required_permissions: ['file:read'] })],
      isLoading: false, error: null, refreshPlugins: vi.fn(),
    });
    (getPluginDetails as ReturnType<typeof vi.fn>).mockResolvedValue(
      makePlugin({ is_external: false, required_permissions: ['file:read'], dangerous_permissions: [], granted_permissions: [] }),
    );

    render(<PluginsPage />);
    fireEvent.click(await screen.findByText('buttons.enable'));

    expect(await screen.findByText('modal.enableDesc')).toBeInTheDocument();
    expect(screen.queryByText('picker.title')).not.toBeInTheDocument();
  });
});
```

> NOTE: confirm the exact import specifiers `PluginsPage.tsx` uses for its children/hooks against the file, and mirror them in the `vi.mock` calls (Vitest matches by resolved path). If a child import path differs, adjust the mock path. `React` is referenced in the `LocalOnlyAction` mock typing — add `import React from 'react';` if the test's TS config needs it.

- [ ] **Step 2: Run it to verify it fails**

Run (from `client/`): `npx vitest run src/__tests__/pages/PluginsPage.scopePicker.test.tsx`
Expected: FAIL — no scope-picker; `togglePlugin` not called with `grant_api_scopes`.

- [ ] **Step 3: Add state, catalog load, and the external enable branch**

In `client/src/pages/PluginsPage.tsx`:

Extend the imports from `../api/plugins` (lines 15-21) to include `getScopeCatalog` and the type:

```tsx
import {
  getPluginDetails,
  getScopeCatalog,
  listPermissions,
  togglePlugin,
  toggleDashboardPanel,
  uninstallPlugin,
} from '../api/plugins';
import type {
  PluginDetail,
  PluginInfo,
  PermissionInfo,
  ScopeInfo,
} from '../api/plugins';
```

Add state (after line 49, `activeTab`):

```tsx
  const [scopeCatalog, setScopeCatalog] = useState<ScopeInfo[]>([]);
  const [showScopeModal, setShowScopeModal] = useState(false);
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);
```

Load the catalog on mount (alongside the permissions effect, after line 56):

```tsx
  useEffect(() => {
    getScopeCatalog()
      .then((res) => setScopeCatalog(res.scopes))
      .catch(console.error);
  }, []);
```

Make `loadPluginDetails` return the loaded detail (so the enable branch can read `is_external`). Replace its body (lines 58-69):

```tsx
  const loadPluginDetails = async (name: string): Promise<PluginDetail | null> => {
    setDetailsLoading(true);
    setActionError(null);
    try {
      const details = await getPluginDetails(name);
      setSelectedPlugin(details);
      return details;
    } catch {
      setActionError(t('errors.loadDetailsFailed'));
      return null;
    } finally {
      setDetailsLoading(false);
    }
  };
```

Replace the enable branch of `handleTogglePlugin` (the `else` at lines 87-91) with:

```tsx
    } else {
      // Enable: load details to learn tier + requested scopes
      const details = await loadPluginDetails(plugin.name);
      if (!details) return;
      if (details.is_external) {
        setSelectedScopes(
          (details.requested_api_scopes ?? []).filter((s) =>
            scopeCatalog.some((c) => c.key === s),
          ),
        );
        setShowScopeModal(true);
      } else {
        setSelectedPermissions(plugin.required_permissions);
        setShowPermissionModal(true);
      }
    }
```

Add the scope-enable handler (after `handleEnableWithPermissions`, line 113):

```tsx
  const handleEnableWithScopes = async () => {
    if (!selectedPlugin) return;
    setActionLoading(true);
    setActionError(null);
    setShowScopeModal(false);
    try {
      await togglePlugin(selectedPlugin.name, {
        enabled: true,
        grant_api_scopes: selectedScopes,
      });
      await refreshPlugins();
      await loadPluginDetails(selectedPlugin.name);
    } catch {
      setActionError(t('errors.enableFailed'));
    } finally {
      setActionLoading(false);
    }
  };
```

- [ ] **Step 4: Add the scope-picker modal JSX**

In `client/src/pages/PluginsPage.tsx`, immediately before the closing `{dialog}` (line 551), add the modal. It iterates the plugin's requested scopes, looks each up in the catalog for `tier`/`dangerous`, groups by tier, pre-checks requested (already in `selectedScopes`), and sends the checked subset:

```tsx
      {/* Scope Grant Modal (external plugins only) */}
      {showScopeModal && selectedPlugin && (() => {
        const descs = t('scopeDescriptions', { returnObjects: true }) as Record<
          string,
          { label: string; description: string }
        >;
        const requested = (selectedPlugin.requested_api_scopes ?? []).filter((s) =>
          scopeCatalog.some((c) => c.key === s),
        );
        const byTier = (tier: 'frontend' | 'backend') =>
          requested
            .map((key) => scopeCatalog.find((c) => c.key === key)!)
            .filter((c) => c.tier === tier);
        const renderScope = (scope: ScopeInfo) => {
          const isChecked = selectedScopes.includes(scope.key);
          const meta = descs?.[scope.key];
          return (
            <label
              key={scope.key}
              className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition ${
                scope.dangerous
                  ? 'bg-amber-500/10 border border-amber-500/20'
                  : 'bg-slate-800/50 border border-slate-700'
              }`}
            >
              <input
                type="checkbox"
                checked={isChecked}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedScopes([...selectedScopes, scope.key]);
                  } else {
                    setSelectedScopes(selectedScopes.filter((s) => s !== scope.key));
                  }
                }}
                className="mt-1 rounded border-slate-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-900"
              />
              <div>
                <div className={`text-sm font-medium ${scope.dangerous ? 'text-amber-400' : 'text-white'}`}>
                  {meta?.label ?? scope.key}
                  {scope.dangerous && (
                    <span className="ml-2 text-xs text-amber-500">({t('picker.dangerous')})</span>
                  )}
                </div>
                {meta?.description && (
                  <p className="text-xs text-slate-500 mt-0.5">{meta.description}</p>
                )}
              </div>
            </label>
          );
        };
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
              <h3 className="text-lg font-medium text-white mb-2">
                {t('picker.title', { name: selectedPlugin.display_name })}
              </h3>
              <p className="text-sm text-slate-400 mb-4">{t('picker.desc')}</p>
              {requested.length === 0 ? (
                <p className="text-sm text-slate-500 mb-6">{t('picker.noScopes')}</p>
              ) : (
                <div className="space-y-4 mb-6 max-h-72 overflow-y-auto">
                  {(['frontend', 'backend'] as const).map((tier) =>
                    byTier(tier).length === 0 ? null : (
                      <div key={tier} className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          {t(`scopeTiers.${tier}`)}
                        </div>
                        {byTier(tier).map(renderScope)}
                      </div>
                    ),
                  )}
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={() => setShowScopeModal(false)}
                  className="flex-1 px-4 py-2 text-sm font-medium rounded-lg border border-slate-700 text-slate-300 hover:border-slate-600 transition-all touch-manipulation active:scale-95"
                >
                  {t('buttons.cancel')}
                </button>
                <button
                  onClick={handleEnableWithScopes}
                  className="flex-1 px-4 py-2 text-sm font-medium rounded-lg bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all touch-manipulation active:scale-95"
                >
                  {t('picker.grant')}
                </button>
              </div>
            </div>
          </div>
        );
      })()}
```

> NOTE: `t(\`scopeTiers.${tier}\`)` is safe — tier keys (`frontend`/`backend`) contain no `:`/`.`. The separator pitfall only affects the *scope keys*, which is why `scopeDescriptions` is read via `returnObjects` and indexed in JS.

- [ ] **Step 5: Run the picker tests to verify they pass**

Run: `npx vitest run src/__tests__/pages/PluginsPage.scopePicker.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 6: Type-check + lint**

Run (from `client/`): `npx tsc --noEmit`
Expected: no new errors. (`ScopeInfo` is imported as a type; `descs` typed inline.)

- [ ] **Step 7: Commit**

```bash
git add client/src/pages/PluginsPage.tsx client/src/__tests__/pages/PluginsPage.scopePicker.test.tsx
git commit -m "feat(plugin-sandbox): external-plugin scope-picker modal in PluginsPage (Phase 5b)"
```

---

## Task 11: i18n — scope descriptions, tiers, picker strings

**Files:**
- Modify: `client/src/i18n/locales/en/plugins.json`
- Modify: `client/src/i18n/locales/de/plugins.json`

**Interfaces:**
- Produces: `scopeDescriptions.<key>.{label,description}` for all six catalog keys; `scopeTiers.{frontend,backend}`; `picker.{title,desc,dangerous,noScopes,grant}` — consumed by Task 10.

- [ ] **Step 1: Add the English keys**

In `client/src/i18n/locales/en/plugins.json`, add three top-level blocks (e.g. after `permissionDescriptions`, before the closing `}`):

```json
  "scopeTiers": {
    "frontend": "Frontend (UI data)",
    "backend": "Backend (capabilities)"
  },
  "picker": {
    "title": "Grant capability scopes — {{name}}",
    "desc": "This external plugin runs sandboxed. Choose which capability scopes to grant. Requested scopes are pre-selected; you can grant fewer.",
    "dangerous": "Dangerous",
    "noScopes": "This plugin requests no capability scopes.",
    "grant": "Grant & Enable"
  },
  "scopeDescriptions": {
    "read:system-info": { "label": "System Info", "description": "Read system metrics and hardware information" },
    "read:storage": { "label": "Storage Info", "description": "Read storage usage and disk information" },
    "read:power": { "label": "Power Info", "description": "Read power and energy data" },
    "storage": { "label": "Plugin Storage", "description": "Read and write the plugin's own key-value storage" },
    "core.system_metrics": { "label": "System Metrics", "description": "Query core system metrics through the capability bridge" },
    "core.notify": { "label": "Notifications", "description": "Send notifications through the core" }
  }
```

(Remember the comma after the preceding block.)

- [ ] **Step 2: Add the German keys**

In `client/src/i18n/locales/de/plugins.json`, add the mirrored blocks:

```json
  "scopeTiers": {
    "frontend": "Frontend (UI-Daten)",
    "backend": "Backend (Capabilities)"
  },
  "picker": {
    "title": "Capability-Scopes gewähren — {{name}}",
    "desc": "Dieses externe Plugin läuft in der Sandbox. Wähle, welche Capability-Scopes gewährt werden. Angefragte Scopes sind vorausgewählt; du kannst weniger gewähren.",
    "dangerous": "Gefährlich",
    "noScopes": "Dieses Plugin fordert keine Capability-Scopes an.",
    "grant": "Gewähren & Aktivieren"
  },
  "scopeDescriptions": {
    "read:system-info": { "label": "Systeminfo", "description": "Systemmetriken und Hardware-Informationen lesen" },
    "read:storage": { "label": "Speicherinfo", "description": "Speichernutzung und Datenträgerdaten lesen" },
    "read:power": { "label": "Energieinfo", "description": "Energie- und Leistungsdaten lesen" },
    "storage": { "label": "Plugin-Speicher", "description": "Eigenen Key-Value-Speicher des Plugins lesen und schreiben" },
    "core.system_metrics": { "label": "Systemmetriken", "description": "Kern-Systemmetriken über die Capability-Bridge abfragen" },
    "core.notify": { "label": "Benachrichtigungen", "description": "Benachrichtigungen über den Kern senden" }
  }
```

- [ ] **Step 3: Validate both JSON files parse**

Run (from `client/`): `node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/plugins.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/plugins.json','utf8')); console.log('ok')"`
Expected: `ok` (no JSON syntax errors — trailing-comma / missing-comma check).

- [ ] **Step 4: Re-run the picker test (still green)**

Run: `npx vitest run src/__tests__/pages/PluginsPage.scopePicker.test.tsx`
Expected: PASS, unchanged. (The picker test asserts on i18n KEYS, not translated text — per the repo's `t:(k)=>k` stub — so adding the real locale strings does not affect it. The new keys are exercised at runtime, not in this unit test.)

- [ ] **Step 5: Commit**

```bash
git add client/src/i18n/locales/en/plugins.json client/src/i18n/locales/de/plugins.json
git commit -m "i18n(plugin-sandbox): scope picker labels/descriptions/tiers (de+en) (Phase 5b)"
```

---

## Task 12: Gap-C frontend nav rendering — vitest

**Files:**
- Test: `client/src/__tests__/contexts/PluginContext.externalNav.test.tsx` (new — centralized mirror tree)

**Interfaces:**
- Consumes: `PluginContext` already flattens `enabledPlugins[].nav_items` into `pluginNavItems` (no code change expected). This task verifies Gap C end-to-end on the client and is the place to catch any special-casing the external `bundle_path` needs.

- [ ] **Step 1: Write the test**

Create `client/src/__tests__/contexts/PluginContext.externalNav.test.tsx` (imports reach `src/` via `../../`). Mock `../../api/plugins`'s `getUIManifest` to return one external plugin with `nav_items`, and `listPlugins` to return it. Render a consumer of `usePlugins()` and assert `pluginNavItems` contains the external nav entry with the plugin-prefixed path:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PluginProvider, usePlugins } from '../../contexts/PluginContext';

vi.mock('../../api/plugins', () => ({
  listPlugins: vi.fn().mockResolvedValue({ plugins: [], total: 0 }),
  getUIManifest: vi.fn().mockResolvedValue({
    plugins: [
      {
        name: 'weather',
        display_name: 'Weather',
        nav_items: [{ path: 'weather', label: 'Weather', icon: 'cloud', admin_only: false, order: 50 }],
        bundle_path: 'bundle.js',
        dashboard_widgets: [],
        granted_api_scopes: ['read:system-info'],
      },
    ],
  }),
}));

// AuthContext provides a token so PluginContext loads (mock per repo convention).
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ token: 't' }) }));
vi.mock('../../lib/features', () => ({ isPi: false }));

function Probe() {
  const { pluginNavItems } = usePlugins();
  return <div data-testid="nav">{pluginNavItems.map((n) => n.path).join(',')}</div>;
}

describe('PluginContext external nav (Gap C)', () => {
  it('renders external plugin nav item from /ui/manifest', async () => {
    render(
      <PluginProvider>
        <Probe />
      </PluginProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('nav')).toHaveTextContent('weather/weather'));
  });
});
```

> NOTE: align the `useAuth`/`isPi` mocks with how other PluginContext tests stub them. The path prefix `weather/weather` is `${plugin.name}/${item.path}` from `PluginContext` line 79.

- [ ] **Step 2: Run it to verify it passes (no source change needed)**

Run (from `client/`): `npx vitest run src/__tests__/contexts/PluginContext.externalNav.test.tsx`
Expected: PASS — confirms Gap C surfaces nav with no PluginContext change.

> If it FAILS because the external `bundle_path` / nav needs special handling that the existing context doesn't do, capture the gap and fix it minimally in `PluginContext.tsx` (the spec anticipated "verify; no special-casing expected, but confirm").

- [ ] **Step 3: Run the full frontend vitest suite for regressions**

Run (from `client/`): `npx vitest run`
Expected: PASS (whole suite green).

- [ ] **Step 4: Commit**

```bash
git add client/src/__tests__/contexts/PluginContext.externalNav.test.tsx
git commit -m "test(plugin-sandbox): Gap C end-to-end -- external nav renders from /ui/manifest (Phase 5b)"
```

---

## Final Verification

- [ ] **Backend:** from `backend/`, run the touched modules:
  `python -m pytest tests/plugins/test_scope_catalog.py tests/plugins/test_manifest.py tests/plugins/test_external_ui_manifest.py tests/plugins/test_external_plugin_routes.py tests/plugins/sandbox/test_spawn_integration_linux.py -v`
  Expected: all pass (Linux integration test SKIPPED on Windows). Then a broader `python -m pytest tests/plugins -v` for plugin-suite regressions. (The full backend suite may hang on Windows — defer to CI per project convention.)
- [ ] **Frontend:** from `client/`, `npx vitest run` then `npx tsc --noEmit` and `npm run build`.
- [ ] Then invoke **superpowers:finishing-a-development-branch** to open the cohesive 5b PR (stacked on 5a until #286 merges).

---

## Notes for the executor

- **Branch:** work continues on `feat/plugin-backend-isolation-phase5b` (stacked on 5a tip). After #286 squash-merges, re-cut from `main` + cherry-pick per the documented playbook.
- **One cohesive PR** for Tasks 1–12. The `PluginDocumentation.tsx` two-tier rewrite is a SEPARATE sibling PR — do not touch it here.
- **vectordb-search** is the mandated codebase search (Grep/Glob are hook-blocked). Use `mcp__vectordb-search__*` with `projectPath` `D:/Programme (x86)/Baluhost` to locate the exact test-fixture conventions referenced in the NOTE blocks.
- **No `&&` in PowerShell.** Run the listed commands from `backend/` or `client/` as written (Bash tool) or chain with `;` in PowerShell.
- **No migration, no deploy action** beyond the 5a provisioning already tracked (install modules 03+10 on BaluNode when the first external plugin arrives).
```