import { describe, it, expect } from 'vitest';
import { getCategoryColor } from '../../../../components/plugins/plugin-management/pluginCategoryColor';

describe('getCategoryColor', () => {
  it('returns the monitoring class string for the monitoring category', () => {
    expect(getCategoryColor('monitoring')).toContain('blue');
  });

  it('returns a distinct class string per known category', () => {
    const known = ['monitoring', 'storage', 'network', 'security', 'general'];
    const results = known.map(getCategoryColor);
    // all five map to a non-empty string, and they are not all identical
    expect(results.every((r) => r.length > 0)).toBe(true);
    expect(new Set(results).size).toBe(5);
  });

  it('falls back to the general class string for an unknown category', () => {
    expect(getCategoryColor('does-not-exist')).toBe(getCategoryColor('general'));
  });
});
