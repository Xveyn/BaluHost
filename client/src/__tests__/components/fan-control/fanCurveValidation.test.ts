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
