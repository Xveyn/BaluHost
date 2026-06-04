import { describe, it, expect } from 'vitest';
import { localRangeToUtcIso, formatTimeForRange } from '../../lib/dateUtils';

describe('localRangeToUtcIso', () => {
  it('maps local start 00:00 and inclusive end day to UTC, clamps end to now', () => {
    // nowMs far in the future so no clamping occurs
    const nowMs = new Date('2030-01-01T00:00:00Z').getTime();
    const { startIso, endIso } = localRangeToUtcIso('2026-06-01', '2026-06-03', nowMs);
    // Start is local midnight of Jun 1; end is local midnight of Jun 4 (exclusive upper bound)
    expect(new Date(startIso).getTime()).toBe(new Date('2026-06-01T00:00:00').getTime());
    expect(new Date(endIso).getTime()).toBe(new Date('2026-06-04T00:00:00').getTime());
  });

  it('clamps end to now when the range reaches today', () => {
    const nowMs = new Date('2026-06-03T12:34:00').getTime();
    const { endIso } = localRangeToUtcIso('2026-06-01', '2026-06-03', nowMs);
    expect(new Date(endIso).getTime()).toBe(nowMs);
  });
});

describe('formatTimeForRange custom', () => {
  it('formats custom timestamps with locale-aware day/month order (de: day before month)', () => {
    // Pass a LOCAL Date to avoid timezone-dependent day shifts in CI.
    const local = new Date(2026, 5, 4, 12, 30); // 2026-06-04 12:30 local (month is 0-based)
    const out = formatTimeForRange(local, 'custom', 'de');
    expect(out).toMatch(/\d{2}:\d{2}/);            // time present
    expect(out).toContain('04');                    // day
    expect(out).toContain('06');                    // month
    expect(out.indexOf('04')).toBeLessThan(out.indexOf('06')); // de order day.month
  });
});
