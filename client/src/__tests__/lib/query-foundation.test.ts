import { describe, it, expect } from 'vitest';
import { queryClient } from '../../lib/queryClient';
import { queryKeys } from '../../lib/queryKeys';

describe('queryClient defaults', () => {
  it('mirrors the previous behavior', () => {
    const q = queryClient.getDefaultOptions().queries;
    expect(q?.staleTime).toBe(0);
    expect(q?.retry).toBe(1);
    expect(q?.refetchOnWindowFocus).toBe(false);
  });
});

describe('queryKeys.monitoring', () => {
  it('builds namespaced current keys', () => {
    expect(queryKeys.monitoring.cpuCurrent()).toEqual(['monitoring', 'cpu', 'current']);
  });

  it('builds history keys with params', () => {
    expect(queryKeys.monitoring.cpuHistory('1h', 'auto')).toEqual([
      'monitoring', 'cpu', 'history', '1h', 'auto',
    ]);
  });

  it('normalizes optional diskName to null', () => {
    expect(queryKeys.monitoring.diskIoHistory('1h', 'auto')).toEqual([
      'monitoring', 'diskIo', 'history', '1h', 'auto', null,
    ]);
    expect(queryKeys.monitoring.diskIoHistory('1h', 'auto', 'sda')).toEqual([
      'monitoring', 'diskIo', 'history', '1h', 'auto', 'sda',
    ]);
  });
});
