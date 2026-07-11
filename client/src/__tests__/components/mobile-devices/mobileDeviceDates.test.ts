import { describe, it, expect } from 'vitest';
import {
  formatMobileDate, mobileExpiry, mobileTimeAgo, notificationTimeAgo,
} from '../../../components/mobile-devices/mobileDeviceDates';

const tStub = ((k: string) => k) as unknown as Parameters<typeof mobileTimeAgo>[1];

describe('formatMobileDate', () => {
  it('returns Nie for null', () => {
    expect(formatMobileDate(null)).toBe('Nie');
  });
  it('returns a non-empty string for a date (no separator assertion)', () => {
    expect(formatMobileDate('2026-01-01T00:00:00Z').length).toBeGreaterThan(0);
  });
});

describe('mobileExpiry', () => {
  const iso = (msFromNow: number) => new Date(Date.now() + msFromNow).toISOString();
  const DAY = 86_400_000;
  it('far future: not expired, not soon', () => {
    const r = mobileExpiry(iso(30 * DAY));
    expect(r.isExpired).toBe(false);
    expect(r.isExpiringSoon).toBe(false);
  });
  it('within 7 days: soon, not expired', () => {
    const r = mobileExpiry(iso(3 * DAY));
    expect(r.isExpired).toBe(false);
    expect(r.isExpiringSoon).toBe(true);
  });
  it('past: expired', () => {
    const r = mobileExpiry(iso(-2 * DAY));
    expect(r.isExpired).toBe(true);
  });
});

describe('mobileTimeAgo', () => {
  it('null returns time.never key', () => {
    expect(mobileTimeAgo(null, tStub)).toBe('time.never');
  });
  it('under a minute returns time.justNow key', () => {
    expect(mobileTimeAgo(new Date(Date.now() - 5_000).toISOString(), tStub)).toBe('time.justNow');
  });
});

describe('notificationTimeAgo', () => {
  it('under a minute', () => {
    expect(notificationTimeAgo(new Date(Date.now() - 5_000).toISOString())).toBe('Gerade eben');
  });
  it('a few minutes', () => {
    expect(notificationTimeAgo(new Date(Date.now() - 120_000).toISOString())).toBe('Vor 2 Min');
  });
});
