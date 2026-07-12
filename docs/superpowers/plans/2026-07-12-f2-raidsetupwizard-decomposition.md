# RaidSetupWizard.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zerlege `client/src/components/RaidSetupWizard.tsx` (547 Zeilen) verhaltenserhaltend in Orchestrator + State-Hook + pure Helfer + Daten + 4 Step-Subkomponenten.

**Architecture:** `RAID_LEVELS`-Daten nach `raid-setup/raidLevels.ts`, pure `calculateArrayCapacity`/`isValidArrayName` nach `raid-setup/raidWizardHelpers.ts`, State/Navigation/Submit nach `hooks/useRaidSetupWizard.ts`, die 4 Render-Funktionen als reine Komponenten unter `raid-setup/`. `RaidSetupWizard.tsx` bleibt Modal-Shell + Step-Switch.

**Tech Stack:** React 18 + TypeScript, Vitest + @testing-library/react, react-i18next, react-hot-toast, Tailwind CSS.

## Global Constraints

- **Verhaltenserhaltend:** Keine Änderung an sichtbarem Verhalten, Rendering oder der öffentlichen `RaidSetupWizardProps`. Konsument `pages/RaidManagement.tsx` (`import RaidSetupWizard from '../components/RaidSetupWizard'`) bleibt unverändert (Default-Export, identische Props).
- **Pure Helfer verbatim:** `calculateArrayCapacity` behält den Dev-Quirk `diskSize = 5 * 1024 ** 3` (5 GB/Disk) exakt; die RAID-Level-Switch-Logik unverändert.
- **Hartcodierte englische Strings** in `RAID_LEVELS` (name/description/redundancy/…) bleiben verbatim (das Original i18n-isiert sie nicht — kein i18n hinzufügen).
- i18n-Keys (`raidWizard.*`), Tailwind-Klassen und DOM-Struktur exakt wie im Original.
- **Kein neuer öffentlicher Re-Export** außerhalb von `RaidSetupWizard` — `raid-setup/*` + Hook sind interne Details.
- **Verify-Gate vor PR:** `npx vitest run`, `npx eslint .` (0 Fehler), `npm run build`. Arbeitsverzeichnis: `client/`.
- **Tests-Layout:** Helfer-/Komponententests unter `client/src/__tests__/components/raid-setup/…`, Hook-Test unter `client/src/__tests__/hooks/…`.
- **CRLF:** `core.autocrlf=true` — LF→CRLF-Warnungen bei `git add` erwartbar.

**Referenz-Typen (aus `client/src/api/raid.ts`):**

```ts
export interface AvailableDisk { name: string; size_bytes: number; model?: string | null; is_partitioned: boolean; partitions: string[]; in_raid: boolean; is_os_disk?: boolean; is_ssd?: boolean; is_cache_device?: boolean; }
export interface CreateArrayPayload { name: string; level: string; devices: string[]; spare_devices?: string[]; }
export function createArray(payload: CreateArrayPayload): Promise<...>;
```

---

## File Structure

**Create:**
- `client/src/components/raid-setup/raidLevels.ts`
- `client/src/components/raid-setup/raidWizardHelpers.ts`
- `client/src/hooks/useRaidSetupWizard.ts`
- `client/src/components/raid-setup/RaidWizardStepIndicator.tsx`
- `client/src/components/raid-setup/RaidDiskSelectionStep.tsx`
- `client/src/components/raid-setup/RaidLevelSelectionStep.tsx`
- `client/src/components/raid-setup/RaidConfirmationStep.tsx`
- `client/src/components/raid-setup/index.ts`
- Tests:
  - `client/src/__tests__/components/raid-setup/raidWizardHelpers.test.ts`
  - `client/src/__tests__/hooks/useRaidSetupWizard.test.tsx`
  - `client/src/__tests__/components/raid-setup/RaidWizardStepIndicator.test.tsx`
  - `client/src/__tests__/components/raid-setup/RaidDiskSelectionStep.test.tsx`
  - `client/src/__tests__/components/raid-setup/RaidLevelSelectionStep.test.tsx`
  - `client/src/__tests__/components/raid-setup/RaidConfirmationStep.test.tsx`

**Modify:**
- `client/src/components/RaidSetupWizard.tsx` — auf Orchestrator reduzieren (Task 7)
- `client/src/components/CLAUDE.md` — `raid-setup/`-Zeile ergänzen (Task 7)

---

## Task 1: `raidLevels.ts` (Daten) + `raidWizardHelpers.ts` (pure Helfer)

**Files:**
- Create: `client/src/components/raid-setup/raidLevels.ts`
- Create: `client/src/components/raid-setup/raidWizardHelpers.ts`
- Test: `client/src/__tests__/components/raid-setup/raidWizardHelpers.test.ts`

**Interfaces:**
- Consumes: `formatBytes` aus `../../lib/formatters`.
- Produces:

