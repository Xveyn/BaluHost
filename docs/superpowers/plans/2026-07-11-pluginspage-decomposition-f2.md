# PluginsPage.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behavior-preserving decomposition of `client/src/pages/PluginsPage.tsx` (691 lines) into one data/state hook, one pure helper, and a `components/plugins/plugin-management/` directory of presentational components, leaving the page a thin ~130-line orchestrator.

**Architecture:** All fetching/state moves into `hooks/usePluginManagement.ts`. Presentational components take props + callbacks only. Moved markup is byte-identical (same JSX, same Tailwind, same i18n keys); the page keeps its default export and path so the router/lazy-load is untouched. Already-extracted `MarketplaceTab`, `PluginDocumentation`, `PluginSettingsSection`, and `usePlugins()` are reused unmodified.

**Tech Stack:** React 18 + TypeScript (strict, `verbatimModuleSyntax`) + Vite + Tailwind + react-i18next + lucide-react + Vitest + @testing-library/react.

## Global Constraints

- **`verbatimModuleSyntax`:** every type-only import MUST use `import type { ... }`. `tsc -b` (CI `npm run build`) enforces this; vitest/esbuild does NOT catch it. Run `npx tsc -b` before each commit.
- **Behavior byte-identical:** same API calls (`getPluginDetails`, `getScopeCatalog`, `listPermissions`, `togglePlugin`, `toggleDashboardPanel`, `uninstallPlugin`), same `.catch(console.error)` swallow on the two mount effects, same `t('errors.*')`/`t('dashboardPanel.enableFailed')` keys, same external/internal enable branching, same modal enable-disabled guards, same `safeExternalUrl`/`resolvePluginString` usage.
- **Test hygiene (T7):** assert on role/text/title, never Tailwind class names. Mock `react-i18next` with `useTranslation: () => ({ t: (k: string) => k })`. Fixtures are complete objects of the real API types (`PluginInfo`, `PluginDetail`, `PermissionInfo`, `ScopeInfo`) from `../api/plugins`. Each test asserts the SPECIFIC targeted behavior of its unit (a branch taken, a callback fired with the right arg, a guard enforced) — not incidental rendering.
- **No dependency changes, no i18n-key changes, no endpoint changes.**
- Source of truth for every moved block: the current `client/src/pages/PluginsPage.tsx` at branch base. Line numbers below refer to that file.
- New component dir: `client/src/components/plugins/plugin-management/`. New tests dir: `client/src/__tests__/components/plugins/plugin-management/` and `client/src/__tests__/hooks/`.

---

### Task 1: `pluginCategoryColor` pure helper

**Files:**
- Create: `client/src/components/plugins/plugin-management/pluginCategoryColor.ts`
- Test: `client/src/__tests__/components/plugins/plugin-management/pluginCategoryColor.test.ts`

**Interfaces:**
- Produces: `export function getCategoryColor(category: string): string`

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/components/plugins/plugin-management/pluginCategoryColor.test.ts
import { describe, it, expect } from 'vitest';
import { getCategoryColor } from '../../../../components/plugins/plugin-management/pluginCategoryColor';

