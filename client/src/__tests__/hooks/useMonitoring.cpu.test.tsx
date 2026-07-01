import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useCpuMonitoring } from '../../hooks/useMonitoring';
import * as monitoringApi from '../../api/monitoring';

vi.mock('../../api/monitoring');
const api = vi.mocked(monitoringApi);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useCpuMonitoring', () => {
  it('maps current + history into the legacy return shape', async () => {
    api.getCpuCurrent.mockResolvedValue({ timestamp: 't0', usage_percent: 42 });
    api.getCpuHistory.mockResolvedValue({
      samples: [{ timestamp: 't0', usage_percent: 42 }],
      sample_count: 1,
      source: 'memory',
    });

    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.current).toEqual({ timestamp: 't0', usage_percent: 42 });
    expect(result.current.history).toHaveLength(1);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('is loading on first render and clears after data arrives', async () => {
    api.getCpuCurrent.mockResolvedValue({ timestamp: 't0', usage_percent: 1 });
    api.getCpuHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('surfaces an error string when a fetch rejects', async () => {
    api.getCpuCurrent.mockRejectedValue(new Error('boom'));
    api.getCpuHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('boom'));
  });

  it('does not fetch when enabled is false', async () => {
    api.getCpuCurrent.mockResolvedValue({ timestamp: 't0', usage_percent: 1 });
    api.getCpuHistory.mockResolvedValue({ samples: [], sample_count: 0, source: 'memory' });

    const { result } = renderHook(() => useCpuMonitoring({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });

    // enabled:false → query never runs: loading is false immediately, no API calls.
    expect(result.current.loading).toBe(false);
    expect(api.getCpuCurrent).not.toHaveBeenCalled();
    expect(api.getCpuHistory).not.toHaveBeenCalled();
  });
});
