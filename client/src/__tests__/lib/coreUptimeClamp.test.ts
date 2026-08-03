import { describe, it, expect } from 'vitest';
import { clampToCoreUptime, findRunningOccurrence } from '../../lib/coreUptimeClamp';
import type { CoreUptimeOccurrence } from '../../api/sleep';

/** Occurrence aus lokalen Wanduhrzeiten bauen — unabhaengig von der TZ der CI. */
function occ(
  startLocal: string,
  endLocal: string,
  window_id = 1,
  label: string | null = null,
): CoreUptimeOccurrence {
  return {
    window_id,
    label,
    start: new Date(startLocal).toISOString(),
    end: new Date(endLocal).toISOString(),
  };
}

const NOW = new Date('2026-05-06T15:00:00');
const WINDOW = occ('2026-05-06T19:00:00', '2026-05-06T23:30:00', 7, 'Abend');

describe('clampToCoreUptime', () => {
  it('shortens an expiry that falls inside a future window', () => {
    const until = new Date('2026-05-06T21:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], NOW);
    expect(result.until).toBe(WINDOW.start);
    expect(result.clampedTo).toEqual(WINDOW);
  });

  it('leaves an expiry before the window untouched', () => {
    const until = new Date('2026-05-06T17:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], NOW);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });

  it('leaves an expiry past the window end untouched', () => {
    const until = new Date('2026-05-07T01:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], NOW);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });

  it('treats an expiry exactly on the window start as already clamped', () => {
    const result = clampToCoreUptime(WINDOW.start, [WINDOW], NOW);
    expect(result.until).toBe(WINDOW.start);
    expect(result.clampedTo).toEqual(WINDOW);
  });

  it('does not shorten when the window is already running', () => {
    const now = new Date('2026-05-06T20:00:00');
    const until = new Date('2026-05-06T21:00:00').toISOString();
    const result = clampToCoreUptime(until, [WINDOW], now);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });

  it('returns the earliest start when windows overlap', () => {
    const late = occ('2026-05-06T20:00:00', '2026-05-06T23:00:00', 2);
    const early = occ('2026-05-06T19:00:00', '2026-05-06T22:00:00', 3);
    const until = new Date('2026-05-06T21:00:00').toISOString();
    expect(clampToCoreUptime(until, [late, early], NOW).until).toBe(early.start);
    expect(clampToCoreUptime(until, [early, late], NOW).until).toBe(early.start);
  });

  it('does not clamp when a running window overlaps a future window that also contains until', () => {
    // Window A is already running (started before `now`); window B starts later
    // but both contain `until`. The earliest start across ALL containing
    // windows is A's — and A's start is already in the past, so the backend
    // (`clamp_to_core_uptime_start`) leaves `until` unchanged. A frontend that
    // filters to future-start windows BEFORE picking the earliest would wrongly
    // clamp to B instead.
    const now = new Date('2026-05-06T14:00:00');
    const running = occ('2026-05-06T08:00:00', '2026-05-06T23:00:00', 4, 'Tag');
    const future = occ('2026-05-06T19:00:00', '2026-05-06T21:00:00', 5, 'Abend');
    const until = new Date('2026-05-06T20:00:00').toISOString();
    const result = clampToCoreUptime(until, [running, future], now);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });

  it('is the identity with no occurrences', () => {
    const until = new Date('2026-05-06T21:00:00').toISOString();
    const result = clampToCoreUptime(until, [], NOW);
    expect(result.until).toBe(until);
    expect(result.clampedTo).toBeNull();
  });
});

describe('findRunningOccurrence', () => {
  it('returns the occurrence covering now', () => {
    const now = new Date('2026-05-06T20:00:00');
    expect(findRunningOccurrence([WINDOW], now)).toEqual(WINDOW);
  });

  it('returns null before the window starts', () => {
    expect(findRunningOccurrence([WINDOW], NOW)).toBeNull();
  });

  it('returns null exactly at the end (end is exclusive)', () => {
    const now = new Date('2026-05-06T23:30:00');
    expect(findRunningOccurrence([WINDOW], now)).toBeNull();
  });
});
