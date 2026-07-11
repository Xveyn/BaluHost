# VCLSettings.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behavior-preserving decomposition of `client/src/components/vcl/VCLSettings.tsx` (633 lines) into one data/state hook, one pure helper, and a `components/vcl/vcl-settings/` directory of presentational components, leaving the component a thin ~120-line orchestrator.

**Architecture:** All fetching/state moves into `hooks/useVclSettings.ts`. Presentational components take props + callbacks only. Moved markup is byte-identical (same JSX, same Tailwind, same mixed `t()`/hard-coded English copy). The component keeps its default export + path so the `vcl` barrel and consumers are untouched.

**Tech Stack:** React 18 + TypeScript (strict, `verbatimModuleSyntax`) + Vite + Tailwind + react-i18next (`admin` namespace) + lucide-react + Vitest + @testing-library/react.

## Global Constraints

- **`verbatimModuleSyntax`:** every type-only import MUST use `import type { ... }`. `tsc -b` (CI `npm run build`) enforces this; vitest/esbuild does NOT. Run `npx tsc -b` before each commit.
- **Behavior byte-identical:** same API calls (`getAdminOverview`, `getAdminUsers`, `getStorageInfo`, `updateUserSettingsAdmin`, `triggerCleanup`, `getReconciliationPreview`, `applyReconciliation`), same `Promise.all` with `getStorageInfo().catch(() => null)`, same `confirm(...)` strings, same `t('vcl.*')`/`t('common.*')` keys (with existing fallback args), same `setTimeout(..., 5000|3000)` timers, same derived values, same `slice(0, 100)` mismatch cap.
- **DO NOT introduce/change i18n or copy.** The file mixes `t('vcl.*')` (namespace `admin`) with hard-coded English strings (mostly the Ownership-Reconciliation section) — preserve BOTH verbatim. The i18n gap is tracked in issue #406.
- **Test hygiene (T7):** assert on role/text/title, never Tailwind class names. Fixtures are complete objects of the real types (`AdminVCLOverview`, `UserVCLStats`, `VCLStorageInfo`, `ReconciliationPreview`, `AffectedUser`, `ReconciliationMismatch`, `VCLSettingsUpdate`) from `../types/vcl`. Each test asserts the SPECIFIC targeted behavior of its unit.
- Source of truth for every moved block: the current `client/src/components/vcl/VCLSettings.tsx` at branch base. Line numbers below refer to that file.
- New component dir: `client/src/components/vcl/vcl-settings/`. New tests: `client/src/__tests__/components/vcl/vcl-settings/` and `client/src/__tests__/hooks/`.
- Import note: `formatBytes` comes from `../../api/vcl` (NOT lib/formatters); `formatNumber` from `../../lib/formatters`; types from `../../types/vcl`. From a component in `vcl-settings/`, these are `../../../api/vcl`, `../../../lib/formatters`, `../../../types/vcl`, and `ByteSizeInput` is `../../ui/ByteSizeInput`.

---

### Task 1: `usageBarColor` pure helper

**Files:**
- Create: `client/src/components/vcl/vcl-settings/usageBarColor.ts`
- Test: `client/src/__tests__/components/vcl/vcl-settings/usageBarColor.test.ts`

**Interfaces:**
- Produces: `export function usageBarColor(percent: number, warn: number, crit: number): string`

- [ ] **Step 1: Write the failing test**

```ts
// usageBarColor.test.ts
import { describe, it, expect } from 'vitest';
import { usageBarColor } from '../../../../components/vcl/vcl-settings/usageBarColor';

describe('usageBarColor', () => {
  it('returns red at/above the crit threshold', () => {
    expect(usageBarColor(95, 80, 95)).toBe('bg-red-500');
    expect(usageBarColor(90, 70, 90)).toBe('bg-red-500');
  });
  it('returns amber at/above warn and below crit', () => {
    expect(usageBarColor(85, 80, 95)).toBe('bg-amber-500');
    expect(usageBarColor(70, 70, 90)).toBe('bg-amber-500');
  });
  it('returns sky below warn', () => {
    expect(usageBarColor(50, 80, 95)).toBe('bg-sky-500');
    expect(usageBarColor(10, 70, 90)).toBe('bg-sky-500');
  });
});
```

- [ ] **Step 2: Run to verify fail.** `cd client ; npx vitest run src/__tests__/components/vcl/vcl-settings/usageBarColor.test.ts` → FAIL.
- [ ] **Step 3: Write the implementation** (covers the two inline ternaries at lines 236 + 526):

```ts
// usageBarColor.ts
export function usageBarColor(percent: number, warn: number, crit: number): string {
  return percent >= crit ? 'bg-red-500' : percent >= warn ? 'bg-amber-500' : 'bg-sky-500';
}
```

