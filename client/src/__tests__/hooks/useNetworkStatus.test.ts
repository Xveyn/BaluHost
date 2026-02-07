import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useNetworkStatus } from '../../hooks/useNetworkStatus';

const mockResponse = {
  timestamp: '2026-02-07T12:00:00Z',
  download_mbps: 100.5,
  upload_mbps: 50.2,
  interface_type: 'ethernet' as const,
};

vi.mock('../../api/monitoring', () => ({
  getNetworkCurrent: vi.fn(),
}));

import { getNetworkCurrent } from '../../api/monitoring';

describe('useNetworkStatus', () => {
  beforeEach(() => {
    vi.mocked(getNetworkCurrent).mockReset();
    vi.mocked(getNetworkCurrent).mockResolvedValue(mockResponse);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches and returns network status', async () => {
    const { result } = renderHook(() =>
      useNetworkStatus({ refreshInterval: 0 })
    );

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.status).toBeDefined();
    expect(result.current.status!.downloadMbps).toBe(100.5);
    expect(result.current.status!.uploadMbps).toBe(50.2);
    expect(result.current.status!.interfaceType).toBe('ethernet');
    expect(result.current.error).toBeNull();
  });

  it('handles errors', async () => {
    vi.mocked(getNetworkCurrent).mockRejectedValue(new Error('API down'));

    const { result } = renderHook(() =>
      useNetworkStatus({ refreshInterval: 0 })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('API down');
    expect(result.current.status).toBeNull();
  });

  it('does not fetch when enabled=false', async () => {
    const { result } = renderHook(() =>
      useNetworkStatus({ enabled: false, refreshInterval: 0 })
    );

    // Give time for effects
    await new Promise((r) => setTimeout(r, 50));

    expect(getNetworkCurrent).not.toHaveBeenCalled();
    expect(result.current.status).toBeNull();
  });

  it('auto-refreshes with interval', async () => {
    vi.useFakeTimers();

    renderHook(() =>
      useNetworkStatus({ refreshInterval: 3000 })
    );

    // Initial call
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(getNetworkCurrent).toHaveBeenCalledTimes(1);

    // After 3 seconds
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(getNetworkCurrent).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it('refetch() works', async () => {
    const { result } = renderHook(() =>
      useNetworkStatus({ refreshInterval: 0 })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(getNetworkCurrent).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refetch();
    });

    expect(getNetworkCurrent).toHaveBeenCalledTimes(2);
  });
});