```ts
// raidLevels.ts
export interface RaidLevelInfo { level: string; name: string; description: string; minDisks: number; redundancy: string; capacity: string; performance: string; recommended?: boolean; }
export const RAID_LEVELS: RaidLevelInfo[];
// raidWizardHelpers.ts
export function calculateArrayCapacity(level: string, diskCount: number): string;
export function isValidArrayName(name: string): boolean;
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/raid-setup/raidWizardHelpers.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { calculateArrayCapacity, isValidArrayName } from '../../../components/raid-setup/raidWizardHelpers';
import { formatBytes } from '../../../lib/formatters';

const DISK = 5 * 1024 ** 3; // 5 GB per disk (dev quirk, preserved)

describe('calculateArrayCapacity', () => {
  it('raid0 = n × disk', () => {
    expect(calculateArrayCapacity('raid0', 3)).toBe(formatBytes(3 * DISK));
  });
  it('raid1 = 1 × disk regardless of count', () => {
    expect(calculateArrayCapacity('raid1', 4)).toBe(formatBytes(DISK));
  });
  it('raid5 = (n-1) × disk', () => {
    expect(calculateArrayCapacity('raid5', 3)).toBe(formatBytes(2 * DISK));
  });
  it('raid6 = (n-2) × disk', () => {
    expect(calculateArrayCapacity('raid6', 4)).toBe(formatBytes(2 * DISK));
  });
  it('raid10 = (n/2) × disk', () => {
    expect(calculateArrayCapacity('raid10', 4)).toBe(formatBytes(2 * DISK));
  });
  it('returns 0 GB for zero disks', () => {
    expect(calculateArrayCapacity('raid1', 0)).toBe('0 GB');
  });
  it('returns 0 GB for an unknown level', () => {
    expect(calculateArrayCapacity('raid99', 3)).toBe('0 GB');
  });
});

describe('isValidArrayName', () => {
  it('accepts md + digits', () => { expect(isValidArrayName('md0')).toBe(true); });
  it('accepts md_ + alphanumerics', () => { expect(isValidArrayName('md_backup')).toBe(true); });
  it('rejects a non-md name', () => { expect(isValidArrayName('raid0')).toBe(false); });
  it('rejects bare "md"', () => { expect(isValidArrayName('md')).toBe(false); });
  it('rejects empty', () => { expect(isValidArrayName('')).toBe(false); });
  it('rejects names longer than 32 chars', () => { expect(isValidArrayName('md' + '1'.repeat(40))).toBe(false); });
  it('rejects special chars', () => { expect(isValidArrayName('md_ab!')).toBe(false); });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/raidWizardHelpers.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/raid-setup/raidLevels.ts` (RAID_LEVELS 1:1 aus `RaidSetupWizard.tsx:15-73`):

```ts
export interface RaidLevelInfo {
  level: string;
  name: string;
  description: string;
  minDisks: number;
  redundancy: string;
  capacity: string;
  performance: string;
  recommended?: boolean;
}

export const RAID_LEVELS: RaidLevelInfo[] = [
  {
    level: 'raid1',
    name: 'RAID 1 (Mirroring)',
    description: 'All data is mirrored across multiple disks. Maximum security through redundancy.',
    minDisks: 2,
    redundancy: 'High (n-1 disks can fail)',
    capacity: '50% (with 2 disks)',
    performance: 'Read: Good / Write: Medium',
    recommended: true,
  },
  {
    level: 'raid0',
    name: 'RAID 0 (Striping)',
    description: 'Data is distributed across multiple disks. Maximum speed but no redundancy.',
    minDisks: 2,
    redundancy: 'None (failure = data loss)',
    capacity: '100%',
    performance: 'Read: Excellent / Write: Excellent',
  },
  {
    level: 'raid5',
    name: 'RAID 5 (Parity)',
    description: 'Data distributed with parity information. Good balance between speed and security.',
    minDisks: 3,
    redundancy: 'Medium (1 disk can fail)',
    capacity: '(n-1)/n × 100%',
    performance: 'Read: Good / Write: Medium',
  },
  {
    level: 'raid6',
    name: 'RAID 6 (Double Parity)',
    description: 'Like RAID 5, but with double parity information. Higher security than RAID 5.',
    minDisks: 4,
    redundancy: 'High (2 disks can fail)',
    capacity: '(n-2)/n × 100%',
    performance: 'Read: Good / Write: Low',
  },
  {
    level: 'raid10',
    name: 'RAID 10 (Mirrored Stripe)',
    description: 'Combination of RAID 0 and RAID 1. High speed with redundancy.',
    minDisks: 4,
    redundancy: 'High (n/2 disks can fail)',
    capacity: '50%',
    performance: 'Read: Excellent / Write: Good',
  },
];
```

`client/src/components/raid-setup/raidWizardHelpers.ts` (aus `calculateArrayCapacity` + `MDADM_NAME_REGEX`; `calculateArrayCapacity` bekommt `level`+`diskCount` als Parameter, prüft Existenz via `RAID_LEVELS.find` — reproduziert das originale `!raidInfo → '0 GB'`):

```ts
import { formatBytes } from '../../lib/formatters';
import { RAID_LEVELS } from './raidLevels';

const MDADM_NAME_REGEX = /^md([0-9]+|_[a-zA-Z0-9]+)$/;

export function isValidArrayName(name: string): boolean {
  return MDADM_NAME_REGEX.test(name) && name.length <= 32;
}

export function calculateArrayCapacity(level: string, diskCount: number): string {
  const raidInfo = RAID_LEVELS.find((r) => r.level === level);
  if (!raidInfo || diskCount === 0) return '0 GB';

  const diskSize = 5 * 1024 ** 3; // 5 GB per disk in dev mode
  const count = diskCount;

  let capacity = 0;
  switch (raidInfo.level) {
    case 'raid0':
      capacity = diskSize * count;
      break;
    case 'raid1':
      capacity = diskSize;
      break;
    case 'raid5':
      capacity = diskSize * (count - 1);
      break;
    case 'raid6':
      capacity = diskSize * (count - 2);
      break;
    case 'raid10':
      capacity = diskSize * (count / 2);
      break;
    default:
      capacity = diskSize;
  }

  return formatBytes(capacity);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/raidWizardHelpers.test.ts`
Expected: PASS (14 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/raid-setup/raidLevels.ts client/src/components/raid-setup/raidWizardHelpers.ts client/src/__tests__/components/raid-setup/raidWizardHelpers.test.ts
git commit -m "feat(raid): extract raidLevels data + pure raidWizardHelpers (#301)"
```

---

## Task 2: `useRaidSetupWizard.ts` (State-Hook)

**Files:**
- Create: `client/src/hooks/useRaidSetupWizard.ts`
- Test: `client/src/__tests__/hooks/useRaidSetupWizard.test.tsx`

**Interfaces:**
- Consumes: `RAID_LEVELS`/`RaidLevelInfo` (Task 1), `isValidArrayName` (Task 1), `createArray`/`AvailableDisk` aus `../api/raid`, `toast`, `useTranslation`.
- Produces:

```ts
export type WizardStep = 'select-disks' | 'raid-level' | 'confirm';
export function useRaidSetupWizard(availableDisks: AvailableDisk[], onClose: () => void, onSuccess: () => void): {
  currentStep: WizardStep; setCurrentStep: (s: WizardStep) => void;
  selectedDisks: string[]; toggleDiskSelection: (name: string) => void;
  selectedRaidLevel: string; setSelectedRaidLevel: (l: string) => void;
  arrayName: string; setArrayName: (n: string) => void;
  busy: boolean;
  freeDisks: AvailableDisk[];
  isArrayNameValid: boolean;
  getSelectedRaidInfo: () => RaidLevelInfo | undefined;
  canProceedFromDiskSelection: () => boolean;
  canProceedFromRaidLevel: () => boolean;
  handleSubmit: (e: FormEvent) => Promise<void>;
};
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/hooks/useRaidSetupWizard.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { AvailableDisk } from '../../api/raid';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/raid', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/raid')>();
  return { ...actual, createArray: vi.fn().mockResolvedValue({ success: true }) };
});

