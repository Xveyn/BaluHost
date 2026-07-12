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
