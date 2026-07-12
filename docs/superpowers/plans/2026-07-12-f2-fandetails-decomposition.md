# FanDetails.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zerlege `client/src/components/fan-control/FanDetails.tsx` (619 Zeilen) verhaltenserhaltend in einen schlanken Orchestrator plus Logik-Hook, pure Helper und 4 reine Präsentations-Subkomponenten.

**Architecture:** Alle Zustandslogik (State, Effekte, 16 Handler) wandert in `hooks/useFanCurveEditor.ts`. `validateCurvePoints` wird zu einer puren Funktion in `fan-control/fanCurveValidation.ts`. Vier JSX-Blöcke werden zu reinen Komponenten unter `fan-control/fan-details/`. `FanDetails.tsx` bleibt Composition-Root. Öffentliche Prop-Signatur, Default-Export und Barrel bleiben identisch.

**Tech Stack:** React 18 + TypeScript, Vitest + @testing-library/react, react-i18next, react-hot-toast, Tailwind CSS.

## Global Constraints

- **Verhaltenserhaltend:** Keine Änderung an sichtbarem Verhalten, API-Calls oder der `FanDetails`-Prop-Schnittstelle. Einziger Konsument `pages/FanControl.tsx` und Barrel `fan-control/index.ts` bleiben unverändert.
- **i18n:** Alle Übersetzungsschlüssel und `useTranslation(['system','common'])`-Namespaces bleiben exakt wie im Original. Keine neuen Strings.
- **Tailwind-Klassen verbatim** aus dem Original übernehmen (kein Restyling).
- **Kein neuer öffentlicher Re-Export** in `fan-control/index.ts` — Hook und `fan-details/*` sind interne Implementierungsdetails.
- **Der `localGpuManualEnabled`-Reset-Befund** (kein Fan-Wechsel-Reset) wird **verhaltensgleich** portiert, NICHT gefixt.
- **Verify-Gate vor PR:** `npx vitest run`, `npx eslint .` (0 Fehler), `npm run build`. Arbeitsverzeichnis für alle Kommandos: `client/`.
- **Tests-Layout:** Komponententests unter `client/src/__tests__/components/fan-control/…`, Hook-Tests unter `client/src/__tests__/hooks/…`.
- **CRLF:** Repo läuft mit `core.autocrlf=true` — LF→CRLF-Warnungen bei `git add` sind erwartbar, kein Fehler.

**Referenz-Typen (aus `client/src/api/fan-control.ts`):**

```ts
export interface FanCurvePoint { temp: number; pwm: number; }
export const CURVE_PRESETS: Record<string, FanCurvePoint[]>; // keys: silent | balanced | performance
export interface FanCurveProfile { id: number; name: string; description?: string | null; curve_points: FanCurvePoint[]; is_system: boolean; created_at?: string; updated_at?: string; }
export interface FanInfo { /* fan_id, name, min_pwm_percent, max_pwm_percent, emergency_temp_celsius, temp_sensor_id, curve_points, hysteresis_celsius, curve_type?, flat_pwm_percent?, target_temp_celsius?, target_pwm_percent?, mix_curve_a_id?, mix_curve_b_id?, mix_function?, sync_fan_id?, is_gpu_fan?, gpu_vendor?, temperature_celsius, pwm_percent, … */ }
export function updateFanConfig(fanId: string, patch: Partial<UpdateFanConfigRequest>): Promise<UpdateFanConfigResponse>;
// CurveType (aus components/fan-control/CurveTypeSelector.tsx):
export type CurveType = 'graph' | 'flat' | 'target' | 'mix' | 'sync';
```

---

## File Structure

**Create:**
- `client/src/components/fan-control/fanCurveValidation.ts` — pure `validateCurvePoints`
- `client/src/hooks/useFanCurveEditor.ts` — State + Effekte + Handler
- `client/src/components/fan-control/fan-details/FanPresetProfileButtons.tsx`
- `client/src/components/fan-control/fan-details/FanCurveGraphControls.tsx`
- `client/src/components/fan-control/fan-details/FanCurveTableEditor.tsx`
- `client/src/components/fan-control/fan-details/FanStatsGrid.tsx`
- `client/src/components/fan-control/fan-details/index.ts` — interner Barrel
- Tests:
  - `client/src/__tests__/components/fan-control/fanCurveValidation.test.ts`
  - `client/src/__tests__/hooks/useFanCurveEditor.test.tsx`
  - `client/src/__tests__/components/fan-control/fan-details/FanPresetProfileButtons.test.tsx`
  - `client/src/__tests__/components/fan-control/fan-details/FanCurveGraphControls.test.tsx`
  - `client/src/__tests__/components/fan-control/fan-details/FanCurveTableEditor.test.tsx`
  - `client/src/__tests__/components/fan-control/fan-details/FanStatsGrid.test.tsx`

**Modify:**
- `client/src/components/fan-control/FanDetails.tsx` — auf Orchestrator reduzieren (Task 7)
- `client/src/components/CLAUDE.md` — `fan-control/`-Zeile um `fan-details/*` ergänzen (Task 7)

---

## Task 1: `fanCurveValidation.ts` (pure Helper)

**Files:**
- Create: `client/src/components/fan-control/fanCurveValidation.ts`
- Test: `client/src/__tests__/components/fan-control/fanCurveValidation.test.ts`

**Interfaces:**
- Consumes: `FanCurvePoint` aus `../../api/fan-control`, `TFunction` aus `i18next`.
- Produces: `validateCurvePoints(points: FanCurvePoint[], bounds: { minPwm: number; maxPwm: number }, t: TFunction): { valid: boolean; error?: string }`.

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fanCurveValidation.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import type { TFunction } from 'i18next';
import { validateCurvePoints } from '../../../components/fan-control/fanCurveValidation';

// t stub: returns the key so we can assert which validation branch fired
const t = ((k: string) => k) as unknown as TFunction;
const bounds = { minPwm: 30, maxPwm: 100 };