describe('getCategoryColor', () => {
  it('returns the monitoring class string for the monitoring category', () => {
    expect(getCategoryColor('monitoring')).toContain('blue');
  });

  it('returns a distinct class string per known category', () => {
    const known = ['monitoring', 'storage', 'network', 'security', 'general'];
    const results = known.map(getCategoryColor);
    // all five map to a non-empty string, and they are not all identical
    expect(results.every((r) => r.length > 0)).toBe(true);
    expect(new Set(results).size).toBe(5);
  });

  it('falls back to the general class string for an unknown category', () => {
    expect(getCategoryColor('does-not-exist')).toBe(getCategoryColor('general'));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/plugins/plugin-management/pluginCategoryColor.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation**

Move the `getCategoryColor` body verbatim from `PluginsPage.tsx:178-187`:

```ts
// client/src/components/plugins/plugin-management/pluginCategoryColor.ts
export function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    monitoring: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    storage: 'bg-green-500/20 text-green-400 border-green-500/30',
    network: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    security: 'bg-red-500/20 text-red-400 border-red-500/30',
    general: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
  };
  return colors[category] || colors.general;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/plugins/plugin-management/pluginCategoryColor.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/plugins/plugin-management/pluginCategoryColor.ts client/src/__tests__/components/plugins/plugin-management/pluginCategoryColor.test.ts
git commit -m "feat(plugins): extract getCategoryColor helper (F2, #301)"
```

---

### Task 2: `usePluginManagement` hook

**Files:**
- Create: `client/src/hooks/usePluginManagement.ts`
- Test: `client/src/__tests__/hooks/usePluginManagement.test.ts`

**Interfaces:**
- Consumes: `usePlugins()` from `../contexts/PluginContext` (`{ plugins, isLoading, error, refreshPlugins }`), `useConfirmDialog()` from `./useConfirmDialog` (`{ confirm, dialog }`), all named functions from `../api/plugins`.
- Produces: `usePluginManagement(): UsePluginManagementResult` (full shape below). Consumed by Tasks 5, 8, 9, 10, 11.

```ts
import type { PluginDetail, PluginInfo, PermissionInfo, ScopeInfo } from '../api/plugins';
import type { ReactNode } from 'react';

export interface UsePluginManagementResult {
  plugins: PluginInfo[];
  isLoading: boolean;
  error: string | null;
  refreshPlugins: () => Promise<void>;
  allPermissions: PermissionInfo[];
  scopeCatalog: ScopeInfo[];
  selectedPlugin: PluginDetail | null;
  detailsLoading: boolean;
  actionLoading: boolean;
  actionError: string | null;
  loadPluginDetails: (name: string) => Promise<PluginDetail | null>;
  handleTogglePlugin: (plugin: PluginInfo) => Promise<void>;
  handleEnableWithPermissions: () => Promise<void>;
  handleEnableWithScopes: () => Promise<void>;
  handleUninstall: (name: string) => Promise<void>;
  handleToggleDashboardPanel: () => Promise<void>;
  showPermissionModal: boolean;
  setShowPermissionModal: (v: boolean) => void;
  selectedPermissions: string[];
  togglePermission: (perm: string) => void;
  showScopeModal: boolean;
  setShowScopeModal: (v: boolean) => void;
  selectedScopes: string[];
  toggleScope: (scope: string) => void;
  dialog: ReactNode;
}
```

**Porting notes (byte-identical to source):**
- State + mount effects: `PluginsPage.tsx:44-68` (11 `useState` except `activeTab` which STAYS in the page; both mount effects with `.catch(console.error)`).
- `loadPluginDetails`: `70-83` verbatim.
- `handleTogglePlugin`: `85-117` verbatim (internal→`setSelectedPermissions(plugin.required_permissions)` + `setShowPermissionModal(true)`; external→filtered `setSelectedScopes` + `setShowScopeModal(true)`).
- `handleEnableWithPermissions`: `119-138` verbatim.
- `handleEnableWithScopes`: `140-157` verbatim.
- `handleUninstall`: `159-176` verbatim (uses `confirm` from `useConfirmDialog`).
- `handleToggleDashboardPanel`: extract the inline onClick at `453-464` — guard `if (!selectedPlugin) return;`, `setActionLoading(true)`, `setActionError(null)`, `await toggleDashboardPanel(selectedPlugin.name, !selectedPlugin.dashboard_panel_enabled)`, `await loadPluginDetails(selectedPlugin.name)`, catch → `setActionError(t('dashboardPanel.enableFailed'))`, finally `setActionLoading(false)`.
- `togglePermission(perm)`: replaces the inline checkbox add/remove at `553-559` — `setSelectedPermissions(prev => prev.includes(perm) ? prev.filter(p => p !== perm) : [...prev, perm])`.
- `toggleScope(scope)`: replaces `623-628` — same pattern on `selectedScopes`.
- `useTranslation(['plugins', 'common'])` inside the hook for the error strings.
- Return the full object above, threading `plugins/isLoading/error/refreshPlugins` from `usePlugins()` and `dialog` from `useConfirmDialog()`.

- [ ] **Step 1: Write the failing test**

```ts
// client/src/__tests__/hooks/usePluginManagement.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import type { PluginInfo, PluginDetail, ScopeInfo } from '../../api/plugins';

const mockRefreshPlugins = vi.fn().mockResolvedValue(undefined);
vi.mock('../../contexts/PluginContext', () => ({
  usePlugins: () => ({
    plugins: [] as PluginInfo[],
    isLoading: false,
    error: null,
    refreshPlugins: mockRefreshPlugins,
  }),
}));

const mockConfirm = vi.fn();
vi.mock('../../hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: mockConfirm, dialog: null }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

vi.mock('../../api/plugins', () => ({
  getPluginDetails: vi.fn(),
  getScopeCatalog: vi.fn().mockResolvedValue({ scopes: [] }),
  listPermissions: vi.fn().mockResolvedValue({ permissions: [] }),
  togglePlugin: vi.fn().mockResolvedValue({}),
  toggleDashboardPanel: vi.fn().mockResolvedValue({}),
  uninstallPlugin: vi.fn().mockResolvedValue({}),
}));

import { usePluginManagement } from '../../hooks/usePluginManagement';
import * as api from '../../api/plugins';

const internalPlugin: PluginInfo = {
  name: 'demo', version: '1.0.0', display_name: 'Demo', description: 'd',
  author: 'a', category: 'general', required_permissions: ['files.read'],
  dangerous_permissions: [], is_enabled: false, has_ui: false, has_routes: false,
};

function detail(over: Partial<PluginDetail> = {}): PluginDetail {
  return {
    name: 'demo', version: '1.0.0', display_name: 'Demo', description: 'd', author: 'a',
    category: 'general', dependencies: [], required_permissions: ['files.read'],
    granted_permissions: [], dangerous_permissions: [], is_enabled: false,
    is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
    has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [],
    dashboard_widgets: [], config: {}, ...over,
  };
}

describe('usePluginManagement', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sets actionError when loadPluginDetails fails and returns null', async () => {
    vi.mocked(api.getPluginDetails).mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => usePluginManagement());
    let ret: PluginDetail | null = detail();
    await act(async () => { ret = await result.current.loadPluginDetails('demo'); });
    expect(ret).toBeNull();
    expect(result.current.actionError).toBe('errors.loadDetailsFailed');
  });

  it('opens the permission modal (not the scope modal) when enabling an internal plugin', async () => {
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(detail({ is_external: false }));
    const { result } = renderHook(() => usePluginManagement());
    await act(async () => { await result.current.handleTogglePlugin(internalPlugin); });
    expect(result.current.showPermissionModal).toBe(true);
    expect(result.current.showScopeModal).toBe(false);
    expect(result.current.selectedPermissions).toEqual(['files.read']);
  });

  it('opens the scope modal seeded with catalog-filtered requested scopes for an external plugin', async () => {
    const catalog: ScopeInfo[] = [{ key: 'ui.read', tier: 'frontend', dangerous: false }];
    vi.mocked(api.getScopeCatalog).mockResolvedValue({ scopes: catalog });
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(
      detail({ is_external: true, requested_api_scopes: ['ui.read', 'not.in.catalog'] }),
    );
    const { result } = renderHook(() => usePluginManagement());
    await waitFor(() => expect(result.current.scopeCatalog).toHaveLength(1));
    await act(async () => { await result.current.handleTogglePlugin({ ...internalPlugin, is_external: true }); });
    expect(result.current.showScopeModal).toBe(true);
    expect(result.current.showPermissionModal).toBe(false);
    expect(result.current.selectedScopes).toEqual(['ui.read']); // 'not.in.catalog' filtered out
  });

  it('does not call uninstallPlugin when the confirm dialog is declined', async () => {
    mockConfirm.mockResolvedValueOnce(false);
    const { result } = renderHook(() => usePluginManagement());
    await act(async () => { await result.current.handleUninstall('demo'); });
    expect(api.uninstallPlugin).not.toHaveBeenCalled();
  });

  it('calls uninstallPlugin and refreshes when the confirm dialog is accepted', async () => {
    mockConfirm.mockResolvedValueOnce(true);
    const { result } = renderHook(() => usePluginManagement());
    await act(async () => { await result.current.handleUninstall('demo'); });
    expect(api.uninstallPlugin).toHaveBeenCalledWith('demo');
    expect(mockRefreshPlugins).toHaveBeenCalled();
  });

  it('togglePermission adds then removes a permission', () => {
    const { result } = renderHook(() => usePluginManagement());
    act(() => result.current.togglePermission('files.write'));
    expect(result.current.selectedPermissions).toContain('files.write');
    act(() => result.current.togglePermission('files.write'));
    expect(result.current.selectedPermissions).not.toContain('files.write');
  });

  it('handleEnableWithPermissions posts enabled:true + grant_permissions from the selection', async () => {
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(detail({ is_external: false }));
    const { result } = renderHook(() => usePluginManagement());
    // seed selectedPlugin + selectedPermissions via the internal-enable branch
    await act(async () => { await result.current.handleTogglePlugin(internalPlugin); });
    await act(async () => { await result.current.handleEnableWithPermissions(); });
    expect(api.togglePlugin).toHaveBeenCalledWith('demo', { enabled: true, grant_permissions: ['files.read'] });
    expect(result.current.showPermissionModal).toBe(false);
  });

  it('handleEnableWithScopes posts enabled:true + grant_api_scopes from the catalog-filtered selection', async () => {
    const catalog: ScopeInfo[] = [{ key: 'ui.read', tier: 'frontend', dangerous: false }];
    vi.mocked(api.getScopeCatalog).mockResolvedValue({ scopes: catalog });
    vi.mocked(api.getPluginDetails).mockResolvedValueOnce(
      detail({ is_external: true, requested_api_scopes: ['ui.read', 'not.in.catalog'] }),
    );
    const { result } = renderHook(() => usePluginManagement());
    await waitFor(() => expect(result.current.scopeCatalog).toHaveLength(1));
    await act(async () => { await result.current.handleTogglePlugin({ ...internalPlugin, is_external: true }); });
    await act(async () => { await result.current.handleEnableWithScopes(); });
    expect(api.togglePlugin).toHaveBeenCalledWith('demo', { enabled: true, grant_api_scopes: ['ui.read'] });
    expect(result.current.showScopeModal).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/hooks/usePluginManagement.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the hook** per the porting notes above (move each handler verbatim from the cited source lines; add `togglePermission`/`toggleScope`/`handleToggleDashboardPanel`; return the full result object).

- [ ] **Step 4: Run test + typecheck**

Run: `cd client && npx vitest run src/__tests__/hooks/usePluginManagement.test.ts`
Expected: PASS (6 tests).
Run: `cd client && npx tsc -b`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/usePluginManagement.ts client/src/__tests__/hooks/usePluginManagement.test.ts
git commit -m "feat(plugins): add usePluginManagement hook (state + actions) (F2, #301)"
```

---

### Task 3: `PluginTabNav`

**Files:**
- Create: `client/src/components/plugins/plugin-management/PluginTabNav.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginTabNav.test.tsx`

**Interfaces:**
- Produces:
```ts
import type { LucideIcon } from 'lucide-react';
export type TabType = 'plugins' | 'marketplace' | 'documentation';
export interface PluginTab { id: TabType; labelKey: string; icon: LucideIcon }
export const TABS: PluginTab[];
export function PluginTabNav(props: {
  activeTab: TabType;
  onSelect: (id: TabType) => void;
}): JSX.Element;
```
- Consumed by Task 11 (page).

**Porting notes:** Move the `TABS` const from `PluginsPage.tsx:34-38` and the `TabType` from `32`. Render the tab bar markup verbatim from `218-233` (the `<div className="flex gap-2 border-b ...">` map), using `activeTab`/`onSelect`. `useTranslation(['plugins', 'common'])` internally.

- [ ] **Step 1: Write the failing test**

```tsx
// PluginTabNav.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PluginTabNav, TABS } from '../../../../components/plugins/plugin-management/PluginTabNav';

describe('PluginTabNav', () => {
  it('renders one button per tab', () => {
    render(<PluginTabNav activeTab="plugins" onSelect={() => {}} />);
    expect(screen.getAllByRole('button')).toHaveLength(TABS.length);
  });

  it('fires onSelect with the clicked tab id', () => {
    const onSelect = vi.fn();
    render(<PluginTabNav activeTab="plugins" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('tabs.marketplace'));
    expect(onSelect).toHaveBeenCalledWith('marketplace');
  });
});
```

- [ ] **Step 2: Run to verify fail.** `cd client && npx vitest run src/__tests__/components/plugins/plugin-management/PluginTabNav.test.tsx` → FAIL.
- [ ] **Step 3: Write the component** per porting notes.
- [ ] **Step 4: Run test + `npx tsc -b`.** Expected: PASS (2 tests), no type errors.
- [ ] **Step 5: Commit** `feat(plugins): extract PluginTabNav (F2, #301)`.

---

### Task 4: `PluginListCard`

**Files:**
- Create: `client/src/components/plugins/plugin-management/PluginListCard.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginListCard.test.tsx`

**Interfaces:**
- Consumes: `getCategoryColor` (Task 1), `PluginInfo`.
- Produces:
```ts
import type { PluginInfo } from '../../../api/plugins';
export function PluginListCard(props: {
  plugin: PluginInfo;
  isSelected: boolean;
  actionLoading: boolean;
  onSelect: (name: string) => void;
  onToggle: (plugin: PluginInfo) => void;
}): JSX.Element;
```
- Consumed by Task 5.

**Porting notes:** Move one card verbatim from `PluginsPage.tsx:271-334`. Replace the outer `onClick={() => loadPluginDetails(plugin.name)}` with `onClick={() => onSelect(plugin.name)}`; the selected-highlight condition uses `isSelected` (was `selectedPlugin?.name === plugin.name`). The toggle button keeps `e.stopPropagation()` then `onToggle(plugin)` (was `handleTogglePlugin`), `disabled={actionLoading}`. Keep `resolvePluginString`, `getCategoryColor`, all badges/error box, `useTranslation` internally.

- [ ] **Step 1: Write the failing test**

```tsx
// PluginListCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: string, fb: string) => fb }));
import { PluginListCard } from '../../../../components/plugins/plugin-management/PluginListCard';

const base: PluginInfo = {
  name: 'demo', version: '1.2.3', display_name: 'Demo Plugin', description: 'desc',
  author: 'a', category: 'monitoring', required_permissions: [], dangerous_permissions: [],
  is_enabled: false, has_ui: false, has_routes: false,
};

describe('PluginListCard', () => {
  it('shows the enable label and the version when disabled', () => {
    render(<PluginListCard plugin={base} isSelected={false} actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getByText('buttons.enable')).toBeInTheDocument();
    expect(screen.getByText('v1.2.3')).toBeInTheDocument();
  });

  it('shows the active badge and disable label when enabled', () => {
    render(<PluginListCard plugin={{ ...base, is_enabled: true }} isSelected={false} actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getByText('status.active')).toBeInTheDocument();
    expect(screen.getByText('buttons.disable')).toBeInTheDocument();
  });

  it('clicking the toggle fires onToggle but NOT onSelect (stopPropagation)', () => {
    const onSelect = vi.fn();
    const onToggle = vi.fn();
    render(<PluginListCard plugin={base} isSelected={false} actionLoading={false} onSelect={onSelect} onToggle={onToggle} />);
    fireEvent.click(screen.getByText('buttons.enable'));
    expect(onToggle).toHaveBeenCalledWith(base);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('clicking the card body fires onSelect with the plugin name', () => {
    const onSelect = vi.fn();
    render(<PluginListCard plugin={base} isSelected={false} actionLoading={false} onSelect={onSelect} onToggle={() => {}} />);
    fireEvent.click(screen.getByText('Demo Plugin'));
    expect(onSelect).toHaveBeenCalledWith('demo');
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Write the component** per porting notes.
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (4 tests), no type errors.
- [ ] **Step 5: Commit** `feat(plugins): extract PluginListCard (F2, #301)`.

---

### Task 5: `PluginList`

**Files:**
- Create: `client/src/components/plugins/plugin-management/PluginList.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginList.test.tsx`

**Interfaces:**
- Consumes: `PluginListCard` (Task 4), `PluginInfo`.
- Produces:
```ts
import type { PluginInfo } from '../../../api/plugins';
export function PluginList(props: {
  plugins: PluginInfo[];
  selectedName: string | null;
  actionLoading: boolean;
  onSelect: (name: string) => void;
  onToggle: (plugin: PluginInfo) => void;
}): JSX.Element;
```
- Consumed by Task 11.

**Porting notes:** Move the empty-state + map from `PluginsPage.tsx:260-337`. Empty-state markup verbatim (`262-268`). Otherwise map `plugins` to `PluginListCard` passing `isSelected={selectedName === plugin.name}` + the callbacks. `useTranslation` internally for the empty-state strings.

- [ ] **Step 1: Write the failing test**

```tsx
// PluginList.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
// stub the card so this test targets only PluginList's own branching
vi.mock('../../../../components/plugins/plugin-management/PluginListCard', () => ({
  PluginListCard: ({ plugin }: { plugin: PluginInfo }) => <div data-testid="card">{plugin.name}</div>,
}));
import { PluginList } from '../../../../components/plugins/plugin-management/PluginList';

const p = (name: string): PluginInfo => ({
  name, version: '1', display_name: name, description: '', author: '', category: 'general',
  required_permissions: [], dangerous_permissions: [], is_enabled: false, has_ui: false, has_routes: false,
});

describe('PluginList', () => {
  it('renders the empty-state when there are no plugins', () => {
    render(<PluginList plugins={[]} selectedName={null} actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getByText('empty.noPlugins')).toBeInTheDocument();
    expect(screen.queryByTestId('card')).not.toBeInTheDocument();
  });

  it('renders one card per plugin when the list is non-empty', () => {
    render(<PluginList plugins={[p('a'), p('b')]} selectedName="a" actionLoading={false} onSelect={() => {}} onToggle={() => {}} />);
    expect(screen.getAllByTestId('card')).toHaveLength(2);
    expect(screen.queryByText('empty.noPlugins')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (2 tests).
- [ ] **Step 5: Commit** `feat(plugins): extract PluginList (F2, #301)`.

---

### Task 6: `PluginDetailsCard` + `PluginPermissionsCard`

**Files:**
- Create: `client/src/components/plugins/plugin-management/PluginDetailsCard.tsx`
- Create: `client/src/components/plugins/plugin-management/PluginPermissionsCard.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginDetailsCard.test.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginPermissionsCard.test.tsx`

**Interfaces:**
- Consumes: `PluginDetail`, `safeExternalUrl`, `resolvePluginString`.
- Produces:
```ts
import type { PluginDetail } from '../../../api/plugins';
export function PluginDetailsCard(props: { plugin: PluginDetail }): JSX.Element;
export function PluginPermissionsCard(props: { plugin: PluginDetail }): JSX.Element;
```
- Consumed by Task 8.

**Porting notes:** `PluginDetailsCard` = the details `<div>` verbatim from `PluginsPage.tsx:352-399` (version/author/category/homepage via `safeExternalUrl`/status/installed; `resolvePluginString` for the title). `PluginPermissionsCard` = the permissions `<div>` verbatim from `402-436` (noPermissions text or the required-perms `<ul>` with dangerous/granted markers). `useTranslation` internally in both.

- [ ] **Step 1: Write the failing tests**

```tsx
// PluginDetailsCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: string, fb: string) => fb }));
import { PluginDetailsCard } from '../../../../components/plugins/plugin-management/PluginDetailsCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '2.0.0', display_name: 'Demo', description: '', author: 'Jane',
  category: 'storage', dependencies: [], required_permissions: [], granted_permissions: [],
  dangerous_permissions: [], is_enabled: true, is_installed: true, has_ui: false, has_routes: false,
  has_background_tasks: false, has_dashboard_panel: false, dashboard_panel_enabled: false,
  nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginDetailsCard', () => {
  it('renders version and author', () => {
    render(<PluginDetailsCard plugin={detail()} />);
    expect(screen.getByText('2.0.0')).toBeInTheDocument();
    expect(screen.getByText('Jane')).toBeInTheDocument();
  });

  it('renders a homepage link only when the url is safe', () => {
    const { rerender } = render(<PluginDetailsCard plugin={detail({ homepage: 'https://example.com' })} />);
    expect(screen.getByRole('link')).toHaveAttribute('href', 'https://example.com/');
    rerender(<PluginDetailsCard plugin={detail({ homepage: 'javascript:alert(1)' })} />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
```

```tsx
// PluginPermissionsCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PluginPermissionsCard } from '../../../../components/plugins/plugin-management/PluginPermissionsCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '',
  category: 'general', dependencies: [], required_permissions: [], granted_permissions: [],
  dangerous_permissions: [], is_enabled: true, is_installed: true, has_ui: false, has_routes: false,
  has_background_tasks: false, has_dashboard_panel: false, dashboard_panel_enabled: false,
  nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginPermissionsCard', () => {
  it('shows the noPermissions text when there are none', () => {
    render(<PluginPermissionsCard plugin={detail()} />);
    expect(screen.getByText('permissions.noPermissions')).toBeInTheDocument();
  });

  it('lists each required permission', () => {
    render(<PluginPermissionsCard plugin={detail({ required_permissions: ['files.read', 'files.write'], granted_permissions: ['files.read'] })} />);
    expect(screen.getByText('files.read')).toBeInTheDocument();
    expect(screen.getByText('files.write')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run both to verify fail** → FAIL.
- [ ] **Step 3: Write both components** per porting notes.
- [ ] **Step 4: Run both tests + `npx tsc -b`** → PASS (4 tests total).
- [ ] **Step 5: Commit** `feat(plugins): extract PluginDetailsCard + PluginPermissionsCard (F2, #301)`.

---

### Task 7: `PluginDashboardPanelCard` + `PluginActionsCard`

**Files:**
- Create: `client/src/components/plugins/plugin-management/PluginDashboardPanelCard.tsx`
- Create: `client/src/components/plugins/plugin-management/PluginActionsCard.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginDashboardPanelCard.test.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginActionsCard.test.tsx`

**Interfaces:**
- Consumes: `PluginDetail`, `LocalOnlyAction` from `../../LocalOnlyAction`.
- Produces:
```ts
import type { PluginDetail } from '../../../api/plugins';
export function PluginDashboardPanelCard(props: {
  plugin: PluginDetail; actionLoading: boolean; onToggle: () => void;
}): JSX.Element;
export function PluginActionsCard(props: {
  plugin: PluginDetail; actionLoading: boolean;
  onConfigure: () => void; onUninstall: (name: string) => void;
}): JSX.Element;
```
- Consumed by Task 8.

**Porting notes:** `PluginDashboardPanelCard` = the panel `<div>` verbatim from `PluginsPage.tsx:440-475` (the inline onClick becomes `onClick={onToggle}`; keep the active/inactive label + enable/disable-panel button + `disabled={actionLoading}`). Render unconditionally — the `has_dashboard_panel && is_enabled` guard stays in the sidebar (Task 8). `PluginActionsCard` = the actions `<div>` verbatim from `489-513`: configure button (`onClick={onConfigure}`, `disabled={!plugin.is_enabled}`), `LocalOnlyAction` wrapping the uninstall button (`onClick={() => onUninstall(plugin.name)}`, `disabled={actionLoading || plugin.is_enabled}`), and the disable-first hint (`508-512`). `useTranslation` internally in both.

- [ ] **Step 1: Write the failing tests**

```tsx
// PluginDashboardPanelCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PluginDashboardPanelCard } from '../../../../components/plugins/plugin-management/PluginDashboardPanelCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: true, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: true, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginDashboardPanelCard', () => {
  it('shows the enable-panel label + inactive state when the panel is off', () => {
    render(<PluginDashboardPanelCard plugin={detail({ dashboard_panel_enabled: false })} actionLoading={false} onToggle={() => {}} />);
    expect(screen.getByText('buttons.enablePanel')).toBeInTheDocument();
    expect(screen.getByText('dashboardPanel.inactive')).toBeInTheDocument();
  });

  it('fires onToggle when the button is clicked', () => {
    const onToggle = vi.fn();
    render(<PluginDashboardPanelCard plugin={detail({ dashboard_panel_enabled: true })} actionLoading={false} onToggle={onToggle} />);
    fireEvent.click(screen.getByText('buttons.disablePanel'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
```

```tsx
// PluginActionsCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('../../../../components/LocalOnlyAction', () => ({ LocalOnlyAction: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
import { PluginActionsCard } from '../../../../components/plugins/plugin-management/PluginActionsCard';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: true, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [], config: {}, ...over,
});

describe('PluginActionsCard', () => {
  it('disables the uninstall button while the plugin is enabled', () => {
    render(<PluginActionsCard plugin={detail({ is_enabled: true })} actionLoading={false} onConfigure={() => {}} onUninstall={() => {}} />);
    expect(screen.getByText('buttons.uninstall').closest('button')).toBeDisabled();
  });

  it('fires onUninstall with the plugin name when enabled=false and clicked', () => {
    const onUninstall = vi.fn();
    render(<PluginActionsCard plugin={detail({ is_enabled: false })} actionLoading={false} onConfigure={() => {}} onUninstall={onUninstall} />);
    fireEvent.click(screen.getByText('buttons.uninstall'));
    expect(onUninstall).toHaveBeenCalledWith('demo');
  });

  it('fires onConfigure when configure is clicked', () => {
    const onConfigure = vi.fn();
    render(<PluginActionsCard plugin={detail()} actionLoading={false} onConfigure={onConfigure} onUninstall={() => {}} />);
    fireEvent.click(screen.getByText('buttons.configure'));
    expect(onConfigure).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run both to verify fail** → FAIL.
- [ ] **Step 3: Write both components** per porting notes.
- [ ] **Step 4: Run both tests + `npx tsc -b`** → PASS (5 tests total).
- [ ] **Step 5: Commit** `feat(plugins): extract PluginDashboardPanelCard + PluginActionsCard (F2, #301)`.

---

### Task 8: `PluginDetailsSidebar`

**Files:**
- Create: `client/src/components/plugins/plugin-management/PluginDetailsSidebar.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PluginDetailsSidebar.test.tsx`

**Interfaces:**
- Consumes: `PluginDetailsCard`, `PluginPermissionsCard`, `PluginDashboardPanelCard`, `PluginActionsCard` (Tasks 6–7), `PluginSettingsSection` from `../PluginSettingsSection`, `PluginDetail`.
- Produces:
```ts
import type { PluginDetail } from '../../../api/plugins';
export function PluginDetailsSidebar(props: {
  plugin: PluginDetail | null;
  detailsLoading: boolean;
  actionLoading: boolean;
  onToggleDashboardPanel: () => void;
  onConfigure: () => void;
  onUninstall: (name: string) => void;
}): JSX.Element;
```
- Consumed by Task 11.

**Porting notes:** Move the sidebar `<div className="space-y-4">` container from `PluginsPage.tsx:340-523`. Three branches verbatim: loading skeleton (`341-348`); `plugin` present → `<>` with `PluginDetailsCard`, `PluginPermissionsCard`, conditional `PluginDashboardPanelCard` (guard `plugin.has_dashboard_panel && plugin.is_enabled`, pass `onToggle={onToggleDashboardPanel}`), conditional `PluginSettingsSection` (guard `plugin.config_schema && plugin.is_enabled`, same props as `479-485`), `PluginActionsCard` (pass `onConfigure`/`onUninstall`); empty branch (`515-521`). Prop name in source was `detailsLoading`/`selectedPlugin` — here `detailsLoading`/`plugin`.

- [ ] **Step 1: Write the failing test**

```tsx
// PluginDetailsSidebar.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginDetail } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
// stub children so this test targets ONLY the sidebar's branching/guards
vi.mock('../../../../components/plugins/plugin-management/PluginDetailsCard', () => ({ PluginDetailsCard: () => <div data-testid="details" /> }));
vi.mock('../../../../components/plugins/plugin-management/PluginPermissionsCard', () => ({ PluginPermissionsCard: () => <div data-testid="perms" /> }));
vi.mock('../../../../components/plugins/plugin-management/PluginDashboardPanelCard', () => ({ PluginDashboardPanelCard: () => <div data-testid="panel" /> }));
vi.mock('../../../../components/plugins/plugin-management/PluginActionsCard', () => ({ PluginActionsCard: () => <div data-testid="actions" /> }));
vi.mock('../../../../components/plugins/PluginSettingsSection', () => ({ PluginSettingsSection: () => <div data-testid="settings" /> }));
import { PluginDetailsSidebar } from '../../../../components/plugins/plugin-management/PluginDetailsSidebar';

const detail = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: true, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [], config: {}, ...over,
});
const noop = () => {};
const props = { detailsLoading: false, actionLoading: false, onToggleDashboardPanel: noop, onConfigure: noop, onUninstall: noop };

describe('PluginDetailsSidebar', () => {
  it('shows the empty prompt when no plugin is selected', () => {
    render(<PluginDetailsSidebar plugin={null} {...props} />);
    expect(screen.getByText('empty.selectPlugin')).toBeInTheDocument();
    expect(screen.queryByTestId('details')).not.toBeInTheDocument();
  });

  it('renders details + permissions + actions for a selected plugin', () => {
    render(<PluginDetailsSidebar plugin={detail()} {...props} />);
    expect(screen.getByTestId('details')).toBeInTheDocument();
    expect(screen.getByTestId('perms')).toBeInTheDocument();
    expect(screen.getByTestId('actions')).toBeInTheDocument();
  });

  it('renders the dashboard-panel card only when has_dashboard_panel && is_enabled', () => {
    const { rerender } = render(<PluginDetailsSidebar plugin={detail({ has_dashboard_panel: true, is_enabled: true })} {...props} />);
    expect(screen.getByTestId('panel')).toBeInTheDocument();
    rerender(<PluginDetailsSidebar plugin={detail({ has_dashboard_panel: true, is_enabled: false })} {...props} />);
    expect(screen.queryByTestId('panel')).not.toBeInTheDocument();
  });

  it('renders the settings section only when config_schema && is_enabled', () => {
    const { rerender } = render(<PluginDetailsSidebar plugin={detail({ config_schema: { type: 'object' }, is_enabled: true })} {...props} />);
    expect(screen.getByTestId('settings')).toBeInTheDocument();
    rerender(<PluginDetailsSidebar plugin={detail({ config_schema: undefined, is_enabled: true })} {...props} />);
    expect(screen.queryByTestId('settings')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Write the component** per porting notes.
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (4 tests).
- [ ] **Step 5: Commit** `feat(plugins): extract PluginDetailsSidebar (F2, #301)`.

---

### Task 9: `PermissionGrantModal`

**Files:**
- Create: `client/src/components/plugins/plugin-management/PermissionGrantModal.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/PermissionGrantModal.test.tsx`

**Interfaces:**
- Consumes: `PluginDetail`, `PermissionInfo`.
- Produces:
```ts
import type { PluginDetail, PermissionInfo } from '../../../api/plugins';
export function PermissionGrantModal(props: {
  plugin: PluginDetail;
  allPermissions: PermissionInfo[];
  selectedPermissions: string[];
  onTogglePermission: (perm: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}): JSX.Element;
```
- Consumed by Task 11.

**Porting notes:** Move the modal `<div className="fixed inset-0 ...">` verbatim from `PluginsPage.tsx:529-593` (the outer `showPermissionModal && selectedPlugin` guard stays in the page). The checkbox `onChange` becomes `onTogglePermission(perm)`; cancel button → `onCancel`; enable button → `onConfirm`, keeping the exact disabled guard `disabled={!plugin.required_permissions.every((p) => selectedPermissions.includes(p))}`. `useTranslation` internally.

- [ ] **Step 1: Write the failing test**

```tsx
// PermissionGrantModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail, PermissionInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { PermissionGrantModal } from '../../../../components/plugins/plugin-management/PermissionGrantModal';

const plugin: PluginDetail = {
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: ['files.read', 'files.write'], granted_permissions: [],
  dangerous_permissions: ['files.write'], is_enabled: false, is_installed: true, has_ui: false, has_routes: false,
  has_background_tasks: false, has_dashboard_panel: false, dashboard_panel_enabled: false,
  nav_items: [], dashboard_widgets: [], config: {},
};
const perms: PermissionInfo[] = [
  { name: 'r', value: 'files.read', dangerous: false, description: 'read' },
  { name: 'w', value: 'files.write', dangerous: true, description: 'write' },
];

describe('PermissionGrantModal', () => {
  it('disables the enable button until every required permission is selected', () => {
    const { rerender } = render(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={['files.read']}
        onTogglePermission={() => {}} onCancel={() => {}} onConfirm={() => {}} />,
    );
    expect(screen.getByText('buttons.enablePlugin').closest('button')).toBeDisabled();
    rerender(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={['files.read', 'files.write']}
        onTogglePermission={() => {}} onCancel={() => {}} onConfirm={() => {}} />,
    );
    expect(screen.getByText('buttons.enablePlugin').closest('button')).not.toBeDisabled();
  });

  it('fires onTogglePermission with the permission when a checkbox changes', () => {
    const onToggle = vi.fn();
    render(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={[]}
        onTogglePermission={onToggle} onCancel={() => {}} onConfirm={() => {}} />,
    );
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(onToggle).toHaveBeenCalledWith('files.read');
  });

  it('fires onConfirm when the (enabled) enable button is clicked', () => {
    const onConfirm = vi.fn();
    render(
      <PermissionGrantModal plugin={plugin} allPermissions={perms} selectedPermissions={['files.read', 'files.write']}
        onTogglePermission={() => {}} onCancel={() => {}} onConfirm={onConfirm} />,
    );
    fireEvent.click(screen.getByText('buttons.enablePlugin'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Write the component** per porting notes.
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (3 tests).
- [ ] **Step 5: Commit** `feat(plugins): extract PermissionGrantModal (F2, #301)`.

---

### Task 10: `ScopeGrantModal`

**Files:**
- Create: `client/src/components/plugins/plugin-management/ScopeGrantModal.tsx`
- Test: `client/src/__tests__/components/plugins/plugin-management/ScopeGrantModal.test.tsx`

**Interfaces:**
- Consumes: `PluginDetail`, `ScopeInfo`.
- Produces:
```ts
import type { PluginDetail, ScopeInfo } from '../../../api/plugins';
export function ScopeGrantModal(props: {
  plugin: PluginDetail;
  scopeCatalog: ScopeInfo[];
  selectedScopes: string[];
  onToggleScope: (scope: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}): JSX.Element;
```
- Consumed by Task 11.

**Porting notes:** Convert the IIFE at `PluginsPage.tsx:596-686` into a component. The inner consts become in-component: `const descs = t('scopeDescriptions', { returnObjects: true }) as Record<string, { label: string; description: string }>`; `const requested = (plugin.requested_api_scopes ?? []).filter((s) => scopeCatalog.some((c) => c.key === s))`; `byTier(tier)` and `renderScope(scope)` as inner functions (the checkbox `onChange` → `onToggleScope(scope.key)`). Modal markup verbatim from `647-684` (cancel → `onCancel`, grant → `onConfirm`; noScopes branch when `requested.length === 0`). `useTranslation(['plugins','common'])` internally.
> Note: under the `t: (k) => k` mock, `t('scopeDescriptions', { returnObjects: true })` returns the string `'scopeDescriptions'`; indexing it yields `undefined`, so `meta?.label ?? scope.key` falls back to the scope key — the component must not assume `descs` is an object (the `?.` guards already handle this).

- [ ] **Step 1: Write the failing test**

```tsx
// ScopeGrantModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PluginDetail, ScopeInfo } from '../../../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { ScopeGrantModal } from '../../../../components/plugins/plugin-management/ScopeGrantModal';

const plugin = (over: Partial<PluginDetail> = {}): PluginDetail => ({
  name: 'demo', version: '1', display_name: 'Demo', description: '', author: '', category: 'general',
  dependencies: [], required_permissions: [], granted_permissions: [], dangerous_permissions: [],
  is_enabled: false, is_installed: true, has_ui: false, has_routes: false, has_background_tasks: false,
  has_dashboard_panel: false, dashboard_panel_enabled: false, nav_items: [], dashboard_widgets: [],
  config: {}, is_external: true, requested_api_scopes: ['ui.read', 'files.write'], ...over,
});
const catalog: ScopeInfo[] = [
  { key: 'ui.read', tier: 'frontend', dangerous: false },
  { key: 'files.write', tier: 'backend', dangerous: true },
];

describe('ScopeGrantModal', () => {
  it('renders both tier groups with one checkbox per requested+catalog scope', () => {
    render(<ScopeGrantModal plugin={plugin()} scopeCatalog={catalog} selectedScopes={[]}
      onToggleScope={() => {}} onCancel={() => {}} onConfirm={() => {}} />);
    expect(screen.getByText('scopeTiers.frontend')).toBeInTheDocument();
    expect(screen.getByText('scopeTiers.backend')).toBeInTheDocument();
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it('shows the noScopes text when no requested scope is in the catalog', () => {
    render(<ScopeGrantModal plugin={plugin({ requested_api_scopes: ['unknown'] })} scopeCatalog={catalog}
      selectedScopes={[]} onToggleScope={() => {}} onCancel={() => {}} onConfirm={() => {}} />);
    expect(screen.getByText('picker.noScopes')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('fires onToggleScope with the scope key on checkbox change', () => {
    const onToggleScope = vi.fn();
    render(<ScopeGrantModal plugin={plugin()} scopeCatalog={catalog} selectedScopes={[]}
      onToggleScope={onToggleScope} onCancel={() => {}} onConfirm={() => {}} />);
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(onToggleScope).toHaveBeenCalledWith('ui.read');
  });

  it('fires onConfirm when grant is clicked', () => {
    const onConfirm = vi.fn();
    render(<ScopeGrantModal plugin={plugin()} scopeCatalog={catalog} selectedScopes={['ui.read']}
      onToggleScope={() => {}} onCancel={() => {}} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText('picker.grant'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL.
- [ ] **Step 3: Write the component** per porting notes.
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (4 tests).
- [ ] **Step 5: Commit** `feat(plugins): extract ScopeGrantModal (F2, #301)`.

---

### Task 11: Barrel + `PluginsPage.tsx` orchestrator + integration test

**Files:**
- Create: `client/src/components/plugins/plugin-management/index.ts`
- Modify: `client/src/pages/PluginsPage.tsx` (full rewrite to orchestrator)
- Test: `client/src/__tests__/pages/PluginsPage.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 1–10 via the barrel, `usePluginManagement` (Task 2), `MarketplaceTab`/`PluginDocumentation`/`PluginSettingsSection` (unchanged).

**Barrel** `index.ts` re-exports: `getCategoryColor`, `TABS`, `type TabType`, `PluginTabNav`, `PluginListCard`, `PluginList`, `PluginDetailsCard`, `PluginPermissionsCard`, `PluginDashboardPanelCard`, `PluginActionsCard`, `PluginDetailsSidebar`, `PermissionGrantModal`, `ScopeGrantModal`.

**Page rewrite:** keep the file header comment + default export `PluginsPage`. Keep ONLY `activeTab` state (`useState<TabType>('plugins')`). Everything else from `usePluginManagement()`. Structure:
1. `if (isLoading) return <spinner/>` (verbatim `189-195`).
2. Header (verbatim `199-215`, refresh button → `refreshPlugins`).
3. `<PluginTabNav activeTab={activeTab} onSelect={setActiveTab} />`.
4. Error banner (`235-239`) + plugins-tab actionError banner (`241-246`).
5. `{activeTab === 'marketplace' && <MarketplaceTab />}`, `{activeTab === 'documentation' && <PluginDocumentation permissions={allPermissions} scopeCatalog={scopeCatalog} />}`.
6. `{activeTab === 'plugins' && (<div className="grid grid-cols-1 lg:grid-cols-3 gap-6"><div className="lg:col-span-2 space-y-4"><PluginList .../></div><PluginDetailsSidebar .../></div>)}` — `PluginList` gets `plugins`, `selectedName={selectedPlugin?.name ?? null}`, `actionLoading`, `onSelect={loadPluginDetails}`, `onToggle={handleTogglePlugin}`; `PluginDetailsSidebar` gets `plugin={selectedPlugin}`, `detailsLoading`, `actionLoading`, `onToggleDashboardPanel={handleToggleDashboardPanel}`, `onConfigure={() => setShowPermissionModal(true)}`, `onUninstall={handleUninstall}`.
7. `{showPermissionModal && selectedPlugin && <PermissionGrantModal ... />}` (props: `plugin={selectedPlugin}`, `allPermissions`, `selectedPermissions`, `onTogglePermission={togglePermission}`, `onCancel={() => setShowPermissionModal(false)}`, `onConfirm={handleEnableWithPermissions}`).
8. `{showScopeModal && selectedPlugin && <ScopeGrantModal ... />}` (props: `plugin={selectedPlugin}`, `scopeCatalog`, `selectedScopes`, `onToggleScope={toggleScope}`, `onCancel={() => setShowScopeModal(false)}`, `onConfirm={handleEnableWithScopes}`).
9. `{dialog}` at the end.

Delete all now-unused imports (the api functions, lucide icons only used by moved markup, `safeExternalUrl`, `resolvePluginString`, `useConfirmDialog`, `LocalOnlyAction`, `useEffect`). Keep `useState`, `useTranslation`, the three reused components, `usePluginManagement`, and the barrel imports. Run eslint to catch leftover unused imports.

- [ ] **Step 1: Write the failing integration test**

```tsx
// client/src/__tests__/pages/PluginsPage.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PluginInfo, PluginDetail } from '../../api/plugins';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const hookValue = {
  plugins: [] as PluginInfo[], isLoading: false, error: null, refreshPlugins: vi.fn(),
  allPermissions: [], scopeCatalog: [], selectedPlugin: null as PluginDetail | null,
  detailsLoading: false, actionLoading: false, actionError: null,
  loadPluginDetails: vi.fn(), handleTogglePlugin: vi.fn(), handleEnableWithPermissions: vi.fn(),
  handleEnableWithScopes: vi.fn(), handleUninstall: vi.fn(), handleToggleDashboardPanel: vi.fn(),
  showPermissionModal: false, setShowPermissionModal: vi.fn(), selectedPermissions: [], togglePermission: vi.fn(),
  showScopeModal: false, setShowScopeModal: vi.fn(), selectedScopes: [], toggleScope: vi.fn(),
  dialog: null,
};
vi.mock('../../hooks/usePluginManagement', () => ({ usePluginManagement: () => hookValue }));
vi.mock('../../components/plugins/MarketplaceTab', () => ({ default: () => <div data-testid="marketplace" /> }));
vi.mock('../../components/plugins/PluginDocumentation', () => ({ default: () => <div data-testid="docs" /> }));
// real plugin-management barrel components render (already unit-tested); make the
// plugin-name resolver deterministic so PluginListCard shows the raw display_name
vi.mock('../../lib/pluginI18n', () => ({ resolvePluginString: (_t: unknown, _k: string, fb: string) => fb }));

import PluginsPage from '../../pages/PluginsPage';

describe('PluginsPage', () => {
  beforeEach(() => { hookValue.plugins = []; hookValue.selectedPlugin = null; });

  it('shows the empty-state on the plugins tab when there are no plugins', () => {
    render(<PluginsPage />);
    expect(screen.getByText('empty.noPlugins')).toBeInTheDocument();
    // sidebar empty prompt is also present
    expect(screen.getByText('empty.selectPlugin')).toBeInTheDocument();
  });

  it('renders the plugin list when plugins exist', () => {
    hookValue.plugins = [{
      name: 'demo', version: '1', display_name: 'Demo Plugin', description: '', author: '',
      category: 'general', required_permissions: [], dangerous_permissions: [],
      is_enabled: false, has_ui: false, has_routes: false,
    }];
    render(<PluginsPage />);
    expect(screen.getByText('Demo Plugin')).toBeInTheDocument();
    expect(screen.queryByText('empty.noPlugins')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify fail** → FAIL (page still in old shape / test imports barrel not yet built).
- [ ] **Step 3: Write the barrel, then rewrite `PluginsPage.tsx`** per the structure above.
- [ ] **Step 4: Full verification**

Run: `cd client && npx vitest run src/__tests__/pages/PluginsPage.test.tsx`
Expected: PASS (2 tests).
Run: `cd client && node -e "console.log(require('fs').readFileSync('src/pages/PluginsPage.tsx','utf8').split(/\r?\n/).length)"`
Expected: < 500 (target ~130).
Run: `cd client && npx tsc -b`
Expected: no errors.
Run: `cd client && npx eslint src/pages/PluginsPage.tsx src/components/plugins/plugin-management src/hooks/usePluginManagement.ts`
Expected: 0 errors (no unused imports).

- [ ] **Step 5: Commit** `refactor(plugins): compose PluginsPage from usePluginManagement + plugin-management/* (F2, #301)`.

---

## Final Verification (after all tasks)

- [ ] `cd client && npx eslint .` → 0 errors.
- [ ] `cd client && npm run build` → green (tsc -b + vite).
- [ ] `cd client && npx vitest run` → full suite green.
- [ ] `PluginsPage.tsx` < 500 lines.
- [ ] Update `client/src/components/CLAUDE.md` (or `pages/CLAUDE.md`) if it catalogs plugin components — add the `plugin-management/` dir; keep docs in sync per CLAUDE.md rules. (Docs-only, fold into the Task 11 commit or a trailing `docs(plugins): ...` commit.)
- [ ] Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of every moved block, especially the two enable branches in `usePluginManagement` and the two modal guards).