import { createArray } from '../../api/raid';
import { useRaidSetupWizard } from '../../hooks/useRaidSetupWizard';

const disk = (name: string, over: Partial<AvailableDisk> = {}): AvailableDisk => ({
  name, size_bytes: 5 * 1024 ** 3, model: null, is_partitioned: true,
  partitions: [`${name}1`], in_raid: false, is_os_disk: false, ...over,
});

describe('useRaidSetupWizard', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('filters out in_raid and os disks from freeDisks', () => {
    const disks = [disk('sda'), disk('sdb', { in_raid: true }), disk('nvme0n1', { is_os_disk: true })];
    const { result } = renderHook(() => useRaidSetupWizard(disks, vi.fn(), vi.fn()));
    expect(result.current.freeDisks.map((d) => d.name)).toEqual(['sda']);
  });

  it('toggleDiskSelection adds then removes a disk', () => {
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda')], vi.fn(), vi.fn()));
    act(() => result.current.toggleDiskSelection('sda'));
    expect(result.current.selectedDisks).toEqual(['sda']);
    act(() => result.current.toggleDiskSelection('sda'));
    expect(result.current.selectedDisks).toEqual([]);
  });

  it('canProceedFromDiskSelection requires >= 2 disks', () => {
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda'), disk('sdb')], vi.fn(), vi.fn()));
    expect(result.current.canProceedFromDiskSelection()).toBe(false);
    act(() => { result.current.toggleDiskSelection('sda'); result.current.toggleDiskSelection('sdb'); });
    expect(result.current.canProceedFromDiskSelection()).toBe(true);
  });

  it('canProceedFromRaidLevel requires >= minDisks for the selected level', () => {
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda'), disk('sdb')], vi.fn(), vi.fn()));
    act(() => { result.current.toggleDiskSelection('sda'); result.current.toggleDiskSelection('sdb'); });
    // default level raid1 (minDisks 2) -> ok with 2
    expect(result.current.canProceedFromRaidLevel()).toBe(true);
    act(() => result.current.setSelectedRaidLevel('raid5')); // minDisks 3
    expect(result.current.canProceedFromRaidLevel()).toBe(false);
  });

  it('handleSubmit calls createArray with the first partition per disk, then onSuccess + onClose', async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda'), disk('sdb')], onClose, onSuccess));
    act(() => { result.current.toggleDiskSelection('sda'); result.current.toggleDiskSelection('sdb'); });
    act(() => result.current.setArrayName('md7'));
    await act(async () => { await result.current.handleSubmit({ preventDefault: vi.fn() } as unknown as React.FormEvent); });
    expect(vi.mocked(createArray)).toHaveBeenCalledWith({ name: 'md7', level: 'raid1', devices: ['sda1', 'sdb1'] });
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/hooks/useRaidSetupWizard.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/hooks/useRaidSetupWizard.ts` (State + Handler 1:1 aus `RaidSetupWizard.tsx`; `isArrayNameValid` via `isValidArrayName`, `getSelectedRaidInfo`/Capacity nutzen `RAID_LEVELS`):

```ts
import { type FormEvent, useState } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import { createArray, type AvailableDisk } from '../api/raid';
import { RAID_LEVELS, type RaidLevelInfo } from '../components/raid-setup/raidLevels';
import { isValidArrayName } from '../components/raid-setup/raidWizardHelpers';

export type WizardStep = 'select-disks' | 'raid-level' | 'confirm';

export function useRaidSetupWizard(
  availableDisks: AvailableDisk[],
  onClose: () => void,
  onSuccess: () => void,
) {
  const { t } = useTranslation('system');
  const [currentStep, setCurrentStep] = useState<WizardStep>('select-disks');
  const [selectedDisks, setSelectedDisks] = useState<string[]>([]);
  const [selectedRaidLevel, setSelectedRaidLevel] = useState<string>('raid1');
  const [arrayName, setArrayName] = useState<string>('md1');
  const [busy, setBusy] = useState<boolean>(false);

  const isArrayNameValid = isValidArrayName(arrayName);

  // Nur Disks die nicht im RAID und keine OS-Disk sind
  const freeDisks = availableDisks.filter((disk) => !disk.in_raid && !disk.is_os_disk);

  const toggleDiskSelection = (diskName: string) => {
    setSelectedDisks((prev) =>
      prev.includes(diskName) ? prev.filter((d) => d !== diskName) : [...prev, diskName]
    );
  };

  const getSelectedRaidInfo = (): RaidLevelInfo | undefined =>
    RAID_LEVELS.find((r) => r.level === selectedRaidLevel);

  const canProceedFromDiskSelection = (): boolean => selectedDisks.length >= 2;

  const canProceedFromRaidLevel = (): boolean => {
    const raidInfo = getSelectedRaidInfo();
    return raidInfo ? selectedDisks.length >= raidInfo.minDisks : false;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);

    try {
      // Use the first partition if available, otherwise pass the whole disk
      const devices = selectedDisks.map((disk) => {
        const diskObj = freeDisks.find((d) => d.name === disk);
        return diskObj?.partitions?.[0] || disk;
      });

      await createArray({
        name: arrayName,
        level: selectedRaidLevel,
        devices,
      });

      toast.success(t('raidWizard.arrayCreated', { name: arrayName }));
      onSuccess();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : t('raidWizard.createFailed');
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return {
    currentStep,
    setCurrentStep,
    selectedDisks,
    toggleDiskSelection,
    selectedRaidLevel,
    setSelectedRaidLevel,
    arrayName,
    setArrayName,
    busy,
    freeDisks,
    isArrayNameValid,
    getSelectedRaidInfo,
    canProceedFromDiskSelection,
    canProceedFromRaidLevel,
    handleSubmit,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/hooks/useRaidSetupWizard.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useRaidSetupWizard.ts client/src/__tests__/hooks/useRaidSetupWizard.test.tsx
git commit -m "feat(raid): add useRaidSetupWizard hook (state + navigation + submit) (#301)"
```

---

## Task 3: `RaidWizardStepIndicator.tsx`

**Files:**
- Create: `client/src/components/raid-setup/RaidWizardStepIndicator.tsx`
- Test: `client/src/__tests__/components/raid-setup/RaidWizardStepIndicator.test.tsx`

**Interfaces:**
- Consumes: `WizardStep` aus `../../hooks/useRaidSetupWizard`.
- Produces: default export `RaidWizardStepIndicator` mit Props `{ currentStep: WizardStep }`.

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/raid-setup/RaidWizardStepIndicator.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import RaidWizardStepIndicator from '../../../components/raid-setup/RaidWizardStepIndicator';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe('RaidWizardStepIndicator', () => {
  it('renders the three step labels', () => {
    render(<RaidWizardStepIndicator currentStep="raid-level" />);
    expect(screen.getByText('raidWizard.steps.disks')).toBeInTheDocument();
    expect(screen.getByText('raidWizard.steps.raidLevel')).toBeInTheDocument();
    expect(screen.getByText('raidWizard.steps.confirm')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidWizardStepIndicator.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/raid-setup/RaidWizardStepIndicator.tsx` (aus `renderStepIndicator`, `RaidSetupWizard.tsx:167-207`):

```tsx
import { useTranslation } from 'react-i18next';
import type { WizardStep } from '../../hooks/useRaidSetupWizard';

interface RaidWizardStepIndicatorProps {
  currentStep: WizardStep;
}

export default function RaidWizardStepIndicator({ currentStep }: RaidWizardStepIndicatorProps) {
  const { t } = useTranslation('system');
  const steps = [
    { id: 'select-disks', label: t('raidWizard.steps.disks') },
    { id: 'raid-level', label: t('raidWizard.steps.raidLevel') },
    { id: 'confirm', label: t('raidWizard.steps.confirm') },
  ];

  const currentIndex = steps.findIndex((s) => s.id === currentStep);

  return (
    <div className="flex items-center justify-center space-x-2 mb-8">
      {steps.map((step, index) => (
        <div key={step.id} className="flex items-center">
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition ${
              index <= currentIndex
                ? 'bg-sky-500/20 text-sky-200 border-2 border-sky-500'
                : 'bg-slate-800/60 text-slate-500 border-2 border-slate-700'
            }`}
          >
            {index + 1}
          </div>
          <span
            className={`ml-2 text-sm font-medium ${
              index <= currentIndex ? 'text-slate-200' : 'text-slate-500'
            }`}
          >
            {step.label}
          </span>
          {index < steps.length - 1 && (
            <div
              className={`mx-4 h-0.5 w-12 ${
                index < currentIndex ? 'bg-sky-500' : 'bg-slate-700'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidWizardStepIndicator.test.tsx`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/raid-setup/RaidWizardStepIndicator.tsx client/src/__tests__/components/raid-setup/RaidWizardStepIndicator.test.tsx
git commit -m "feat(raid): extract RaidWizardStepIndicator component (#301)"
```

---

## Task 4: `RaidDiskSelectionStep.tsx`

**Files:**
- Create: `client/src/components/raid-setup/RaidDiskSelectionStep.tsx`
- Test: `client/src/__tests__/components/raid-setup/RaidDiskSelectionStep.test.tsx`

**Interfaces:**
- Consumes: `AvailableDisk` aus `../../api/raid`, `formatBytes` aus `../../lib/formatters`.
- Produces: default export `RaidDiskSelectionStep` mit Props:

```ts
interface RaidDiskSelectionStepProps {
  freeDisks: AvailableDisk[];
  selectedDisks: string[];
  onToggleDisk: (name: string) => void;
  canProceed: boolean;
  onCancel: () => void;
  onNext: () => void;
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/raid-setup/RaidDiskSelectionStep.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { AvailableDisk } from '../../../api/raid';
import RaidDiskSelectionStep from '../../../components/raid-setup/RaidDiskSelectionStep';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const disk = (name: string): AvailableDisk => ({
  name, size_bytes: 5 * 1024 ** 3, model: 'Dev Disk', is_partitioned: true,
  partitions: [`${name}1`], in_raid: false, is_os_disk: false,
});
const base = { freeDisks: [disk('sda'), disk('sdb')], selectedDisks: [], onToggleDisk: vi.fn(), canProceed: false, onCancel: vi.fn(), onNext: vi.fn() };

describe('RaidDiskSelectionStep', () => {
  it('shows the empty state when there are no free disks', () => {
    render(<RaidDiskSelectionStep {...base} freeDisks={[]} />);
    expect(screen.getByText('raidWizard.selectDisks.noDisks')).toBeInTheDocument();
  });

  it('toggling a disk fires onToggleDisk', () => {
    const onToggleDisk = vi.fn();
    render(<RaidDiskSelectionStep {...base} onToggleDisk={onToggleDisk} />);
    fireEvent.click(screen.getByText('/dev/sda'));
    expect(onToggleDisk).toHaveBeenCalledWith('sda');
  });

  it('Next is disabled when canProceed is false and enabled when true', () => {
    const { rerender } = render(<RaidDiskSelectionStep {...base} canProceed={false} />);
    expect(screen.getByText('raidWizard.next')).toBeDisabled();
    rerender(<RaidDiskSelectionStep {...base} canProceed />);
    expect(screen.getByText('raidWizard.next')).not.toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidDiskSelectionStep.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/raid-setup/RaidDiskSelectionStep.tsx` (aus `renderDiskSelection`, `RaidSetupWizard.tsx:209-303`; `canProceedFromDiskSelection()` → `canProceed`-Prop, `setCurrentStep('raid-level')` → `onNext`, `onClose` → `onCancel`, `toggleDiskSelection` → `onToggleDisk`):

```tsx
import { useTranslation } from 'react-i18next';
import type { AvailableDisk } from '../../api/raid';
import { formatBytes } from '../../lib/formatters';

interface RaidDiskSelectionStepProps {
  freeDisks: AvailableDisk[];
  selectedDisks: string[];
  onToggleDisk: (name: string) => void;
  canProceed: boolean;
  onCancel: () => void;
  onNext: () => void;
}

export default function RaidDiskSelectionStep({
  freeDisks, selectedDisks, onToggleDisk, canProceed, onCancel, onNext,
}: RaidDiskSelectionStepProps) {
  const { t } = useTranslation('system');

  return (
    <div>
      <h3 className="text-xl font-semibold text-white">{t('raidWizard.selectDisks.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">
        {t('raidWizard.selectDisks.description')}
      </p>

      <div className="mt-6 space-y-3">
        {freeDisks.length === 0 ? (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-center">
            <p className="text-sm text-amber-200">
              {t('raidWizard.selectDisks.noDisks')}
            </p>
          </div>
        ) : (
          freeDisks.map((disk) => (
            <button
              key={disk.name}
              type="button"
              onClick={() => onToggleDisk(disk.name)}
              className={`w-full rounded-lg border p-4 text-left transition ${
                selectedDisks.includes(disk.name)
                  ? 'border-sky-500 bg-sky-500/15'
                  : 'border-slate-700/70 bg-slate-900/60 hover:border-slate-600'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div
                    className={`flex h-5 w-5 items-center justify-center rounded border-2 transition ${
                      selectedDisks.includes(disk.name)
                        ? 'border-sky-500 bg-sky-500'
                        : 'border-slate-600 bg-slate-900'
                    }`}
                  >
                    {selectedDisks.includes(disk.name) && (
                      <svg className="h-3 w-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </div>
                  <div>
                    <p className="font-medium text-slate-200">/dev/{disk.name}</p>
                    <p className="text-xs text-slate-400">{disk.model || t('raidWizard.selectDisks.unknownModel')}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-slate-300">{formatBytes(disk.size_bytes)}</p>
                  {disk.partitions.length > 0 && (
                    <p className="text-xs text-slate-500">
                      {t('raidWizard.selectDisks.partitions', { count: disk.partitions.length })}
                    </p>
                  )}
                </div>
              </div>
            </button>
          ))
        )}
      </div>

      {selectedDisks.length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-700/70 bg-slate-900/60 p-3">
          <p className="text-sm text-slate-300">
            {t('raidWizard.selectDisks.disksSelected', { count: selectedDisks.length })}
          </p>
        </div>
      )}

      <div className="mt-6 flex justify-end gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
        >
          {t('raidWizard.cancel')}
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!canProceed}
          className={`rounded-lg border px-4 py-2 text-sm transition ${
            canProceed
              ? 'border-sky-500/40 bg-sky-500/15 text-sky-100 hover:border-sky-500/60'
              : 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
          }`}
        >
          {t('raidWizard.next')}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidDiskSelectionStep.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/raid-setup/RaidDiskSelectionStep.tsx client/src/__tests__/components/raid-setup/RaidDiskSelectionStep.test.tsx
git commit -m "feat(raid): extract RaidDiskSelectionStep component (#301)"
```

---

## Task 5: `RaidLevelSelectionStep.tsx`

**Files:**
- Create: `client/src/components/raid-setup/RaidLevelSelectionStep.tsx`
- Test: `client/src/__tests__/components/raid-setup/RaidLevelSelectionStep.test.tsx`

**Interfaces:**
- Consumes: `RAID_LEVELS` aus `./raidLevels`.
- Produces: default export `RaidLevelSelectionStep` mit Props:

```ts
interface RaidLevelSelectionStepProps {
  selectedDisks: string[];
  selectedRaidLevel: string;
  onSelectLevel: (level: string) => void;
  canProceed: boolean;
  onBack: () => void;
  onCancel: () => void;
  onNext: () => void;
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/raid-setup/RaidLevelSelectionStep.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RaidLevelSelectionStep from '../../../components/raid-setup/RaidLevelSelectionStep';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = { selectedDisks: ['sda', 'sdb'], selectedRaidLevel: 'raid1', onSelectLevel: vi.fn(), canProceed: true, onBack: vi.fn(), onCancel: vi.fn(), onNext: vi.fn() };

describe('RaidLevelSelectionStep', () => {
  it('only lists RAID levels whose minDisks the selection meets', () => {
    // 2 disks -> raid1 & raid0 (minDisks 2) shown; raid5/6/10 hidden
    render(<RaidLevelSelectionStep {...base} />);
    expect(screen.getByText('RAID 1 (Mirroring)')).toBeInTheDocument();
    expect(screen.getByText('RAID 0 (Striping)')).toBeInTheDocument();
    expect(screen.queryByText('RAID 5 (Parity)')).not.toBeInTheDocument();
  });

  it('shows more levels as disk count grows', () => {
    render(<RaidLevelSelectionStep {...base} selectedDisks={['sda', 'sdb', 'sdc', 'sdd']} />);
    expect(screen.getByText('RAID 5 (Parity)')).toBeInTheDocument();
    expect(screen.getByText('RAID 10 (Mirrored Stripe)')).toBeInTheDocument();
  });

  it('selecting a level fires onSelectLevel', () => {
    const onSelectLevel = vi.fn();
    render(<RaidLevelSelectionStep {...base} onSelectLevel={onSelectLevel} />);
    fireEvent.click(screen.getByText('RAID 0 (Striping)'));
    expect(onSelectLevel).toHaveBeenCalledWith('raid0');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidLevelSelectionStep.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/raid-setup/RaidLevelSelectionStep.tsx` (aus `renderRaidLevelSelection`, `RaidSetupWizard.tsx:305-402`; `setSelectedRaidLevel` → `onSelectLevel`, `setCurrentStep(...)` → `onBack`/`onNext`, `onClose` → `onCancel`, `canProceedFromRaidLevel()` → `canProceed`):

```tsx
import { useTranslation } from 'react-i18next';
import { RAID_LEVELS } from './raidLevels';

interface RaidLevelSelectionStepProps {
  selectedDisks: string[];
  selectedRaidLevel: string;
  onSelectLevel: (level: string) => void;
  canProceed: boolean;
  onBack: () => void;
  onCancel: () => void;
  onNext: () => void;
}

export default function RaidLevelSelectionStep({
  selectedDisks, selectedRaidLevel, onSelectLevel, canProceed, onBack, onCancel, onNext,
}: RaidLevelSelectionStepProps) {
  const { t } = useTranslation('system');
  const availableRaidLevels = RAID_LEVELS.filter((r) => selectedDisks.length >= r.minDisks);

  return (
    <div>
      <h3 className="text-xl font-semibold text-white">{t('raidWizard.raidLevel.title')}</h3>
      <p className="mt-1 text-sm text-slate-400">
        {t('raidWizard.raidLevel.description', { count: selectedDisks.length })}
      </p>

      <div className="mt-6 space-y-3">
        {availableRaidLevels.map((raid) => (
          <button
            key={raid.level}
            type="button"
            onClick={() => onSelectLevel(raid.level)}
            className={`w-full rounded-lg border p-4 text-left transition ${
              selectedRaidLevel === raid.level
                ? 'border-sky-500 bg-sky-500/15'
                : 'border-slate-700/70 bg-slate-900/60 hover:border-slate-600'
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-white">{raid.name}</p>
                  {raid.recommended && (
                    <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-200">
                      {t('raidWizard.raidLevel.recommended')}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-slate-400">{raid.description}</p>

                <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <p className="text-slate-500">{t('raidWizard.raidLevel.redundancy')}</p>
                    <p className="text-slate-300">{raid.redundancy}</p>
                  </div>
                  <div>
                    <p className="text-slate-500">{t('raidWizard.raidLevel.capacity')}</p>
                    <p className="text-slate-300">{raid.capacity}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-slate-500">{t('raidWizard.raidLevel.performance')}</p>
                    <p className="text-slate-300">{raid.performance}</p>
                  </div>
                </div>
              </div>
              <div
                className={`ml-4 flex h-5 w-5 items-center justify-center rounded-full border-2 transition ${
                  selectedRaidLevel === raid.level
                    ? 'border-sky-500 bg-sky-500'
                    : 'border-slate-600 bg-slate-900'
                }`}
              >
                {selectedRaidLevel === raid.level && (
                  <div className="h-2 w-2 rounded-full bg-white" />
                )}
              </div>
            </div>
          </button>
        ))}
      </div>

      <div className="mt-6 flex justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
        >
          {t('raidWizard.back')}
        </button>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
          >
            {t('raidWizard.cancel')}
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={!canProceed}
            className={`rounded-lg border px-4 py-2 text-sm transition ${
              canProceed
                ? 'border-sky-500/40 bg-sky-500/15 text-sky-100 hover:border-sky-500/60'
                : 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
            }`}
          >
            {t('raidWizard.next')}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidLevelSelectionStep.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/raid-setup/RaidLevelSelectionStep.tsx client/src/__tests__/components/raid-setup/RaidLevelSelectionStep.test.tsx
git commit -m "feat(raid): extract RaidLevelSelectionStep component (#301)"
```

---

## Task 6: `RaidConfirmationStep.tsx`

**Files:**
- Create: `client/src/components/raid-setup/RaidConfirmationStep.tsx`
- Test: `client/src/__tests__/components/raid-setup/RaidConfirmationStep.test.tsx`

**Interfaces:**
- Consumes: `RaidLevelInfo` aus `./raidLevels`.
- Produces: default export `RaidConfirmationStep` mit Props:

```ts
interface RaidConfirmationStepProps {
  arrayName: string;
  onArrayNameChange: (name: string) => void;
  isArrayNameValid: boolean;
  raidInfo: RaidLevelInfo | undefined;
  capacity: string;
  selectedDisks: string[];
  busy: boolean;
  onBack: () => void;
  onCancel: () => void;
  onSubmit: (e: FormEvent) => void;
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/raid-setup/RaidConfirmationStep.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RaidConfirmationStep from '../../../components/raid-setup/RaidConfirmationStep';
import { RAID_LEVELS } from '../../../components/raid-setup/raidLevels';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = {
  arrayName: 'md1', onArrayNameChange: vi.fn(), isArrayNameValid: true,
  raidInfo: RAID_LEVELS[0], capacity: '5 GB', selectedDisks: ['sda', 'sdb'],
  busy: false, onBack: vi.fn(), onCancel: vi.fn(), onSubmit: vi.fn(),
};

describe('RaidConfirmationStep', () => {
  it('renders capacity, disk chips and the create button', () => {
    render(<RaidConfirmationStep {...base} />);
    expect(screen.getByText('5 GB')).toBeInTheDocument();
    expect(screen.getByText('/dev/sda')).toBeInTheDocument();
    expect(screen.getByText('raidWizard.createArray')).toBeInTheDocument();
  });

  it('typing in the name input fires onArrayNameChange', () => {
    const onArrayNameChange = vi.fn();
    render(<RaidConfirmationStep {...base} onArrayNameChange={onArrayNameChange} />);
    fireEvent.change(screen.getByPlaceholderText('md0'), { target: { value: 'md2' } });
    expect(onArrayNameChange).toHaveBeenCalledWith('md2');
  });

  it('disables submit when the name is invalid', () => {
    render(<RaidConfirmationStep {...base} isArrayNameValid={false} />);
    expect(screen.getByText('raidWizard.createArray')).toBeDisabled();
  });

  it('shows the creating label and disables submit while busy', () => {
    render(<RaidConfirmationStep {...base} busy />);
    expect(screen.getByText('raidWizard.creating')).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidConfirmationStep.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/raid-setup/RaidConfirmationStep.tsx` (aus `renderConfirmation`, `RaidSetupWizard.tsx:404-527`; `arrayName`/`setArrayName`/`isArrayNameValid`/`raidInfo`/`capacity`/`selectedDisks`/`busy` → Props, `setCurrentStep('raid-level')` → `onBack`, `onClose` → `onCancel`, `handleSubmit` → `onSubmit`):

```tsx
import { type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { RaidLevelInfo } from './raidLevels';

interface RaidConfirmationStepProps {
  arrayName: string;
  onArrayNameChange: (name: string) => void;
  isArrayNameValid: boolean;
  raidInfo: RaidLevelInfo | undefined;
  capacity: string;
  selectedDisks: string[];
  busy: boolean;
  onBack: () => void;
  onCancel: () => void;
  onSubmit: (e: FormEvent) => void;
}

export default function RaidConfirmationStep({
  arrayName, onArrayNameChange, isArrayNameValid, raidInfo, capacity, selectedDisks, busy, onBack, onCancel, onSubmit,
}: RaidConfirmationStepProps) {
  const { t } = useTranslation('system');

  return (
    <form onSubmit={onSubmit}>
      <h3 className="text-xl font-semibold text-white">{t('raidWizard.confirm.title')}</h3>
      <p className="mt-2 text-sm text-slate-400">{t('raidWizard.confirm.description')}</p>

      <div className="mt-6 space-y-4">
        {/* Array Name */}
        <div>
          <label className="block text-sm font-medium text-slate-300">{t('raidWizard.confirm.arrayName')}</label>
          <input
            type="text"
            value={arrayName}
            onChange={(e) => onArrayNameChange(e.target.value)}
            required
            pattern="^md([0-9]+|_[a-zA-Z0-9]+)$"
            maxLength={32}
            placeholder="md0"
            className={`mt-1 w-full rounded-lg border bg-slate-950/70 px-3 py-2 text-sm text-slate-200 focus:outline-none ${
              arrayName && !isArrayNameValid
                ? 'border-red-500/60 focus:border-red-500'
                : 'border-slate-800 focus:border-sky-500'
            }`}
          />
          {arrayName && !isArrayNameValid && (
            <p className="mt-1 text-xs text-red-400">
              {t('raidWizard.confirm.invalidName', 'Name must be "md" + digits (e.g. md0) or "md_" + alphanumerics (e.g. md_backup).')}
            </p>
          )}
        </div>

        {/* Configuration Summary */}
        <div className="rounded-lg border border-slate-700/70 bg-slate-900/60 p-4">
          <h4 className="font-medium text-white">{t('raidWizard.confirm.summary')}</h4>

          <div className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">{t('raidWizard.confirm.raidLevelLabel')}</span>
              <span className="font-medium text-slate-200">{raidInfo?.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">{t('raidWizard.confirm.diskCount')}</span>
              <span className="font-medium text-slate-200">{selectedDisks.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">{t('raidWizard.confirm.availableCapacity')}</span>
              <span className="font-medium text-emerald-200">{capacity}</span>
            </div>
          </div>

          <div className="mt-4 border-t border-slate-800 pt-3">
            <p className="text-xs font-medium text-slate-400">{t('raidWizard.confirm.selectedDisks')}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {selectedDisks.map((disk) => (
                <span
                  key={disk}
                  className="rounded-md bg-slate-800/60 px-2 py-1 text-xs font-medium text-slate-300"
                >
                  /dev/{disk}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Warning */}
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
          <div className="flex items-start gap-3">
            <svg
              className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <div>
              <p className="text-sm font-medium text-amber-200">{t('raidWizard.confirm.warningTitle')}</p>
              <p className="mt-1 text-xs text-amber-200/80">
                {t('raidWizard.confirm.warningMessage')}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
        >
          {t('raidWizard.back')}
        </button>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-600"
          >
            {t('raidWizard.cancel')}
          </button>
          <button
            type="submit"
            disabled={busy || !isArrayNameValid}
            className={`rounded-lg border px-4 py-2 text-sm transition ${
              busy || !isArrayNameValid
                ? 'cursor-not-allowed border-slate-800 bg-slate-900/60 text-slate-500'
                : 'border-emerald-500/40 bg-emerald-500/15 text-emerald-100 hover:border-emerald-500/60'
            }`}
          >
            {busy ? t('raidWizard.creating') : t('raidWizard.createArray')}
          </button>
        </div>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup/RaidConfirmationStep.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/raid-setup/RaidConfirmationStep.tsx client/src/__tests__/components/raid-setup/RaidConfirmationStep.test.tsx
git commit -m "feat(raid): extract RaidConfirmationStep component (#301)"
```

---

## Task 7: Barrel + Orchestrator rewire + Docs

**Files:**
- Create: `client/src/components/raid-setup/index.ts`
- Modify: `client/src/components/RaidSetupWizard.tsx` (auf Orchestrator reduzieren)
- Modify: `client/src/components/CLAUDE.md` (`raid-setup/`-Zeile ergänzen)

**Interfaces:**
- Consumes: `useRaidSetupWizard` (Task 2), `calculateArrayCapacity` (Task 1), `RaidWizardStepIndicator`/`RaidDiskSelectionStep`/`RaidLevelSelectionStep`/`RaidConfirmationStep` (Tasks 3-6), `AvailableDisk`.
- Produces: `RaidSetupWizard` (Default-Export, **unveränderte** `RaidSetupWizardProps`).

- [ ] **Step 1: Create the internal barrel**

`client/src/components/raid-setup/index.ts`:

```ts
export { default as RaidWizardStepIndicator } from './RaidWizardStepIndicator';
export { default as RaidDiskSelectionStep } from './RaidDiskSelectionStep';
export { default as RaidLevelSelectionStep } from './RaidLevelSelectionStep';
export { default as RaidConfirmationStep } from './RaidConfirmationStep';
```

- [ ] **Step 2: Rewrite `RaidSetupWizard.tsx` as the orchestrator**

Ersetze den **gesamten** Inhalt von `client/src/components/RaidSetupWizard.tsx` durch:

```tsx
import type { AvailableDisk } from '../api/raid';
import { useRaidSetupWizard } from '../hooks/useRaidSetupWizard';
import { calculateArrayCapacity } from './raid-setup/raidWizardHelpers';
import {
  RaidWizardStepIndicator,
  RaidDiskSelectionStep,
  RaidLevelSelectionStep,
  RaidConfirmationStep,
} from './raid-setup';

interface RaidSetupWizardProps {
  availableDisks: AvailableDisk[];
  onClose: () => void;
  onSuccess: () => void;
}

export default function RaidSetupWizard({ availableDisks, onClose, onSuccess }: RaidSetupWizardProps) {
  const w = useRaidSetupWizard(availableDisks, onClose, onSuccess);
  const capacity = calculateArrayCapacity(w.selectedRaidLevel, w.selectedDisks.length);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl rounded-2xl border border-slate-800/60 bg-slate-900/95 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <RaidWizardStepIndicator currentStep={w.currentStep} />

        {w.currentStep === 'select-disks' && (
          <RaidDiskSelectionStep
            freeDisks={w.freeDisks}
            selectedDisks={w.selectedDisks}
            onToggleDisk={w.toggleDiskSelection}
            canProceed={w.canProceedFromDiskSelection()}
            onCancel={onClose}
            onNext={() => w.setCurrentStep('raid-level')}
          />
        )}
        {w.currentStep === 'raid-level' && (
          <RaidLevelSelectionStep
            selectedDisks={w.selectedDisks}
            selectedRaidLevel={w.selectedRaidLevel}
            onSelectLevel={w.setSelectedRaidLevel}
            canProceed={w.canProceedFromRaidLevel()}
            onBack={() => w.setCurrentStep('select-disks')}
            onCancel={onClose}
            onNext={() => w.setCurrentStep('confirm')}
          />
        )}
        {w.currentStep === 'confirm' && (
          <RaidConfirmationStep
            arrayName={w.arrayName}
            onArrayNameChange={w.setArrayName}
            isArrayNameValid={w.isArrayNameValid}
            raidInfo={w.getSelectedRaidInfo()}
            capacity={capacity}
            selectedDisks={w.selectedDisks}
            busy={w.busy}
            onBack={() => w.setCurrentStep('raid-level')}
            onCancel={onClose}
            onSubmit={w.handleSubmit}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Update `components/CLAUDE.md`**

Füge in `client/src/components/CLAUDE.md` in der Feature-Subdir-Tabelle eine neue Zeile hinzu (alphabetisch bei `raid/`), bzw. ergänze eine eigene `raid-setup/`-Zeile:

```
| `raid-setup/` | RAID creation wizard — `RaidSetupWizard` composes `raid-setup/*`: `RaidWizardStepIndicator`, `RaidDiskSelectionStep`, `RaidLevelSelectionStep`, `RaidConfirmationStep` + `raidLevels` data + pure `raidWizardHelpers` (`calculateArrayCapacity`/`isValidArrayName`); state/navigation/submit in `hooks/useRaidSetupWizard` (extracted F2/#301) |
```

- [ ] **Step 4: Run the combined raid-setup + hook suite**

Run (in `client/`): `npx vitest run src/__tests__/components/raid-setup src/__tests__/hooks/useRaidSetupWizard.test.tsx`
Expected: PASS (alle Tasks-1–6-Tests grün).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/raid-setup/index.ts client/src/components/RaidSetupWizard.tsx client/src/components/CLAUDE.md
git commit -m "refactor(raid): RaidSetupWizard thin orchestrator over raid-setup/* + useRaidSetupWizard (#301)"
```

---

## Task 8: Full verification gate

**Files:** none (verification only).

- [ ] **Step 1: Full frontend test suite**

Run (in `client/`): `npx vitest run`
Expected: PASS, keine Regressionen.

- [ ] **Step 2: ESLint 0-error gate**

Run (in `client/`): `npx eslint .`
Expected: 0 Fehler. Achte auf ungenutzte Imports im neuen `RaidSetupWizard.tsx` (aus dem Original entfernt: `useState`, `FormEvent`, `toast`, `useTranslation`, `createArray`, `formatBytes`). Falls Fehler: entfernen, bis grün.

- [ ] **Step 3: Production build (tsc -b + vite)**

Run (in `client/`): `npm run build`
Expected: erfolgreicher Build, keine Typfehler.

- [ ] **Step 4: Confirm line count target**

`RaidSetupWizard.tsx` sollte deutlich unter 500 Zeilen liegen (~75). Bestätigen.

- [ ] **Step 5: Final commit (falls Verifikation Fixes brachte)**

```bash
git add -A
git commit -m "chore(raid): verification fixes for RaidSetupWizard decomposition (#301)"
```

(Nur committen, wenn Schritte 1–3 Änderungen erforderten.)

---

## Self-Review (durchgeführt beim Schreiben)

**1. Spec coverage:** ✅ Alle Spec-Einheiten haben Tasks — `raidLevels` + pure `raidWizardHelpers` (T1), `useRaidSetupWizard` (T2), 4 Step-Subkomponenten (T3-T6), Orchestrator + Barrel + Docs (T7), Verify-Gate (T8). Der 5-GB-Dev-Quirk in `calculateArrayCapacity` ist verbatim übernommen.

**2. Placeholder scan:** ✅ Kein TBD/TODO. Jeder Code-Schritt vollständig, Tests mit konkreten Assertions (Capacity via `formatBytes(expected)` verglichen → robust gegen das Formatierungs-Format), jedes Kommando mit erwarteter Ausgabe.

**3. Type consistency:** ✅ `WizardStep` aus dem Hook exportiert, in StepIndicator konsumiert. `RaidLevelInfo`/`RAID_LEVELS` aus `raidLevels.ts` in Helpers/Hook/LevelStep/ConfirmStep konsumiert. Hook-Return-Namen (`toggleDiskSelection`, `getSelectedRaidInfo`, `canProceedFrom*`, `handleSubmit`, `setSelectedRaidLevel`, `setArrayName`, `setCurrentStep`) stimmen mit T7-Verdrahtung überein. Step-Prop-Namen (`onToggleDisk`, `onSelectLevel`, `onArrayNameChange`, `canProceed`, `onNext`/`onBack`/`onCancel`/`onSubmit`) konsistent zwischen Interfaces und Orchestrator. `calculateArrayCapacity(level, diskCount)`-Signatur konsistent T1↔T7.

**Bewusst außerhalb Scope:** die hartcodierten englischen `RAID_LEVELS`-Strings + der 5-GB-Dev-Quirk bleiben verbatim (kein i18n/Fix).
