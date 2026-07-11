# VCLSettings.tsx Decomposition — Design (F2 / #301)

**Date:** 2026-07-11
**Finding:** F2 (components > 500 lines), umbrella issue #301.
**Target:** `client/src/components/vcl/VCLSettings.tsx` — currently **633 lines**.

## Goal

Behavior-preserving decomposition of `VCLSettings.tsx` (the admin VCL settings /
stats / maintenance / reconciliation dashboard) into one data/state hook, one
pure helper, and a directory of presentational components under a new
`components/vcl/vcl-settings/`.

**Non-goals:** no change to API calls, endpoints, i18n keys, copy (the file
mixes `t('vcl.*')` in the `admin` namespace with hard-coded English strings,
mostly in the Ownership-Reconciliation section — both stay **verbatim**; do NOT
introduce or change i18n, that is scope creep tracked in issue #406), Tailwind
styling, `confirm(...)` wording, `setTimeout(... , 5000/3000)` success-message
timers, or any computed value. The component keeps its path
(`components/vcl/VCLSettings.tsx`, **default export** `VCLSettings`) so the
`vcl/index.ts` barrel and consumers are untouched. `VCLTrackingPanel` and
`VersionHistoryModal` (siblings in `vcl/`) are unrelated and untouched.

## Constraints

- Every extracted value is **byte-identical** in behavior: same seven vcl API
  calls, same `Promise.all` (`getStorageInfo().catch(() => null)`), same
  error/success handling + timers, same `confirm(...)` strings, same derived
  values (`compressionRatio`, `totalSavings`, `savingsPercent`), same
  `slice(0, 100)` mismatch cap + "Showing 100 of N" note, same
  `formatBytes`/`formatNumber` usage.
- Extracted components are **presentational**: props in, callbacks in, no data
  fetching. The extracted hook owns all fetching/state.
- Tests are T7-conform: assert on role/text/title, never Tailwind classes;
  fixtures are complete objects of the real types (`AdminVCLOverview`,
  `UserVCLStats`, `VCLStorageInfo`, `ReconciliationPreview`, `VCLSettingsUpdate`).
- Hard-coded English strings preserved verbatim; the `t('vcl.*')` / `t('common.*')`
  calls stay as `t()` (with their existing fallback second args where present).

## Current inline blocks (what moves)

| Block | Current lines | Destination |
|---|---|---|
| 12 `useState` + `useTranslation('admin')` + mount effect + all handlers (`loadData`, `handleCleanup`, `handleScanMismatches`, `handleApplyReconciliation`, `handleEditUser`, `handleSaveUserSettings`) | 46–167 | `hooks/useVclSettings.ts` |
| Disk/quota usage-bar color ternary (`>= crit red : >= warn amber : sky`) | 236, 526 | `vcl-settings/usageBarColor.ts` (pure) |
| Error + success banners | 188–199 | `vcl-settings/VclMessageBanners.tsx` |
| Storage info card | 202–247 | `vcl-settings/VclStorageInfoCard.tsx` |
| Stats grid (4 cards) | 250–293 | `vcl-settings/VclStatsGrid.tsx` |
| Detailed stats card (8 fields) | 296–344 | `vcl-settings/VclStorageDetailsCard.tsx` |
| Maintenance actions card | 347–378 | `vcl-settings/VclMaintenanceCard.tsx` |
| Ownership reconciliation card (controls + affected-users + mismatch table) | 381–488 | `vcl-settings/VclReconciliationCard.tsx` |
| User limits table | 491–577 | `vcl-settings/VclUserQuotasTable.tsx` |
| Edit user modal | 580–629 | `vcl-settings/VclEditUserModal.tsx` |

## New units & interfaces

### `hooks/useVclSettings.ts`

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

Body ports lines 46–167 verbatim: the 12 `useState`, `useTranslation('admin')`,
the mount effect (`loadData`), and every handler (same `Promise.all`, same
`confirm(...)` strings, same `t('vcl.*')` message keys, same `setTimeout` timers,
same `getApiErrorMessage` fallbacks incl. the hard-coded English ones for the
reconciliation handlers). `setEditForm`, `setEditingUser`, `setForceOverQuota`
are exposed so the presentational modal/reconciliation card can drive their form
state through orchestrator-wired callbacks.

### `vcl-settings/usageBarColor.ts` (pure)

```ts
export function usageBarColor(percent: number, warn: number, crit: number): string;
```

Returns `percent >= crit ? 'bg-red-500' : percent >= warn ? 'bg-amber-500' :
'bg-sky-500'`. Covers both inline bar ternaries: storage disk bar =
`usageBarColor(disk_used_percent, 70, 90)` (line 236); user-quota bar =
`usageBarColor(usage_percent, 80, 95)` (line 526). The user-row **text**-color
ternary (`text-red-400`/`text-amber-400`/`text-slate-300`, different classes)
stays inline in `VclUserQuotasTable`.

### Presentational components (`components/vcl/vcl-settings/`)

- **`VclMessageBanners.tsx`** — `{ error: string | null; successMessage: string | null }`.
  The two banners (188–199); each renders only when its prop is set.
- **`VclStorageInfoCard.tsx`** — `{ storageInfo: VCLStorageInfo }`. Storage card
  (203–246), using `formatBytes` (from `../../../api/vcl`), `formatNumber` (from
  `../../../lib/formatters`), `usageBarColor(storageInfo.disk_used_percent, 70, 90)`,
  and the two `t('vcl.storageInfo.*', 'fallback')` calls + the hard-coded
  "Custom Path" badge. `useTranslation('admin')` internally. The `{storageInfo && }`
  guard stays in the orchestrator.
- **`VclStatsGrid.tsx`** — `{ overview: AdminVCLOverview; totalSavings: number;
  savingsPercent: number }`. The 4 stat cards (250–293).
- **`VclStorageDetailsCard.tsx`** — `{ overview: AdminVCLOverview;
  compressionRatio: number }`. The detailed-stats card (296–344).
- **`VclMaintenanceCard.tsx`** — `{ actionLoading: boolean; onDryRunCleanup:
  () => void; onTriggerCleanup: () => void; onRefresh: () => void }`. The
  maintenance card (347–378).
- **`VclReconciliationCard.tsx`** — `{ reconPreview: ReconciliationPreview | null;
  reconLoading: boolean; forceOverQuota: boolean; onScan: () => void;
  onForceChange: (v: boolean) => void; onApply: () => void }`. The whole
  reconciliation card (381–488): scan button, force checkbox, apply button,
  affected-users summary, and the mismatch table (`slice(0, 100)` + "Showing 100
  of N"). All hard-coded English strings verbatim. `formatBytes` used.
- **`VclUserQuotasTable.tsx`** — `{ users: UserVCLStats[]; onEditUser:
  (user: UserVCLStats) => void }`. The user-limits table (491–577), using
  `formatBytes`/`formatNumber`, `usageBarColor(usage_percent, 80, 95)` for the
  bar, the inline text-color ternary, the Mode/Manual/Auto + status badges, and
  the empty-row (`colSpan={8}`). `useTranslation('admin')` internally.
- **`VclEditUserModal.tsx`** — `{ editingUser: UserVCLStats; editForm:
  VCLSettingsUpdate; actionLoading: boolean; onMaxSizeChange: (bytes: number) =>
  void; onEnabledChange: (v: boolean) => void; onCancel: () => void; onSave:
  () => void }`. The modal (581–629) with `ByteSizeInput`. The
  `{editingUser && }` guard stays in the orchestrator.

### `vcl-settings/index.ts`

Barrel exporting all components + `usageBarColor`.

### `VCLSettings.tsx` (after)

Calls `useVclSettings()`. Keeps the `if (loading) return <spinner/>` (169–175)
and `if (!overview) return null` (177) early-returns verbatim, and the derived
`compressionRatio`/`totalSavings`/`savingsPercent` (179–183). Composes
`VclMessageBanners`, `{storageInfo && <VclStorageInfoCard .../>}`, `VclStatsGrid`,
`VclStorageDetailsCard`, `VclMaintenanceCard` (`onDryRunCleanup={() =>
handleCleanup(true)}`, `onTriggerCleanup={() => handleCleanup(false)}`,
`onRefresh={loadData}`), `VclReconciliationCard` (`onScan={handleScanMismatches}`,
`onForceChange={setForceOverQuota}`, `onApply={handleApplyReconciliation}`),
`VclUserQuotasTable` (`onEditUser={handleEditUser}`), and
`{editingUser && <VclEditUserModal ... onMaxSizeChange={(bytes) =>
setEditForm({ ...editForm, max_size_bytes: bytes })} onEnabledChange={(v) =>
setEditForm({ ...editForm, is_enabled: v })} onCancel={() =>
setEditingUser(null)} onSave={handleSaveUserSettings} />}`. Target: **~120
lines** (from 633).

## Testing

Broad + integration (Vitest, T7-conform):

- **`usageBarColor`** — `(95, 80, 95) → red`, `(85, 80, 95) → amber`,
  `(50, 80, 95) → sky`; storage thresholds `(90, 70, 90) → red`,
  `(70, 70, 90) → amber`, `(10, 70, 90) → sky`.
- **`useVclSettings`** — `renderHook`: mount loads overview/users/storage
  (`Promise.all`); `handleCleanup(false)` with `confirm` returning `false` makes
  no `triggerCleanup` call; `handleScanMismatches` with 0 mismatches sets the
  "No ownership mismatches found" success message; `handleSaveUserSettings`
  calls `updateUserSettingsAdmin(editingUser.user_id, editForm)`. Mock
  `../api/vcl`, `../lib/errorHandling`, and `window.confirm`.
- **Component renders** — `VclMessageBanners` (error only / success only / both),
  `VclStorageInfoCard` (path + Custom Path badge when `is_custom_path`),
  `VclStatsGrid` (totals + savings %), `VclStorageDetailsCard` (compression ratio,
  "Never" when no last-cleanup), `VclMaintenanceCard` (each callback fires),
  `VclReconciliationCard` (scan fires; apply + force-checkbox shown only when
  `total_mismatches > 0`; "Showing 100 of N" when > 100), `VclUserQuotasTable`
  (row per user, empty-row when none, edit fires with user, Manual/Auto badge),
  `VclEditUserModal` (save/cancel fire, enabled checkbox fires onEnabledChange).
- **Integration** (`__tests__/components/vcl/VCLSettings.test.tsx`) — mock the
  hook; assert stats grid + user table render for a populated fixture; `loading`
  → spinner; `overview: null` → renders nothing.

## Verification gates

- `VCLSettings.tsx` < 500 lines (target ~120).
- `eslint .` — 0 errors.
- `npm run build` (tsc -b + vite) — green (`import type` for type-only imports —
  `verbatimModuleSyntax` enforced by `tsc -b`, not vitest).
- `vitest run` — full suite green.
- Multi-agent whole-branch review — READY TO MERGE (field-for-field audit of
  every moved block, especially `loadData`'s `Promise.all`, the reconciliation
  handlers, and the derived-value computation).
