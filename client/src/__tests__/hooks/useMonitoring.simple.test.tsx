import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useMemoryMonitoring, useNetworkMonitoring } from '../../hooks/useMonitoring';
import * as monitoringApi from '../../api/monitoring';

vi.mock('../../api/monitoring');
const api = vi.mocked(monitoringApi);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useMemoryMonitoring', () => {
  it('maps current + history into the legacy shape', async () => {
    api.getMemoryCurrent.mockResolvedValue({
      timestamp: 't0', used_bytes: 10, total_bytes: 100, percent: 10,
    });
    api.getMemoryHistory.mockResolvedValue({
      samples: [{ timestamp: 't0', used_bytes: 10, total_bytes: 100, percent: 10 }],
      sample_count: 1, source: 'memory',
    });

    const { result } = renderHook(() => useMemoryMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.current?.percent).toBe(10);
    expect(result.current.history).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('does not fetch when enabled is false', async () => {
    api.getMemoryCurrent.mockResolvedValue({ timestamp: 't0', used_bytes: 1, total_bytes: 2, percent: 50 });
    api.getMemoryHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useMemoryMonitoring({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(false);
    expect(api.getMemoryCurrent).not.toHaveBeenCalled();
    expect(api.getMemoryHistory).not.toHaveBeenCalled();
  });
});

describe('useNetworkMonitoring', () => {
  it('surfaces an error string when a fetch rejects', async () => {
    api.getNetworkCurrent.mockRejectedValue(new Error('net-down'));
    api.getNetworkHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useNetworkMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('net-down'));
  });
});