- [ ] **Step 4: Run to verify pass** → PASS (3 tests).
- [ ] **Step 5: Commit** `feat(vcl): extract usageBarColor helper (F2, #301)`.

---

### Task 2: `useVclSettings` hook

**Files:**
- Create: `client/src/hooks/useVclSettings.ts`
- Test: `client/src/__tests__/hooks/useVclSettings.test.ts`

**Interfaces:**
- Consumes: the seven functions + `formatBytes` from `../api/vcl`; `getApiErrorMessage` from `../lib/errorHandling`; types from `../types/vcl`; `useTranslation`.
- Produces: `useVclSettings(): UseVclSettingsResult` (full shape below). Consumed by Task 9.

```ts
import type {
  AdminVCLOverview, UserVCLStats, VCLSettingsUpdate,
  VCLStorageInfo, ReconciliationPreview,
} from '../types/vcl';
import type { Dispatch, SetStateAction } from 'react';

export interface UseVclSettingsResult {
  overview: AdminVCLOverview | null;
  storageInfo: VCLStorageInfo | null;
  users: UserVCLStats[];
  loading: boolean;
  actionLoading: boolean;
  error: string | null;
  successMessage: string | null;
  editingUser: UserVCLStats | null;
  editForm: VCLSettingsUpdate;
  setEditForm: Dispatch<SetStateAction<VCLSettingsUpdate>>;
  reconPreview: ReconciliationPreview | null;
  reconLoading: boolean;
  forceOverQuota: boolean;
  setForceOverQuota: Dispatch<SetStateAction<boolean>>;
  loadData: () => Promise<void>;
  handleCleanup: (dryRun?: boolean) => Promise<void>;
  handleScanMismatches: () => Promise<void>;
  handleApplyReconciliation: () => Promise<void>;
  handleEditUser: (user: UserVCLStats) => void;
  handleSaveUserSettings: () => Promise<void>;
  setEditingUser: Dispatch<SetStateAction<UserVCLStats | null>>;
}

export function useVclSettings(): UseVclSettingsResult;
```

**Porting notes (byte-identical):** move lines 46–167 verbatim — the 12 `useState`, `useTranslation('admin')`, the mount effect (`loadData`), and every handler. Preserve: `loadData`'s `Promise.all([getAdminOverview(), getAdminUsers(100, 0), getStorageInfo().catch(() => null)])`, the `setUsers(usersData?.users || [])`, the catch that sets empty users + null overview; `handleCleanup`'s `confirm(t('vcl.maintenance.confirmCleanup'))` guard, the `t(dryRun ? 'vcl.cleanup.dryRunResult' : 'vcl.cleanup.result', {...})` message, the `setTimeout(..., 5000)`, the `if (!dryRun) loadData()`; `handleScanMismatches`'s `'No ownership mismatches found'` + `setTimeout(..., 3000)`; `handleApplyReconciliation`'s `confirm('Apply ownership reconciliation? ...')` + hard-coded fallbacks; `handleEditUser`; `handleSaveUserSettings`'s `updateUserSettingsAdmin(editingUser.user_id, editForm)` + `t('vcl.settingsUpdated', {...})`. Expose `setEditForm`, `setEditingUser`, `setForceOverQuota`. `getApiErrorMessage` fallbacks verbatim (mix of `t(...)` and hard-coded English).

- [ ] **Step 1: Write the failing test**

