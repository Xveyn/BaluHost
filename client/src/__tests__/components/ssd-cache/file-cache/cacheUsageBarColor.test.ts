import { describe, it, expect } from 'vitest';
import { cacheUsageBarColor } from '../../../../components/ssd-cache/file-cache/cacheUsageBarColor';

describe('cacheUsageBarColor', () => {
  it('returns red at/above 90%', () => {
    expect(cacheUsageBarColor(95)).toBe('bg-red-500');
    expect(cacheUsageBarColor(90)).toBe('bg-red-500');
  });
  it('returns amber at/above 70% and below 90%', () => {
    expect(cacheUsageBarColor(75)).toBe('bg-amber-500');
    expect(cacheUsageBarColor(70)).toBe('bg-amber-500');
  });
  it('returns cyan below 70%', () => {
    expect(cacheUsageBarColor(50)).toBe('bg-cyan-500');
    expect(cacheUsageBarColor(0)).toBe('bg-cyan-500');
  });
});
