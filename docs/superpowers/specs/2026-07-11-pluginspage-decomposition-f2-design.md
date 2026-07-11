# PluginsPage.tsx Decomposition — Design (F2 / #301)

**Date:** 2026-07-11
**Finding:** F2 (components > 500 lines), umbrella issue #301.
**Target:** `client/src/pages/PluginsPage.tsx` — currently **691 lines**.

## Goal

Behavior-preserving decomposition of `PluginsPage.tsx` (the admin plugin
management page) into one data/state hook, one pure helper, and a directory of
presentational components under a new `components/plugins/plugin-management/`.

**Non-goals:** no change to queries, endpoints, the `usePlugins()` context, i18n
keys, copy, Tailwind styling, modal behavior, `safeExternalUrl` usage, or any
computed value. The page keeps its path (`pages/PluginsPage.tsx`, **default
export** `PluginsPage`) so the router / lazy-load in `App.tsx` is untouched. The
already-extracted `MarketplaceTab`, `PluginDocumentation`, and
`PluginSettingsSection` are reused as-is — not modified.

## Constraints

- Every extracted value is **byte-identical** in behavior: same API calls
  (`getPluginDetails`, `getScopeCatalog`, `listPermissions`, `togglePlugin`,
  `toggleDashboardPanel`, `uninstallPlugin`), same `.catch(console.error)`
  swallow on the two mount effects, same error-string i18n keys, same
  external/internal enable branching, same modal enable-disabled guards.
- Extracted components are **presentational**: props in, callbacks in, no data
  fetching. The extracted hook owns all fetching/state.
- Tests are T7-conform: assert on role/text/title, never Tailwind classes;
  fixtures are complete objects of the real API types (`PluginInfo`,
  `PluginDetail`, `PermissionInfo`, `ScopeInfo`).

## Current inline blocks (what moves)

| Block | Current lines | Destination |
|---|---|---|
| 11 `useState` + 2 mount effects + all handlers (`loadPluginDetails`, `handleTogglePlugin`, `handleEnableWithPermissions`, `handleEnableWithScopes`, `handleUninstall`) | 44–176 | `hooks/usePluginManagement.ts` |
| `getCategoryColor` | 178–187 | `plugin-management/pluginCategoryColor.ts` (pure) |
| Tab navigation (TABS const + bar) | 34–38, 218–233 | `plugin-management/PluginTabNav.tsx` |
| Plugin list card | 271–334 | `plugin-management/PluginListCard.tsx` |
| Plugin list (empty-state + map) | 260–337 | `plugin-management/PluginList.tsx` |
| Details card | 352–399 | `plugin-management/PluginDetailsCard.tsx` |
| Permissions card | 402–436 | `plugin-management/PluginPermissionsCard.tsx` |
| Dashboard-panel card | 439–476 | `plugin-management/PluginDashboardPanelCard.tsx` |
| Actions card | 489–513 | `plugin-management/PluginActionsCard.tsx` |
| Sidebar container (loading / selected / empty; hosts the 4 cards + `PluginSettingsSection`) | 340–523 | `plugin-management/PluginDetailsSidebar.tsx` |
| Permission grant modal | 528–594 | `plugin-management/PermissionGrantModal.tsx` |
| Scope grant modal (IIFE + `byTier`/`renderScope`) | 596–686 | `plugin-management/ScopeGrantModal.tsx` |

## New units & interfaces

### `hooks/usePluginManagement.ts`

