# F2 — PowerManagement Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `client/src/pages/PowerManagement.tsx` (632 lines) into three focused `components/power/` subcomponents + one pure validation helper, bringing the page under 500 lines with no behavior/UX/layout change.

**Architecture:** Pure move-refactor. Extract the auto-scaling threshold config card, the permission panels, and the top status-card row into their own components. The one piece of real logic (auto-scaling validation) becomes a pure function. New components mirror the existing `DynamicModeSection` contract (`useTranslation` internally, `busy`/`onBusyChange`/`onRefresh` props for the stateful one).

**Tech Stack:** React 18 + TypeScript, TanStack Query (already in place), Tailwind, react-i18next, Vitest + React Testing Library.

## Global Constraints

- **No behavior, UX, or layout change.** Rendered DOM must be identical. In particular: do NOT add wrapper `<div>`s to reach elements in tests (`StatCard` does not forward `data-testid` — its props are fixed `label, value, unit, subValue, color, icon`; wrapping a card would change the grid layout). Assert via text or via a component's *own* root `data-testid`.
- The auto-scaling **enable/disable toggle button** lives in the preset-selection card and stays there (`handleToggleAutoScaling` stays in the page). Only the auto-scaling **config card** (`:456-580`) moves.
- New components live in `client/src/components/power/` and use `useTranslation(['system','common'])` **internally** (no `t` prop) — matching `DynamicModeSection`/`OsAutoSuspendCard`.
- Component tests go in `client/src/__tests__/components/power/`, following `OsAutoSuspendCard.test.tsx`: explicit `import { describe, expect, it, vi, beforeEach } from 'vitest'`; `vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))`; `vi.mock` for api + `react-hot-toast`; query the component's own `data-testid` via `container.querySelector('[data-testid="…"]')`.
- **Verification gate (Task 5):** `npx vitest run` all green (currently 603 + the new tests), `npx eslint .` 0 errors, `npm run build` (tsc -b + vite) green.
- Windows shell: chain with `;`, never `&&`.

---

### Task 1: Pure `isValidAutoScaling` helper

**Files:**
- Modify: `client/src/components/power/utils.ts` (append)
- Test: `client/src/__tests__/components/power/isValidAutoScaling.test.ts`

**Interfaces:**
- Produces: `isValidAutoScaling(cfg: Pick<AutoScalingConfig, 'cpu_surge_threshold' | 'cpu_medium_threshold' | 'cpu_low_threshold' | 'cooldown_seconds'>): boolean` — `true` when `surge > medium > low`, each threshold in `[0,100]`, and `cooldown_seconds >= 0`. It is the exact negation of the inline guard in `PowerManagement.tsx:145-155`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/power/isValidAutoScaling.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { isValidAutoScaling } from '../../../components/power/utils';

const base = {
  cpu_surge_threshold: 90,
  cpu_medium_threshold: 60,
  cpu_low_threshold: 30,
  cooldown_seconds: 15,
};

