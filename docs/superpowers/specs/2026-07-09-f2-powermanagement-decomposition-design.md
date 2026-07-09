# F2 — PowerManagement Page Decomposition (Design)

**Date:** 2026-07-09
**Finding:** F2 (#301, part of #298) — 22 non-test components > 500 lines violate the
`pages/CLAUDE.md` convention ("minimal logic in page files").
**Scope of this spec:** the first F2 page — `client/src/pages/PowerManagement.tsx`
(currently 632 lines). One page = one PR. Each subsequent F2 page gets its own
spec → plan → PR.

## Goal

Bring `PowerManagement.tsx` under 500 lines by extracting three self-contained
subcomponents into `client/src/components/power/`, and pull the one piece of real
logic (auto-scaling threshold validation) into a pure, unit-tested function.

This is a **pure move-refactor**: no behavior, UX, or layout changes. The rendered
output must be identical.

## Current state

`PowerManagement.tsx` (632 lines) already had its data layer migrated to TanStack
Query (`usePowerManagementData`, #393). What remains oversized is the render tree
plus the auto-scaling edit logic. The page currently holds:

- Data via `usePowerManagementData()` (status, presets, demands, intensities,
  history, autoScaling, dynamicConfig, loading, error, lastUpdated, refetch).
- Local state: `busy`, `editorPreset`, `editingAutoScaling`, `editAutoScaling`.
- Handlers: `handleRefresh`, `handlePresetSelect`, `handleUnregisterDemand`,
  `handleToggleAutoScaling`, `handleStartEditAutoScaling`,
  `handleCancelEditAutoScaling`, `handleSaveAutoScaling` (with inline validation),
  `handleSwitchBackend`, `handleSavePreset`, `handleDeletePreset`.
- Render: header (backend indicator + switch + refresh) · 4 StatCards ·
  `DynamicModeSection` · preset selection card (incl. the auto-scaling **toggle**
  button) · preset details · service intensity · demands · history ·
  `GpuPowerCard` · `AuthorityPanel` · `BoostRulesEditor` · auto-scaling **config**
  card (~120 lines, edit + display) · permission warning banner · permission
  status card · preset editor modal.

Existing precedent: `DynamicModeSection` is already an extracted subcomponent that
takes `{ config, isAdmin, busy, onBusyChange, onRefresh }`. The new
`AutoScalingSection` mirrors this contract.

## Components to extract

### A. `components/power/AutoScalingSection.tsx`

The auto-scaling **config card** (the ~120-line threshold editor: display mode +
edit mode + save). Owns `editingAutoScaling` / `editAutoScaling` state internally.

- **Props:** `{ autoScaling: AutoScalingConfig; isAdmin: boolean; busy: boolean;
  onBusyChange: (busy: boolean) => void; onRefresh: () => void; t: TFunction }`
  (mirrors `DynamicModeSection`).
- **Behavior:** on save, validates via the pure helper, calls
  `updateAutoScalingConfig`, toasts, then `onRefresh()`. Uses `onBusyChange` to
  drive the shared page `busy` flag (so cross-section concurrency stays blocked,
  exactly as today).
- **Validation** extracted to a pure function (see below).

> The enable/disable **toggle button** lives in the preset-selection card and stays
> there (moving it would be a UX change). The small `handleToggleAutoScaling`
> remains in the page.

### B. `components/power/PermissionStatusCard.tsx`

The permission warning banner **and** the 4-tile permission status grid (shown only
for the Linux backend). Pure presentational.

- **Props:** `{ status: PowerStatusResponse; t: TFunction }`.
- Renders nothing / the banner / the grid based on
  `status.is_using_linux_backend` and `status.permission_status` exactly as today.

### C. `components/power/PowerStatusCards.tsx`

The row of 4 top `StatCard`s (active preset, current property, CPU frequency,
active demands). Pure presentational.

- **Props:** `{ status: PowerStatusResponse | null; activePreset?: PowerPreset;
  currentProperty?: ServicePowerProperty; demands: PowerDemandInfo[];
  lastUpdated: Date | null; t: TFunction }`.
- The "highest demand" reduce logic moves with the card (kept inline; it is
  display-only).

## Pure logic: `isValidAutoScaling`

Extract the inline validation from `handleSaveAutoScaling` into a pure function,
co-located with `AutoScalingSection` (or `components/power/utils`):

```ts
// true = valid, false = invalid (surge > medium > low, each 0–100, cooldown >= 0)
export function isValidAutoScaling(cfg: AutoScalingConfig): boolean
```

This is the only non-trivial logic in the file and the one thing worth TDD-ing
independently of the DOM.

## Result

`PowerManagement.tsx`: ~632 → **~380–420 lines**. It becomes: the data hook, the
preset/backend/refresh/toggle handlers, and composition of the extracted pieces.

## Testing (full — component tests requested)

The repo already has an RTL + i18n component-test pattern (`ConfirmDialog.test.tsx`,
`PowerMenu.test.tsx`, `ConnectedDevicesWidget.test.tsx`), so no new infra.

1. **Pure/TDD:** `isValidAutoScaling` — RED→GREEN, covering the ordering and range
   rules and the boundary cases.
2. **Component tests (RTL):**
   - `AutoScalingSection`: renders display values; entering edit mode shows inputs;
     an invalid threshold set blocks save (no `updateAutoScalingConfig` call, error
     toast); a valid save calls `updateAutoScalingConfig` + `onRefresh`.
   - `PermissionStatusCard`: renders the 4 tiles; the warning banner appears only
     when `has_write_access` is false; renders nothing without a Linux backend.
   - `PowerStatusCards`: renders the four cards with the provided values.

## Verification

- New tests green.
- Full frontend vitest suite green (currently 603) — no regressions.
- `eslint .` 0 errors; `npm run build` (tsc -b + vite) green.

## Out of scope

- No behavior/UX/layout change (the toggle button stays in the preset card).
- No changes to the data hook, the preset editor modal, `DynamicModeSection`,
  `GpuPowerCard`, `AuthorityPanel`, or `BoostRulesEditor`.
- Other F2 pages (SharesPage, FileManager, …) — each its own later spec/PR.
