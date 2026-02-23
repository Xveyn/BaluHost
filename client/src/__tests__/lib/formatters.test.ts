import { describe, it, expect, beforeEach } from 'vitest';
import { formatBytes, formatUptime, formatPercentage, formatNumber } from '../../lib/formatters';
import { setByteUnitMode } from '../../lib/byteUnits';

beforeEach(() => {
  setByteUnitMode('binary');
});

describe('formatBytes (binary mode — default)', () => {
  it('returns "0 B" for zero', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('returns "0 B" for NaN', () => {
    expect(formatBytes(NaN)).toBe('0 B');
  });

  it('returns "0 B" for negative values', () => {
    expect(formatBytes(-100)).toBe('0 B');
  });

  it('formats bytes below 1 KiB', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('formats exactly 1 KiB', () => {
    expect(formatBytes(1024)).toBe('1,00 KiB');
  });

  it('formats 1.5 GiB', () => {
    expect(formatBytes(1.5 * 1024 ** 3)).toBe('1,50 GiB');
  });

  it('formats 1 TiB', () => {
    expect(formatBytes(1024 ** 4)).toBe('1,00 TiB');
  });

  it('formats 1 PiB', () => {
    expect(formatBytes(1024 ** 5)).toBe('1,00 PiB');
  });

  it('rounds large values within a unit (>=100)', () => {
    expect(formatBytes(500 * 1024 ** 3)).toBe('500 GiB');
  });

  it('uses 1 decimal for values >= 10', () => {
    expect(formatBytes(15 * 1024 ** 2)).toBe('15,0 MiB');
  });
});

describe('formatBytes (decimal mode)', () => {
  beforeEach(() => {
    setByteUnitMode('decimal');
  });

  it('returns "0 B" for zero', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('formats exactly 1 KB (1000 bytes)', () => {
    expect(formatBytes(1000)).toBe('1,00 KB');
  });

  it('formats 1.5 GB', () => {
    expect(formatBytes(1.5 * 1000 ** 3)).toBe('1,50 GB');
  });

  it('formats 1 TB', () => {
    expect(formatBytes(1000 ** 4)).toBe('1,00 TB');
  });

  it('rounds large values within a unit (>=100)', () => {
    expect(formatBytes(500 * 1000 ** 3)).toBe('500 GB');
  });
});

describe('formatUptime', () => {
  it('formats 0 seconds', () => {
    expect(formatUptime(0)).toBe('0d 0h 0m');
  });

  it('formats 59 seconds as 0d 0h 0m', () => {
    expect(formatUptime(59)).toBe('0d 0h 0m');
  });

  it('formats 3661 seconds', () => {
    expect(formatUptime(3661)).toBe('0d 1h 1m');
  });

  it('formats 90061 seconds', () => {
    expect(formatUptime(90061)).toBe('1d 1h 1m');
  });
});

describe('formatPercentage', () => {
  it('formats 0 percent', () => {
    expect(formatPercentage(0)).toBe('0,0%');
  });

  it('formats 42.5 percent', () => {
    expect(formatPercentage(42.5)).toBe('42,5%');
  });

  it('formats 100 percent', () => {
    expect(formatPercentage(100)).toBe('100,0%');
  });

  it('accepts custom decimal places', () => {
    expect(formatPercentage(42.567, 2)).toBe('42,57%');
  });
});

describe('formatNumber', () => {
  it('formats with de locale (comma as decimal separator)', () => {
    expect(formatNumber(1.5, 1, 'de')).toBe('1,5');
  });

  it('formats with en locale (dot as decimal separator)', () => {
    expect(formatNumber(1.5, 1, 'en')).toBe('1.5');
  });

  it('formats zero decimals', () => {
    expect(formatNumber(42, 0, 'de')).toBe('42');
  });

  it('pads to minimum fraction digits', () => {
    expect(formatNumber(1, 2, 'de')).toBe('1,00');
  });
});
