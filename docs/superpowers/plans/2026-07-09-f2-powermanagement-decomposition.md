# F2 — PowerManagement Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `client/src/pages/PowerManagement.tsx` (632 lines) into three focused `components/power/` subcomponents + one pure validation helper, bringing the page under 500 lines with no behavior/UX/layout change.

**Architecture:** Pure move-refactor. Extract the auto-scaling threshold config card, the permission panels, and the top status-card row into their own components. The one piece of real logic (auto-scaling validation) becomes a pure function. New components mirror the existing `DynamicModeSection` contract (`useTranslation` internally, `busy`/`onBusyChange`/`onRefresh` props for the stateful one).

**Tech Stack:** React 18 + TypeScript, TanStack Query (already in place), Tailwind, react-i18next, Vitest + React Testing Library.

## Global Constraints

- **No behavior, UX, or layout change.** Rendered output must be identical. The auto-scaling **enable/disable toggle button** stays in the preset-selection card (do NOT move it).
- New components live in `client/src/components/power/` and use `useTranslation(['system','common'])` **internally** (no `t` prop) — matching `DynamicModeSection`/`OsAutoSuspendCard`.
- Component tests go in `client/src/__tests__/components/power/`, following the `OsAutoSuspendCard.test.tsx` pattern: `vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))`, `vi.mock` for api + `react-hot-toast`, assert via `data-testid`.
- Verification gate (Task 5): full `npx vitest run` green (currently 603), `npx eslint .` 0 errors, `npm run build` green.
- Windows shell: chain with `;`, never `&&` (see project CLAUDE.md).

---

### Task 1: Pure `isValidAutoScaling` helper

**Files:**
- Modify: `client/src/components/power/utils.ts` (append)
- Test: `client/src/__tests__/components/power/isValidAutoScaling.test.ts`

**Interfaces:**
- Produces: `isValidAutoScaling(cfg: Pick<AutoScalingConfig, 'cpu_surge_threshold' | 'cpu_medium_threshold' | 'cpu_low_threshold' | 'cooldown_seconds'>): boolean` — `true` when `surge > medium > low`, each threshold in `[0,100]`, and `cooldown_seconds >= 0`. (Negation of the inline guard in `PowerManagement.tsx` `handleSaveAutoScaling`.)

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

Add at the end of `client/src/components/power/utils.ts` (add `AutoScalingConfig` to the existing `import type { ... } from '../../api/power-management'`):

```ts
import type { AutoScalingConfig } from '../../api/power-management';

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

Extracts the four top `StatCard`s (source: `PowerManagement.tsx:299-345`, the block after `{/* Status Cards */}` up to `{/* Dynamic Mode Section */}`).

**Files:**
- Create: `client/src/components/power/PowerStatusCards.tsx`
- Test: `client/src/__tests__/components/power/PowerStatusCards.test.tsx`

**Interfaces:**
- Produces: `PowerStatusCards` (default or named export — use **named**) with props
  `{ status: PowerStatusResponse | null; activePreset?: PowerPreset; currentProperty?: ServicePowerProperty; demands: PowerDemandInfo[]; lastUpdated: Date | null }`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/power/PowerStatusCards.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

import { PowerStatusCards } from '../../../components/power/PowerStatusCards';

describe('PowerStatusCards', () => {
  it('renders the active demands count', () => {
    render(
      <PowerStatusCards
        status={{ current_frequency_mhz: 3400 } as never}
        activePreset={{ id: 1, name: 'Balanced', description: 'd' } as never}
        currentProperty="low"
        demands={[{ source: 'a', level: 'low' }, { source: 'b', level: 'medium' }] as never}
        lastUpdated={new Date(0)}
      />,
    );
    expect(screen.getByTestId('power-stat-active-demands').textContent).toContain('2');
  });
});
```

