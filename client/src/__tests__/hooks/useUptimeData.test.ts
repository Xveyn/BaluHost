import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import type { CurrentUptimeResponse, UptimeHistoryResponse } from '../../api/monitoring';

vi.mock('../../api/monitoring', () => ({
  getUptimeCurrent: vi.fn(),
  getUptimeHistory: vi.fn(),
}));

import { getUptimeCurrent, getUptimeHistory } from '../../api/monitoring';
import { useUptimeData } from '../../hooks/useUptimeData';

const currentMock = vi.mocked(getUptimeCurrent);
const historyMock = vi.mocked(getUptimeHistory);

const current: CurrentUptimeResponse = {
  timestamp: '2026-07-09T12:00:00Z',
  server_uptime_seconds: 3600,
  system_uptime_seconds: 7200,
  server_start_time: '2026-07-09T11:00:00Z',
  system_boot_time: '2026-07-09T10:00:00Z',
} as CurrentUptimeResponse;

const historyResponse: UptimeHistoryResponse = {
  samples: [
    { timestamp: '2026-07-09T11:00:00Z', server_uptime_seconds: 100, system_uptime_seconds: 200 },
  ],
  sleep_events: [
    { timestamp: '2026-07-09T11:30:00Z', new_state: 'soft_sleep', duration_seconds: 60 },
  ],
} as unknown as UptimeHistoryResponse;

describe('useUptimeData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentMock.mockResolvedValue(current);
    historyMock.mockResolvedValue(historyResponse);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns current, history and sleep events from the two queries', async () => {
    const { result } = renderHook(() => useUptimeData('1h'), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.current).not.toBeNull();
      expect(result.current.history).toHaveLength(1);
    });

    expect(result.current.current?.server_uptime_seconds).toBe(3600);
    expect(result.current.sleepEvents).toHaveLength(1);
    expect(result.current.error).toBeNull();
    expect(getUptimeHistory).toHaveBeenCalledWith('1h');
  });

  it('surfaces an error when the current query fails with no prior data', async () => {
    currentMock.mockRejectedValue(new Error('uptime down'));
    historyMock.mockRejectedValue(new Error('uptime down'));

    const { result } = renderHook(() => useUptimeData('1h'), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.error).toBe('uptime down');
    });
    expect(result.current.current).toBeNull();
  });

  it('polls both endpoints on the interval', async () => {
    vi.useFakeTimers();

    renderHook(() => useUptimeData('1h', 10000), { wrapper: createQueryWrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(getUptimeCurrent).toHaveBeenCalledTimes(1);
    expect(getUptimeHistory).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(getUptimeCurrent).toHaveBeenCalledTimes(2);
    expect(getUptimeHistory).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('retains the last known current across a transient poll error', async () => {
    vi.useFakeTimers();

    const { result } = renderHook(() => useUptimeData('1h', 10000), { wrapper: createQueryWrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(result.current.current?.server_uptime_seconds).toBe(3600);

    currentMock.mockRejectedValue(new Error('blip'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });

    // Data is retained (TanStack keeps the last successful value on error).
    expect(result.current.current?.server_uptime_seconds).toBe(3600);

    vi.useRealTimers();
  });
});