```ts
import type {
  PluginDetail, PluginInfo, PermissionInfo, ScopeInfo,
} from '../api/plugins';

export interface UsePluginManagementResult {
  // passthrough from usePlugins()
  plugins: PluginInfo[];
  isLoading: boolean;
  error: string | null;
  refreshPlugins: () => Promise<void>;
  // catalog (mount-loaded)
  allPermissions: PermissionInfo[];
  scopeCatalog: ScopeInfo[];
  // selection + details
  selectedPlugin: PluginDetail | null;
  detailsLoading: boolean;
  actionLoading: boolean;
  actionError: string | null;
  loadPluginDetails: (name: string) => Promise<PluginDetail | null>;
  // toggle / enable / uninstall
  handleTogglePlugin: (plugin: PluginInfo) => Promise<void>;
  handleEnableWithPermissions: () => Promise<void>;
  handleEnableWithScopes: () => Promise<void>;
  handleUninstall: (name: string) => Promise<void>;
  handleToggleDashboardPanel: () => Promise<void>;
  // permission modal
  showPermissionModal: boolean;
  setShowPermissionModal: (v: boolean) => void;
  selectedPermissions: string[];
  togglePermission: (perm: string) => void;
  // scope modal
  showScopeModal: boolean;
  setShowScopeModal: (v: boolean) => void;
  selectedScopes: string[];
  toggleScope: (scope: string) => void;
  // confirm dialog element (from useConfirmDialog)
  dialog: React.ReactNode;
}

export function usePluginManagement(): UsePluginManagementResult;
```

Body ports every handler verbatim (same `setActionLoading`/`setActionError`
sequencing, same `refreshPlugins()` + `loadPluginDetails()` follow-ups, same
`t('errors.*')` keys). `handleToggleDashboardPanel` extracts the inline onClick
at 453–464 (guards on `selectedPlugin`, calls `toggleDashboardPanel(name,
!enabled)`, then `loadPluginDetails`, `t('dashboardPanel.enableFailed')` on
error). `togglePermission`/`toggleScope` replace the inline checkbox
add/remove logic. The `confirm` + `dialog` come from `useConfirmDialog()`
inside the hook. `useTranslation(['plugins','common'])` internally for error
strings.

### `plugin-management/pluginCategoryColor.ts` (pure)

```ts
export function getCategoryColor(category: string): string;
```

Verbatim from 178–187: the `Record<string,string>` of Tailwind class strings
per category (monitoring/storage/network/security/general) with `|| general`
fallback.

### Presentational components (`components/plugins/plugin-management/`)

- **`PluginTabNav.tsx`** — `{ tabs: { id: TabType; labelKey: string; icon: LucideIcon }[]; activeTab: TabType; onSelect: (id: TabType) => void }`. Renders the tab bar (218–233). `TabType` exported from here; `TABS` const moves here too. `useTranslation` internally.
- **`PluginListCard.tsx`** — `{ plugin: PluginInfo; isSelected: boolean; actionLoading: boolean; onSelect: (name: string) => void; onToggle: (plugin: PluginInfo) => void }`. One card (271–334): icon, name/version/active badge, description, category (`getCategoryColor`) + UI + review badges, toggle button (with `stopPropagation`), error box. `resolvePluginString` + `useTranslation` internally.
- **`PluginList.tsx`** — `{ plugins: PluginInfo[]; selectedName: string | null; actionLoading: boolean; onSelect; onToggle }`. Empty-state (262–268) or map of `PluginListCard` (260–337).
- **`PluginDetailsCard.tsx`** — `{ plugin: PluginDetail }`. The `<dl>` (352–399): version/author/category/homepage(`safeExternalUrl`)/status/installed. `useTranslation` internally.
- **`PluginPermissionsCard.tsx`** — `{ plugin: PluginDetail }`. Permissions list (402–436), dangerous/granted markers.
- **`PluginDashboardPanelCard.tsx`** — `{ plugin: PluginDetail; actionLoading: boolean; onToggle: () => void }`. Card (439–476); only rendered when `has_dashboard_panel && is_enabled` (guard stays in the sidebar).
- **`PluginActionsCard.tsx`** — `{ plugin: PluginDetail; actionLoading: boolean; onConfigure: () => void; onUninstall: (name: string) => void }`. Configure + uninstall (inside `LocalOnlyAction`) + disable-first hint (489–513).
- **`PluginDetailsSidebar.tsx`** — `{ plugin: PluginDetail | null; detailsLoading: boolean; actionLoading: boolean; onToggleDashboardPanel: () => void; onConfigure: () => void; onUninstall: (name: string) => void }`. Loading skeleton (341–348) / selected (`PluginDetailsCard`, `PluginPermissionsCard`, conditional `PluginDashboardPanelCard`, conditional `PluginSettingsSection`, `PluginActionsCard`) / empty (515–521).
- **`PermissionGrantModal.tsx`** — `{ plugin: PluginDetail; allPermissions: PermissionInfo[]; selectedPermissions: string[]; onTogglePermission: (perm: string) => void; onCancel: () => void; onConfirm: () => void }`. Modal (528–594); the enable button stays disabled until every `required_permissions` is in `selectedPermissions` (verbatim guard).
- **`ScopeGrantModal.tsx`** — `{ plugin: PluginDetail; scopeCatalog: ScopeInfo[]; selectedScopes: string[]; onToggleScope: (scope: string) => void; onCancel: () => void; onConfirm: () => void }`. Modal (596–686); the IIFE's `descs`/`requested`/`byTier`/`renderScope` become in-component consts/functions. `scopeDescriptions` via `t(..., { returnObjects: true })` verbatim.

