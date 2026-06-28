# Plugin Documentation — Two-Tier Rewrite (Operator-Focused)

**Status:** Spec
**Date:** 2026-06-28
**Track:** Plugin-Sandboxing Track B — sibling doc PR to Phase 5b (#287, merged)
**Scope:** Frontend only — `client/src/components/plugins/PluginDocumentation.tsx` + its `plugins` i18n strings + a vitest. No backend changes.

## Problem

The plugin **Documentation** tab (`PluginDocumentation.tsx`, rendered in `PluginsPage`) still describes the *old* single-tier model exclusively:

- A dangerous-permissions banner about `file:write` / `system:execute` / `db:write` / `user:write`.
- An installation section that says "drop your folder into `backend/app/plugins/installed/` and restart" — the bundled/dev path, **wrong for external/marketplace plugins**.
- A permission-category reference (file / system / network / db / user / device / events) and a 26-entry hooks grid — the in-process authoring model.

Phase 5b (#287) shipped the real model: **two trust tiers** (bundled in-process/trusted vs external sandboxed) and a **capability-scope** grant flow for external plugins, backed by `GET /api/plugins/scope-catalog` and `scopeDescriptions`/`scopeTiers` i18n keys. The doc has not caught up, so it is now misleading.

## Goals

- Rewrite the doc tab **tier-first**: lead with the two trust tiers, then the external capability-scope model, then a condensed bundled reference.
- Consume the **live scope catalog** (no drift): render the 6 grantable scopes grouped by tier with their i18n labels/descriptions and danger flags — the same data the enable-time scope-picker uses.
- **Operator/admin focus** (the page is admin-only): depth on "bundled vs external, what scopes mean, what's safe to grant"; author reference (hooks, `plugin.json` layout, full permission list) trimmed to a concise summary + GitHub link.
- Fix the inaccurate installation text (Marketplace flow + scope-picker, not "drop folder in `installed/`").

## Non-Goals

- No backend changes (the catalog endpoint + i18n keys already exist from #287).
- No new scopes, no changes to the scope-picker, the catalog, or `PluginsPage`'s data fetching beyond passing the existing `scopeCatalog` state down as a prop.
- Not a full developer handbook — author detail stays condensed (operator focus, per design decision).
- No change to the Marketplace tab or the enable flow themselves.

## Architecture

### Data flow

`PluginsPage` already fetches and holds both `allPermissions` (via `listPermissions()`) and `scopeCatalog` (via `getScopeCatalog()`, added in #287 Task 10). It currently renders:

```tsx
{activeTab === 'documentation' && (
  <PluginDocumentation permissions={allPermissions} />
)}
```

Add the catalog as a second prop (mirrors `permissions`):

```tsx
{activeTab === 'documentation' && (
  <PluginDocumentation permissions={allPermissions} scopeCatalog={scopeCatalog} />
)}
```

No new fetch. The doc is always in sync with the backend catalog.

### Component props

```tsx
import type { PermissionInfo, ScopeInfo } from '../../api/plugins';

interface PluginDocumentationProps {
  permissions: PermissionInfo[];
  scopeCatalog: ScopeInfo[];   // { key, tier: 'frontend'|'backend', dangerous }
}
```

`ScopeInfo` already exists in `client/src/api/plugins.ts` (#287).

### i18next separator-safe scope lookup (critical)

Scope keys contain `:` (i18next nsSeparator) and `.` (keySeparator) — e.g. `read:system-info`, `core.system_metrics`. A dynamic `t('scopeDescriptions.' + key)` mis-parses. Use the **same pattern as the scope-picker** (`PluginsPage.tsx`):

```tsx
const scopeDescs = t('scopeDescriptions', { returnObjects: true }) as
  Record<string, { label: string; description: string }>;
// ...later: scopeDescs?.[scope.key]?.label ?? scope.key
```

Tier headings are separator-safe (`frontend`/`backend` have no `:`/`.`): `t(\`scopeTiers.${tier}\`)`.

## Components & Content

The rewritten component renders these sections top → bottom. All user-facing strings via `useTranslation('plugins')`.

### 1. Security banner (reframed)

Keep the amber `AlertTriangle` banner, but reframe the body to the two-tier reality:
- Title: `t('docs.securityWarning')` (reuse) — copy reworded (see i18n below) to mention both tiers.
- Body: bundled = fully trusted (runs in-process, in-repo); external/marketplace = sandboxed but you still grant capability scopes — only install and grant what you trust.
- Keep the dangerous-permission list (`file:write`, `file:delete`, `system:execute`, `db:write`, `user:write`) but prefix it as **bundled-only** (these are the old permission model; external plugins cannot get them).

### 2. Trust Tiers (NEW — centerpiece)

A two-card grid (`md:grid-cols-2`), styling consistent with existing cards (`rounded-xl border border-slate-800 bg-slate-900/50 p-6`):

- **Bundled** card (icon `ShieldCheck`): `t('tiers.bundled.label')` + `t('tiers.bundled.description')` — in-process Python in the host, full host access, old permission model, ships in-repo / maintained by BaluHost.
- **External** card (icon `Lock` or `Boxes`): `t('tiers.external.label')` + `t('tiers.external.description')` — marketplace plugins, run as low-privilege `baluhost-plugin` in a subprocess + network namespace, reach the host only through admin-granted capability scopes over RPC; no host Python, DB, filesystem, or shell.

Section heading: `t('tiers.title')`.

### 3. Capability Scopes (NEW)

Consumes `scopeCatalog`. Intro line `t('tiers.scopesIntro')` ("these are the scopes you grant an external plugin in the enable dialog"). Then group the catalog by tier and render each scope, mirroring the picker's grouping:

```tsx
(['frontend', 'backend'] as const).map((tier) => {
  const scopes = scopeCatalog.filter((s) => s.tier === tier);
  if (scopes.length === 0) return null;
  // heading: t(`scopeTiers.${tier}`)
  // each scope: <code>{scope.key}</code> + label + description + danger flag
});
```

Each scope row: the key as `<code>`, `scopeDescs?.[scope.key]?.label ?? scope.key` (bold), `scopeDescs?.[scope.key]?.description` (muted), and an amber danger marker if `scope.dangerous` (all six are currently `false`, but render the flag conditionally so it's future-proof).

Section heading: `t('tiers.scopesTitle')`.

### 4. Installing & enabling (reframed)

Replace the old "drop folder in `installed/`" installation block. New content (`t('tiers.installTitle')` + prose):
- **External (Marketplace):** `t('tiers.installExternal')` — install from the Marketplace tab (downloaded, checksum-verified); on enable you pick which requested capability scopes to grant (the scope-picker).
- **Bundled:** `t('tiers.installBundled')` — ship in-repo, granted via the permission modal.
- Keep the existing `docs.marketplaceHint` callout (still accurate).

### 5. Bundled reference (condensed)

- Keep the permission-category grid (`PERMISSION_CATEGORY_*` + `permissionMap`) — still accurate for bundled plugins — but under a heading that scopes it to bundled (`t('docs.permissions')` reused, intro reworded to "bundled plugins").
- **Trim the hooks grid:** replace the 26-entry `HOOKS_BY_CATEGORY_KEY` grid with a one-paragraph summary (`t('docs.eventHooksDescription')` reused/reworded) + total count + the GitHub link for the full list. Remove `HOOK_CATEGORY_KEYS`, `HOOKS_BY_CATEGORY_KEY`, `HOOK_CATEGORY_ICONS`, `hooksByCategory`, `totalHooks` and the unused icon imports they pull in.

### 6. Version footer

Unchanged (`useFormattedVersion`, Plugin API version, GitHub link).

## i18n

**File:** `client/src/i18n/locales/{de,en}/plugins.json`.

Add a top-level `tiers` block (both languages):

```jsonc
"tiers": {
  "title": "Trust tiers",                       // DE: "Vertrauensstufen"
  "bundled": {
    "label": "Bundled (in-process, trusted)",   // DE: "Bundled (In-Process, vertraut)"
    "description": "Ship with BaluHost and run as Python inside the server with full host access (the permission model below). Maintained in-repo."
  },
  "external": {
    "label": "External (sandboxed)",            // DE: "Extern (Sandbox)"
    "description": "Marketplace plugins run in an isolated subprocess as a low-privilege user with no network, reaching the host only through the capability scopes you grant — no host code, database, filesystem, or shell access."
  },
  "scopesTitle": "Capability scopes",           // DE: "Capability-Scopes"
  "scopesIntro": "When you enable an external plugin, you grant a subset of these scopes in the enable dialog. Each scope is enforced by the sandbox.",
  "installTitle": "Installing & enabling",       // DE: "Installieren & Aktivieren"
  "installExternal": "Install external plugins from the Marketplace tab (downloaded and checksum-verified). When you enable one, pick which of its requested capability scopes to grant.",
  "installBundled": "Bundled plugins ship with BaluHost; enabling one grants its declared permissions via the permission dialog."
}
```

(German strings authored to mirror the English meaning.)

**Reuse from #287:** `scopeDescriptions.<key>.{label,description}` (6 keys), `scopeTiers.{frontend,backend}`.

**Reuse existing:** `docs.securityWarning`, `docs.dangerousPermissions`, `docs.permissionDesc*`, `docs.permissions`, `docs.available`, `docs.eventHooks`, `docs.hooks`, `docs.eventHooksDescription`, `docs.marketplaceHint`, `docs.documentationOnGitHub`, the `categories.*` and `permissionDescriptions.*` blocks.

**Remove (stale — describe the old install path / full structure that the rewrite drops):** `docs.installation`, `docs.installationDesc`, `docs.systemOverview`, `docs.lifecycle`, `docs.discovery(+Desc)`, `docs.registration(+Desc)`, `docs.permissionCheck(+Desc)`, `docs.activation(+Desc)`, `docs.pluginStructure`, `docs.pluginStructureManifest`, `docs.pluginStructureEntry`, `docs.pluginStructureRoutes`, `docs.pluginStructureUI`, and the `hooks.*` / `hookCategories.*` blocks if the hooks grid is removed. Remove from BOTH locale files. (Verify each key is unused elsewhere via vectordb/Read before deleting; if any is referenced outside this component, keep it.)

## Error handling

- `scopeCatalog` empty (fetch failed or not yet loaded): the Capability-Scopes section renders a small muted "unavailable" note (`t('tiers.scopesUnavailable')`) instead of an empty/blank section; the rest of the doc renders normally. (`PluginsPage` fetches on mount, so under normal use the catalog is present by the time the tab is opened.)
- `scopeDescs?.[key]` missing for a key: fall back to the raw `scope.key` for the label and omit the description (the `?.` chain already handles this).

## Testing

**Vitest** at `client/src/__tests__/components/plugins/PluginDocumentation.twoTier.test.tsx` (centralized mirror tree; `t:(k)=>k` stub per repo convention — assert on i18n keys / scope keys, not English):

- Renders both trust-tier cards (assert `tiers.bundled.label` and `tiers.external.label` keys present).
- Given a mocked `scopeCatalog` of the 6 scopes, the Capability-Scopes section renders each scope key (`read:system-info` … `core.notify`) grouped under the two `scopeTiers.*` headings.
- Empty `scopeCatalog` → renders the `tiers.scopesUnavailable` note, no crash.
- (Light) the condensed bundled permission reference still renders for a provided `permissions` prop.

Mock `react-i18next` (`t:(k)=>k`), `../../contexts/VersionContext` (`useFormattedVersion`). No backend.

**Pre-PR gates (per the CI gotcha hit on #287 — see `project_frontend_ci_build_gotchas`):** from `client/`, run `npx eslint .` (0 errors), `npm run build` (`tsc -b` over app/node/test projects — exit 0), and `npx vitest run`. The new test lives under `src/__tests__` which `tsconfig.app.json` excludes and `tsconfig.test.json` already covers (vite-env.d.ts include fixed on main).

## Decomposition & Rollout

One cohesive PR on `feat/plugin-documentation-two-tier` (branched from main after #287 merge). Suggested task order:
1. Prop threading: `ScopeInfo` prop on `PluginDocumentation` + pass `scopeCatalog` from `PluginsPage`.
2. Component rewrite: tier cards + capability-scopes section + reframed install + condensed bundled reference (remove hooks-grid machinery).
3. i18n: add `tiers.*` (de+en), remove stale `docs.*`/`hooks.*`/`hookCategories.*` keys (verified unused).
4. Vitest + run the three pre-PR gates.

No migration, no deploy action. Sibling to #287; no dependency beyond the already-merged catalog endpoint + i18n keys.

## Self-Review

- **Coverage:** every design section maps to a task (1 prop, 2 rewrite, 3 i18n, 4 test). Live catalog consumption, separator-safe lookup, reframed install, condensed bundled ref, error fallback, tests — all specified.
- **Consistency:** `scopeCatalog: ScopeInfo[]` prop name + `scopeDescs` returnObjects pattern identical to the picker; tier keys `frontend`/`backend` match `scopeTiers.*` and the backend catalog.
- **Scope:** frontend-only, single component + its locale strings; operator focus locks the trim decision.
- **Ambiguity:** stale-key removal is gated on a per-key "unused elsewhere" check (don't delete a key another component shares).
