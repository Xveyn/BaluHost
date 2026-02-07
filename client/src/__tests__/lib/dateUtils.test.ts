import { describe, it, expect } from 'vitest';
import {
  parseUtcTimestamp,
  formatTimestamp,
  formatDate,
  formatDateTime,
  formatTimeForRange,
} from '../../lib/dateUtils';

describe('parseUtcTimestamp', () => {
  it('appends Z to timestamps without timezone suffix', () => {
    const date = parseUtcTimestamp('2026-01-28T19:41:47');
    // Should be interpreted as UTC, not local time
    expect(date.getUTCHours()).toBe(19);
    expect(date.getUTCMinutes()).toBe(41);
    expect(date.getUTCSeconds()).toBe(47);
  });

  it('keeps timestamps that already have Z suffix', () => {
    const date = parseUtcTimestamp('2026-01-28T19:41:47Z');
    expect(date.getUTCHours()).toBe(19);
  });

  it('keeps timestamps with offset suffix', () => {
    const date = parseUtcTimestamp('2026-01-28T21:41:47+02:00');
    // +02:00 means 21:41 local = 19:41 UTC
    expect(date.getUTCHours()).toBe(19);
  });
});

describe('formatTimestamp', () => {
  it('formats a UTC timestamp to locale time string', () => {
    const result = formatTimestamp('2026-01-28T12:00:00Z', 'de-DE');
    // The exact result depends on the test runner's timezone, but it should be a valid time string
    expect(result).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });
});

describe('formatDate', () => {
  it('formats a UTC timestamp to locale date string', () => {
    const result = formatDate('2026-01-28T12:00:00Z', 'de-DE');
    // de-DE format: DD.MM.YYYY or similar
    expect(result).toContain('28');
    expect(result).toContain('2026');
  });
});

describe('formatDateTime', () => {
  it('formats a UTC timestamp to locale date+time string', () => {
    const result = formatDateTime('2026-01-28T12:00:00Z', 'de-DE');
    expect(result).toContain('28');
    expect(result).toContain('2026');
  });
});

describe('formatTimeForRange', () => {
  const testDate = new Date('2026-01-28T14:30:00Z');

  it('formats for 10m range (HH:mm)', () => {
    const result = formatTimeForRange(testDate, '10m', 'de');
    expect(result).toMatch(/\d{2}:\d{2}/);
  });

  it('formats for 1h range (HH:mm)', () => {
    const result = formatTimeForRange(testDate, '1h', 'de');
    expect(result).toMatch(/\d{2}:\d{2}/);
  });

  it('formats for 24h range (HH:mm)', () => {
    const result = formatTimeForRange(testDate, '24h', 'de');
    expect(result).toMatch(/\d{2}:\d{2}/);
  });

  it('formats for today range (HH:mm)', () => {
    const result = formatTimeForRange(testDate, 'today', 'de');
    expect(result).toMatch(/\d{2}:\d{2}/);
  });

  it('formats for 7d range (weekday + HH:mm)', () => {
    const result = formatTimeForRange(testDate, '7d', 'de');
    // Should contain a weekday abbreviation and time
    expect(result).toMatch(/.+\s\d{2}:\d{2}/);
  });

  it('formats for week range (weekday + HH:mm)', () => {
    const result = formatTimeForRange(testDate, 'week', 'de');
    expect(result).toMatch(/.+\s\d{2}:\d{2}/);
  });

  it('formats for month range (dd.MM.)', () => {
    const result = formatTimeForRange(testDate, 'month', 'de');
    expect(result).toMatch(/\d{2}/);
  });

  it('accepts string timestamps', () => {
    const result = formatTimeForRange('2026-01-28T14:30:00', '10m', 'de');
    expect(result).toMatch(/\d{2}:\d{2}/);
  });

  it('accepts epoch milliseconds', () => {
    const result = formatTimeForRange(testDate.getTime(), '10m', 'de');
    expect(result).toMatch(/\d{2}:\d{2}/);
  });
});
