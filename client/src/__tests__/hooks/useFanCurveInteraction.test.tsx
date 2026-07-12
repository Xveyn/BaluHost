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
