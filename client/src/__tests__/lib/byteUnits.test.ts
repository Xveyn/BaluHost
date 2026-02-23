import { describe, it, expect, beforeEach } from 'vitest';
import { getByteUnitMode, setByteUnitMode, getUnitConfig, subscribe, getSnapshot } from '../../lib/byteUnits';

beforeEach(() => {
  setByteUnitMode('binary');
});

describe('getByteUnitMode / setByteUnitMode', () => {
  it('defaults to binary', () => {
    expect(getByteUnitMode()).toBe('binary');
  });

  it('switches to decimal', () => {
    setByteUnitMode('decimal');
    expect(getByteUnitMode()).toBe('decimal');
  });

  it('is idempotent — setting same mode does not trigger listeners', () => {
    let calls = 0;
    const unsub = subscribe(() => { calls++; });
    setByteUnitMode('binary'); // already binary
    expect(calls).toBe(0);
    unsub();
  });
});

describe('getUnitConfig', () => {
  it('returns binary config', () => {
    const cfg = getUnitConfig('binary');
    expect(cfg.divisor).toBe(1024);
    expect(cfg.units).toEqual(['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']);
  });

  it('returns decimal config', () => {
    const cfg = getUnitConfig('decimal');
    expect(cfg.divisor).toBe(1000);
    expect(cfg.units).toEqual(['B', 'KB', 'MB', 'GB', 'TB', 'PB']);
  });
});

describe('subscribe / getSnapshot', () => {
  it('notifies subscribers on mode change', () => {
    let calls = 0;
    const unsub = subscribe(() => { calls++; });
    setByteUnitMode('decimal');
    expect(calls).toBe(1);
    unsub();
  });

  it('unsubscribe stops notifications', () => {
    let calls = 0;
    const unsub = subscribe(() => { calls++; });
    unsub();
    setByteUnitMode('decimal');
    expect(calls).toBe(0);
  });

  it('getSnapshot returns current mode', () => {
    expect(getSnapshot()).toBe('binary');
    setByteUnitMode('decimal');
    expect(getSnapshot()).toBe('decimal');
  });
});