```ts
// useVclSettings.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const { overview, users, storage } = vi.hoisted(() => ({
  overview: {
    total_versions: 10, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 5,
    unique_blobs: 4, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
    total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 1, cached_versions_count: 2,
    total_users: 3, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null,
  },
  users: [{ user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500, usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic' }],
  storage: null,
}));

vi.mock('../../api/vcl', () => ({
  getAdminOverview: vi.fn().mockResolvedValue(overview),
  getAdminUsers: vi.fn().mockResolvedValue({ users, total: 1 }),
  getStorageInfo: vi.fn().mockResolvedValue(storage),
  updateUserSettingsAdmin: vi.fn().mockResolvedValue({}),
  triggerCleanup: vi.fn().mockResolvedValue({ deleted_versions: 0, freed_bytes: 0 }),
  getReconciliationPreview: vi.fn().mockResolvedValue({ total_mismatches: 0, mismatches: [], affected_users: [] }),
  applyReconciliation: vi.fn().mockResolvedValue({ message: 'ok' }),
  formatBytes: (n: number) => `${n}B`,
}));
vi.mock('../../lib/errorHandling', () => ({ getApiErrorMessage: (_e: unknown, fb: string) => fb }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { useVclSettings } from '../../hooks/useVclSettings';
import * as api from '../../api/vcl';

describe('useVclSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('loads overview + users on mount', async () => {
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    expect(result.current.users).toHaveLength(1);
    expect(api.getStorageInfo).toHaveBeenCalled();
  });

  it('does not call triggerCleanup when the confirm is declined (non-dry-run)', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    await act(async () => { await result.current.handleCleanup(false); });
    expect(api.triggerCleanup).not.toHaveBeenCalled();
  });

  it('sets the no-mismatches success message when the scan finds none', async () => {
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    await act(async () => { await result.current.handleScanMismatches(); });
    expect(result.current.successMessage).toBe('No ownership mismatches found');
  });

  it('handleSaveUserSettings sends the edit form for the editing user', async () => {
    const { result } = renderHook(() => useVclSettings());
    await waitFor(() => expect(result.current.overview).not.toBeNull());
    act(() => result.current.handleEditUser(users[0]));
    await act(async () => { await result.current.handleSaveUserSettings(); });
    expect(api.updateUserSettingsAdmin).toHaveBeenCalledWith(
      1, expect.objectContaining({ max_size_bytes: 1000, is_enabled: true }),
    );
  });
});
```
> Note: fixtures are declared via `vi.hoisted()` so the `vi.mock` factory can reference them without hitting vitest's hoisting TDZ (any const referenced inside a `vi.mock` factory must be hoisted).

- [ ] **Step 2: Run to verify fail** → FAIL (module not found).
- [ ] **Step 3: Write the hook** per the porting notes (move 46–167 verbatim; return the full object).
- [ ] **Step 4: Run test + gates**

Run: `cd client ; npx vitest run src/__tests__/hooks/useVclSettings.test.ts` → PASS (4 tests).
Run: `cd client ; npx tsc -b` → no errors.
Run: `cd client ; npx eslint src/hooks/useVclSettings.ts` → 0 errors (add `// eslint-disable-next-line react-hooks/exhaustive-deps` on the mount effect ONLY if eslint flags it, preserving the original `[]` deps).

- [ ] **Step 5: Commit** `feat(vcl): add useVclSettings hook (state + actions) (F2, #301)`.

---

### Task 3: `VclMessageBanners` + `VclStatsGrid` + `VclStorageDetailsCard`

**Files:**
- Create: `client/src/components/vcl/vcl-settings/VclMessageBanners.tsx`
- Create: `client/src/components/vcl/vcl-settings/VclStatsGrid.tsx`
- Create: `client/src/components/vcl/vcl-settings/VclStorageDetailsCard.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclMessageBanners.test.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclStatsGrid.test.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclStorageDetailsCard.test.tsx`

**Interfaces:**
- Consumes: `formatBytes` (`../../../api/vcl`), `formatNumber` (`../../../lib/formatters`), `AdminVCLOverview`.
- Produces:
```ts
import type { AdminVCLOverview } from '../../../types/vcl';
export function VclMessageBanners(props: { error: string | null; successMessage: string | null }): JSX.Element;
export function VclStatsGrid(props: { overview: AdminVCLOverview; totalSavings: number; savingsPercent: number }): JSX.Element;
export function VclStorageDetailsCard(props: { overview: AdminVCLOverview; compressionRatio: number }): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** `VclMessageBanners` = the two banners verbatim from `VCLSettings.tsx:188-199` (each guarded by its prop). `VclStatsGrid` = the 4 stat cards verbatim from `250-293` (uses `overview`, `savingsPercent`, `totalSavings`; `formatBytes`/`formatNumber`; `useTranslation('admin')`). `VclStorageDetailsCard` = the detailed-stats card verbatim from `296-344` (uses `overview`, `compressionRatio`; `useTranslation('admin')`; keeps the `last_cleanup_at ? ... : t('vcl.storageDetails.never')` and `updated_at ? ... : t('common.na')` fallbacks).

- [ ] **Step 1: Write the failing tests**

```tsx
// VclMessageBanners.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VclMessageBanners } from '../../../../components/vcl/vcl-settings/VclMessageBanners';

