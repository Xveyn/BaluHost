# FanCurveChart.tsx Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zerlege `client/src/components/fan-control/FanCurveChart.tsx` (577 Zeilen) verhaltenserhaltend in Orchestrator + Interaktions-Hook + pure Geometrie + 3 Präsentations-Subkomponenten.

**Architecture:** Die reine Koordinaten-Arithmetik wandert in `fanCurveGeometry.ts` (DOM-frei, testbar). Die gesamte Interaktions-/State-Logik (Drag/Click/Touch, Document-Listener, Refs, Effekte, DOM-Bounds) wandert verbatim in `hooks/useFanCurveInteraction.ts`. Tooltip/Legende/Hint werden reine Komponenten. `FanCurveChart.tsx` bleibt Recharts-Rendering + Overlay-Verdrahtung.

**Tech Stack:** React 18 + TypeScript, Recharts, Vitest + @testing-library/react, react-i18next.

## Global Constraints

- **Verhaltenserhaltend:** Keine Änderung an sichtbarem Verhalten, Rendering, Interaktion, oder der öffentlichen `FanCurveChartProps`. Konsument `FanDetails.tsx` und der äußere Barrel `fan-control/index.ts` bleiben unverändert (`FanCurveChart` behält Default-Export + identische Props inkl. des ungenutzten `isEditing?`).
- **ZWEI GETRENNTE RECHENPFADE — nicht vereinheitlichen:** `computeChartValue` (Click/Tap) rundet auf **Integer** + liefert `inBounds`; `computeDraggedPoint` (Drag) rundet auf **0.1**. Beide bleiben getrennt und exakt wie im Original.
- **DOM-Reads bleiben im Hook:** `getBoundingClientRect`, `querySelector`, die `getChartBounds`-Fallback-Kette. Nur die Arithmetik ist pure.
- **Hardcodierte englische Strings** in Legende und Hint-Text bleiben VERBATIM (kein i18n hinzufügen — das ist #406, separat).
- i18n-Keys, Tailwind-Klassen, Recharts-Props und DOM-Struktur exakt wie im Original.
- **Kein neuer öffentlicher Re-Export** in `fan-control/index.ts`.
- **Verify-Gate vor PR:** `npx vitest run`, `npx eslint .` (0 Fehler), `npm run build` — plus **manuelles Durchspielen der Drag/Touch-Interaktion** im laufenden Frontend. Arbeitsverzeichnis für Kommandos: `client/`.
- **Tests-Layout:** Geometrie-/Komponententests unter `client/src/__tests__/components/fan-control/…`, Hook-Test unter `client/src/__tests__/hooks/…`.
- **CRLF:** `core.autocrlf=true` — LF→CRLF-Warnungen bei `git add` erwartbar.

**Referenz-Typen (aus `client/src/api/fan-control.ts`):**

```ts
export interface FanCurvePoint { temp: number; pwm: number; }
```

---

## File Structure

**Create:**
- `client/src/components/fan-control/fanCurveGeometry.ts`
- `client/src/hooks/useFanCurveInteraction.ts`
- `client/src/components/fan-control/fan-curve-chart/FanCurveTooltip.tsx`
- `client/src/components/fan-control/fan-curve-chart/FanChartLegend.tsx`
- `client/src/components/fan-control/fan-curve-chart/FanChartHint.tsx`
- `client/src/components/fan-control/fan-curve-chart/index.ts`
- Tests:
  - `client/src/__tests__/components/fan-control/fanCurveGeometry.test.ts`
  - `client/src/__tests__/hooks/useFanCurveInteraction.test.tsx`
  - `client/src/__tests__/components/fan-control/fan-curve-chart/FanCurveTooltip.test.tsx`
  - `client/src/__tests__/components/fan-control/fan-curve-chart/FanChartLegend.test.tsx`
  - `client/src/__tests__/components/fan-control/fan-curve-chart/FanChartHint.test.tsx`

**Modify:**
- `client/src/components/fan-control/FanCurveChart.tsx` — auf Orchestrator reduzieren (Task 6)
- `client/src/components/CLAUDE.md` — `fan-control/`-Zeile ergänzen (Task 6)

---

## Task 1: `fanCurveGeometry.ts` (pure Geometrie)

**Files:**
- Create: `client/src/components/fan-control/fanCurveGeometry.ts`
- Test: `client/src/__tests__/components/fan-control/fanCurveGeometry.test.ts`

**Interfaces:**
- Consumes: nichts (pure).
- Produces:

```ts
export interface ChartValueConfig { emergencyTemp: number; minPWM: number; maxPWM: number; }
export interface RectLike { left: number; top: number; width: number; height: number; }
export function computeChartValue(clientX: number, clientY: number, bounds: RectLike, cfg: ChartValueConfig): { temp: number; pwm: number; inBounds: boolean };
export function computeDraggedPoint(clientX: number, clientY: number, plotRect: RectLike, cfg: ChartValueConfig): { temp: number; pwm: number };
export function findNearestPointIndex(clientX: number, clientY: number, bounds: RectLike, sortedPoints: { temp: number; pwm: number }[], emergencyTemp: number, hitRadius?: number): number | null;
```

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fanCurveGeometry.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { computeChartValue, computeDraggedPoint, findNearestPointIndex } from '../../../components/fan-control/fanCurveGeometry';

const cfg = { emergencyTemp: 90, minPWM: 0, maxPWM: 100 }; // tempRange = 100
const unit = { left: 0, top: 0, width: 100, height: 100 };

describe('computeChartValue (click/tap — integer rounding)', () => {
  it('maps center pixel to integer temp/pwm and inBounds', () => {
    const r = computeChartValue(50, 20, unit, cfg);
    expect(r).toEqual({ temp: 50, pwm: 80, inBounds: true });
  });

  it('clamps out-of-range values and reports inBounds false when far outside', () => {
    const r = computeChartValue(200, 200, unit, cfg);
    expect(r.temp).toBe(100); // clamp to emergencyTemp + 10
    expect(r.pwm).toBe(0);    // clamp to minPWM
    expect(r.inBounds).toBe(false);
  });

  it('respects minPWM/maxPWM clamps from config', () => {
    const r = computeChartValue(10, 5, { left: 0, top: 0, width: 100, height: 100 }, { emergencyTemp: 90, minPWM: 30, maxPWM: 90 });
    expect(r.pwm).toBe(90); // raw 95 -> clamp to maxPWM 90
  });
});

describe('computeDraggedPoint (drag — 0.1 rounding)', () => {
  it('rounds to one decimal — distinct from the integer path for the same input', () => {
    const wide = { left: 0, top: 0, width: 150, height: 100 };
    const dragged = computeDraggedPoint(50, 20, wide, cfg);
    const clicked = computeChartValue(50, 20, wide, cfg);
    expect(dragged.temp).toBe(33.3); // round((50/150)*100 * 10)/10
    expect(clicked.temp).toBe(33);   // round((50/150)*100)
  });

  it('clamps temp and pwm', () => {
    const r = computeDraggedPoint(-100, 500, unit, { emergencyTemp: 90, minPWM: 20, maxPWM: 80 });
    expect(r.temp).toBe(0);   // clamp to 0
    expect(r.pwm).toBe(20);   // clamp to minPWM
  });
});

describe('findNearestPointIndex', () => {
  const sorted = [{ temp: 20, pwm: 30 }, { temp: 60, pwm: 80 }]; // p0 @(20,70), p1 @(60,20)
  it('returns the index of a point within the hit radius', () => {
    expect(findNearestPointIndex(22, 71, unit, sorted, 90)).toBe(0);
    expect(findNearestPointIndex(61, 21, unit, sorted, 90)).toBe(1);
  });
  it('returns null when no point is within the hit radius', () => {
    expect(findNearestPointIndex(0, 0, unit, sorted, 90)).toBeNull();
  });
  it('returns null for an empty point list', () => {
    expect(findNearestPointIndex(50, 50, unit, [], 90)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fanCurveGeometry.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fanCurveGeometry.ts` (Arithmetik 1:1 aus `FanCurveChart.tsx` `pixelToValue`/`updatePointPosition`/`findPointNear`):

```ts
export interface ChartValueConfig {
  emergencyTemp: number;
  minPWM: number;
  maxPWM: number;
}

export interface RectLike {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Click / tap-to-add path (from pixelToValue): INTEGER rounding + inBounds flag.
 */
export function computeChartValue(
  clientX: number,
  clientY: number,
  bounds: RectLike,
  cfg: ChartValueConfig,
): { temp: number; pwm: number; inBounds: boolean } {
  const x = clientX - bounds.left;
  const y = clientY - bounds.top;
  const tempRange = cfg.emergencyTemp + 10;

  const temp = Math.round((x / bounds.width) * tempRange);
  const pwm = Math.round(100 - (y / bounds.height) * 100);

  return {
    temp: Math.max(0, Math.min(cfg.emergencyTemp + 10, temp)),
    pwm: Math.max(cfg.minPWM, Math.min(cfg.maxPWM, pwm)),
    inBounds: x >= -5 && x <= bounds.width + 5 && y >= -5 && y <= bounds.height + 5,
  };
}

/**
 * Drag path (from updatePointPosition): 0.1 rounding, clamped.
 */
export function computeDraggedPoint(
  clientX: number,
  clientY: number,
  plotRect: RectLike,
  cfg: ChartValueConfig,
): { temp: number; pwm: number } {
  const x = clientX - plotRect.left;
  const y = clientY - plotRect.top;
  const chartWidth = plotRect.width;
  const chartHeight = plotRect.height;

  const tempRange = cfg.emergencyTemp + 10;
  const pwmRange = 100;

  const newTemp = Math.round(((x / chartWidth) * tempRange) * 10) / 10;
  const newPWM = Math.round((100 - (y / chartHeight) * pwmRange) * 10) / 10;

  return {
    temp: Math.max(0, Math.min(cfg.emergencyTemp + 10, newTemp)),
    pwm: Math.max(cfg.minPWM, Math.min(cfg.maxPWM, newPWM)),
  };
}

/**
 * Nearest curve point (in sorted order) within hitRadius, or null (from findPointNear).
 */
export function findNearestPointIndex(
  clientX: number,
  clientY: number,
  bounds: RectLike,
  sortedPoints: { temp: number; pwm: number }[],
  emergencyTemp: number,
  hitRadius = 10,
): number | null {
  const x = clientX - bounds.left;
  const y = clientY - bounds.top;
  const tempRange = emergencyTemp + 10;

  let nearestIndex: number | null = null;
  let nearestDist = Infinity;

  sortedPoints.forEach((point, index) => {
    const pointX = (point.temp / tempRange) * bounds.width;
    const pointY = ((100 - point.pwm) / 100) * bounds.height;
    const dist = Math.sqrt(Math.pow(x - pointX, 2) + Math.pow(y - pointY, 2));

    if (dist < hitRadius && dist < nearestDist) {
      nearestDist = dist;
      nearestIndex = index;
    }
  });

  return nearestIndex;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fanCurveGeometry.test.ts`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fanCurveGeometry.ts client/src/__tests__/components/fan-control/fanCurveGeometry.test.ts
git commit -m "feat(fan-control): extract pure fanCurveGeometry helpers (#301)"
```

---

## Task 2: `useFanCurveInteraction.ts` (Interaktions-Hook)

**Files:**
- Create: `client/src/hooks/useFanCurveInteraction.ts`
- Test: `client/src/__tests__/hooks/useFanCurveInteraction.test.tsx`

**Interfaces:**
- Consumes: `computeChartValue`/`computeDraggedPoint`/`findNearestPointIndex` (Task 1), `FanCurvePoint` aus `../api/fan-control`.
- Produces:

```ts
export interface ChartDataPoint extends FanCurvePoint { isCurrentPoint?: boolean; originalIndex?: number; }
export interface FanCurveInteractionConfig { minPWM: number; maxPWM: number; emergencyTemp: number; isReadOnly: boolean; minPoints: number; maxPoints: number; }
export function useFanCurveInteraction(points: FanCurvePoint[], onPointsChange: (points: FanCurvePoint[]) => void, cfg: FanCurveInteractionConfig): {
  chartRef: RefObject<HTMLDivElement>;
  overlayRef: RefObject<HTMLDivElement>;
  draggingIndex: number | null;
  canEdit: boolean;
  localPoints: FanCurvePoint[];
  sortedPoints: Array<FanCurvePoint & { originalIndex: number }>;
  chartData: ChartDataPoint[];
  handleRemovePoint: (index: number) => void;
  handleOverlayMouseDown: (e: ReactMouseEvent) => void;
  handleOverlayClick: (e: ReactMouseEvent) => void;
  handleOverlayContextMenu: (e: ReactMouseEvent) => void;
  handleOverlayTouchStart: (e: ReactTouchEvent) => void;
};
```

> Note: `handleRemovePoint` wird zusätzlich zurückgegeben (im Original war es intern, nur von `handleOverlayContextMenu` aufgerufen) — als Testbarkeits-Affordanz. Der Orchestrator nutzt es nicht; das ändert kein Verhalten.

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/hooks/useFanCurveInteraction.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFanCurveInteraction } from '../../hooks/useFanCurveInteraction';

const cfg = (over: Partial<Parameters<typeof useFanCurveInteraction>[2]> = {}) => ({
  minPWM: 30, maxPWM: 100, emergencyTemp: 90, isReadOnly: false, minPoints: 2, maxPoints: 10, ...over,
});

describe('useFanCurveInteraction', () => {
  it('handleRemovePoint removes the correct original-index point (sorted->original remap)', () => {
    const onPointsChange = vi.fn();
    const pts = [{ temp: 60, pwm: 80 }, { temp: 20, pwm: 30 }, { temp: 40, pwm: 50 }];
    const { result } = renderHook(() => useFanCurveInteraction(pts, onPointsChange, cfg()));
    // sorted display order: [20(orig1), 40(orig2), 60(orig0)]; removing sorted idx 0 drops original idx 1 (temp 20)
    act(() => result.current.handleRemovePoint(0));
    expect(onPointsChange).toHaveBeenCalledWith([{ temp: 60, pwm: 80 }, { temp: 40, pwm: 50 }]);
    expect(result.current.localPoints).toEqual([{ temp: 60, pwm: 80 }, { temp: 40, pwm: 50 }]);
  });

  it('handleRemovePoint is blocked at minPoints', () => {
    const onPointsChange = vi.fn();
    const pts = [{ temp: 20, pwm: 30 }, { temp: 60, pwm: 80 }];
    const { result } = renderHook(() => useFanCurveInteraction(pts, onPointsChange, cfg()));
    act(() => result.current.handleRemovePoint(0));
    expect(onPointsChange).not.toHaveBeenCalled();
    expect(result.current.localPoints).toHaveLength(2);
  });

  it('syncs external points into localPoints/sortedPoints when not dragging', () => {
    const onPointsChange = vi.fn();
    const { result, rerender } = renderHook(
      ({ p }) => useFanCurveInteraction(p, onPointsChange, cfg()),
      { initialProps: { p: [{ temp: 20, pwm: 30 }, { temp: 60, pwm: 80 }] } },
    );
    rerender({ p: [{ temp: 25, pwm: 35 }, { temp: 65, pwm: 85 }, { temp: 80, pwm: 95 }] });
    expect(result.current.localPoints).toHaveLength(3);
    expect(result.current.sortedPoints.map((sp) => sp.temp)).toEqual([25, 65, 80]);
  });

  it('exposes chartData derived from sorted points with isCurrentPoint false', () => {
    const onPointsChange = vi.fn();
    const pts = [{ temp: 60, pwm: 80 }, { temp: 20, pwm: 30 }];
    const { result } = renderHook(() => useFanCurveInteraction(pts, onPointsChange, cfg()));
    expect(result.current.chartData.map((d) => d.temp)).toEqual([20, 60]);
    expect(result.current.chartData.every((d) => d.isCurrentPoint === false)).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/hooks/useFanCurveInteraction.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/hooks/useFanCurveInteraction.ts` (verbatim-Port; einzige inhaltliche Änderung: `pixelToValue`/`findPointNear`/`updatePointPosition`-Arithmetik ruft die pure Geometrie):

```ts
import { useState, useRef, useCallback, useEffect } from 'react';
import type { MouseEvent as ReactMouseEvent, TouchEvent as ReactTouchEvent, RefObject } from 'react';
import type { FanCurvePoint } from '../api/fan-control';
import { computeChartValue, computeDraggedPoint, findNearestPointIndex } from '../components/fan-control/fanCurveGeometry';

export interface ChartDataPoint extends FanCurvePoint {
  isCurrentPoint?: boolean;
  originalIndex?: number;
}

export interface FanCurveInteractionConfig {
  minPWM: number;
  maxPWM: number;
  emergencyTemp: number;
  isReadOnly: boolean;
  minPoints: number;
  maxPoints: number;
}

export function useFanCurveInteraction(
  points: FanCurvePoint[],
  onPointsChange: (points: FanCurvePoint[]) => void,
  cfg: FanCurveInteractionConfig,
) {
  const { minPWM, maxPWM, emergencyTemp, isReadOnly, minPoints, maxPoints } = cfg;

  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [localPoints, setLocalPoints] = useState<FanCurvePoint[]>(points);
  const chartRef = useRef<HTMLDivElement>(null);
  const localPointsRef = useRef<FanCurvePoint[]>(localPoints);
  const wasDraggingRef = useRef(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  // Editing is always enabled when not read-only (FanControl-style behavior)
  const canEdit = !isReadOnly;

  // Refs for stable access in document-level handlers (survive React re-renders)
  const canEditRef = useRef(canEdit);
  const maxPointsRef = useRef(maxPoints);
  const onPointsChangeRef = useRef(onPointsChange);

  useEffect(() => { canEditRef.current = canEdit; }, [canEdit]);
  useEffect(() => { maxPointsRef.current = maxPoints; }, [maxPoints]);
  useEffect(() => { onPointsChangeRef.current = onPointsChange; }, [onPointsChange]);

  // Update local points when external points change (but not while dragging)
  useEffect(() => {
    if (draggingIndex === null) {
      setLocalPoints(points);
    }
  }, [points, draggingIndex]);

  // Keep ref in sync with state
  useEffect(() => {
    localPointsRef.current = localPoints;
  }, [localPoints]);

  const pointsWithIndices = localPoints.map((point, index) => ({
    ...point,
    originalIndex: index,
  }));

  const sortedPoints = [...pointsWithIndices].sort((a, b) => a.temp - b.temp);

  const chartData: ChartDataPoint[] = sortedPoints.map((point) => ({
    ...point,
    isCurrentPoint: false,
  }));

  const handleRemovePoint = useCallback((index: number) => {
    if (!canEdit || localPoints.length <= minPoints) return;

    const originalIndex = sortedPoints[index]?.originalIndex;
    if (originalIndex === undefined) return;

    const updatedPoints = localPoints.filter((_, i) => i !== originalIndex);
    setLocalPoints(updatedPoints);
    onPointsChange(updatedPoints);
  }, [canEdit, localPoints, minPoints, onPointsChange, sortedPoints]);

  const updatePointPosition = useCallback((clientX: number, clientY: number, index: number) => {
    if (!chartRef.current) return;

    const cartesianGrid = chartRef.current.querySelector('.recharts-cartesian-grid');
    if (!cartesianGrid) return;

    const rect = cartesianGrid.getBoundingClientRect();

    const originalIndex = sortedPoints[index].originalIndex;
    if (originalIndex === undefined) return;

    const { temp, pwm } = computeDraggedPoint(clientX, clientY, rect, { emergencyTemp, minPWM, maxPWM });

    const updatedPoints = [...localPoints];
    updatedPoints[originalIndex] = { temp, pwm };

    setLocalPoints(updatedPoints);
  }, [sortedPoints, localPoints, minPWM, maxPWM, emergencyTemp]);

  const getChartBounds = useCallback((): DOMRect | null => {
    if (!chartRef.current) return null;

    const cartesianGrid = chartRef.current.querySelector('.recharts-cartesian-grid');
    if (cartesianGrid) {
      const rect = cartesianGrid.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return rect;
    }

    const horizontalLines = chartRef.current.querySelector('.recharts-cartesian-grid-horizontal');
    if (horizontalLines) {
      const rect = horizontalLines.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return rect;
    }

    const surface = chartRef.current.querySelector('.recharts-surface');
    if (surface) {
      const svgRect = surface.getBoundingClientRect();
      const margin = { top: 5, right: 20, left: 0, bottom: 55 };
      const yAxis = chartRef.current.querySelector('.recharts-yAxis');
      const yAxisWidth = yAxis ? yAxis.getBoundingClientRect().width : 60;
      return new DOMRect(
        svgRect.left + margin.left + yAxisWidth,
        svgRect.top + margin.top,
        svgRect.width - margin.left - margin.right - yAxisWidth,
        svgRect.height - margin.top - margin.bottom,
      );
    }

    return null;
  }, []);

  const pixelToValue = useCallback((clientX: number, clientY: number) => {
    const bounds = getChartBounds();
    if (!bounds) return null;
    return computeChartValue(clientX, clientY, bounds, { emergencyTemp, minPWM, maxPWM });
  }, [emergencyTemp, minPWM, maxPWM, getChartBounds]);

  const findPointNear = useCallback((clientX: number, clientY: number): number | null => {
    const bounds = getChartBounds();
    if (!bounds) return null;
    return findNearestPointIndex(clientX, clientY, bounds, sortedPoints, emergencyTemp);
  }, [sortedPoints, emergencyTemp, getChartBounds]);

  const handleOverlayMouseDown = useCallback((e: ReactMouseEvent) => {
    if (!canEdit) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex === null) return; // Click-to-add handled by onClick

    e.preventDefault();
    setDraggingIndex(pointIndex);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      updatePointPosition(moveEvent.clientX, moveEvent.clientY, pointIndex);
    };

    const handleMouseUp = () => {
      wasDraggingRef.current = true; // Suppress the following onClick
      setDraggingIndex(null);
      onPointsChangeRef.current(localPointsRef.current);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      requestAnimationFrame(() => { wasDraggingRef.current = false; });
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [canEdit, findPointNear, updatePointPosition]);

  const handleOverlayClick = useCallback((e: ReactMouseEvent) => {
    if (wasDraggingRef.current) {
      wasDraggingRef.current = false;
      return;
    }
    if (!canEdit) return;
    if (localPoints.length >= maxPoints) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex !== null) return;

    const values = pixelToValue(e.clientX, e.clientY);
    if (!values || !values.inBounds) return;

    const newPoint: FanCurvePoint = { temp: values.temp, pwm: values.pwm };
    const updatedPoints = [...localPoints, newPoint];
    setLocalPoints(updatedPoints);
    onPointsChange(updatedPoints);
  }, [canEdit, localPoints, maxPoints, findPointNear, pixelToValue, onPointsChange]);

  const handleOverlayContextMenu = useCallback((e: ReactMouseEvent) => {
    e.preventDefault();
    if (!canEdit) return;

    const pointIndex = findPointNear(e.clientX, e.clientY);
    if (pointIndex !== null) {
      handleRemovePoint(pointIndex);
    }
  }, [canEdit, findPointNear, handleRemovePoint]);

  const handleOverlayTouchStart = useCallback((e: ReactTouchEvent) => {
    if (!canEdit) return;

    const touch = e.touches[0];
    const pointIndex = findPointNear(touch.clientX, touch.clientY);

    if (pointIndex !== null) {
      e.preventDefault();
      setDraggingIndex(pointIndex);

      const handleTouchMove = (moveEvent: TouchEvent) => {
        const moveTouch = moveEvent.touches[0];
        updatePointPosition(moveTouch.clientX, moveTouch.clientY, pointIndex);
      };

      const handleTouchEnd = () => {
        setDraggingIndex(null);
        onPointsChangeRef.current(localPointsRef.current);
        document.removeEventListener('touchmove', handleTouchMove);
        document.removeEventListener('touchend', handleTouchEnd);
      };

      document.addEventListener('touchmove', handleTouchMove);
      document.addEventListener('touchend', handleTouchEnd);
    } else {
      const startX = touch.clientX;
      const startY = touch.clientY;

      const handleTouchEnd = (endEvent: TouchEvent) => {
        const endTouch = endEvent.changedTouches[0];
        if (!endTouch) return;

        const dist = Math.sqrt(
          Math.pow(endTouch.clientX - startX, 2) + Math.pow(endTouch.clientY - startY, 2),
        );

        if (dist >= 10) return;
        if (!canEditRef.current) return;
        if (localPointsRef.current.length >= maxPointsRef.current) return;

        const values = pixelToValue(endTouch.clientX, endTouch.clientY);
        if (!values || !values.inBounds) return;

        const newPoint: FanCurvePoint = { temp: values.temp, pwm: values.pwm };
        const updatedPoints = [...localPointsRef.current, newPoint];
        setLocalPoints(updatedPoints);
        onPointsChangeRef.current(updatedPoints);
      };

      document.addEventListener('touchend', handleTouchEnd, { once: true });
    }
  }, [canEdit, findPointNear, updatePointPosition, pixelToValue]);

  return {
    chartRef: chartRef as RefObject<HTMLDivElement>,
    overlayRef: overlayRef as RefObject<HTMLDivElement>,
    draggingIndex,
    canEdit,
    localPoints,
    sortedPoints,
    chartData,
    handleRemovePoint,
    handleOverlayMouseDown,
    handleOverlayClick,
    handleOverlayContextMenu,
    handleOverlayTouchStart,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/hooks/useFanCurveInteraction.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useFanCurveInteraction.ts client/src/__tests__/hooks/useFanCurveInteraction.test.tsx
git commit -m "feat(fan-control): add useFanCurveInteraction hook (drag/click/touch) (#301)"
```

---

## Task 3: `FanCurveTooltip.tsx`

**Files:**
- Create: `client/src/components/fan-control/fan-curve-chart/FanCurveTooltip.tsx`
- Test: `client/src/__tests__/components/fan-control/fan-curve-chart/FanCurveTooltip.test.tsx`

**Interfaces:**
- Consumes: `ChartDataPoint` aus `../../../hooks/useFanCurveInteraction`, `formatNumber` aus `../../../lib/formatters`.
- Produces: default export `FanCurveTooltip` mit Props `{ active?: boolean; payload?: Array<{ payload: ChartDataPoint }> }`.

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fan-curve-chart/FanCurveTooltip.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanCurveTooltip from '../../../../components/fan-control/fan-curve-chart/FanCurveTooltip';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe('FanCurveTooltip', () => {
  it('returns null when inactive', () => {
    const { container } = render(<FanCurveTooltip active={false} payload={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the curve-point label and pwm for an active curve point', () => {
    render(<FanCurveTooltip active payload={[{ payload: { temp: 50, pwm: 70, isCurrentPoint: false } }]} />);
    expect(screen.getByText('system:fanControl.curve.curvePoint')).toBeInTheDocument();
    expect(screen.getByText(/→ 70%/)).toBeInTheDocument();
  });

  it('renders the current label when isCurrentPoint is set', () => {
    render(<FanCurveTooltip active payload={[{ payload: { temp: 50, pwm: 70, isCurrentPoint: true } }]} />);
    expect(screen.getByText('system:fanControl.curve.current')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-curve-chart/FanCurveTooltip.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fan-curve-chart/FanCurveTooltip.tsx` (aus `CustomTooltip`, `FanCurveChart.tsx:193-208`):

```tsx
import { useTranslation } from 'react-i18next';
import { formatNumber } from '../../../lib/formatters';
import type { ChartDataPoint } from '../../../hooks/useFanCurveInteraction';

interface FanCurveTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ChartDataPoint }>;
}

export default function FanCurveTooltip({ active, payload }: FanCurveTooltipProps) {
  const { t } = useTranslation(['system', 'common']);

  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0].payload as ChartDataPoint;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-slate-400">
        {data.isCurrentPoint ? t('system:fanControl.curve.current') : t('system:fanControl.curve.curvePoint')}
      </p>
      <p className="text-sm font-semibold text-white">
        {formatNumber(data.temp, 1)}°C → {data.pwm}%
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-curve-chart/FanCurveTooltip.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-curve-chart/FanCurveTooltip.tsx client/src/__tests__/components/fan-control/fan-curve-chart/FanCurveTooltip.test.tsx
git commit -m "feat(fan-control): extract FanCurveTooltip component (#301)"
```

---

## Task 4: `FanChartLegend.tsx`

**Files:**
- Create: `client/src/components/fan-control/fan-curve-chart/FanChartLegend.tsx`
- Test: `client/src/__tests__/components/fan-control/fan-curve-chart/FanChartLegend.test.tsx`

**Interfaces:**
- Produces: default export `FanChartLegend` mit Props `{ currentTemp: number | null; emergencyTemp: number }`.

Note: Die englischen Strings sind hartcodiert wie im Original — NICHT i18n-isieren.

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fan-curve-chart/FanChartLegend.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanChartLegend from '../../../../components/fan-control/fan-curve-chart/FanChartLegend';

describe('FanChartLegend', () => {
  it('shows the current operating point entry only when currentTemp is set', () => {
    const { rerender } = render(<FanChartLegend currentTemp={45} emergencyTemp={90} />);
    expect(screen.getByText('Current Operating Point')).toBeInTheDocument();
    expect(screen.getByText('Emergency Temp (90°C)')).toBeInTheDocument();

    rerender(<FanChartLegend currentTemp={null} emergencyTemp={90} />);
    expect(screen.queryByText('Current Operating Point')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-curve-chart/FanChartLegend.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fan-curve-chart/FanChartLegend.tsx` (aus `FanCurveChart.tsx:549-565`):

```tsx
interface FanChartLegendProps {
  currentTemp: number | null;
  emergencyTemp: number;
}

export default function FanChartLegend({ currentTemp, emergencyTemp }: FanChartLegendProps) {
  return (
    <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-400">
      <div className="flex items-center gap-2">
        <div className="w-3 h-3 rounded-full bg-sky-500 border-2 border-slate-900" />
        <span>Curve Points</span>
      </div>
      {currentTemp !== null && (
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-emerald-400 border-2 border-slate-900" />
          <span>Current Operating Point</span>
        </div>
      )}
      <div className="flex items-center gap-2">
        <div className="w-8 h-0.5 bg-rose-500" style={{ borderTop: '2px dashed' }} />
        <span>Emergency Temp ({emergencyTemp}°C)</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-curve-chart/FanChartLegend.test.tsx`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-curve-chart/FanChartLegend.tsx client/src/__tests__/components/fan-control/fan-curve-chart/FanChartLegend.test.tsx
git commit -m "feat(fan-control): extract FanChartLegend component (#301)"
```

---

## Task 5: `FanChartHint.tsx`

**Files:**
- Create: `client/src/components/fan-control/fan-curve-chart/FanChartHint.tsx`
- Test: `client/src/__tests__/components/fan-control/fan-curve-chart/FanChartHint.test.tsx`

**Interfaces:**
- Produces: default export `FanChartHint` mit Props `{ pointCount: number; minPoints: number; maxPoints: number }`.

Note: Hartcodierte englische Strings wie im Original — NICHT i18n-isieren.

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/fan-control/fan-curve-chart/FanChartHint.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanChartHint from '../../../../components/fan-control/fan-curve-chart/FanChartHint';

describe('FanChartHint', () => {
  it('appends the min hint at minPoints', () => {
    render(<FanChartHint pointCount={2} minPoints={2} maxPoints={10} />);
    expect(screen.getByText(/min 2 points/)).toBeInTheDocument();
  });

  it('appends the max hint at maxPoints', () => {
    render(<FanChartHint pointCount={10} minPoints={2} maxPoints={10} />);
    expect(screen.getByText(/max 10 points/)).toBeInTheDocument();
  });

  it('shows neither hint in the middle of the range', () => {
    render(<FanChartHint pointCount={5} minPoints={2} maxPoints={10} />);
    expect(screen.queryByText(/min 2 points/)).not.toBeInTheDocument();
    expect(screen.queryByText(/max 10 points/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-curve-chart/FanChartHint.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`client/src/components/fan-control/fan-curve-chart/FanChartHint.tsx` (aus `FanCurveChart.tsx:567-573`):

```tsx
interface FanChartHintProps {
  pointCount: number;
  minPoints: number;
  maxPoints: number;
}

export default function FanChartHint({ pointCount, minPoints, maxPoints }: FanChartHintProps) {
  return (
    <p className="mt-3 text-xs text-slate-400 italic">
      <strong>Left-click</strong> on graph to add point • <strong>Drag</strong> points to move • <strong>Right-click</strong> point to remove
      {pointCount <= minPoints && ' (min 2 points)'}
      {pointCount >= maxPoints && ` (max ${maxPoints} points)`}
    </p>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control/fan-curve-chart/FanChartHint.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-curve-chart/FanChartHint.tsx client/src/__tests__/components/fan-control/fan-curve-chart/FanChartHint.test.tsx
git commit -m "feat(fan-control): extract FanChartHint component (#301)"
```

---

## Task 6: Barrel + Orchestrator rewire + Docs

**Files:**
- Create: `client/src/components/fan-control/fan-curve-chart/index.ts`
- Modify: `client/src/components/fan-control/FanCurveChart.tsx` (auf Orchestrator reduzieren)
- Modify: `client/src/components/CLAUDE.md` (`fan-control/`-Zeile ergänzen)

**Interfaces:**
- Consumes: `useFanCurveInteraction` + `ChartDataPoint` (Task 2), `FanCurveTooltip`/`FanChartLegend`/`FanChartHint` (Tasks 3-5), `FanCurvePoint` + `formatNumber`.
- Produces: `FanCurveChart` (Default-Export, **unveränderte** `FanCurveChartProps`).

- [ ] **Step 1: Create the internal barrel**

`client/src/components/fan-control/fan-curve-chart/index.ts`:

```ts
export { default as FanCurveTooltip } from './FanCurveTooltip';
export { default as FanChartLegend } from './FanChartLegend';
export { default as FanChartHint } from './FanChartHint';
```

- [ ] **Step 2: Rewrite `FanCurveChart.tsx` as the orchestrator**

Ersetze den **gesamten** Inhalt von `client/src/components/fan-control/FanCurveChart.tsx` durch:

```tsx
import { useCallback } from 'react';
import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { FanCurvePoint } from '../../api/fan-control';
import { formatNumber } from '../../lib/formatters';
import { useFanCurveInteraction, type ChartDataPoint } from '../../hooks/useFanCurveInteraction';
import { FanCurveTooltip, FanChartLegend, FanChartHint } from './fan-curve-chart';

interface FanCurveChartProps {
  points: FanCurvePoint[];
  onPointsChange: (points: FanCurvePoint[]) => void;
  currentTemp: number | null;
  currentPWM: number;
  minPWM: number;
  maxPWM: number;
  emergencyTemp: number;
  isEditing?: boolean; // Kept for API compatibility, not used (FanControl-style always editable)
  isReadOnly: boolean;
  minPoints?: number; // Minimum number of points allowed (default: 2)
  maxPoints?: number; // Maximum number of points allowed (default: 10)
}

export default function FanCurveChart({
  points,
  onPointsChange,
  currentTemp,
  currentPWM,
  minPWM,
  maxPWM,
  emergencyTemp,
  // isEditing - Kept in interface for API compatibility, but not used (FanControl-style always editable)
  isReadOnly,
  minPoints = 2,
  maxPoints = 10,
}: FanCurveChartProps) {
  const {
    chartRef,
    overlayRef,
    draggingIndex,
    canEdit,
    localPoints,
    chartData,
    handleOverlayMouseDown,
    handleOverlayClick,
    handleOverlayContextMenu,
    handleOverlayTouchStart,
  } = useFanCurveInteraction(points, onPointsChange, {
    minPWM, maxPWM, emergencyTemp, isReadOnly, minPoints, maxPoints,
  });

  // Stable render function for dot prop (useCallback keeps reference identity across renders)
  const renderDot = useCallback((props: { cx?: number; cy?: number; payload?: ChartDataPoint; index?: number }) => {
    const { cx, cy, payload, index } = props;

    if (cx === undefined || cy === undefined) return null;
    if (!payload) return null;
    if (payload.isCurrentPoint) return null;

    const isHovered = draggingIndex === index;
    const radius = isHovered ? 10 : 7;
    const fill = isHovered ? '#38bdf8' : '#0ea5e9'; // sky-400 / sky-500

    return (
      <g>
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill={fill}
          stroke="#1e293b"
          strokeWidth={2}
          style={{
            cursor: canEdit ? 'grab' : 'default',
            transition: 'r 0.15s ease',
            pointerEvents: 'none', // Events handled by overlay
          }}
        />
        {isHovered && (
          <text x={cx} y={cy - 16} textAnchor="middle" fill="#e2e8f0"
            fontSize={12} fontWeight={600} style={{ pointerEvents: 'none' }}>
            {payload.temp.toFixed(1)}°C / {payload.pwm.toFixed(1)}%
          </text>
        )}
      </g>
    );
  }, [draggingIndex, canEdit]);

  // Data for the current operating point (separate from curve)
  const currentPointData = currentTemp !== null ? [{ temp: currentTemp, currentPwm: currentPWM }] : [];

  return (
    <div
      ref={chartRef}
      className="w-full relative"
      style={{ cursor: canEdit ? 'crosshair' : 'default' }}
    >
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart
          data={chartData}
          margin={{ top: 5, right: 20, left: 0, bottom: 55 }}
        >
          {/* Grid */}
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#334155"
            opacity={0.3}
          />

          {/* X Axis - Temperature */}
          <XAxis
            dataKey="temp"
            type="number"
            domain={[0, emergencyTemp + 10]}
            label={{
              value: 'Temperature (°C)',
              position: 'bottom',
              offset: 35,
              style: { fill: '#94a3b8', fontSize: 12 }
            }}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            stroke="#475569"
          />

          {/* Y Axis - PWM */}
          <YAxis
            type="number"
            domain={[0, 100]}
            label={{
              value: 'PWM (%)',
              angle: -90,
              position: 'insideLeft',
              style: { fill: '#94a3b8', fontSize: 12 }
            }}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            stroke="#475569"
          />

          <Tooltip content={<FanCurveTooltip />} />

          {/* Emergency temperature line */}
          <ReferenceLine
            x={emergencyTemp}
            stroke="#f43f5e"
            strokeDasharray="5 5"
            strokeWidth={2}
            label={{
              value: 'Emergency',
              position: 'top',
              fill: '#f43f5e',
              fontSize: 11
            }}
          />

          {/* Current temperature line */}
          {currentTemp !== null && (
            <ReferenceLine
              x={currentTemp}
              stroke="#34d399"
              strokeDasharray="3 3"
              strokeWidth={1.5}
              label={{
                value: `Now: ${formatNumber(currentTemp, 1)}°C`,
                position: 'top',
                fill: '#34d399',
                fontSize: 11
              }}
            />
          )}

          {/* Fan curve line */}
          <Line
            type="linear"
            dataKey="pwm"
            data={chartData}
            stroke="#0ea5e9"
            strokeWidth={3}
            dot={renderDot}
            activeDot={false}
            isAnimationActive={false}
          />

          {/* Current operating point - rendered as separate scatter */}
          {currentTemp !== null && (
            <Scatter
              data={currentPointData}
              dataKey="currentPwm"
              fill="#34d399"
              shape={(props: { cx?: number; cy?: number }) => (
                <circle
                  cx={props.cx}
                  cy={props.cy}
                  r={7}
                  fill="#34d399"
                  stroke="#1e293b"
                  strokeWidth={2}
                />
              )}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Transparent overlay for event handling - always rendered, disabled via pointerEvents */}
      <div
        ref={overlayRef}
        className="absolute inset-0"
        style={{
          zIndex: 10,
          cursor: canEdit ? (draggingIndex !== null ? 'grabbing' : 'crosshair') : 'default',
          background: 'rgba(0,0,0,0.001)', // Force browser hit-testing
          pointerEvents: canEdit ? 'auto' : 'none',
        }}
        onMouseDown={handleOverlayMouseDown}
        onClick={handleOverlayClick}
        onContextMenu={handleOverlayContextMenu}
        onTouchStart={handleOverlayTouchStart}
      />

      <FanChartLegend currentTemp={currentTemp} emergencyTemp={emergencyTemp} />

      {canEdit && (
        <FanChartHint pointCount={localPoints.length} minPoints={minPoints} maxPoints={maxPoints} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update `components/CLAUDE.md`**

Ersetze in `client/src/components/CLAUDE.md` die `fan-control/`-Tabellenzeile (die bereits `FanDetails`/`fan-details/*` beschreibt) und ergänze die FanCurveChart-Zerlegung. Neue Zeile:

```
| `fan-control/` | Fan curves, schedules, profiles — `FanDetails` composes `fan-details/*` (`FanPresetProfileButtons`, `FanCurveGraphControls`, `FanCurveTableEditor`, `FanStatsGrid`) + pure `fanCurveValidation`; state/handlers in `hooks/useFanCurveEditor`. `FanCurveChart` composes `fan-curve-chart/*` (`FanCurveTooltip`, `FanChartLegend`, `FanChartHint`) + pure `fanCurveGeometry`; drag/click/touch interaction in `hooks/useFanCurveInteraction` (extracted F2/#301) |
```

- [ ] **Step 4: Run the combined fan-control + hook suite**

Run (in `client/`): `npx vitest run src/__tests__/components/fan-control src/__tests__/hooks/useFanCurveInteraction.test.tsx`
Expected: PASS (alle Tasks-1–5-Tests grün).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/fan-control/fan-curve-chart/index.ts client/src/components/fan-control/FanCurveChart.tsx client/src/components/CLAUDE.md
git commit -m "refactor(fan-control): FanCurveChart thin orchestrator over fan-curve-chart/* + useFanCurveInteraction (#301)"
```

---

## Task 7: Full verification gate

**Files:** none (verification only).

- [ ] **Step 1: Full frontend test suite**

Run (in `client/`): `npx vitest run`
Expected: PASS, keine Regressionen.

- [ ] **Step 2: ESLint 0-error gate**

Run (in `client/`): `npx eslint .`
Expected: 0 Fehler. Achte auf ungenutzte Imports im neuen `FanCurveChart.tsx` (aus dem Original entfernt: `useState`, `useRef`, `useEffect`, `Line`? nein — `Line` bleibt; entfernt: `React`-default falls vorhanden, `formatNumber` bleibt, die Recharts-Imports bleiben alle genutzt). Verifiziere: keine ungenutzten Symbole. Falls Fehler: entfernen, bis grün.

- [ ] **Step 3: Production build (tsc -b + vite)**

Run (in `client/`): `npm run build`
Expected: erfolgreicher Build, keine Typfehler.

- [ ] **Step 4: Confirm line count target**

`FanCurveChart.tsx` sollte deutlich unter 500 Zeilen liegen (~200). Bestätigen.

- [ ] **Step 5: Manual interaction verification (nicht optional)**

Da Unit-Tests das volle Drag/Touch-Verhalten nicht abdecken, muss die Chart-Interaktion im laufenden Frontend durchgespielt werden (FanControl-Seite, ein Lüfter im Graph-Curve-Modus):
- Punkt per **Drag** verschieben → PWM/Temp ändert sich flüssig, wird beim Loslassen gespeichert.
- **Left-click** auf leere Fläche → neuer Punkt.
- **Right-click** auf Punkt → Punkt entfernt (respektiert min 2).
- Kein „Geister-Punkt" direkt nach einem Drag (Click-Suppression via `wasDraggingRef`).

Dies dokumentieren (was geprüft, Ergebnis). Wenn der Controller keinen laufenden Browser hat, per Playwright-MCP oder `/run` gegen die App treiben; andernfalls dem menschlichen Partner zur manuellen Bestätigung übergeben.

- [ ] **Step 6: Final commit (falls Verifikation Fixes brachte)**

```bash
git add -A
git commit -m "chore(fan-control): verification fixes for FanCurveChart decomposition (#301)"
```

(Nur committen, wenn Schritte 1–3 Änderungen erforderten.)

---

## Self-Review (durchgeführt beim Schreiben)

**1. Spec coverage:** ✅ Alle Spec-Einheiten haben Tasks — `fanCurveGeometry` mit beiden getrennten Rechenpfaden (T1), `useFanCurveInteraction` als Verbatim-Port inkl. DOM-Bounds + Handler (T2), 3 Subkomponenten (T3-T5), Orchestrator + Barrel + Docs (T6), Verify-Gate inkl. manueller Interaktionsprüfung (T7).

**2. Placeholder scan:** ✅ Kein TBD/TODO. Jeder Code-Schritt vollständig, jeder Test konkrete Assertions mit durchgerechneten Erwartungswerten (z.B. 33 vs 33.3 für den Rounding-Unterschied), jedes Kommando mit erwarteter Ausgabe.

**3. Type consistency:** ✅ `ChartDataPoint` aus dem Hook exportiert und in Tooltip + Orchestrator konsumiert. `RectLike`/`ChartValueConfig` in T1 definiert, in T2 via die Geometrie-Funktionen genutzt. Hook-Return-Namen (`chartRef`, `overlayRef`, `chartData`, `localPoints`, `handleOverlay*`, `handleRemovePoint`) stimmen mit T6-Verdrahtung überein. `computeChartValue`/`computeDraggedPoint`/`findNearestPointIndex`-Signaturen konsistent zwischen T1-Definition und T2-Aufrufen.

**Bewusste Zusatz-Affordanz:** `handleRemovePoint` wird im Hook-Return ergänzt (im Original nur intern) — reine Testbarkeit, kein Verhaltenswechsel, vom Orchestrator ungenutzt.

**Fidelity-Kern:** Die zwei getrennten Rechenpfade sind in T1 als separate Funktionen mit eigenen Tests fixiert; T2 ruft `computeDraggedPoint` im (DOM-lesenden) `updatePointPosition` und `computeChartValue` in `pixelToValue`. `getChartBounds`-Fallback-Kette bleibt verbatim im Hook.
