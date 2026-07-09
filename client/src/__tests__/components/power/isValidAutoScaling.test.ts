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