describe('VclMessageBanners', () => {
  it('renders only the error when only error is set', () => {
    render(<VclMessageBanners error="boom" successMessage={null} />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });
  it('renders only the success when only success is set', () => {
    render(<VclMessageBanners error={null} successMessage="done" />);
    expect(screen.getByText('done')).toBeInTheDocument();
  });
  it('renders nothing when both are null', () => {
    const { container } = render(<VclMessageBanners error={null} successMessage={null} />);
    expect(container.textContent).toBe('');
  });
});
```

```tsx
// VclStatsGrid.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { AdminVCLOverview } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclStatsGrid } from '../../../../components/vcl/vcl-settings/VclStatsGrid';

const overview = (over: Partial<AdminVCLOverview> = {}): AdminVCLOverview => ({
  total_versions: 1234, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 5,
  unique_blobs: 4, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
  total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 1, cached_versions_count: 2,
  total_users: 7, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null, ...over,
});

describe('VclStatsGrid', () => {
  it('renders the total-versions count and the active-users count', () => {
    render(<VclStatsGrid overview={overview()} totalSavings={300} savingsPercent={30} />);
    expect(screen.getByText('1,234')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });
});
```

```tsx
// VclStorageDetailsCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { AdminVCLOverview } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclStorageDetailsCard } from '../../../../components/vcl/vcl-settings/VclStorageDetailsCard';

const overview = (over: Partial<AdminVCLOverview> = {}): AdminVCLOverview => ({
  total_versions: 10, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 8,
  unique_blobs: 6, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
  total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 3, cached_versions_count: 2,
  total_users: 3, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null, ...over,
});

describe('VclStorageDetailsCard', () => {
  it('renders unique/total blobs and the never-cleanup fallback', () => {
    render(<VclStorageDetailsCard overview={overview()} compressionRatio={2.5} />);
    expect(screen.getByText('6 / 8')).toBeInTheDocument();
    // last_cleanup_at is null → the 'never' i18n key renders (appears twice: cleanup + priority mode)
    expect(screen.getAllByText('vcl.storageDetails.never').length).toBeGreaterThanOrEqual(1);
  });
});
```

- [ ] **Step 2: Run all three → FAIL.**
- [ ] **Step 3: Write all three components** per porting notes.
- [ ] **Step 4: Run all three tests + `npx tsc -b`** → PASS (5 tests total).
- [ ] **Step 5: Commit** `feat(vcl): extract VclMessageBanners + VclStatsGrid + VclStorageDetailsCard (F2, #301)`.

---

### Task 4: `VclStorageInfoCard`

**Files:**
- Create: `client/src/components/vcl/vcl-settings/VclStorageInfoCard.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclStorageInfoCard.test.tsx`

**Interfaces:**
- Consumes: `formatBytes`, `formatNumber`, `usageBarColor` (Task 1), `VCLStorageInfo`.
- Produces: `export function VclStorageInfoCard(props: { storageInfo: VCLStorageInfo }): JSX.Element;`
- Consumed by Task 9.

**Porting notes:** Move the storage-info card verbatim from `VCLSettings.tsx:203-246` (the outer `{storageInfo && ...}` guard stays in the orchestrator). The inline disk-bar color ternary at line 236 becomes `usageBarColor(storageInfo.disk_used_percent, 70, 90)`. Keep `formatBytes` (`../../../api/vcl`), `formatNumber` (`../../../lib/formatters`), the `t('vcl.storageInfo.*', 'fallback')` calls + the hard-coded "Custom Path" badge, the `Math.min(..., 100)` bar width. `useTranslation('admin')` internally.

- [ ] **Step 1: Write the failing test**

```tsx
// VclStorageInfoCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { VCLStorageInfo } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_k: string, fb?: string) => fb ?? _k }) }));
import { VclStorageInfoCard } from '../../../../components/vcl/vcl-settings/VclStorageInfoCard';

const info = (over: Partial<VCLStorageInfo> = {}): VCLStorageInfo => ({
  storage_path: '/mnt/vcl', is_custom_path: false, blob_count: 42,
  total_compressed_bytes: 1000, disk_total_bytes: 2000, disk_available_bytes: 1500,
  disk_used_percent: 25, ...over,
});

describe('VclStorageInfoCard', () => {
  it('renders the storage path', () => {
    render(<VclStorageInfoCard storageInfo={info()} />);
    expect(screen.getByText('/mnt/vcl')).toBeInTheDocument();
  });
  it('shows the Custom Path badge only when is_custom_path', () => {
    const { rerender } = render(<VclStorageInfoCard storageInfo={info({ is_custom_path: false })} />);
    expect(screen.queryByText('Custom Path')).not.toBeInTheDocument();
    rerender(<VclStorageInfoCard storageInfo={info({ is_custom_path: true })} />);
    expect(screen.getByText('Custom Path')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (2 tests).
- [ ] **Step 5: Commit** `feat(vcl): extract VclStorageInfoCard (F2, #301)`.

---

### Task 5: `VclMaintenanceCard`

**Files:**
- Create: `client/src/components/vcl/vcl-settings/VclMaintenanceCard.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclMaintenanceCard.test.tsx`

**Interfaces:**
- Produces:
```ts
export function VclMaintenanceCard(props: {
  actionLoading: boolean;
  onDryRunCleanup: () => void;
  onTriggerCleanup: () => void;
  onRefresh: () => void;
}): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** Move the maintenance card verbatim from `VCLSettings.tsx:347-378`: dry-run button (`onClick={onDryRunCleanup}`), trigger button (`onClick={onTriggerCleanup}`), refresh button (`onClick={onRefresh}`), each `disabled={actionLoading}`, keep the `RefreshCw` spin class on refresh + the `t('vcl.maintenance.*')` keys. `useTranslation('admin')` internally.

- [ ] **Step 1: Write the failing test**

```tsx
// VclMaintenanceCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclMaintenanceCard } from '../../../../components/vcl/vcl-settings/VclMaintenanceCard';

describe('VclMaintenanceCard', () => {
  it('fires each callback on its button', () => {
    const onDryRunCleanup = vi.fn(), onTriggerCleanup = vi.fn(), onRefresh = vi.fn();
    render(<VclMaintenanceCard actionLoading={false}
      onDryRunCleanup={onDryRunCleanup} onTriggerCleanup={onTriggerCleanup} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByText('vcl.maintenance.dryRunCleanup'));
    fireEvent.click(screen.getByText('vcl.maintenance.triggerCleanup'));
    fireEvent.click(screen.getByText('vcl.maintenance.refreshStats'));
    expect(onDryRunCleanup).toHaveBeenCalledTimes(1);
    expect(onTriggerCleanup).toHaveBeenCalledTimes(1);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
  it('disables all buttons while an action is loading', () => {
    render(<VclMaintenanceCard actionLoading={true}
      onDryRunCleanup={() => {}} onTriggerCleanup={() => {}} onRefresh={() => {}} />);
    for (const k of ['vcl.maintenance.dryRunCleanup', 'vcl.maintenance.triggerCleanup', 'vcl.maintenance.refreshStats']) {
      expect(screen.getByText(k).closest('button')).toBeDisabled();
    }
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (2 tests).
- [ ] **Step 5: Commit** `feat(vcl): extract VclMaintenanceCard (F2, #301)`.

---

### Task 6: `VclReconciliationCard`

**Files:**
- Create: `client/src/components/vcl/vcl-settings/VclReconciliationCard.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclReconciliationCard.test.tsx`

**Interfaces:**
- Consumes: `formatBytes`, `ReconciliationPreview`.
- Produces:
```ts
import type { ReconciliationPreview } from '../../../types/vcl';
export function VclReconciliationCard(props: {
  reconPreview: ReconciliationPreview | null;
  reconLoading: boolean;
  forceOverQuota: boolean;
  onScan: () => void;
  onForceChange: (v: boolean) => void;
  onApply: () => void;
}): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** Move the whole reconciliation card verbatim from `VCLSettings.tsx:381-488`: the scan button (`onClick={onScan}`, `disabled={reconLoading}`), the `{reconPreview && reconPreview.total_mismatches > 0 && (...)}` block containing the force checkbox (`onChange={(e) => onForceChange(e.target.checked)}`) + apply button (`onClick={onApply}`, `Apply ({reconPreview.total_mismatches} versions)`), the affected-users summary (`affected_users.map`), and the mismatch table (`mismatches.slice(0, 100).map`, `ArrowRight`, `formatBytes`) + the `{total_mismatches > 100 && "Showing 100 of N"}` note. All hard-coded English strings verbatim. No `useTranslation` needed (this card is fully hard-coded English).

- [ ] **Step 1: Write the failing test**

```tsx
// VclReconciliationCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReconciliationPreview } from '../../../../types/vcl';
import { VclReconciliationCard } from '../../../../components/vcl/vcl-settings/VclReconciliationCard';

const preview = (over: Partial<ReconciliationPreview> = {}): ReconciliationPreview => ({
  total_mismatches: 0, mismatches: [], affected_users: [], ...over,
});
const base = { reconLoading: false, forceOverQuota: false, onScan: () => {}, onForceChange: () => {}, onApply: () => {} };

describe('VclReconciliationCard', () => {
  it('fires onScan when Scan for Mismatches is clicked', () => {
    const onScan = vi.fn();
    render(<VclReconciliationCard {...base} reconPreview={null} onScan={onScan} />);
    fireEvent.click(screen.getByText('Scan for Mismatches'));
    expect(onScan).toHaveBeenCalledTimes(1);
  });
  it('hides Apply + force checkbox when there are no mismatches', () => {
    render(<VclReconciliationCard {...base} reconPreview={preview({ total_mismatches: 0 })} />);
    expect(screen.queryByText(/^Apply \(/)).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
  it('shows Apply with the mismatch count when there are mismatches', () => {
    render(<VclReconciliationCard {...base} reconPreview={preview({
      total_mismatches: 2,
      mismatches: [
        { file_id: 1, file_path: '/a/b.txt', version_id: 11, version_number: 3, current_version_user_id: 1, current_version_username: 'alice', current_file_owner_id: 2, current_file_owner_username: 'bob', compressed_size: 100 },
      ],
      affected_users: [{ user_id: 2, username: 'bob', quota_delta: 100, current_usage: 0, max_size: 1000, would_exceed_quota: false }],
    })} />);
    expect(screen.getByText('Apply (2 versions)')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).toBeInTheDocument();
    expect(screen.getByText('b.txt')).toBeInTheDocument();
  });
  it('fires onForceChange when the force checkbox toggles', () => {
    const onForceChange = vi.fn();
    render(<VclReconciliationCard {...base} onForceChange={onForceChange}
      reconPreview={preview({ total_mismatches: 1, mismatches: [], affected_users: [] })} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onForceChange).toHaveBeenCalledWith(true);
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (4 tests).
- [ ] **Step 5: Commit** `feat(vcl): extract VclReconciliationCard (F2, #301)`.

---

### Task 7: `VclUserQuotasTable`

**Files:**
- Create: `client/src/components/vcl/vcl-settings/VclUserQuotasTable.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclUserQuotasTable.test.tsx`

**Interfaces:**
- Consumes: `formatBytes`, `formatNumber`, `usageBarColor` (Task 1), `UserVCLStats`.
- Produces:
```ts
import type { UserVCLStats } from '../../../types/vcl';
export function VclUserQuotasTable(props: { users: UserVCLStats[]; onEditUser: (user: UserVCLStats) => void }): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** Move the user-limits table verbatim from `VCLSettings.tsx:491-577`. The inline usage-bar color ternary at line 526 becomes `usageBarColor(usagePercent, 80, 95)` (keep `isWarning`/`isCritical` for the inline TEXT-color ternary — that stays inline, different classes). Keep the Mode/Manual/Auto + status badges, the edit button (`onClick={() => onEditUser(user)}`), the empty-row (`colSpan={8}`), `formatBytes`/`formatNumber`, and all `t('vcl.userQuotas.*')`/`t('common.*')` keys. `useTranslation('admin')` internally.

- [ ] **Step 1: Write the failing test**

```tsx
// VclUserQuotasTable.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { UserVCLStats } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclUserQuotasTable } from '../../../../components/vcl/vcl-settings/VclUserQuotasTable';

const user = (over: Partial<UserVCLStats> = {}): UserVCLStats => ({
  user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500,
  usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic', ...over,
});

describe('VclUserQuotasTable', () => {
  it('renders the empty-state row when there are no users', () => {
    render(<VclUserQuotasTable users={[]} onEditUser={() => {}} />);
    expect(screen.getByText('vcl.userQuotas.noUsers')).toBeInTheDocument();
  });
  it('renders a row per user and fires onEditUser with the user', () => {
    const onEditUser = vi.fn();
    render(<VclUserQuotasTable users={[user({ user_id: 9, username: 'zoe' })]} onEditUser={onEditUser} />);
    expect(screen.getByText('zoe')).toBeInTheDocument();
    fireEvent.click(screen.getByText('common.edit'));
    expect(onEditUser).toHaveBeenCalledWith(expect.objectContaining({ user_id: 9 }));
  });
  it('shows the Manual badge for manual-mode users', () => {
    render(<VclUserQuotasTable users={[user({ vcl_mode: 'manual' })]} onEditUser={() => {}} />);
    expect(screen.getByText('Manual')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (3 tests).
- [ ] **Step 5: Commit** `feat(vcl): extract VclUserQuotasTable (F2, #301)`.

---

### Task 8: `VclEditUserModal`

**Files:**
- Create: `client/src/components/vcl/vcl-settings/VclEditUserModal.tsx`
- Test: `client/src/__tests__/components/vcl/vcl-settings/VclEditUserModal.test.tsx`

**Interfaces:**
- Consumes: `ByteSizeInput` (`../../ui/ByteSizeInput`), `UserVCLStats`, `VCLSettingsUpdate`.
- Produces:
```ts
import type { UserVCLStats, VCLSettingsUpdate } from '../../../types/vcl';
export function VclEditUserModal(props: {
  editingUser: UserVCLStats;
  editForm: VCLSettingsUpdate;
  actionLoading: boolean;
  onMaxSizeChange: (bytes: number) => void;
  onEnabledChange: (v: boolean) => void;
  onCancel: () => void;
  onSave: () => void;
}): JSX.Element;
```
- Consumed by Task 9.

**Porting notes:** Move the modal verbatim from `VCLSettings.tsx:581-629` (the outer `{editingUser && ...}` guard stays in the orchestrator). The `ByteSizeInput` `onChange` → `onMaxSizeChange(bytes)` (was `setEditForm({ ...editForm, max_size_bytes: bytes })`); the enable checkbox `onChange` → `onEnabledChange(e.target.checked)`; cancel → `onCancel`; save → `onSave` (`disabled={actionLoading}`). Keep `editForm.max_size_bytes || 0`, `editForm.is_enabled ?? true`, and all `t('vcl.editModal.*')`/`t('common.*')` keys. `useTranslation('admin')` internally.

- [ ] **Step 1: Write the failing test**

```tsx
// VclEditUserModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { UserVCLStats, VCLSettingsUpdate } from '../../../../types/vcl';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
import { VclEditUserModal } from '../../../../components/vcl/vcl-settings/VclEditUserModal';

const editingUser: UserVCLStats = {
  user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500,
  usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic',
};
const editForm: VCLSettingsUpdate = { max_size_bytes: 1000, is_enabled: true };
const base = { editingUser, editForm, actionLoading: false,
  onMaxSizeChange: () => {}, onEnabledChange: () => {}, onCancel: () => {}, onSave: () => {} };

describe('VclEditUserModal', () => {
  it('fires onSave and onCancel from the footer buttons', () => {
    const onSave = vi.fn(), onCancel = vi.fn();
    render(<VclEditUserModal {...base} onSave={onSave} onCancel={onCancel} />);
    fireEvent.click(screen.getByText('common.save'));
    fireEvent.click(screen.getByText('common.cancel'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
  it('fires onEnabledChange when the enable checkbox toggles', () => {
    const onEnabledChange = vi.fn();
    render(<VclEditUserModal {...base} onEnabledChange={onEnabledChange} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onEnabledChange).toHaveBeenCalledWith(false);
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the component.**
- [ ] **Step 4: Run test + `npx tsc -b`** → PASS (2 tests).
- [ ] **Step 5: Commit** `feat(vcl): extract VclEditUserModal (F2, #301)`.

---

### Task 9: Barrel + `VCLSettings.tsx` orchestrator + integration test

**Files:**
- Create: `client/src/components/vcl/vcl-settings/index.ts`
- Modify: `client/src/components/vcl/VCLSettings.tsx` (full rewrite to orchestrator)
- Test: `client/src/__tests__/components/vcl/VCLSettings.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 1–8 via the barrel, `useVclSettings` (Task 2).

**Barrel** `index.ts` re-exports: `usageBarColor`, `VclMessageBanners`, `VclStorageInfoCard`, `VclStatsGrid`, `VclStorageDetailsCard`, `VclMaintenanceCard`, `VclReconciliationCard`, `VclUserQuotasTable`, `VclEditUserModal`.

**Orchestrator rewrite:** keep the file header comment + default export `VCLSettings`. Call `useVclSettings()`. Keep the `if (loading) return <spinner/>` (169–175) and `if (!overview) return null` (177) verbatim, and the derived `const compressionRatio = overview.compression_ratio; const totalSavings = overview.total_savings_bytes; const savingsPercent = overview.total_size_bytes > 0 ? ((totalSavings / overview.total_size_bytes) * 100) : 0;` (179–183). Structure inside `<div className="space-y-6">`:
1. `<VclMessageBanners error={error} successMessage={successMessage} />`
2. `{storageInfo && <VclStorageInfoCard storageInfo={storageInfo} />}`
3. `<VclStatsGrid overview={overview} totalSavings={totalSavings} savingsPercent={savingsPercent} />`
4. `<VclStorageDetailsCard overview={overview} compressionRatio={compressionRatio} />`
5. `<VclMaintenanceCard actionLoading={actionLoading} onDryRunCleanup={() => handleCleanup(true)} onTriggerCleanup={() => handleCleanup(false)} onRefresh={loadData} />`
6. `<VclReconciliationCard reconPreview={reconPreview} reconLoading={reconLoading} forceOverQuota={forceOverQuota} onScan={handleScanMismatches} onForceChange={setForceOverQuota} onApply={handleApplyReconciliation} />`
7. `<VclUserQuotasTable users={users} onEditUser={handleEditUser} />`
8. `{editingUser && <VclEditUserModal editingUser={editingUser} editForm={editForm} actionLoading={actionLoading} onMaxSizeChange={(bytes) => setEditForm({ ...editForm, max_size_bytes: bytes })} onEnabledChange={(v) => setEditForm({ ...editForm, is_enabled: v })} onCancel={() => setEditingUser(null)} onSave={handleSaveUserSettings} />}`

Delete all now-unused imports (the API functions, `useState`/`useEffect`, `getApiErrorMessage`, `ByteSizeInput`, `formatBytes`/`formatNumber`, `useTranslation` if unused, and the lucide icons only used by moved markup). Keep `useVclSettings` + the barrel imports. Run eslint to catch leftovers.

- [ ] **Step 1: Write the failing integration test**

```tsx
// client/src/__tests__/components/vcl/VCLSettings.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { AdminVCLOverview, UserVCLStats } from '../../../types/vcl';
import type { UseVclSettingsResult } from '../../../hooks/useVclSettings';

const overview: AdminVCLOverview = {
  total_versions: 10, total_size_bytes: 1000, total_compressed_bytes: 400, total_blobs: 5,
  unique_blobs: 4, deduplication_savings_bytes: 100, compression_savings_bytes: 200,
  total_savings_bytes: 300, compression_ratio: 2.5, priority_count: 1, cached_versions_count: 2,
  total_users: 3, last_cleanup_at: null, last_priority_mode_at: null, updated_at: null,
};
const users: UserVCLStats[] = [{ user_id: 1, username: 'alice', max_size_bytes: 1000, current_usage_bytes: 500, usage_percent: 50, total_versions: 4, is_enabled: true, vcl_mode: 'automatic' }];

const hookValue: UseVclSettingsResult = {
  overview, storageInfo: null, users, loading: false, actionLoading: false, error: null,
  successMessage: null, editingUser: null, editForm: {}, setEditForm: vi.fn(),
  reconPreview: null, reconLoading: false, forceOverQuota: false, setForceOverQuota: vi.fn(),
  loadData: vi.fn(), handleCleanup: vi.fn(), handleScanMismatches: vi.fn(),
  handleApplyReconciliation: vi.fn(), handleEditUser: vi.fn(), handleSaveUserSettings: vi.fn(),
  setEditingUser: vi.fn(),
};
vi.mock('../../../hooks/useVclSettings', () => ({ useVclSettings: () => hookValue }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }) }));

import VCLSettings from '../../../components/vcl/VCLSettings';

describe('VCLSettings', () => {
  beforeEach(() => { Object.assign(hookValue, { loading: false, overview, users }); });

  it('renders the stats grid + user table for a populated fixture', () => {
    render(<VCLSettings />);
    expect(screen.getByText('alice')).toBeInTheDocument();           // user table
    expect(screen.getByText('Ownership Reconciliation')).toBeInTheDocument(); // recon card
  });

  it('renders none of the dashboard content while loading (early-return spinner)', () => {
    hookValue.loading = true;
    render(<VCLSettings />);
    expect(screen.queryByText('alice')).not.toBeInTheDocument();
    expect(screen.queryByText('Ownership Reconciliation')).not.toBeInTheDocument();
  });

  it('renders nothing when overview is null (and not loading)', () => {
    Object.assign(hookValue, { loading: false, overview: null });
    const { container } = render(<VCLSettings />);
    expect(container).toBeEmptyDOMElement();
  });
});
```
> Note: `overview: null` is not assignable to the `UseVclSettingsResult.overview` type as a plain reassignment via `Object.assign` on a typed const is fine (widening at runtime); if TS complains, cast the override object `as Partial<UseVclSettingsResult>`.

- [ ] **Step 2: Run to verify fail** → FAIL (old shape / barrel not built).
- [ ] **Step 3: Write the barrel, then rewrite `VCLSettings.tsx`** per the structure above.
- [ ] **Step 4: Full verification**

Run: `cd client ; npx vitest run src/__tests__/components/vcl/VCLSettings.test.tsx` → PASS (3 tests).
Run: `cd client ; node -e "console.log(require('fs').readFileSync('src/components/vcl/VCLSettings.tsx','utf8').split(/\r?\n/).length)"` → under 500 (target ~120).
Run: `cd client ; npx tsc -b` → no errors.
Run: `cd client ; npx eslint src/components/vcl/VCLSettings.tsx src/components/vcl/vcl-settings src/hooks/useVclSettings.ts` → 0 errors (no unused imports).

- [ ] **Step 5: Commit** `refactor(vcl): compose VCLSettings from useVclSettings + vcl-settings/* (F2, #301)`.

---

## Final Verification (after all tasks)

- [ ] `cd client ; npx eslint .` → 0 errors.
- [ ] `cd client ; npm run build` → green (tsc -b + vite).
- [ ] `cd client ; npx vitest run` → full suite green.
- [ ] `VCLSettings.tsx` < 500 lines.
- [ ] Update `client/src/components/CLAUDE.md` `vcl/` row to note the `vcl-settings/` decomposition + `useVclSettings` hook (docs-only; fold into the Task 9 commit or a trailing `docs(vcl): ...` commit).
- [ ] Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of every moved block, especially `loadData`'s `Promise.all`, the reconciliation handlers, and the derived-value computation).
