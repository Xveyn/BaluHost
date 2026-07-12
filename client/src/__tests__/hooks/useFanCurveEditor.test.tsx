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
import { updateFanConfig } from '../../api/fan-control';
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
    const f = fan();
    const { result } = renderHook(() => useFanCurveEditor(f, opts()));
    expect(result.current.hasUnsavedChanges).toBe(false);
    expect(result.current.curvePoints).toHaveLength(2);
  });

  it('handleAddPoint appends a point and flags unsaved changes', () => {
    const f = fan();
    const { result } = renderHook(() => useFanCurveEditor(f, opts()));
    act(() => result.current.handleAddPoint());
    expect(result.current.curvePoints).toHaveLength(3);
    expect(result.current.hasUnsavedChanges).toBe(true);
  });

  it('handleRemovePoint keeps at least 2 points', () => {
    const f = fan();
    const { result } = renderHook(() => useFanCurveEditor(f, opts()));
    act(() => result.current.handleRemovePoint(0));
    expect(result.current.curvePoints).toHaveLength(2); // guard blocks removal below 2
  });

  it('handleUpdatePoint edits a field', () => {
    const f = fan();
    const { result } = renderHook(() => useFanCurveEditor(f, opts()));
    act(() => result.current.handleUpdatePoint(0, 'pwm', 55));
    expect(result.current.curvePoints[0].pwm).toBe(55);
  });

  it('handleApplyPreset replaces points from CURVE_PRESETS', () => {
    const f = fan();
    const { result } = renderHook(() => useFanCurveEditor(f, opts()));
    act(() => result.current.handleApplyPreset('silent'));
    expect(result.current.curvePoints).toHaveLength(5); // silent preset has 5 points
    expect(result.current.hasUnsavedChanges).toBe(true);
  });

  it('handleSaveCurve blocks on an invalid curve (single point) and does not call onCurveUpdate', () => {
    const o = opts();
    const f = fan({ curve_points: [{ temp: 40, pwm: 40 }] });
    const { result } = renderHook(() => useFanCurveEditor(f, o));
    act(() => result.current.handleSaveCurve());
    expect(toast.error).toHaveBeenCalled();
    expect(o.onCurveUpdate).not.toHaveBeenCalled();
  });

  it('handleSaveCurve calls onCurveUpdate on a valid curve', () => {
    const o = opts();
    const f = fan();
    const { result } = renderHook(() => useFanCurveEditor(f, o));
    act(() => result.current.handleSaveCurve());
    expect(o.onCurveUpdate).toHaveBeenCalledWith('fan1', expect.any(Array));
  });

  it('handleCurveTypeChange pushes the new type to updateFanConfig (API wiring survives extraction)', async () => {
    const f = fan();
    const { result } = renderHook(() => useFanCurveEditor(f, opts()));
    await act(async () => { await result.current.handleCurveTypeChange('flat'); });
    expect(vi.mocked(updateFanConfig)).toHaveBeenCalledWith('fan1', { curve_type: 'flat' });
    expect(result.current.curveType).toBe('flat');
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