describe('isValidAutoScaling', () => {
  it('accepts a correctly ordered config', () => {
    expect(isValidAutoScaling(base)).toBe(true);
  });

  it('rejects when surge is not strictly greater than medium', () => {
    expect(isValidAutoScaling({ ...base, cpu_surge_threshold: 60 })).toBe(false);
  });

  it('rejects when medium is not strictly greater than low', () => {
    expect(isValidAutoScaling({ ...base, cpu_medium_threshold: 30 })).toBe(false);
  });

  it('rejects an out-of-range threshold', () => {
    expect(isValidAutoScaling({ ...base, cpu_surge_threshold: 120 })).toBe(false);
    expect(isValidAutoScaling({ ...base, cpu_low_threshold: -1 })).toBe(false);
  });

  it('rejects a negative cooldown', () => {
    expect(isValidAutoScaling({ ...base, cooldown_seconds: -5 })).toBe(false);
  });

  it('accepts boundary values 0 and 100 while preserving ordering', () => {
    expect(isValidAutoScaling({
      cpu_surge_threshold: 100, cpu_medium_threshold: 50, cpu_low_threshold: 0, cooldown_seconds: 0,
    })).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/power/isValidAutoScaling.test.ts`
Expected: FAIL — `isValidAutoScaling` is not exported from `utils.ts`.

- [ ] **Step 3: Append the implementation to `utils.ts`**

`client/src/components/power/utils.ts` already imports several types from `../../api/power-management`. Add `AutoScalingConfig` to that existing `import type { … }` line (do not add a second import statement), then append:

```ts
/**
 * Validates auto-scaling CPU thresholds: surge > medium > low, each in [0,100],
 * cooldown >= 0. Pure — extracted from PowerManagement's save handler.
 */
export function isValidAutoScaling(
  cfg: Pick<AutoScalingConfig, 'cpu_surge_threshold' | 'cpu_medium_threshold' | 'cpu_low_threshold' | 'cooldown_seconds'>,
): boolean {
  const inRange = (n: number) => n >= 0 && n <= 100;
  return (
    cfg.cpu_surge_threshold > cfg.cpu_medium_threshold &&
    cfg.cpu_medium_threshold > cfg.cpu_low_threshold &&
    inRange(cfg.cpu_surge_threshold) &&
    inRange(cfg.cpu_medium_threshold) &&
    inRange(cfg.cpu_low_threshold) &&
    cfg.cooldown_seconds >= 0
  );
}
```

> If `utils.ts` has no existing `import type … from '../../api/power-management'` line, add `import type { AutoScalingConfig } from '../../api/power-management';` at the top.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/power/isValidAutoScaling.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/utils.ts client/src/__tests__/components/power/isValidAutoScaling.test.ts
git commit -m "refactor(power): extract pure isValidAutoScaling helper (#301)"
```

---

### Task 2: `PowerStatusCards` component

Extracts the four top `StatCard`s. **Source:** `PowerManagement.tsx:300-344` — the `<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">…</div>` block right after `{/* Status Cards */}`, up to (not including) `{/* Dynamic Mode Section */}`.

**Files:**
- Create: `client/src/components/power/PowerStatusCards.tsx`
- Test: `client/src/__tests__/components/power/PowerStatusCards.test.tsx`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: named export `PowerStatusCards` with props
  `{ status: PowerStatusResponse | null; activePreset?: PowerPreset; currentProperty?: ServicePowerProperty; demands: PowerDemandInfo[]; lastUpdated: Date | null }`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/power/PowerStatusCards.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PowerStatusCards } from '../../../components/power/PowerStatusCards';
import type { PowerDemandInfo } from '../../../api/power-management';

const demands = [
  { source: 'a', level: 'low' },
  { source: 'b', level: 'medium' },
] as unknown as PowerDemandInfo[];

describe('PowerStatusCards', () => {
  it('renders all four stat cards including the active-demands count', () => {
    render(
      <PowerStatusCards
        status={{ current_frequency_mhz: 3400 } as never}
        activePreset={{ id: 1, name: 'Balanced', description: 'desc' } as never}
        currentProperty="low"
        demands={demands}
        lastUpdated={new Date(0)}
      />,
    );
    expect(screen.getByText('system:power.statusCards.activePreset')).toBeTruthy();
    expect(screen.getByText('system:power.statusCards.currentProperty')).toBeTruthy();
    expect(screen.getByText('system:power.statusCards.cpuFrequency')).toBeTruthy();
    expect(screen.getByText('system:power.statusCards.activeDemands')).toBeTruthy();
    // active-demands StatCard value is `demands.length`
    expect(screen.getByText('2')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/power/PowerStatusCards.test.tsx`
Expected: FAIL — cannot resolve `../../../components/power/PowerStatusCards`.

- [ ] **Step 3: Create the component**

Create `client/src/components/power/PowerStatusCards.tsx`. Imports:
```tsx
import { useTranslation } from 'react-i18next';
import { StatCard } from '../ui/StatCard';
import { getPresetIcon } from './utils';
import {
  PROFILE_INFO,
  PROPERTY_INFO,
  formatClockSpeed,
  type PowerStatusResponse,
  type PowerDemandInfo,
  type ServicePowerProperty,
  type PowerPreset,
} from '../../api/power-management';
```
Signature + props:
```tsx
interface PowerStatusCardsProps {
  status: PowerStatusResponse | null;
  activePreset?: PowerPreset;
  currentProperty?: ServicePowerProperty;
  demands: PowerDemandInfo[];
  lastUpdated: Date | null;
}

export function PowerStatusCards({
  status, activePreset, currentProperty, demands, lastUpdated,
}: PowerStatusCardsProps) {
  const { t } = useTranslation(['system', 'common']);
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* the four <StatCard …/> elements, moved verbatim from PowerManagement.tsx:301-343 */}
    </div>
  );
}
```
**Move the four `<StatCard …/>` elements verbatim** from `PowerManagement.tsx:301-343` into the returned `<div>`. No expression edits — `status`, `activePreset`, `currentProperty`, `demands`, `lastUpdated`, `t`, `PROPERTY_INFO`, `PROFILE_INFO`, `formatClockSpeed`, `getPresetIcon` are all in scope via props/imports. Do NOT add any `data-testid` (the test asserts on text).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/power/PowerStatusCards.test.tsx`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/PowerStatusCards.tsx client/src/__tests__/components/power/PowerStatusCards.test.tsx
git commit -m "refactor(power): extract PowerStatusCards (#301)"
```

---

### Task 3: `PermissionStatusCard` component

Extracts the permission warning banner + the 4-tile status grid. **Source:** `PowerManagement.tsx:582-660` — the `{/* Permission Warning Banner */}` block (`:582-604`) and the `{/* Permission Status (Linux backend only) */}` block (`:606-660`).

**Files:**
- Create: `client/src/components/power/PermissionStatusCard.tsx`
- Test: `client/src/__tests__/components/power/PermissionStatusCard.test.tsx`

**Interfaces:**
- Produces: named export `PermissionStatusCard` with props `{ status: PowerStatusResponse | null }`. Returns `null` unless `status?.is_using_linux_backend && status.permission_status`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/power/PermissionStatusCard.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PermissionStatusCard } from '../../../components/power/PermissionStatusCard';

const linuxStatus = (writeAccess: boolean) => ({
  is_using_linux_backend: true,
  permission_status: {
    has_write_access: writeAccess, user: 'baluhost',
    in_cpufreq_group: true, sudo_available: false,
  },
}) as never;

describe('PermissionStatusCard', () => {
  it('renders nothing without a Linux backend', () => {
    const { container } = render(<PermissionStatusCard status={{ is_using_linux_backend: false } as never} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows the warning banner when write access is missing', () => {
    const { container } = render(<PermissionStatusCard status={linuxStatus(false)} />);
    expect(container.querySelector('[data-testid="power-permission-warning"]')).not.toBeNull();
  });

  it('hides the warning banner when write access is present', () => {
    const { container } = render(<PermissionStatusCard status={linuxStatus(true)} />);
    expect(container.querySelector('[data-testid="power-permission-warning"]')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/power/PermissionStatusCard.test.tsx`
Expected: FAIL — cannot resolve the module.

- [ ] **Step 3: Create the component**

Create `client/src/components/power/PermissionStatusCard.tsx`:
```tsx
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import type { PowerStatusResponse } from '../../api/power-management';

interface PermissionStatusCardProps {
  status: PowerStatusResponse | null;
}

export function PermissionStatusCard({ status }: PermissionStatusCardProps) {
  const { t } = useTranslation(['system', 'common']);
  if (!status?.is_using_linux_backend || !status.permission_status) return null;
  return (
    <>
      {/* Permission Warning Banner — moved from PowerManagement.tsx:583-604 */}
      {/* Permission Status grid — moved from PowerManagement.tsx:607-659 */}
    </>
  );
}
```
- **Move the warning-banner block** (`PowerManagement.tsx:583-603`, the inner `<div className="mb-4 rounded-xl border border-amber-500/30 …">…</div>`) into the fragment, wrapped so it only shows when write access is missing:
  `{!status.permission_status.has_write_access && ( <div data-testid="power-permission-warning" className="mb-4 rounded-xl …"> … </div> )}`
  — i.e. add `data-testid="power-permission-warning"` to that banner's root `<div>` and keep only the `!…has_write_access` guard (the `is_using_linux_backend && permission_status` guards are handled by the early return).
- **Move the status-grid block** (`PowerManagement.tsx:608-659`, the `<div className="card border-slate-700/50 p-4 sm:p-6"> … </div>`) into the fragment verbatim. All `status.permission_status.*` references stay in scope.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/power/PermissionStatusCard.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/PermissionStatusCard.tsx client/src/__tests__/components/power/PermissionStatusCard.test.tsx
git commit -m "refactor(power): extract PermissionStatusCard (#301)"
```

---

### Task 4: `AutoScalingSection` component

Extracts the auto-scaling **config card**. **Source:** `PowerManagement.tsx:456-580` (the `{isAdmin && autoScaling && ( <div className="card …"> … </div> )}` block) plus the edit state (`editingAutoScaling`, `editAutoScaling`) and the handlers `handleStartEditAutoScaling` (`:129-134`), `handleCancelEditAutoScaling` (`:136-139`), `handleSaveAutoScaling` (`:141-169`). Validation via `isValidAutoScaling` (Task 1).

**Files:**
- Create: `client/src/components/power/AutoScalingSection.tsx`
- Test: `client/src/__tests__/components/power/AutoScalingSection.test.tsx`

**Interfaces:**
- Consumes: `isValidAutoScaling` (Task 1); `updateAutoScalingConfig` (api).
- Produces: named export `AutoScalingSection` with props
  `{ autoScaling: AutoScalingConfig; dimmed: boolean; busy: boolean; onBusyChange: (b: boolean) => void; onRefresh: () => void }`.
  (`isAdmin` gating stays in the page — the page renders the section only when `isAdmin && autoScaling`.)

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/power/AutoScalingSection.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../../api/power-management', async () => {
  const actual = await vi.importActual<typeof import('../../../api/power-management')>('../../../api/power-management');
  return { ...actual, updateAutoScalingConfig: vi.fn() };
});

import { updateAutoScalingConfig } from '../../../api/power-management';
import { AutoScalingSection } from '../../../components/power/AutoScalingSection';

const cfg = {
  enabled: true,
  cpu_surge_threshold: 90, cpu_medium_threshold: 60, cpu_low_threshold: 30,
  cooldown_seconds: 15, use_cpu_monitoring: true,
} as never;

function renderSection() {
  const onRefresh = vi.fn();
  const onBusyChange = vi.fn();
  render(
    <AutoScalingSection
      autoScaling={cfg}
      dimmed={false}
      busy={false}
      onBusyChange={onBusyChange}
      onRefresh={onRefresh}
    />,
  );
  return { onRefresh, onBusyChange };
}

describe('AutoScalingSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the config card in display mode', () => {
    const { container } = renderSection();
    expect(container.querySelector('[data-testid="auto-scaling-section"]')).not.toBeNull();
  });

  it('blocks save on an invalid threshold ordering (no API call)', async () => {
    (updateAutoScalingConfig as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    renderSection();
    fireEvent.click(screen.getByTestId('auto-scaling-edit'));
    // surge (10) below medium (60) → invalid ordering
    fireEvent.change(screen.getByTestId('auto-scaling-input-surge'), { target: { value: '10' } });
    fireEvent.click(screen.getByTestId('auto-scaling-save'));
    await waitFor(() => {});
    expect(updateAutoScalingConfig).not.toHaveBeenCalled();
  });

  it('saves a valid edit: calls the API and onRefresh', async () => {
    (updateAutoScalingConfig as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    const { onRefresh } = renderSection();
    fireEvent.click(screen.getByTestId('auto-scaling-edit'));
    fireEvent.click(screen.getByTestId('auto-scaling-save'));
    await waitFor(() => expect(updateAutoScalingConfig).toHaveBeenCalledTimes(1));
    expect(onRefresh).toHaveBeenCalled();
  });
});
```

> `screen.getByTestId` is used here (React Testing Library resolves it against the document body); the `PermissionStatusCard` test uses `container.querySelector` — both work. Do not depend on `@testing-library/jest-dom` matchers (`.toBeInTheDocument()`); this suite uses plain `.toBeTruthy()`/`.not.toBeNull()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/power/AutoScalingSection.test.tsx`
Expected: FAIL — cannot resolve `AutoScalingSection`.

- [ ] **Step 3: Create the component**

Create `client/src/components/power/AutoScalingSection.tsx`:
```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { AdminBadge } from '../ui/AdminBadge';
import { handleApiError } from '../../lib/errorHandling';
import { updateAutoScalingConfig, type AutoScalingConfig } from '../../api/power-management';
import { isValidAutoScaling } from './utils';

interface AutoScalingSectionProps {
  autoScaling: AutoScalingConfig;
  dimmed: boolean;
  busy: boolean;
  onBusyChange: (b: boolean) => void;
  onRefresh: () => void;
}

export function AutoScalingSection({
  autoScaling, dimmed, busy, onBusyChange, onRefresh,
}: AutoScalingSectionProps) {
  const { t } = useTranslation(['system', 'common']);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<AutoScalingConfig | null>(null);

  const startEdit = () => {
    setDraft({ ...autoScaling });
    setEditing(true);
  };
  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
  };
  const save = async () => {
    if (!draft || busy) return;
    if (!isValidAutoScaling(draft)) {
      toast.error(t('system:power.autoScaling.validationError'));
      return;
    }
    onBusyChange(true);
    try {
      await updateAutoScalingConfig(draft);
      onRefresh();
      setEditing(false);
      setDraft(null);
      toast.success(t('system:power.autoScaling.thresholdsSaved'));
    } catch (err) {
      handleApiError(err, t('system:power.autoScaling.thresholdsSaveFailed'));
    } finally {
      onBusyChange(false);
    }
  };

  return (
    <div
      data-testid="auto-scaling-section"
      className={`card border-slate-700/50 p-4 sm:p-6 ${dimmed ? 'opacity-50 pointer-events-none' : ''}`}
    >
      {/* header (title + AdminBadge + edit / cancel+save buttons) and body
          (edit inputs vs display), moved verbatim from PowerManagement.tsx:459-578 */}
    </div>
  );
}
```
Move the **inner** card content from `PowerManagement.tsx:459-578` (everything inside the `<div className="card …">`, i.e. the header `<div className="mb-3 …">…</div>` and the `{editingAutoScaling && editAutoScaling ? (…) : (…)}` body) into this component's `<div>`, applying exactly these renames — nothing else changes:
- `editingAutoScaling` → `editing`
- `editAutoScaling` → `draft` (display reads like `draft.cpu_surge_threshold`; the four `setEditAutoScaling({ ...editAutoScaling, … })` onChange calls → `setDraft({ ...draft!, … })`)
- `handleStartEditAutoScaling` → `startEdit`
- `handleCancelEditAutoScaling` → `cancelEdit`
- `handleSaveAutoScaling` → `save`
- `autoScaling.*` (display-mode reads at `:562/566/570/574/575`) stay as `autoScaling.*` (the prop)
- `busy` stays `busy` (the prop)

Add three `data-testid`s during the move: `auto-scaling-edit` on the edit button (`:465-474`), `auto-scaling-save` on the save button (`:484-490`), and `auto-scaling-input-surge` on the surge `<input>` (`:501-508`).

> **Draft typing:** the onChange handlers run only inside the `editing && draft` branch, where `draft` is non-null, so `setDraft({ ...draft!, cpu_surge_threshold: Number(e.target.value) })` is safe. tsc in Task 5 confirms.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/power/AutoScalingSection.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/AutoScalingSection.tsx client/src/__tests__/components/power/AutoScalingSection.test.tsx
git commit -m "refactor(power): extract AutoScalingSection (#301)"
```

---

### Task 5: Wire the three components into `PowerManagement.tsx` + verify

**Files:**
- Modify: `client/src/pages/PowerManagement.tsx`
- Modify: `client/src/components/CLAUDE.md`

**Interfaces:**
- Consumes: `PowerStatusCards` (Task 2), `PermissionStatusCard` (Task 3), `AutoScalingSection` (Task 4).

- [ ] **Step 1: Replace the three render blocks and remove moved code**

In `client/src/pages/PowerManagement.tsx`:

1. Add imports alongside the other `components/power/*` imports:
```tsx
import { PowerStatusCards } from '../components/power/PowerStatusCards';
import { PermissionStatusCard } from '../components/power/PermissionStatusCard';
import { AutoScalingSection } from '../components/power/AutoScalingSection';
```
2. Replace the Status-Cards block (`:299-344`, the comment + its `<div className="grid …lg:grid-cols-4">…</div>`) with:
```tsx
      {/* Status Cards */}
      <PowerStatusCards
        status={status}
        activePreset={activePreset}
        currentProperty={currentProperty}
        demands={demands}
        lastUpdated={lastUpdated}
      />
```
3. Replace the Auto-Scaling block (`:456-580`, the whole `{isAdmin && autoScaling && ( … )}`) with:
```tsx
      {/* Auto-Scaling Config (Admin only) */}
      {isAdmin && autoScaling && (
        <AutoScalingSection
          autoScaling={autoScaling}
          dimmed={!!status?.dynamic_mode_enabled}
          busy={busy}
          onBusyChange={setBusy}
          onRefresh={() => void refetch()}
        />
      )}
```
4. Replace the two permission blocks (`:582-660`) with:
```tsx
      {/* Permission panels (Linux backend only) */}
      <PermissionStatusCard status={status} />
```
5. Remove the now-unused state and handlers from the page: the `editingAutoScaling` and `editAutoScaling` `useState` lines (`:74-75`), and `handleStartEditAutoScaling` (`:129-134`), `handleCancelEditAutoScaling` (`:136-139`), `handleSaveAutoScaling` (`:141-169`).
6. Remove now-unused imports (Steps 3-4 flag any still referenced): `AlertTriangle` (moved to PermissionStatusCard), `StatCard` (moved to PowerStatusCards), and from `../api/power-management` the symbols now used only by PowerStatusCards — `PROFILE_INFO`, `PROPERTY_INFO`, `formatClockSpeed` — plus `getPresetIcon` (from `../components/power/utils`). **Keep** `updateAutoScalingConfig` (still used by `handleToggleAutoScaling` at `:119`), `AdminBadge` (still used in the preset card / header), `ServicePowerProperty` (still used at `:247`), and the `AutoScalingConfig` type (still referenced by `editAutoScaling`? — those state lines are removed; if `AutoScalingConfig` is no longer referenced anywhere in the file after removal, drop it too — tsc will flag).

> `handleToggleAutoScaling` (`:113-127`), the auto-scaling toggle button in the preset card, and the preset editor modal stay untouched.

- [ ] **Step 2: Confirm the line count dropped**

Run (PowerShell): `cd client ; (Get-Content src/pages/PowerManagement.tsx | Measure-Object -Line).Lines`
Expected: under 500 (target ~380-420).

- [ ] **Step 3: Typecheck + build**

Run: `cd client ; npm run build`
Expected: `✓ built` (tsc -b then vite), no `error TS`. Fix any unused-import/var errors by removing the dead imports/handlers flagged in Step 1.6.

- [ ] **Step 4: Full lint gate**

Run: `cd client ; npx eslint .`
Expected: no output (0 errors — the CI gate is 0-error).

- [ ] **Step 5: Full test suite**

Run: `cd client ; npx vitest run`
Expected: all green — the prior 603 + the new power tests (isValidAutoScaling 6, PowerStatusCards 1, PermissionStatusCard 3, AutoScalingSection 3). No regressions.

- [ ] **Step 6: Update `components/CLAUDE.md`**

In `client/src/components/CLAUDE.md`, the Feature Subdirectories `power/` row reads "Power profile management". Add a terse note that `PowerManagement` composes `PowerStatusCards`, `PermissionStatusCard`, and `AutoScalingSection` (extracted for F2/#301). Keep it to one line.

- [ ] **Step 7: Commit**

```bash
git add client/src/pages/PowerManagement.tsx client/src/components/CLAUDE.md
git commit -m "refactor(power): compose PowerManagement from extracted subcomponents (#301)"
```

---

## Notes for the implementer

- The JSX being moved is long but must be **relocated verbatim** — do not "improve" markup, class names, or i18n keys. The only permitted diffs are the variable renames in Task 4 (`editingAutoScaling→editing`, `editAutoScaling→draft`, handler names), the `dimmed`/`onRefresh`/`onBusyChange` wiring, and the added `data-testid`s named in each task. `StatCard` gets no testid (Task 2).
- Tasks 2-4 add components that are not yet imported anywhere; that is expected — they are covered by their own tests. Only Task 5 wires them into the page.
- After Task 5, `PowerManagement.tsx` should still render identically; the gate (build + `eslint .` + full vitest) is the proof.
- Line numbers in this plan are from `PowerManagement.tsx` at 632 lines (spec HEAD). If earlier edits shift them, match on the quoted comment markers / JSX instead.
