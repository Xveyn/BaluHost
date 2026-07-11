import { describe, it, expect } from 'vitest';
import { usageBarColor } from '../../../../components/vcl/vcl-settings/usageBarColor';

describe('usageBarColor', () => {
  it('returns red at/above the crit threshold', () => {
    expect(usageBarColor(95, 80, 95)).toBe('bg-red-500');
    expect(usageBarColor(90, 70, 90)).toBe('bg-red-500');
  });
  it('returns amber at/above warn and below crit', () => {
    expect(usageBarColor(85, 80, 95)).toBe('bg-amber-500');
    expect(usageBarColor(70, 70, 90)).toBe('bg-amber-500');
  });
  it('returns sky below warn', () => {
    expect(usageBarColor(50, 80, 95)).toBe('bg-sky-500');
    expect(usageBarColor(10, 70, 90)).toBe('bg-sky-500');
  });
});
