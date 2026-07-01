import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useMemoryMonitoring } from '../../hooks/useMonitoring';

const mockMemCurrent = {
  timestamp: '2026-01-01T12:00:00Z',
  total_bytes: 16 * 1024 * 1024 * 1024,
  used_bytes: 8 * 1024 * 1024 * 1024,
  percent: 50.0,
  available_bytes: 8 * 1024 * 1024 * 1024,
};

const mockMemHistory = {
  samples: [
    { timestamp: '2026-01-01T12:00:00Z', percent: 48, used_bytes: 7.5e9, total_bytes: 16e9 },
  ],
  sample_count: 1,
  source: 'memory',
};

vi.mock('../../api/monitoring', () => ({
  getCpuCurrent: vi.fn(),
  getCpuHistory: vi.fn(),
  getMemoryCurrent: vi.fn(),
  getMemoryHistory: vi.fn(),
  getNetworkCurrent: vi.fn(),
  getNetworkHistory: vi.fn(),
  getDiskIoCurrent: vi.fn(),
  getDiskIoHistory: vi.fn(),
  getProcessesCurrent: vi.fn(),
  getProcessesHistory: vi.fn(),
}));

import { getMemoryCurrent, getMemoryHistory } from '../../api/monitoring';

// Note: useCpuMonitoring is covered by the dedicated
// `useMonitoring.cpu.test.tsx` suite (renders under a QueryClientProvider,
// as required now that the hook is backed by @tanstack/react-query).

describe('useMemoryMonitoring', () => {
  beforeEach(() => {
    vi.mocked(getMemoryCurrent).mockReset();
    vi.mocked(getMemoryHistory).mockReset();
    vi.mocked(getMemoryCurrent).mockResolvedValue(mockMemCurrent);
    vi.mocked(getMemoryHistory).mockResolvedValue(mockMemHistory);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches memory data on mount', async () => {
    const { result } = renderHook(() => useMemoryMonitoring({ pollInterval: 999_999, enabled: true }));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.current).toEqual(mockMemCurrent);
    expect(result.current.history).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });
});