describe('validateCurvePoints', () => {
  it('rejects fewer than 2 points', () => {
    const r = validateCurvePoints([{ temp: 40, pwm: 50 }], bounds, t);
    expect(r.valid).toBe(false);
    expect(r.error).toBe('system:fanControl.validation.minPoints');
  });

  it('rejects non-ascending temperatures', () => {
    const r = validateCurvePoints([{ temp: 50, pwm: 40 }, { temp: 50, pwm: 60 }], bounds, t);
    expect(r.valid).toBe(false);
    expect(r.error).toBe('system:fanControl.validation.ascendingTemp');
  });

  it('rejects pwm below minPwm', () => {
    const r = validateCurvePoints([{ temp: 40, pwm: 10 }, { temp: 60, pwm: 80 }], bounds, t);
    expect(r.valid).toBe(false);
    expect(r.error).toBe('system:fanControl.validation.pwmRange');
  });

  it('rejects pwm above maxPwm', () => {
    const r = validateCurvePoints([{ temp: 40, pwm: 50 }, { temp: 60, pwm: 120 }], bounds, t);
    expect(r.valid).toBe(false);
    expect(r.error).toBe('system:fanControl.validation.pwmRange');
  });

  it('accepts a valid ascending in-range curve', () => {
    const r = validateCurvePoints([{ temp: 40, pwm: 40 }, { temp: 60, pwm: 80 }], bounds, t);
    expect(r.valid).toBe(true);
    expect(r.error).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fanCurveValidation.test.ts`
Expected: FAIL — `Failed to resolve import ".../fanCurveValidation"`.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fanCurveValidation.ts`:

```ts
import type { TFunction } from 'i18next';
import type { FanCurvePoint } from '../../api/fan-control';

export interface CurveBounds {
  minPwm: number;
  maxPwm: number;
}

/**
 * Validates a fan curve. Pure — pwm bounds and the i18n `t` function are passed in.
 * Rules (unchanged from FanDetails): >= 2 points, strictly ascending temps,
 * every pwm within [minPwm, maxPwm].
 */
export function validateCurvePoints(
  points: FanCurvePoint[],
  bounds: CurveBounds,
  t: TFunction,
): { valid: boolean; error?: string } {
  if (points.length < 2) {
    return { valid: false, error: t('system:fanControl.validation.minPoints') };
  }

  const sorted = [...points].sort((a, b) => a.temp - b.temp);
  for (let i = 0; i < sorted.length - 1; i++) {
    if (sorted[i].temp >= sorted[i + 1].temp) {
      return { valid: false, error: t('system:fanControl.validation.ascendingTemp') };
    }
  }

  for (const point of points) {
    if (point.pwm < bounds.minPwm || point.pwm > bounds.maxPwm) {
      return {
        valid: false,
        error: t('system:fanControl.validation.pwmRange', { min: bounds.minPwm, max: bounds.maxPwm }),
      };
    }
  }

  return { valid: true };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fanCurveValidation.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fanCurveValidation.ts client/src/__tests__/components/fan-control/fanCurveValidation.test.ts
git commit -m "feat(fan-control): extract pure validateCurvePoints helper (#301)"
```

---

## Task 2: `useFanCurveEditor.ts` (Logik-Hook)

**Files:**
- Create: `client/src/hooks/useFanCurveEditor.ts`
- Test: `client/src/__tests__/hooks/useFanCurveEditor.test.tsx`

**Interfaces:**
- Consumes: `validateCurvePoints` (Task 1), `CurveType` aus `../components/fan-control/CurveTypeSelector`, `FanInfo`/`FanCurvePoint`/`FanCurveProfile`/`CURVE_PRESETS`/`updateFanConfig` aus `../api/fan-control`, `handleApiError` aus `../lib/errorHandling`, `toast`, `useTranslation`.
- Produces:

```ts
function useFanCurveEditor(fan: FanInfo, opts: UseFanCurveEditorOptions): {
  curvePoints: FanCurvePoint[];
  viewMode: 'chart' | 'table';
  setViewMode: (m: 'chart' | 'table') => void;
  hysteresis: number;
  isUpdatingHysteresis: boolean;
  curveType: CurveType;
  localGpuManualEnabled: boolean;
  setLocalGpuManualEnabled: (v: boolean) => void;
  showMoreProfiles: boolean;
  setShowMoreProfiles: (v: boolean) => void;
  canEdit: boolean;
  hasUnsavedChanges: boolean;
  hysteresisChanged: boolean;
  systemProfiles: FanCurveProfile[];
  userProfiles: FanCurveProfile[];
  handleCurveTypeChange: (v: CurveType) => Promise<void>;
  handleFlatChange: (v: number) => Promise<void>;
  handleTargetChange: (a: { targetTemp: number; targetPwm: number }) => Promise<void>;
  handleMixChange: (a: { curveAId: number | null; curveBId: number | null; fn: 'max' | 'sum' }) => Promise<void>;
  handleSyncChange: (v: string | null) => Promise<void>;
  handleSaveCurve: () => void;
  handleDiscardChanges: () => void;
  handleAddPoint: () => void;
  handleRemovePoint: (index: number) => void;
  handleUpdatePoint: (index: number, field: 'temp' | 'pwm', value: number) => void;
  handleApplyPreset: (preset: string) => void;
  handleApplyProfileCurve: (profile: FanCurveProfile) => void;
  handleChartPointsChange: (points: FanCurvePoint[]) => void;
  handleHysteresisChange: (value: number) => Promise<void>;
  handleHysteresisSave: () => Promise<void>;
  handleAdvancedChange: (patch: Partial<FanInfo>) => Promise<void>;
};

interface UseFanCurveEditorOptions {
  isReadOnly: boolean;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  onConfigUpdate?: () => void;
  onEditingChange?: (isEditing: boolean) => void;
  onApplyProfile?: (profile: FanCurveProfile) => void;
  profiles?: FanCurveProfile[];
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/hooks/useFanCurveEditor.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { FanInfo } from '../../api/fan-control';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../lib/errorHandling', () => ({ handleApiError: vi.fn() }));
vi.mock('../../api/fan-control', async (importActual) => {
  const actual = await importActual<typeof import('../../api/fan-control')>();
  return { ...actual, updateFanConfig: vi.fn().mockResolvedValue({ success: true }) };
});

import toast from 'react-hot-toast';
import { useFanCurveEditor } from '../../hooks/useFanCurveEditor';

const fan = (over: Partial<FanInfo> = {}): FanInfo => ({
  fan_id: 'fan1', name: 'CPU Fan', rpm: 1200, pwm_percent: 50, temperature_celsius: 45,
  mode: 'auto', is_active: true, min_pwm_percent: 30, max_pwm_percent: 100,
  emergency_temp_celsius: 90, temp_sensor_id: null, hysteresis_celsius: 3,
  curve_points: [{ temp: 40, pwm: 40 }, { temp: 60, pwm: 80 }],
  curve_type: 'graph',
  ...over,
} as FanInfo);

const opts = () => ({ isReadOnly: false, onCurveUpdate: vi.fn(), onConfigUpdate: vi.fn(), onEditingChange: vi.fn() });

describe('useFanCurveEditor', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('starts with no unsaved changes', () => {
    const { result } = renderHook(() => useFanCurveEditor(fan(), opts()));
    expect(result.current.hasUnsavedChanges).toBe(false);
    expect(result.current.curvePoints).toHaveLength(2);
  });

  it('handleAddPoint appends a point and flags unsaved changes', () => {
    const { result } = renderHook(() => useFanCurveEditor(fan(), opts()));
    act(() => result.current.handleAddPoint());
    expect(result.current.curvePoints).toHaveLength(3);
    expect(result.current.hasUnsavedChanges).toBe(true);
  });

  it('handleRemovePoint keeps at least 2 points', () => {
    const { result } = renderHook(() => useFanCurveEditor(fan(), opts()));
    act(() => result.current.handleRemovePoint(0));
    expect(result.current.curvePoints).toHaveLength(2); // guard blocks removal below 2
  });

  it('handleUpdatePoint edits a field', () => {
    const { result } = renderHook(() => useFanCurveEditor(fan(), opts()));
    act(() => result.current.handleUpdatePoint(0, 'pwm', 55));
    expect(result.current.curvePoints[0].pwm).toBe(55);
  });

  it('handleApplyPreset replaces points from CURVE_PRESETS', () => {
    const { result } = renderHook(() => useFanCurveEditor(fan(), opts()));
    act(() => result.current.handleApplyPreset('silent'));
    expect(result.current.curvePoints).toHaveLength(5); // silent preset has 5 points
    expect(result.current.hasUnsavedChanges).toBe(true);
  });

  it('handleSaveCurve blocks on an invalid curve (single point) and does not call onCurveUpdate', () => {
    const o = opts();
    const { result } = renderHook(() => useFanCurveEditor(fan({ curve_points: [{ temp: 40, pwm: 40 }] }), o));
    act(() => result.current.handleSaveCurve());
    expect(toast.error).toHaveBeenCalled();
    expect(o.onCurveUpdate).not.toHaveBeenCalled();
  });

  it('handleSaveCurve calls onCurveUpdate on a valid curve', () => {
    const o = opts();
    const { result } = renderHook(() => useFanCurveEditor(fan(), o));
    act(() => result.current.handleSaveCurve());
    expect(o.onCurveUpdate).toHaveBeenCalledWith('fan1', expect.any(Array));
  });

  it('does not overwrite user-edited points when the fan prop re-syncs', () => {
    const { result, rerender } = renderHook(
      ({ f }) => useFanCurveEditor(f, opts()),
      { initialProps: { f: fan() } },
    );
    act(() => result.current.handleUpdatePoint(0, 'pwm', 55));
    // Same fan_id, server pushes a different curve — userEdited guard must keep local edits
    rerender({ f: fan({ curve_points: [{ temp: 40, pwm: 99 }, { temp: 60, pwm: 99 }] }) });
    expect(result.current.curvePoints[0].pwm).toBe(55);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/hooks/useFanCurveEditor.test.tsx`
Expected: FAIL — `Failed to resolve import ".../hooks/useFanCurveEditor"`.

- [ ] **Step 3: Write minimal implementation**

`client/src/hooks/useFanCurveEditor.ts` (Logik 1:1 aus `FanDetails.tsx` portiert; einzige inhaltliche Änderung: `validateCurvePoints` erhält `bounds`-Objekt + `t` als Parameter):

```ts
import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import toast from 'react-hot-toast';
import { useTranslation } from 'react-i18next';
import type { FanInfo, FanCurvePoint, FanCurveProfile } from '../api/fan-control';
import { CURVE_PRESETS, updateFanConfig } from '../api/fan-control';
import { handleApiError } from '../lib/errorHandling';
import type { CurveType } from '../components/fan-control/CurveTypeSelector';
import { validateCurvePoints } from '../components/fan-control/fanCurveValidation';

export interface UseFanCurveEditorOptions {
  isReadOnly: boolean;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  onConfigUpdate?: () => void;
  onEditingChange?: (isEditing: boolean) => void;
  onApplyProfile?: (profile: FanCurveProfile) => void;
  profiles?: FanCurveProfile[];
}

export function useFanCurveEditor(fan: FanInfo, opts: UseFanCurveEditorOptions) {
  const { isReadOnly, onCurveUpdate, onConfigUpdate, onEditingChange, onApplyProfile, profiles } = opts;
  const { t } = useTranslation(['system', 'common']);

  const [curvePoints, setCurvePoints] = useState<FanCurvePoint[]>(fan.curve_points);
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');
  const [hysteresis, setHysteresis] = useState<number>(fan.hysteresis_celsius ?? 3.0);
  const [isUpdatingHysteresis, setIsUpdatingHysteresis] = useState(false);
  const [curveType, setCurveType] = useState<CurveType>((fan.curve_type as CurveType) ?? 'graph');
  const [localGpuManualEnabled, setLocalGpuManualEnabled] = useState(false);
  const [showMoreProfiles, setShowMoreProfiles] = useState(false);

  // Tracks whether the user has manually edited the curve (prevents auto-refresh overwrites)
  const userEditedRef = useRef(false);

  // Editing is always enabled when not read-only (FanControl-style)
  const canEdit = !isReadOnly;

  // Sync curveType from server when fan changes
  useEffect(() => {
    setCurveType((fan.curve_type as CurveType) ?? 'graph');
  }, [fan.fan_id, fan.curve_type]);

  // Check if curve has been modified (compare with original)
  const hasUnsavedChanges = useMemo(() => {
    if (curvePoints.length !== fan.curve_points.length) return true;
    const sortedCurrent = [...curvePoints].sort((a, b) => a.temp - b.temp);
    const sortedOriginal = [...fan.curve_points].sort((a, b) => a.temp - b.temp);
    return sortedCurrent.some((p, i) =>
      p.temp !== sortedOriginal[i].temp || p.pwm !== sortedOriginal[i].pwm
    );
  }, [curvePoints, fan.curve_points]);

  // Sync curve points from server — but only when user hasn't manually edited
  useEffect(() => {
    if (!userEditedRef.current) {
      setCurvePoints(fan.curve_points);
    }
  }, [fan.fan_id, fan.curve_points]);

  // Reset userEditedRef when switching to a different fan
  useEffect(() => {
    userEditedRef.current = false;
    setCurvePoints(fan.curve_points);
  }, [fan.fan_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setHysteresis(fan.hysteresis_celsius ?? 3.0);
  }, [fan.fan_id, fan.hysteresis_celsius]);

  // Notify parent when there are unsaved changes (to pause auto-refresh)
  useEffect(() => {
    onEditingChange?.(hasUnsavedChanges);
  }, [hasUnsavedChanges, onEditingChange]);

  const handleCurveTypeChange = async (v: CurveType) => {
    if (isReadOnly) return;
    setCurveType(v);
    try {
      await updateFanConfig(fan.fan_id, { curve_type: v });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
      setCurveType((fan.curve_type as CurveType) ?? 'graph');
    }
  };

  const handleFlatChange = async (v: number) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { flat_pwm_percent: v });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleTargetChange = async ({ targetTemp, targetPwm }: { targetTemp: number; targetPwm: number }) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { target_temp_celsius: targetTemp, target_pwm_percent: targetPwm });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleMixChange = async ({ curveAId, curveBId, fn }: { curveAId: number | null; curveBId: number | null; fn: 'max' | 'sum' }) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { mix_curve_a_id: curveAId, mix_curve_b_id: curveBId, mix_function: fn });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleSyncChange = async (v: string | null) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, { sync_fan_id: v });
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const handleSaveCurve = () => {
    const validation = validateCurvePoints(
      curvePoints,
      { minPwm: fan.min_pwm_percent, maxPwm: fan.max_pwm_percent },
      t,
    );
    if (!validation.valid) {
      toast.error(validation.error || t('system:fanControl.validation.invalidCurve'));
      return;
    }

    userEditedRef.current = false;
    onCurveUpdate(fan.fan_id, curvePoints);
  };

  const handleDiscardChanges = () => {
    userEditedRef.current = false;
    setCurvePoints(fan.curve_points);
  };

  const handleAddPoint = () => {
    userEditedRef.current = true;
    const lastPoint = curvePoints[curvePoints.length - 1];
    const newTemp = lastPoint ? lastPoint.temp + 10 : 40;
    const newPWM = lastPoint ? Math.min(lastPoint.pwm + 10, 100) : 50;
    setCurvePoints([...curvePoints, { temp: newTemp, pwm: newPWM }]);
  };

  const handleRemovePoint = (index: number) => {
    if (curvePoints.length > 2) {
      userEditedRef.current = true;
      setCurvePoints(curvePoints.filter((_, i) => i !== index));
    }
  };

  const handleUpdatePoint = (index: number, field: 'temp' | 'pwm', value: number) => {
    userEditedRef.current = true;
    const updated = [...curvePoints];
    updated[index] = { ...updated[index], [field]: value };
    setCurvePoints(updated);
  };

  const handleApplyPreset = (preset: string) => {
    const presetPoints = CURVE_PRESETS[preset];
    if (presetPoints) {
      userEditedRef.current = true;
      setCurvePoints([...presetPoints]);
      toast.success(t('system:fanControl.curve.presetApplied', { preset }));
    }
  };

  const handleApplyProfileCurve = (profile: FanCurveProfile) => {
    if (onApplyProfile) {
      onApplyProfile(profile);
    } else {
      userEditedRef.current = true;
      setCurvePoints([...profile.curve_points]);
      toast.success(t('system:fanControl.curve.presetApplied', { preset: profile.name }));
    }
    setShowMoreProfiles(false);
  };

  // Wrapper for FanCurveChart's onPointsChange — marks as user-edited
  const handleChartPointsChange = useCallback((points: FanCurvePoint[]) => {
    userEditedRef.current = true;
    setCurvePoints(points);
  }, []);

  const handleHysteresisChange = async (value: number) => {
    setHysteresis(value);
  };

  const handleHysteresisSave = async () => {
    if (isReadOnly) return;

    setIsUpdatingHysteresis(true);
    try {
      await updateFanConfig(fan.fan_id, { hysteresis_celsius: hysteresis });
      toast.success(t('system:fanControl.messages.hysteresisSet', { value: hysteresis }));
      onConfigUpdate?.();
    } catch {
      toast.error(t('system:fanControl.messages.hysteresisFailed'));
      setHysteresis(fan.hysteresis_celsius ?? 3.0);
    } finally {
      setIsUpdatingHysteresis(false);
    }
  };

  const handleAdvancedChange = async (patch: Partial<FanInfo>) => {
    if (isReadOnly) return;
    try {
      await updateFanConfig(fan.fan_id, patch as Parameters<typeof updateFanConfig>[1]);
      onConfigUpdate?.();
    } catch (error: unknown) {
      handleApiError(error, t('system:fanControl.messages.curveFailed'));
    }
  };

  const systemProfiles = profiles?.filter(p => p.is_system) ?? [];
  const userProfiles = profiles?.filter(p => !p.is_system) ?? [];
  const hysteresisChanged = hysteresis !== (fan.hysteresis_celsius ?? 3.0);

  return {
    curvePoints, viewMode, setViewMode, hysteresis, isUpdatingHysteresis, curveType,
    localGpuManualEnabled, setLocalGpuManualEnabled, showMoreProfiles, setShowMoreProfiles,
    canEdit, hasUnsavedChanges, hysteresisChanged, systemProfiles, userProfiles,
    handleCurveTypeChange, handleFlatChange, handleTargetChange, handleMixChange,
    handleSyncChange, handleSaveCurve, handleDiscardChanges, handleAddPoint,
    handleRemovePoint, handleUpdatePoint, handleApplyPreset, handleApplyProfileCurve,
    handleChartPointsChange, handleHysteresisChange, handleHysteresisSave, handleAdvancedChange,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/hooks/useFanCurveEditor.test.tsx`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useFanCurveEditor.ts client/src/__tests__/hooks/useFanCurveEditor.test.tsx
git commit -m "feat(fan-control): add useFanCurveEditor hook (state + handlers) (#301)"
```

---

## Task 3: `FanPresetProfileButtons.tsx`

**Files:**
- Create: `client/src/components/fan-control/fan-details/FanPresetProfileButtons.tsx`
- Test: `client/src/__tests__/components/fan-control/fan-details/FanPresetProfileButtons.test.tsx`

**Interfaces:**
- Consumes: `FanCurveProfile` aus `../../../api/fan-control`.
- Produces: default export `FanPresetProfileButtons` mit Props:

```ts
interface FanPresetProfileButtonsProps {
  isReadOnly: boolean;
  systemProfiles: FanCurveProfile[];
  userProfiles: FanCurveProfile[];
  showMoreProfiles: boolean;
  onToggleMore: () => void;
  onApplyPreset: (preset: string) => void;
  onApplyProfile: (profile: FanCurveProfile) => void;
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fan-details/FanPresetProfileButtons.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { FanCurveProfile } from '../../../../api/fan-control';
import FanPresetProfileButtons from '../../../../components/fan-control/fan-details/FanPresetProfileButtons';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = {
  isReadOnly: false, systemProfiles: [], userProfiles: [],
  showMoreProfiles: false, onToggleMore: vi.fn(),
  onApplyPreset: vi.fn(), onApplyProfile: vi.fn(),
};

describe('FanPresetProfileButtons', () => {
  it('renders nothing when read-only', () => {
    const { container } = render(<FanPresetProfileButtons {...base} isReadOnly />);
    expect(container.firstChild).toBeNull();
  });

  it('falls back to hardcoded presets when there are no system profiles', () => {
    const onApplyPreset = vi.fn();
    render(<FanPresetProfileButtons {...base} onApplyPreset={onApplyPreset} />);
    fireEvent.click(screen.getByText('system:fanControl.presets.silent'));
    expect(onApplyPreset).toHaveBeenCalledWith('silent');
  });

  it('renders a system profile button and fires onApplyProfile', () => {
    const p: FanCurveProfile = { id: 1, name: 'balanced', curve_points: [], is_system: true };
    const onApplyProfile = vi.fn();
    render(<FanPresetProfileButtons {...base} systemProfiles={[p]} onApplyProfile={onApplyProfile} />);
    fireEvent.click(screen.getByText('Balanced'));
    expect(onApplyProfile).toHaveBeenCalledWith(p);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanPresetProfileButtons.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fan-details/FanPresetProfileButtons.tsx` (JSX aus `FanDetails.tsx:271-345` verbatim, Handler/State über Props):

```tsx
import { Zap, Volume2, Gauge, ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FanCurveProfile } from '../../../api/fan-control';

interface FanPresetProfileButtonsProps {
  isReadOnly: boolean;
  systemProfiles: FanCurveProfile[];
  userProfiles: FanCurveProfile[];
  showMoreProfiles: boolean;
  onToggleMore: () => void;
  onApplyPreset: (preset: string) => void;
  onApplyProfile: (profile: FanCurveProfile) => void;
}

export default function FanPresetProfileButtons({
  isReadOnly, systemProfiles, userProfiles, showMoreProfiles,
  onToggleMore, onApplyPreset, onApplyProfile,
}: FanPresetProfileButtonsProps) {
  const { t } = useTranslation(['system', 'common']);

  if (isReadOnly) return null;

  return (
    <div className="flex gap-2 flex-wrap items-center">
      {/* System profiles (or fallback to hardcoded presets) */}
      {systemProfiles.length > 0 ? (
        systemProfiles.map(p => {
          const icons: Record<string, typeof Volume2> = { silent: Volume2, balanced: Gauge, performance: Zap };
          const Icon = icons[p.name] ?? Gauge;
          return (
            <button
              key={p.id}
              onClick={() => onApplyProfile(p)}
              className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
              title={p.description ?? ''}
            >
              <Icon className="w-4 h-4" />
              {p.name.charAt(0).toUpperCase() + p.name.slice(1)}
            </button>
          );
        })
      ) : (
        <>
          <button
            onClick={() => onApplyPreset('silent')}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
            title={t('system:fanControl.presets.silentDesc')}
          >
            <Volume2 className="w-4 h-4" />
            {t('system:fanControl.presets.silent')}
          </button>
          <button
            onClick={() => onApplyPreset('balanced')}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
            title={t('system:fanControl.presets.balancedDesc')}
          >
            <Gauge className="w-4 h-4" />
            {t('system:fanControl.presets.balanced')}
          </button>
          <button
            onClick={() => onApplyPreset('performance')}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
            title={t('system:fanControl.presets.performanceDesc')}
          >
            <Zap className="w-4 h-4" />
            {t('system:fanControl.presets.performance')}
          </button>
        </>
      )}

      {/* User profiles dropdown */}
      {userProfiles.length > 0 && (
        <div className="relative">
          <button
            onClick={onToggleMore}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm flex items-center gap-1.5 transition-colors"
          >
            {t('system:fanControl.profiles.more')}
            <ChevronDown className={`w-3 h-3 transition-transform ${showMoreProfiles ? 'rotate-180' : ''}`} />
          </button>
          {showMoreProfiles && (
            <div className="absolute right-0 top-full mt-1 z-10 bg-slate-800 border border-slate-700 rounded-lg shadow-xl py-1 min-w-[160px]">
              {userProfiles.map(p => (
                <button
                  key={p.id}
                  onClick={() => onApplyProfile(p)}
                  className="w-full text-left px-3 py-2 text-sm text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  {p.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanPresetProfileButtons.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-details/FanPresetProfileButtons.tsx client/src/__tests__/components/fan-control/fan-details/FanPresetProfileButtons.test.tsx
git commit -m "feat(fan-control): extract FanPresetProfileButtons component (#301)"
```

---

## Task 4: `FanCurveGraphControls.tsx`

**Files:**
- Create: `client/src/components/fan-control/fan-details/FanCurveGraphControls.tsx`
- Test: `client/src/__tests__/components/fan-control/fan-details/FanCurveGraphControls.test.tsx`

**Interfaces:**
- Produces: default export `FanCurveGraphControls` mit Props:

```ts
interface FanCurveGraphControlsProps {
  viewMode: 'chart' | 'table';
  onViewModeChange: (mode: 'chart' | 'table') => void;
  hasUnsavedChanges: boolean;
  isReadOnly: boolean;
  onSave: () => void;
  onDiscard: () => void;
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fan-details/FanCurveGraphControls.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FanCurveGraphControls from '../../../../components/fan-control/fan-details/FanCurveGraphControls';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const base = {
  viewMode: 'chart' as const, onViewModeChange: vi.fn(),
  hasUnsavedChanges: false, isReadOnly: false, onSave: vi.fn(), onDiscard: vi.fn(),
};

describe('FanCurveGraphControls', () => {
  it('switches view mode on toggle click', () => {
    const onViewModeChange = vi.fn();
    render(<FanCurveGraphControls {...base} onViewModeChange={onViewModeChange} />);
    fireEvent.click(screen.getByText('system:fanControl.curve.table'));
    expect(onViewModeChange).toHaveBeenCalledWith('table');
  });

  it('hides save/discard when there are no unsaved changes', () => {
    render(<FanCurveGraphControls {...base} hasUnsavedChanges={false} />);
    expect(screen.queryByText('system:fanControl.curve.save')).not.toBeInTheDocument();
  });

  it('shows save/discard and fires callbacks when there are unsaved changes', () => {
    const onSave = vi.fn();
    const onDiscard = vi.fn();
    render(<FanCurveGraphControls {...base} hasUnsavedChanges onSave={onSave} onDiscard={onDiscard} />);
    fireEvent.click(screen.getByText('system:fanControl.curve.save'));
    fireEvent.click(screen.getByText('system:fanControl.curve.discard'));
    expect(onSave).toHaveBeenCalled();
    expect(onDiscard).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanCurveGraphControls.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fan-details/FanCurveGraphControls.tsx` (JSX aus `FanDetails.tsx:358-407` verbatim):

```tsx
import { Table, LineChart as LineChartIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface FanCurveGraphControlsProps {
  viewMode: 'chart' | 'table';
  onViewModeChange: (mode: 'chart' | 'table') => void;
  hasUnsavedChanges: boolean;
  isReadOnly: boolean;
  onSave: () => void;
  onDiscard: () => void;
}

export default function FanCurveGraphControls({
  viewMode, onViewModeChange, hasUnsavedChanges, isReadOnly, onSave, onDiscard,
}: FanCurveGraphControlsProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
      <p className="text-sm text-slate-400">
        {t('system:fanControl.curve.configureInfo')}
      </p>
      <div className="flex gap-2 items-center">
        {/* View Mode Toggle */}
        <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
          <button
            onClick={() => onViewModeChange('chart')}
            className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
              viewMode === 'chart'
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <LineChartIcon className="w-3 h-3" />
            {t('system:fanControl.curve.chart')}
          </button>
          <button
            onClick={() => onViewModeChange('table')}
            className={`px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1 ${
              viewMode === 'table'
                ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <Table className="w-3 h-3" />
            {t('system:fanControl.curve.table')}
          </button>
        </div>

        {/* Save/Discard Buttons - only shown when there are unsaved changes */}
        {hasUnsavedChanges && !isReadOnly && (
          <div className="flex gap-2">
            <button
              onClick={onDiscard}
              className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 text-sm"
            >
              {t('system:fanControl.curve.discard')}
            </button>
            <button
              onClick={onSave}
              className="px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 shadow-lg shadow-emerald-500/30 text-sm"
            >
              {t('system:fanControl.curve.save')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanCurveGraphControls.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-details/FanCurveGraphControls.tsx client/src/__tests__/components/fan-control/fan-details/FanCurveGraphControls.test.tsx
git commit -m "feat(fan-control): extract FanCurveGraphControls component (#301)"
```

---

## Task 5: `FanCurveTableEditor.tsx`

**Files:**
- Create: `client/src/components/fan-control/fan-details/FanCurveTableEditor.tsx`
- Test: `client/src/__tests__/components/fan-control/fan-details/FanCurveTableEditor.test.tsx`

**Interfaces:**
- Consumes: `FanCurvePoint` aus `../../../api/fan-control`.
- Produces: default export `FanCurveTableEditor` mit Props:

```ts
interface FanCurveTableEditorProps {
  curvePoints: FanCurvePoint[];
  canEdit: boolean;
  minPwm: number;
  maxPwm: number;
  onUpdatePoint: (index: number, field: 'temp' | 'pwm', value: number) => void;
  onRemovePoint: (index: number) => void;
  onAddPoint: () => void;
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fan-details/FanCurveTableEditor.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { FanCurvePoint } from '../../../../api/fan-control';
import FanCurveTableEditor from '../../../../components/fan-control/fan-details/FanCurveTableEditor';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const points: FanCurvePoint[] = [{ temp: 40, pwm: 40 }, { temp: 60, pwm: 80 }];
const base = {
  curvePoints: points, canEdit: true, minPwm: 30, maxPwm: 100,
  onUpdatePoint: vi.fn(), onRemovePoint: vi.fn(), onAddPoint: vi.fn(),
};

describe('FanCurveTableEditor', () => {
  it('shows Add Point when editable and under 10 points', () => {
    const onAddPoint = vi.fn();
    render(<FanCurveTableEditor {...base} onAddPoint={onAddPoint} />);
    fireEvent.click(screen.getByText('system:fanControl.curve.addPoint'));
    expect(onAddPoint).toHaveBeenCalled();
  });

  it('renders plain values (no inputs) when not editable', () => {
    render(<FanCurveTableEditor {...base} canEdit={false} />);
    expect(screen.queryByText('system:fanControl.curve.addPoint')).not.toBeInTheDocument();
    expect(screen.getByText('40°C')).toBeInTheDocument();
  });

  it('fires onUpdatePoint with the original index (sorted view maps back)', () => {
    const onUpdatePoint = vi.fn();
    render(<FanCurveTableEditor {...base} onUpdatePoint={onUpdatePoint} />);
    const tempInputs = screen.getAllByRole('spinbutton');
    fireEvent.change(tempInputs[0], { target: { value: '42' } });
    expect(onUpdatePoint).toHaveBeenCalledWith(0, 'temp', 42);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanCurveTableEditor.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fan-details/FanCurveTableEditor.tsx` (JSX aus `FanDetails.tsx:429-497` verbatim; `fan.min_pwm_percent`/`fan.max_pwm_percent` → `minPwm`/`maxPwm`-Props):

```tsx
import { useTranslation } from 'react-i18next';
import type { FanCurvePoint } from '../../../api/fan-control';

interface FanCurveTableEditorProps {
  curvePoints: FanCurvePoint[];
  canEdit: boolean;
  minPwm: number;
  maxPwm: number;
  onUpdatePoint: (index: number, field: 'temp' | 'pwm', value: number) => void;
  onRemovePoint: (index: number) => void;
  onAddPoint: () => void;
}

export default function FanCurveTableEditor({
  curvePoints, canEdit, minPwm, maxPwm, onUpdatePoint, onRemovePoint, onAddPoint,
}: FanCurveTableEditorProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-700">
          <thead className="bg-slate-800">
            <tr>
              <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.temperatureCol')}</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.pwmCol')}</th>
              {canEdit && <th className="px-4 py-2 text-left text-sm font-medium text-slate-300">{t('system:fanControl.details.actionsCol')}</th>}
            </tr>
          </thead>
          <tbody>
            {[...curvePoints]
              .map((point, originalIndex) => ({ ...point, originalIndex }))
              .sort((a, b) => a.temp - b.temp)
              .map((point) => (
                <tr key={point.originalIndex} className="border-t border-slate-700">
                  <td className="px-4 py-2">
                    {canEdit ? (
                      <input
                        type="number"
                        value={point.temp}
                        onChange={(e) => onUpdatePoint(point.originalIndex, 'temp', parseFloat(e.target.value))}
                        className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                        min={0}
                        max={150}
                      />
                    ) : (
                      <span className="text-slate-300">{point.temp}°C</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {canEdit ? (
                      <input
                        type="number"
                        value={point.pwm}
                        onChange={(e) => onUpdatePoint(point.originalIndex, 'pwm', parseInt(e.target.value))}
                        className="w-20 px-2 py-1 border border-slate-600 rounded bg-slate-800 text-white"
                        min={minPwm}
                        max={maxPwm}
                      />
                    ) : (
                      <span className="text-slate-300">{point.pwm}%</span>
                    )}
                  </td>
                  {canEdit && (
                    <td className="px-4 py-2">
                      <button
                        onClick={() => onRemovePoint(point.originalIndex)}
                        disabled={curvePoints.length <= 2}
                        className="text-rose-400 hover:text-rose-300 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                      >
                        {t('system:fanControl.curve.remove')}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {canEdit && curvePoints.length < 10 && (
        <button
          onClick={onAddPoint}
          className="mt-3 px-4 py-2 bg-sky-500 text-white rounded-lg hover:bg-sky-600 shadow-lg shadow-sky-500/30 text-sm"
        >
          {t('system:fanControl.curve.addPoint')}
        </button>
      )}
    </>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanCurveTableEditor.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-details/FanCurveTableEditor.tsx client/src/__tests__/components/fan-control/fan-details/FanCurveTableEditor.test.tsx
git commit -m "feat(fan-control): extract FanCurveTableEditor component (#301)"
```

---

## Task 6: `FanStatsGrid.tsx`

**Files:**
- Create: `client/src/components/fan-control/fan-details/FanStatsGrid.tsx`
- Test: `client/src/__tests__/components/fan-control/fan-details/FanStatsGrid.test.tsx`

**Interfaces:**
- Consumes: `FanInfo` aus `../../../api/fan-control`.
- Produces: default export `FanStatsGrid` mit Props:

```ts
interface FanStatsGridProps {
  fan: FanInfo;
  canEdit: boolean;
  hysteresis: number;
  isUpdatingHysteresis: boolean;
  hysteresisChanged: boolean;
  onHysteresisChange: (value: number) => void;
  onHysteresisSave: () => void;
}
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fan-details/FanStatsGrid.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { FanInfo } from '../../../../api/fan-control';
import FanStatsGrid from '../../../../components/fan-control/fan-details/FanStatsGrid';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const fan = (over: Partial<FanInfo> = {}): FanInfo => ({
  fan_id: 'fan1', name: 'CPU Fan', rpm: 1200, pwm_percent: 50, temperature_celsius: 45,
  mode: 'auto', is_active: true, min_pwm_percent: 30, max_pwm_percent: 100,
  emergency_temp_celsius: 90, temp_sensor_id: 'hwmon0_temp1', hysteresis_celsius: 3,
  curve_points: [], ...over,
} as FanInfo);

const base = {
  fan: fan(), canEdit: true, hysteresis: 3, isUpdatingHysteresis: false,
  hysteresisChanged: false, onHysteresisChange: vi.fn(), onHysteresisSave: vi.fn(),
};

describe('FanStatsGrid', () => {
  it('renders min/max pwm and emergency temp', () => {
    render(<FanStatsGrid {...base} />);
    expect(screen.getByText('30%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('90°C')).toBeInTheDocument();
  });

  it('saves hysteresis on blur when editable', () => {
    const onHysteresisSave = vi.fn();
    render(<FanStatsGrid {...base} onHysteresisSave={onHysteresisSave} />);
    fireEvent.blur(screen.getByRole('spinbutton'));
    expect(onHysteresisSave).toHaveBeenCalled();
  });

  it('renders read-only hysteresis when not editable', () => {
    render(<FanStatsGrid {...base} canEdit={false} />);
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByText('3°C')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanStatsGrid.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fan-details/FanStatsGrid.tsx` (JSX aus `FanDetails.tsx:562-615` verbatim):

```tsx
import { Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FanInfo } from '../../../api/fan-control';

interface FanStatsGridProps {
  fan: FanInfo;
  canEdit: boolean;
  hysteresis: number;
  isUpdatingHysteresis: boolean;
  hysteresisChanged: boolean;
  onHysteresisChange: (value: number) => void;
  onHysteresisSave: () => void;
}

export default function FanStatsGrid({
  fan, canEdit, hysteresis, isUpdatingHysteresis, hysteresisChanged,
  onHysteresisChange, onHysteresisSave,
}: FanStatsGridProps) {
  const { t } = useTranslation(['system', 'common']);

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 pt-4 border-t border-slate-700">
      <div>
        <p className="text-xs text-slate-400">{t('system:fanControl.details.minPwm')}</p>
        <p className="text-lg font-bold text-white">{fan.min_pwm_percent}%</p>
      </div>
      <div>
        <p className="text-xs text-slate-400">{t('system:fanControl.details.maxPwm')}</p>
        <p className="text-lg font-bold text-white">{fan.max_pwm_percent}%</p>
      </div>
      <div>
        <p className="text-xs text-slate-400">{t('system:fanControl.details.emergencyTemp')}</p>
        <p className="text-lg font-bold text-white">{fan.emergency_temp_celsius}°C</p>
      </div>
      <div>
        <p className="text-xs text-slate-400">{t('system:fanControl.details.sensorId')}</p>
        <p className="text-sm font-mono text-slate-300">{fan.temp_sensor_id || '—'}</p>
      </div>
      <div>
        <p className="text-xs text-slate-400 flex items-center gap-1">
          {t('system:fanControl.details.hysteresis')}
          <span
            className="cursor-help"
            title={t('system:fanControl.details.hysteresisTooltip')}
          >
            <Info className="w-3 h-3 text-slate-500" />
          </span>
        </p>
        {canEdit ? (
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={hysteresis}
              onChange={(e) => onHysteresisChange(parseFloat(e.target.value) || 0)}
              onBlur={onHysteresisSave}
              onKeyDown={(e) => e.key === 'Enter' && onHysteresisSave()}
              className="w-16 px-2 py-1 text-sm border border-slate-600 rounded bg-slate-800 text-white"
              min={0}
              max={15}
              step={0.5}
              disabled={isUpdatingHysteresis}
            />
            <span className="text-sm text-slate-400">°C</span>
            {hysteresisChanged && !isUpdatingHysteresis && (
              <span className="text-xs text-amber-400">{t('system:fanControl.details.unsaved')}</span>
            )}
            {isUpdatingHysteresis && (
              <span className="text-xs text-sky-400">{t('system:fanControl.details.saving')}</span>
            )}
          </div>
        ) : (
          <p className="text-lg font-bold text-white">{fan.hysteresis_celsius ?? 3.0}°C</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-details/FanStatsGrid.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-details/FanStatsGrid.tsx client/src/__tests__/components/fan-control/fan-details/FanStatsGrid.test.tsx
git commit -m "feat(fan-control): extract FanStatsGrid component (#301)"
```

---

## Task 7: Barrel + Orchestrator rewire + Docs

**Files:**
- Create: `client/src/components/fan-control/fan-details/index.ts`
- Modify: `client/src/components/fan-control/FanDetails.tsx` (auf Orchestrator reduzieren)
- Modify: `client/src/components/CLAUDE.md` (`fan-control/`-Zeile ergänzen)

**Interfaces:**
- Consumes: `useFanCurveEditor` (Task 2), `FanPresetProfileButtons` (Task 3), `FanCurveGraphControls` (Task 4), `FanCurveTableEditor` (Task 5), `FanStatsGrid` (Task 6), unveränderte `CurveTypeSelector`/`CurveEditorFlat`/`CurveEditorTarget`/`CurveEditorMix`/`CurveEditorSync`/`AdvancedFanSettings`/`GpuManualModeToggle`/`FanCurveChart`.
- Produces: `FanDetails` (Default-Export, **unveränderte** `FanDetailsProps`).

- [ ] **Step 1: Create the internal barrel**

`client/src/components/fan-control/fan-details/index.ts`:

```ts
export { default as FanPresetProfileButtons } from './FanPresetProfileButtons';
export { default as FanCurveGraphControls } from './FanCurveGraphControls';
export { default as FanCurveTableEditor } from './FanCurveTableEditor';
export { default as FanStatsGrid } from './FanStatsGrid';
```

- [ ] **Step 2: Rewrite `FanDetails.tsx` as the orchestrator**

Ersetze den **gesamten** Inhalt von `client/src/components/fan-control/FanDetails.tsx` durch:

```tsx
import { TrendingUp } from 'lucide-react';
import type { FanInfo, FanCurvePoint, FanCurveProfile } from '../../api/fan-control';
import CurveTypeSelector from './CurveTypeSelector';
import CurveEditorFlat from './CurveEditorFlat';
import CurveEditorTarget from './CurveEditorTarget';
import CurveEditorMix from './CurveEditorMix';
import CurveEditorSync from './CurveEditorSync';
import AdvancedFanSettings from './AdvancedFanSettings';
import GpuManualModeToggle from './GpuManualModeToggle';
import FanCurveChart from './FanCurveChart';
import { useTranslation } from 'react-i18next';
import { useFanCurveEditor } from '../../hooks/useFanCurveEditor';
import {
  FanPresetProfileButtons,
  FanCurveGraphControls,
  FanCurveTableEditor,
  FanStatsGrid,
} from './fan-details';

interface FanDetailsProps {
  fan: FanInfo;
  onCurveUpdate: (fanId: string, points: FanCurvePoint[]) => void;
  isReadOnly: boolean;
  onEditingChange?: (isEditing: boolean) => void;
  onConfigUpdate?: () => void;
  profiles?: FanCurveProfile[];
  onApplyProfile?: (profile: FanCurveProfile) => void;
  allFans?: FanInfo[];
}

export default function FanDetails({ fan, onCurveUpdate, isReadOnly, onEditingChange, onConfigUpdate, profiles, onApplyProfile, allFans }: FanDetailsProps) {
  const { t } = useTranslation(['system', 'common']);
  const editor = useFanCurveEditor(fan, {
    isReadOnly, onCurveUpdate, onConfigUpdate, onEditingChange, onApplyProfile, profiles,
  });

  return (
    <div className="card">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-sky-400" />
          {fan.name} - {t('system:fanControl.curve.title')}
        </h2>

        <FanPresetProfileButtons
          isReadOnly={isReadOnly}
          systemProfiles={editor.systemProfiles}
          userProfiles={editor.userProfiles}
          showMoreProfiles={editor.showMoreProfiles}
          onToggleMore={() => editor.setShowMoreProfiles(!editor.showMoreProfiles)}
          onApplyPreset={editor.handleApplyPreset}
          onApplyProfile={editor.handleApplyProfileCurve}
        />
      </div>

      {/* Curve Editor */}
      <div className="mb-4">
        <div className="mb-4">
          <CurveTypeSelector value={editor.curveType} onChange={editor.handleCurveTypeChange} disabled={isReadOnly} />
        </div>

        {/* Graph curve: original chart + table editor */}
        {editor.curveType === 'graph' && (
          <>
            <FanCurveGraphControls
              viewMode={editor.viewMode}
              onViewModeChange={editor.setViewMode}
              hasUnsavedChanges={editor.hasUnsavedChanges}
              isReadOnly={isReadOnly}
              onSave={editor.handleSaveCurve}
              onDiscard={editor.handleDiscardChanges}
            />

            {editor.viewMode === 'chart' && (
              <div className="mt-4">
                <FanCurveChart
                  points={editor.curvePoints}
                  onPointsChange={editor.handleChartPointsChange}
                  currentTemp={fan.temperature_celsius}
                  currentPWM={fan.pwm_percent}
                  minPWM={fan.min_pwm_percent}
                  maxPWM={fan.max_pwm_percent}
                  emergencyTemp={fan.emergency_temp_celsius}
                  isEditing={editor.canEdit}
                  isReadOnly={isReadOnly}
                />
              </div>
            )}

            {editor.viewMode === 'table' && (
              <FanCurveTableEditor
                curvePoints={editor.curvePoints}
                canEdit={editor.canEdit}
                minPwm={fan.min_pwm_percent}
                maxPwm={fan.max_pwm_percent}
                onUpdatePoint={editor.handleUpdatePoint}
                onRemovePoint={editor.handleRemovePoint}
                onAddPoint={editor.handleAddPoint}
              />
            )}
          </>
        )}

        {editor.curveType === 'flat' && (
          <CurveEditorFlat
            value={fan.flat_pwm_percent ?? 50}
            onChange={editor.handleFlatChange}
            disabled={isReadOnly}
          />
        )}

        {editor.curveType === 'target' && (
          <CurveEditorTarget
            targetTemp={fan.target_temp_celsius ?? 65}
            targetPwm={fan.target_pwm_percent ?? 80}
            onChange={editor.handleTargetChange}
            disabled={isReadOnly}
          />
        )}

        {editor.curveType === 'mix' && (
          <CurveEditorMix
            profiles={profiles ?? []}
            curveAId={fan.mix_curve_a_id ?? null}
            curveBId={fan.mix_curve_b_id ?? null}
            fn={(fan.mix_function as 'max' | 'sum') ?? 'max'}
            onChange={editor.handleMixChange}
            disabled={isReadOnly}
          />
        )}

        {editor.curveType === 'sync' && (
          <CurveEditorSync
            allFans={allFans ?? []}
            currentFanId={fan.fan_id}
            syncFanId={fan.sync_fan_id ?? null}
            onChange={editor.handleSyncChange}
            disabled={isReadOnly}
          />
        )}
      </div>

      {/* Advanced Settings */}
      <div className="mt-4">
        <AdvancedFanSettings fan={fan} onChange={editor.handleAdvancedChange} disabled={isReadOnly} />
      </div>

      {/* GPU Manual Mode Toggle (AMD GPU fans only) */}
      {fan.is_gpu_fan && fan.gpu_vendor === 'amd' && (
        <div className="mt-4">
          <GpuManualModeToggle
            fanId={fan.fan_id}
            enabled={editor.localGpuManualEnabled}
            onChange={editor.setLocalGpuManualEnabled}
          />
        </div>
      )}

      {/* Fan Stats */}
      <FanStatsGrid
        fan={fan}
        canEdit={editor.canEdit}
        hysteresis={editor.hysteresis}
        isUpdatingHysteresis={editor.isUpdatingHysteresis}
        hysteresisChanged={editor.hysteresisChanged}
        onHysteresisChange={editor.handleHysteresisChange}
        onHysteresisSave={editor.handleHysteresisSave}
      />
    </div>
  );
}
```

- [ ] **Step 3: Update `components/CLAUDE.md`**

Ersetze in `client/src/components/CLAUDE.md` die `fan-control/`-Tabellenzeile:

```
| `fan-control/` | Fan curves, schedules, profiles |
```

durch:

```
| `fan-control/` | Fan curves, schedules, profiles — `FanDetails` composes `fan-details/*` (`FanPresetProfileButtons`, `FanCurveGraphControls`, `FanCurveTableEditor`, `FanStatsGrid`) + pure `fanCurveValidation` helper; state/handlers in `hooks/useFanCurveEditor` (extracted F2/#301) |
```

- [ ] **Step 4: Run the full fan-control + hook test suite**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control src/__tests__/hooks/useFanCurveEditor.test.tsx`
Expected: PASS (alle Tasks-1–6-Tests grün).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-details/index.ts client/src/components/fan-control/FanDetails.tsx client/src/components/CLAUDE.md
git commit -m "refactor(fan-control): FanDetails thin orchestrator over fan-details/* + useFanCurveEditor (#301)"
```

---

## Task 8: Full verification gate

**Files:** none (verification only).

- [ ] **Step 1: Full frontend test suite**

Run (in `client/`): `npx vitest run`
Expected: PASS, keine Regressionen. Falls rot: fixen, bis grün.

- [ ] **Step 2: ESLint 0-error gate**

Run (in `client/`): `npx eslint .`
Expected: 0 Fehler. Achte auf ungenutzte Imports in `FanDetails.tsx` (z.B. `useState`, `useEffect`, `useMemo`, `useRef`, `useCallback`, `Table`, `LineChartIcon`, `Zap`, `Volume2`, `Gauge`, `Info`, `ChevronDown`, `toast`, `handleApiError`, `CURVE_PRESETS`, `updateFanConfig`, `CurveType` — alle müssen entfernt sein). Falls Fehler: entfernen, bis grün.

- [ ] **Step 3: Production build (tsc -b + vite)**

Run (in `client/`): `npm run build`
Expected: erfolgreicher Build, keine Typfehler.

- [ ] **Step 4: Confirm line count target**

`FanDetails.tsx` sollte deutlich unter 500 Zeilen liegen (~200). Bestätigen.

- [ ] **Step 5: Final commit (falls Verifikation Fixes brachte)**

```bash
git add -A
git commit -m "chore(fan-control): verification fixes for FanDetails decomposition (#301)"
```

(Nur committen, wenn Schritte 1–3 tatsächlich Änderungen erforderten.)

---

## Self-Review (durchgeführt beim Schreiben)

**1. Spec coverage:** ✅ Alle Spec-Einheiten haben Tasks — `fanCurveValidation` (T1), `useFanCurveEditor` inkl. aller 16 Handler + `localGpuManualEnabled`-Portierung (T2), 4 Subkomponenten (T3–T6), Orchestrator + Barrel + Docs (T7), Verify-Gate (T8). Der Nebenbefund `localGpuManualEnabled` ist in T2 verhaltensgleich portiert (kein Fix) — spec-konform.

**2. Placeholder scan:** ✅ Keine TBD/TODO/„handle edge cases". Jeder Code-Schritt zeigt vollständigen Code, jeder Test konkrete Assertions, jedes Kommando erwartete Ausgabe.

**3. Type consistency:** ✅ Hook-Return-Namen (`setViewMode`, `handleUpdatePoint`, `handleApplyProfileCurve`, `setShowMoreProfiles`, `setLocalGpuManualEnabled` …) stimmen mit den Verdrahtungen in T7 überein. Prop-Namen der Subkomponenten (`onViewModeChange`, `onUpdatePoint`, `onApplyPreset`, `onApplyProfile`, `minPwm`/`maxPwm`) sind über Interfaces-Blöcke und Orchestrator konsistent. `onApplyPreset: (preset: string)` matcht `handleApplyPreset: (preset: string)`. `CurveType` bleibt aus `CurveTypeSelector` importiert.

**Bekanntes Detail:** `FanCurveChart`-Props (`points`, `onPointsChange`, `currentTemp`, `currentPWM`, `minPWM`, `maxPWM`, `emergencyTemp`, `isEditing`, `isReadOnly`) 1:1 aus dem Original übernommen — unverändert.
