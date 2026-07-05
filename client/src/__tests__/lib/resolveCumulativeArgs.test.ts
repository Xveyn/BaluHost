import { describe, it, expect } from 'vitest';
import { resolveCumulativeArgs } from '../../lib/energyPolling';

describe('resolveCumulativeArgs', () => {
  it('passes a preset period through with no custom range', () => {
    expect(resolveCumulativeArgs('today', null, null)).toEqual({
      period: 'today',
      start: undefined,
      end: undefined,
    });
    expect(resolveCumulativeArgs('week', null, null)).toEqual({
      period: 'week',
      start: undefined,
      end: undefined,
    });
  });

  it('maps a custom range to period=today + the start/end bounds', () => {
    expect(
      resolveCumulativeArgs('custom', '2026-01-01T00:00:00Z', '2026-01-31T23:59:59Z'),
    ).toEqual({
      period: 'today',
      start: '2026-01-01T00:00:00Z',
      end: '2026-01-31T23:59:59Z',
    });
  });

  it('yields undefined bounds for a custom period with nothing applied yet', () => {
    expect(resolveCumulativeArgs('custom', null, null)).toEqual({
      period: 'today',
      start: undefined,
      end: undefined,
    });
  });
});