### `plugin-management/index.ts`

Barrel exporting all components + `getCategoryColor` + `TabType`.

### `PluginsPage.tsx` (after)

Calls `usePluginManagement()`. Keeps only `activeTab` state (tab selection is
pure view state, no data) — everything else comes from the hook. Renders:
header (title + conditional refresh button), `PluginTabNav`, error banners,
tab switch (`MarketplaceTab` / `PluginDocumentation` unchanged; `plugins` tab =
`PluginList` + `PluginDetailsSidebar` in the `grid lg:grid-cols-3` layout),
`PermissionGrantModal`, `ScopeGrantModal`, `{dialog}`. Target: **~130 lines**
(from 691).

## Testing

Broad + integration (Vitest, T7-conform):

- **`pluginCategoryColor`** — each known category returns its class string;
  unknown category falls back to `general`.
- **`usePluginManagement`** — `renderHook`: `loadPluginDetails` failure sets
  `actionError` to `errors.loadDetailsFailed` and returns null; enabling an
  external plugin (`is_external: true`) opens the scope modal seeded with
  catalog-filtered requested scopes; enabling an internal plugin opens the
  permission modal; `handleUninstall` with `confirm` resolving `false` makes no
  `uninstallPlugin` call. Mock `../api/plugins`, `usePlugins`,
  `useConfirmDialog`.
- **Component renders** — `PluginListCard` (active badge when enabled, toggle
  fires with `stopPropagation` not selecting), `PluginList` (empty-state text),
  `PluginDetailsCard` (values + no homepage row when url unsafe),
  `PluginPermissionsCard` (noPermissions text; granted vs not),
  `PluginDashboardPanelCard` (active/inactive label, toggle fires),
  `PluginActionsCard` (uninstall disabled while enabled), `PluginTabNav`
  (select fires), `PermissionGrantModal` (enable disabled until all required
  checked, confirm fires), `ScopeGrantModal` (frontend/backend tier groups
  render, noScopes branch, grant fires).
- **Integration** (`__tests__/pages/PluginsPage.test.tsx`) — mock the hook;
  assert list + sidebar render for a populated fixture; empty `plugins` →
  empty-state; tab switch shows Marketplace/Documentation.

## Verification gates

- `PluginsPage.tsx` < 500 lines (target ~130).
- `eslint .` — 0 errors.
- `npm run build` (tsc -b + vite) — green (mind `import type` for all type-only
  imports — `verbatimModuleSyntax` is enforced by `tsc -b`, not vitest).
- `vitest run` — full suite green.
- Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of
  every moved block, especially the two enable branches and the modal guards).
