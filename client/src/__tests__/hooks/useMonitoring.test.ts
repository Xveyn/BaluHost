import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useCpuMonitoring, useMemoryMonitoring } from '../../hooks/useMonitoring';

const mockCpuCurrent = {
  usage_percent: 35.2,
  frequency_mhz: 3600,
  temperature_celsius: 55,
  core_count: 6,
  thread_count: 12,
  per_thread_usage: [30, 40, 35, 25, 42, 38, 30, 40, 35, 25, 42, 38],
};

const mockCpuHistory = {
  samples: [
    { timestamp: '2026-01-01T12:00:00Z', usage_percent: 30, frequency_mhz: 3600, temperature_celsius: 54 },
    { timestamp: '2026-01-01T12:01:00Z', usage_percent: 35, frequency_mhz: 3600, temperature_celsius: 55 },
  ],
};

const mockMemCurrent = {
  total_bytes: 16 * 1024 * 1024 * 1024,
  used_bytes: 8 * 1024 * 1024 * 1024,
  available_bytes: 8 * 1024 * 1024 * 1024,
  usage_percent: 50.0,
};

const mockMemHistory = {
  samples: [
    { timestamp: '2026-01-01T12:00:00Z', usage_percent: 48, used_bytes: 7.5e9 },
  ],
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

import {
  getCpuCurrent,
  getCpuHistory,
  getMemoryCurrent,
  getMemoryHistory,
} from '../../api/monitoring';

describe('useCpuMonitoring', () => {
  beforeEach(() => {
    vi.mocked(getCpuCurrent).mockReset();
    vi.mocked(getCpuHistory).mockReset();
    vi.mocked(getCpuCurrent).mockResolvedValue(mockCpuCurrent);
    vi.mocked(getCpuHistory).mockResolvedValue(mockCpuHistory);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches CPU data on mount', async () => {
    // Use a very long poll interval so only the initial fetch fires
    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999_999, enabled: true }));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.current).toEqual(mockCpuCurrent);
    expect(result.current.history).toHaveLength(2);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('handles fetch errors', async () => {
    vi.mocked(getCpuCurrent).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useCpuMonitoring({ pollInterval: 999_999, enabled: true }));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Network error');
    expect(result.current.current).toBeNull();
  });

  it('does not fetch when enabled=false', () => {
    renderHook(() => useCpuMonitoring({ pollInterval: 999_999, enabled: false }));

    // Synchronous check — effect should not have scheduled anything
    expect(getCpuCurrent).not.toHaveBeenCalled();
  });
});

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