> Note: add `import { vi } from 'vitest';` to the import line if the runner needs it explicitly (match the sibling `OsAutoSuspendCard.test.tsx`, which relies on global `vi`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/power/PowerStatusCards.test.tsx`
Expected: FAIL — cannot resolve `../../../components/power/PowerStatusCards`.

- [ ] **Step 3: Create the component**

Create `client/src/components/power/PowerStatusCards.tsx`:
- Imports: `useTranslation` from `react-i18next`; `StatCard` from `../ui/StatCard`; `getPresetIcon` from `./utils`; `PROFILE_INFO, PROPERTY_INFO, formatClockSpeed, type PowerStatusResponse, type PowerDemandInfo, type ServicePowerProperty, type PowerPreset` from `../../api/power-management`.
- Signature: `export function PowerStatusCards({ status, activePreset, currentProperty, demands, lastUpdated }: PowerStatusCardsProps) { const { t } = useTranslation(['system','common']); return (<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"> …four StatCards… </div>); }`
- **Move the four `<StatCard …/>` elements verbatim from `PowerManagement.tsx:300-345`** (everything between the opening `<div className="grid …lg:grid-cols-4">` and its closing `</div>`). No expression changes — `status`, `activePreset`, `currentProperty`, `demands`, `lastUpdated`, `t`, `PROPERTY_INFO`, `PROFILE_INFO`, `formatClockSpeed`, `getPresetIcon` are all in scope via props/imports.
- Add `data-testid="power-stat-active-demands"` to the **fourth** `StatCard` (active demands) by wrapping its `value={demands.length}` — pass `data-testid` if `StatCard` forwards it; otherwise wrap the card in a `<div data-testid="power-stat-active-demands">`. Verify by reading `components/ui/StatCard.tsx` whether it spreads extra props; if not, use the wrapping `<div>`.

Define the props interface at the top:

```tsx
interface PowerStatusCardsProps {
  status: PowerStatusResponse | null;
  activePreset?: PowerPreset;
  currentProperty?: ServicePowerProperty;
  demands: PowerDemandInfo[];
  lastUpdated: Date | null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client ; npx vitest run src/__tests__/components/power/PowerStatusCards.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/PowerStatusCards.tsx client/src/__tests__/components/power/PowerStatusCards.test.tsx
git commit -m "refactor(power): extract PowerStatusCards (#301)"
```

---

### Task 3: `PermissionStatusCard` component

Extracts the permission warning banner + status grid (source: `PowerManagement.tsx:582-661`, `{/* Permission Warning Banner */}` through the end of `{/* Permission Status (Linux backend only) */}`).

**Files:**
- Create: `client/src/components/power/PermissionStatusCard.tsx`
- Test: `client/src/__tests__/components/power/PermissionStatusCard.test.tsx`

**Interfaces:**
- Produces: `PermissionStatusCard` (named export) with props `{ status: PowerStatusResponse | null }`. Renders `null` unless `status?.is_using_linux_backend && status.permission_status`.

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/power/PermissionStatusCard.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

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
    render(<PermissionStatusCard status={linuxStatus(false)} />);
    expect(screen.getByTestId('power-permission-warning')).toBeTruthy();
  });

  it('hides the warning banner when write access is present', () => {
    render(<PermissionStatusCard status={linuxStatus(true)} />);
    expect(screen.queryByTestId('power-permission-warning')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/power/PermissionStatusCard.test.tsx`
Expected: FAIL — cannot resolve the module.

- [ ] **Step 3: Create the component**

Create `client/src/components/power/PermissionStatusCard.tsx`:
- Imports: `useTranslation` from `react-i18next`; `AlertTriangle` from `lucide-react`; `type PowerStatusResponse` from `../../api/power-management`.
- Signature:

```tsx
interface PermissionStatusCardProps {
  status: PowerStatusResponse | null;
}

export function PermissionStatusCard({ status }: PermissionStatusCardProps) {
  const { t } = useTranslation(['system', 'common']);
  if (!status?.is_using_linux_backend || !status.permission_status) return null;
  const perm = status.permission_status;
  return (
    <>
      {/* warning banner + status grid (moved) */}
    </>
  );
}
```
- **Move the two JSX blocks verbatim** from `PowerManagement.tsx:582-661`: the `{/* Permission Warning Banner */}` block (`status?.is_using_linux_backend && status.permission_status && !status.permission_status.has_write_access && (…)`) and the `{/* Permission Status (Linux backend only) */}` block. Inside the component the outer `status?.is_using_linux_backend && status.permission_status &&` guards are already handled by the early return, so keep only the inner `!status.permission_status.has_write_access &&` guard on the banner (reference `perm` / `status` — both in scope).
- On the outer `<div>` of the warning banner, add `data-testid="power-permission-warning"`.

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

Extracts the auto-scaling **config card** (source: `PowerManagement.tsx:456-581`, `{/* Auto-Scaling Config (Admin only) */}` block) plus the edit state and the `handleStartEditAutoScaling` / `handleCancelEditAutoScaling` / `handleSaveAutoScaling` handlers. Uses `isValidAutoScaling` from Task 1.

**Files:**
- Create: `client/src/components/power/AutoScalingSection.tsx`
- Test: `client/src/__tests__/components/power/AutoScalingSection.test.tsx`

**Interfaces:**
- Consumes: `isValidAutoScaling` (Task 1).
- Produces: `AutoScalingSection` (named export) with props
  `{ autoScaling: AutoScalingConfig; dimmed: boolean; busy: boolean; onBusyChange: (b: boolean) => void; onRefresh: () => void }`.
  (`isAdmin` gating stays in the page — page renders the section only when `isAdmin && autoScaling`.)

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

function renderSection(overrides = {}) {
  const onRefresh = vi.fn();
  const onBusyChange = vi.fn();
  render(
    <AutoScalingSection
      autoScaling={cfg}
      dimmed={false}
      busy={false}
      onBusyChange={onBusyChange}
      onRefresh={onRefresh}
      {...overrides}
    />,
  );
  return { onRefresh, onBusyChange };
}

describe('AutoScalingSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the current thresholds in display mode', () => {
    renderSection();
    expect(screen.getByTestId('auto-scaling-section')).toBeTruthy();
  });

  it('blocks save on an invalid threshold ordering (no API call)', async () => {
    (updateAutoScalingConfig as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    renderSection();
    fireEvent.click(screen.getByTestId('auto-scaling-edit'));
    // Set surge below medium → invalid
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

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client ; npx vitest run src/__tests__/components/power/AutoScalingSection.test.tsx`
Expected: FAIL — cannot resolve `AutoScalingSection`.

- [ ] **Step 3: Create the component**

Create `client/src/components/power/AutoScalingSection.tsx`:
- Imports: `useState` (react); `useTranslation` (react-i18next); `toast` (react-hot-toast); `AdminBadge` from `../ui/AdminBadge`; `updateAutoScalingConfig, type AutoScalingConfig` from `../../api/power-management`; `handleApiError` from `../../lib/errorHandling`; `isValidAutoScaling` from `./utils`.
- Props interface as in Interfaces above.
- Internal state: `const [editing, setEditing] = useState(false); const [draft, setDraft] = useState<AutoScalingConfig | null>(null);` (renamed from `editingAutoScaling`/`editAutoScaling`).
- Handlers (moved from the page, `setBusy`→`onBusyChange`, `refetch`→`onRefresh`, `autoScaling` is the prop, validation via `isValidAutoScaling`):

```tsx
const startEdit = () => setDraft({ ...autoScaling });
const cancelEdit = () => { setEditing(false); setDraft(null); };
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
```
> Note: entering edit mode is `onClick={() => { startEdit(); setEditing(true); }}` on the edit button, matching the old `handleStartEditAutoScaling` (which set both) — keep that combined behavior.

- Return: move the `{/* Auto-Scaling Config (Admin only) */}` card JSX from `PowerManagement.tsx:456-581`, but:
  - Drop the outer `{isAdmin && autoScaling && (` wrapper (page gates it). The root element is the `<div className={\`card border-slate-700/50 p-4 sm:p-6 ${'{'}dimmed ? 'opacity-50 pointer-events-none' : ''{'}'}\`}>` — replace the old `status?.dynamic_mode_enabled` expression with the `dimmed` prop. Add `data-testid="auto-scaling-section"`.
  - Rename references: `editingAutoScaling` → `editing`, `editAutoScaling` → `draft`, `setEditAutoScaling` → `setDraft`, `handleStartEditAutoScaling` → the combined `() => { startEdit(); setEditing(true); }`, `handleCancelEditAutoScaling` → `cancelEdit`, `handleSaveAutoScaling` → `save`, `autoScaling.` → `autoScaling.` (prop, unchanged), `busy` → `busy` (prop).
  - Add `data-testid` to: the edit button (`auto-scaling-edit`), the save button (`auto-scaling-save`), and the surge `<input>` (`auto-scaling-input-surge`).

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

**Interfaces:**
- Consumes: `PowerStatusCards` (Task 2), `PermissionStatusCard` (Task 3), `AutoScalingSection` (Task 4).

- [ ] **Step 1: Replace the three render blocks and remove moved code**

In `client/src/pages/PowerManagement.tsx`:

1. Add imports near the other `components/power/*` imports:
```tsx
import { PowerStatusCards } from '../components/power/PowerStatusCards';
import { PermissionStatusCard } from '../components/power/PermissionStatusCard';
import { AutoScalingSection } from '../components/power/AutoScalingSection';
```
2. Replace the `{/* Status Cards */}` block (`:299-345`) with:
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
3. Replace the whole `{/* Auto-Scaling Config (Admin only) */}` block (`:456-581`) with:
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
4. Replace the `{/* Permission Warning Banner */}` + `{/* Permission Status (Linux backend only) */}` blocks (`:582-661`) with:
```tsx
      {/* Permission panels (Linux backend only) */}
      <PermissionStatusCard status={status} />
```
5. Remove the now-unused page state and handlers: `editingAutoScaling`, `editAutoScaling` (`useState`), `handleStartEditAutoScaling`, `handleCancelEditAutoScaling`, `handleSaveAutoScaling`.
6. Remove now-unused imports from `PowerManagement.tsx`: `updateAutoScalingConfig` **only if** no longer referenced (it is still used by `handleToggleAutoScaling` — **keep it**), `AlertTriangle` (moved to PermissionStatusCard — remove), `StatCard` (moved — remove), `formatClockSpeed`/`getPresetIcon`/`PROPERTY_INFO`/`PROFILE_INFO` (moved to PowerStatusCards — remove **only if** not used elsewhere in the file; `PROPERTY_INFO`/`PROFILE_INFO`/`getPresetIcon`/`formatClockSpeed` were used only by the status cards — remove). Let eslint/tsc confirm (Steps 3-4).

> `handleToggleAutoScaling` and the auto-scaling **toggle button** in the preset card stay untouched.

- [ ] **Step 2: Confirm line count dropped**

Run: `cd client ; (Get-Content src/pages/PowerManagement.tsx | Measure-Object -Line).Lines`  *(PowerShell)*
Expected: under 500 (target ~380–420).

- [ ] **Step 3: eslint the touched files**

Run: `cd client ; npx eslint src/pages/PowerManagement.tsx src/components/power/PowerStatusCards.tsx src/components/power/PermissionStatusCard.tsx src/components/power/AutoScalingSection.tsx src/components/power/utils.ts`
Expected: no output (0 errors). Fix any unused-import / unused-var errors by removing the dead imports/handlers flagged.

- [ ] **Step 4: Build (typecheck)**

Run: `cd client ; npm run build`
Expected: `✓ built` twice (tsc -b + vite), no `error TS`.

- [ ] **Step 5: Full suite**

Run: `cd client ; npx vitest run`
Expected: all green — 603 prior + the new power tests (isValidAutoScaling 6, PowerStatusCards 1, PermissionStatusCard 3, AutoScalingSection 3). No regressions.

- [ ] **Step 6: Update `components/CLAUDE.md`**

In `client/src/components/CLAUDE.md`, under the `power/` feature-dir note (or the top-level component list), add one line noting the three new power subcomponents extracted from `PowerManagement` (F2/#301). Keep it terse.

- [ ] **Step 7: Commit**

```bash
git add client/src/pages/PowerManagement.tsx client/src/components/CLAUDE.md
git commit -m "refactor(power): compose PowerManagement from extracted subcomponents (#301)"
```

---

## Notes for the implementer

- Before Task 2 Step 3, read `client/src/components/ui/StatCard.tsx` to confirm whether it forwards arbitrary props (for the `data-testid`); if not, wrap the target card in a `<div data-testid=…>`.
- The JSX being moved is long but must be **relocated verbatim** — do not "improve" markup, class names, or i18n keys. Any diff beyond variable-name renames (`editingAutoScaling→editing`, `editAutoScaling→draft`) and the `dimmed`/`onRefresh`/`onBusyChange` wiring is out of scope.
- After each task, the app must still compile; only Task 5 wires the page, so Tasks 2–4 add unused components (that is expected and fine — they are covered by their own tests).
