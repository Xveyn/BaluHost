# Plugin Backend Isolation — Phase 5b: Scope Catalog, Scope-Picker & UI Surfacing

**Status:** Spec
**Date:** 2026-06-28
**Track:** Plugin-Sandboxing Track B (Backend Python Isolation), Phase 5b
**Predecessors:** Phase 1–4 merged (#282–#285); Phase 5a (hardened spawn) → PR #286 (open). This branch is stacked on 5a until #286 merges, then re-cut from main + cherry-pick.
**Sibling (separate PR):** the `PluginDocumentation.tsx` two-tier rewrite — own spec/plan, sequenced **after** this PR (it consumes this PR's scope-catalog endpoint + `scopeDescriptions` i18n keys).

## Problem

Track B isolates external plugins in a hardened subprocess, but the UI and authoring contract have not caught up:

1. **No scope-granting UI.** `granted_api_scopes` is persisted by `plugin_service.enable_plugin(api_scopes=…)`, but nothing in the UI sets it — `PluginToggleRequest` only carries the old `grant_permissions`. An admin enabling an external plugin cannot choose which capability scopes to grant.
2. **The scope vocabulary is undocumented and overloaded.** `granted_api_scopes` is a single column read by two enforcement layers with different vocabularies — the Track A frontend SDK (`read:system-info`, `read:storage`, `read:power` — see `client/src/lib/plugin-sandbox/scopeCatalog.ts`) and the Track B backend `CapabilityRouter` (`storage`, `core.system_metrics`, `core.notify` — see `CAPABILITY_SCOPE`). There is no human-facing catalog of what is grantable.
3. **External plugins are invisible in the UI (Gap C).** `PluginManager.get_ui_manifest()` iterates `self._enabled` and reads `self._plugins.get(name)` — external sandboxed plugins are **not** in `self._plugins`, so their nav items, bundle, and dashboard widgets never reach the SPA. The `/ui/manifest` enrichment loop compounds this by resolving manifests against `plugins_dir[0]` (the bundled dir), the wrong path for external plugins. And the static `PluginManifestUI` only has `bundle`/`styles` — it cannot declare nav items, so even a fixed get_ui_manifest has nothing to surface.

Plus three robustness/quality follow-ups carried from 5a: a success-side audit event, a real (un-mocked) Linux integration test of the spawn path, and a CLAUDE.md note on the two trust tiers.

Greenfield: 0 external plugins are deployed. This makes the UI and authoring contract correct **before** the ecosystem grows.

## Goals

- A single **server-defined scope catalog** (SSOT) of the scopes grantable to external plugins, exposed via an endpoint; the picker (and later the doc) consume only it.
- An **install/enable-time scope-picker** for external plugins: the admin grants a subset of the scopes the plugin's manifest requests; the choice persists to `granted_api_scopes`.
- **Gap C closed:** external sandboxed plugins surface their nav items / bundle / dashboard widgets in the SPA, declared **statically in `plugin.json`** (no host Python, no running worker required).
- Fold in the three 5a follow-ups: success audit `plugin_sandbox_spawned`, a Linux/root-gated spawn integration test, and the `plugins/CLAUDE.md` trust-tier note.

## Non-Goals

- **The `PluginDocumentation.tsx` two-tier rewrite** — separate PR (consumes this PR's catalog endpoint + `scopeDescriptions` keys).
- **New backend capabilities / new frontend api scopes.** The catalog enumerates exactly the six scopes the two enforcement layers already implement. No new scope is added.
- **Changing the Track A frontend enforcement** (`scopeCatalog.ts` regex patterns stay as-is — they are the enforcement detail; the catalog is the human/granting layer).
- **A second DB column.** `granted_api_scopes` stays the single union column; each enforcement layer filters to its own vocabulary (status quo).
- **Bundled-plugin changes.** Bundled plugins stay trusted/in-process with the old permission model; the scope-picker is external-only.
- Mount/seccomp/cgroups hardening (5a Non-Goal), signing (Track C).

## Architecture

### Scope model

`granted_api_scopes` is a union bag consumed by two layers:

| Tier | Scope keys | Enforced by | Gates |
|---|---|---|---|
| `frontend` | `read:system-info`, `read:storage`, `read:power` | `client/src/lib/plugin-sandbox/scopeCatalog.ts` (regex) | iframe SDK `api.get()` → Core endpoints |
| `backend` | `storage`, `core.system_metrics`, `core.notify` | `CapabilityRouter` (`CAPABILITY_SCOPE`) | worker `cap_call` |

A plugin's `plugin.json` `api_scopes` may request any subset of these six. The admin grants a subset at enable time. Strings not in a layer's vocabulary are ignored by that layer (status quo, preserved).

The **catalog** is server-defined structural data (`key`, `tier`, `dangerous`) — human labels/descriptions live in frontend i18n (`scopeDescriptions.<key>`), exactly like the existing `permissionDescriptions` pattern, so the text stays translatable. Drift is prevented by tests: backend-tier keys must equal `set(CAPABILITY_SCOPE.values())`; the frontend `scopeCatalog.ts` keys must be a subset of the catalog's frontend-tier keys.

### Gap C — static nav declaration

`PluginManifestUI` gains `nav_items` and optional `dashboard_widgets`. `get_ui_manifest()` keeps the existing path for in-process plugins (`self._plugins`) and adds a branch for enabled external plugins (in `self._sandboxes`, not in `self._plugins`): it builds the manifest entry from the plugin's `DiscoveredPlugin.manifest.ui`. The `/ui/manifest` enrichment loop resolves each plugin's manifest from its **actual discovered directory**, not `plugins_dir[0]`.

## Components & Files

### Backend

**`backend/app/plugins/scope_catalog.py` (NEW)**

```python
from dataclasses import dataclass
from typing import Literal
from app.plugins.sandbox.capabilities import CAPABILITY_SCOPE

@dataclass(frozen=True)
class ScopeInfo:
    key: str
    tier: Literal["frontend", "backend"]
    dangerous: bool

# Frontend-tier keys mirror client/src/lib/plugin-sandbox/scopeCatalog.ts.
_FRONTEND_SCOPES = ("read:system-info", "read:storage", "read:power")

SCOPE_CATALOG: tuple[ScopeInfo, ...] = (
    *(ScopeInfo(k, "frontend", False) for k in _FRONTEND_SCOPES),
    *(ScopeInfo(v, "backend", False) for v in sorted(set(CAPABILITY_SCOPE.values()))),
)
CATALOG_KEYS = frozenset(s.key for s in SCOPE_CATALOG)
```

- The backend-tier entries are **derived** from `CAPABILITY_SCOPE.values()` so they cannot drift from what the router actually enforces.

**`backend/app/api/routes/plugins.py`** — new endpoint:

```python
@router.get("/scope-catalog", response_model=ScopeCatalogResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_scope_catalog(request: Request, response: Response,
                            current_user: User = Depends(get_current_user)) -> ScopeCatalogResponse:
    """Grantable external-plugin scopes (structural; labels are i18n on the client)."""
    return ScopeCatalogResponse(scopes=[ScopeInfoSchema(key=s.key, tier=s.tier, dangerous=s.dangerous)
                                        for s in SCOPE_CATALOG])
```

Schemas `ScopeInfoSchema {key, tier, dangerous}` + `ScopeCatalogResponse {scopes: list}` in `backend/app/schemas/plugin.py`.

**`backend/app/plugins/manifest.py`** — extend `PluginManifestUI`:

```python
class ManifestNavItem(BaseModel):
    path: str
    label: str
    icon: Optional[str] = None
    admin_only: bool = False
    order: int = 100

class PluginManifestUI(BaseModel):
    bundle: str = Field(..., description="Path to the JS bundle, relative to plugin dir")
    styles: Optional[str] = Field(default=None)
    nav_items: List[ManifestNavItem] = Field(default_factory=list)
    dashboard_widgets: List[str] = Field(default_factory=list)
```

Backward-compatible: existing manifests without `nav_items` parse with empty defaults.

**`backend/app/plugins/manager.py`** — `get_ui_manifest()`:

```python
for name in self._enabled:
    plugin = self._plugins.get(name)
    if plugin:
        ...  # existing in-process path, unchanged
        continue
    # External sandboxed plugin: surface UI from its static manifest.
    discovered = self.get_discovered(name)
    if discovered and discovered.source == "external" and discovered.manifest and discovered.manifest.ui:
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
```

**`backend/app/api/routes/plugins.py`** — `/ui/manifest` enrichment: resolve each plugin's manifest from its discovered dir, not `plugins_dir[0]`:

```python
for item in result.plugins:
    record = plugin_service.get_installed_plugin(db, item.name)
    item.granted_api_scopes = (record.granted_api_scopes or []) if record else []
    discovered = plugin_manager.get_discovered(item.name)
    item.min_runtime_abi = (discovered.manifest.min_runtime_abi
                            if discovered and discovered.manifest else None)
```

**`backend/app/schemas/plugin.py`** — `PluginToggleRequest`:

```python
class PluginToggleRequest(BaseModel):
    enabled: bool
    grant_permissions: List[str] = Field(default_factory=list)  # bundled (old model)
    grant_api_scopes: List[str] = Field(default_factory=list,
        description="Capability scopes to grant an external plugin (filtered to the catalog)")
```

**`backend/app/api/routes/plugins.py`** — `_toggle_external`: when enabling, filter `body.grant_api_scopes` to `CATALOG_KEYS`, pass to `plugin_service.enable_plugin(api_scopes=…)` and `plugin_manager.enable_plugin(granted_api_scopes=…)`.

**`backend/app/plugins/manager.py`** — `_enable_external` success audit (5a follow-up): after `supervisor.start()` succeeds and the sandbox is registered:

```python
get_audit_logger_db().log_security_event(
    action="plugin_sandbox_spawned", user="system", resource=f"plugin:{name}",
    details={"granted_api_scopes": sorted(granted_api_scopes)}, success=True,
)
```

**`backend/tests/plugins/sandbox/test_spawn_integration_linux.py` (NEW, 5a follow-up)** — `pytest.mark.skipif` unless Linux + root + provisioned (`baluhost-plugin` exists, wrapper executable). Spawns a fixture plugin through the real wrapper and asserts the worker connects + answers `health`. Documents that it runs only on a provisioned Linux box / dedicated CI lane, never Windows.

**`backend/app/plugins/CLAUDE.md` (5a follow-up)** — a short "Trust tiers" note: bundled = in-process, fully trusted, old permission model; external = sandboxed subprocess (low-priv user, netns, default-deny capability scopes), no host/DB/FS/shell.

### Frontend

**`client/src/api/plugins.ts`** — `ScopeInfo {key; tier; dangerous}`, `getScopeCatalog()`; `grant_api_scopes?: string[]` on the toggle payload; `requested_api_scopes` on the plugin-details type (from `manifest.api_scopes`, surfaced by `get_plugin_details` — add it to `PluginDetailResponse` if absent).

**Enable modal (external plugins)** — extend the existing enable flow (`PluginsPage.tsx` / its enable modal component): when the plugin is external, fetch the catalog + the plugin's `requested_api_scopes`, render a checklist grouped by tier (`frontend` / `backend`), **requested scopes pre-checked**, danger-flagged scopes visibly marked. On confirm, send `grant_api_scopes` (the checked subset) in the toggle. Bundled plugins keep the existing permissions modal unchanged.

**External nav** — `PluginContext` already consumes `/ui/manifest` `nav_items`; once Gap C fills external entries they render in the sidebar automatically. Verify during implementation that the sidebar and `PluginPage` resolve the external plugin's `bundle_path` via the existing `/api/plugins/{name}/ui/...` asset route (Track A iframe host) — no special-casing expected, but confirm.

**i18n (`client/src/i18n/locales/{de,en}/plugins.json`)** — add `scopeDescriptions.<key>` (label + description per scope, both languages), `scopeTiers.{frontend,backend}` (short tier labels for the picker grouping), and picker strings (`picker.title`, `picker.grantSubset`, `picker.dangerous`, etc.). The larger two-tier prose stays for the doc PR.

## Data Flow

```
Admin enables an EXTERNAL plugin
  → modal fetches GET /api/plugins/scope-catalog  (6 ScopeInfo)
                + GET /api/plugins/{name}          (requested_api_scopes from manifest)
  → checklist (requested pre-checked, grouped by tier, danger-flagged)
  → POST /api/plugins/{name}/toggle { enabled: true, grant_api_scopes: [<checked>] }
      → _toggle_external: filter to CATALOG_KEYS
        → plugin_service.enable_plugin(api_scopes=…)        # persist granted_api_scopes
        → plugin_manager.enable_plugin(granted_api_scopes=…) # spawn (5a hardened) + build_capability_router(name, scopes)
        → audit plugin_sandbox_spawned (success)

Sidebar / PluginPage render
  → GET /api/plugins/ui/manifest
      → get_ui_manifest(): in-process plugins (self._plugins) + external (discovered.manifest.ui.nav_items)
      → each item enriched with granted_api_scopes (DB) + min_runtime_abi (discovered manifest)
  → external nav_items appear; iframe host loads bundle via /api/plugins/{name}/ui/<bundle>
```

## Error Handling

| Condition | Behavior |
|---|---|
| `grant_api_scopes` contains unknown/foreign string | Filtered out against `CATALOG_KEYS` before persisting (defense in depth; the layers ignore unknowns anyway). |
| External plugin manifest has no `ui` | Not surfaced in `get_ui_manifest` (no nav) — same as an in-process plugin returning `None`. |
| External plugin disabled / not spawned | Absent from `self._enabled` → absent from `/ui/manifest`. |
| Catalog endpoint while not admin | `get_current_user` is sufficient (read-only structural data, no secrets); matches the existing `/permissions` endpoint's auth. |
| Linux integration test on Windows / unprovisioned | Skipped (marker), never fails the Windows dev suite. |

## Testing

**Backend**
- `scope_catalog`: endpoint returns the six entries; backend-tier keys `== set(CAPABILITY_SCOPE.values())` (drift guard); each entry has `key/tier/dangerous`.
- `manifest`: `nav_items`/`dashboard_widgets` parse; a manifest without them defaults to empty (backward-compat).
- `get_ui_manifest` (Gap C): an enabled external plugin (mock discovered+manifest+sandbox, not in `self._plugins`) appears with its manifest `nav_items`/`bundle_path`; in-process plugins unchanged.
- `/ui/manifest`: external plugin item carries `granted_api_scopes` (DB) + `min_runtime_abi` (its own manifest); enrichment no longer mis-resolves against `plugins_dir[0]`.
- `toggle`: `grant_api_scopes` filtered to catalog and persisted; a foreign string is dropped.
- `_enable_external`: `plugin_sandbox_spawned` audit emitted on success (extend the 5a fail-closed test module).
- Linux integration test: gated; documented.

**Frontend (vitest)**
- `getScopeCatalog()` typed mapping.
- Enable modal for an external plugin: pre-checks requested scopes, groups by tier, includes danger flag, sends the checked subset as `grant_api_scopes`; a bundled plugin still shows the permissions modal (no scope picker).
- Sidebar renders an external plugin's nav item from a mocked `/ui/manifest` (Gap C end-to-end on the client).

## Decomposition & Rollout

- **One cohesive 5b PR** for all of the above. Subagent-driven sequences backend tasks (catalog, manifest, Gap C, toggle, audit) before the frontend tasks that consume them.
- **Separate doc PR** (sibling): `PluginDocumentation.tsx` two-tier rewrite + `tiers.*` prose, after this PR.
- Branch stacked on 5a (#286) until it merges; then re-cut from main + cherry-pick (the documented squash-merge playbook).
- No migration (the `granted_api_scopes` column already exists). No deploy/prod action beyond the 5a provisioning already tracked.

## Self-Review

- **Spec coverage:** scope catalog (model + endpoint + drift guard); scope-picker (toggle field + modal + persist); Gap C (manifest nav schema + get_ui_manifest external branch + enrichment fix); 3 follow-ups (success audit + Linux test + CLAUDE.md). Each has a component + a test (or, for the doc note, a doc deliverable).
- **Consistency:** `grant_api_scopes` (request) → `granted_api_scopes` (column/router) naming kept distinct and deliberate; `ScopeInfo{key,tier,dangerous}` shape identical backend↔frontend; nav item shape (`path/label/icon/admin_only/order`) mirrors the in-code `PluginNavItem`.
- **Scope:** UI + authoring contract only; the doc rewrite is explicitly carved out. Single testable deliverable.
- **Ambiguity:** catalog labels are i18n (not server text) — stated once and consistently; backend-tier keys are derived (not hand-listed) to prevent drift.
